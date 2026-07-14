import logging
import os
import threading
from typing import Any, Callable, Optional

from app.services import io_service

_log_anomalie = logging.getLogger("gestore_film.anomalie")

ConflittoCallback = Callable[[dict, dict], None]
IoCallback = Callable[[dict, dict], None]

class FileMoverUniversale:
    """Micro-servizio responsabile unicamente dello spostamento fisico dei file."""

    @staticmethod
    def sposta_file(
        r: dict[str, Any],
        target_root: str,
        azione: str,
        pulisci: bool,
        config: dict[str, Any],
        motore_film: Any,
        motore_serie: Any,
        motore_musica: Any,
        radice_sorgente: Optional[str],
        evento_conflitto: threading.Event,
        ottieni_decisione_conflitto: Callable[[], Optional[str]],
        reset_conflitto: Callable[[], None],
        callback_ui_io: Optional[IoCallback] = None,
        callback_ui_conflitto: Optional[ConflittoCallback] = None,
    ) -> dict[str, Any]:
        tipo = r.get("tipo_media")
        percorso = r["percorso_originale"]
        ext = r["estensione"]

        m = r.get("match_principale") or {}
        nome_ep = r.get("nome_episodio", "")
        if tipo == "serie":
            struttura = motore_serie.costruisci_nome_jellyfin(m, r.get("stagione", "01"), r.get("episodio", "01"), r.get("info_tecnica", {}), ext, nome_ep)
            dest_rel = os.path.join(struttura["cartella_serie"], struttura["cartella_stagione"], struttura["nome_file"])
        elif tipo == "musica":
            struttura = motore_musica.costruisci_nome_jellyfin(r.get("info_id3", {}), ext)
            dest_rel = os.path.join(struttura["cartella_artista"], struttura["cartella_album"], struttura["nome_file"])
        else:
            struttura = motore_film.costruisci_nome_jellyfin(m.get("titolo", "Sconosciuto"), m, r.get("info_tecnica", {}), ext)
            dest_rel = os.path.join(struttura.get("decade", ""), struttura["cartella"], struttura["nome_file"])

        if percorso.lower().startswith("ftp://"):
            return {"successo": False, "errore": "FTP non supportato per questo flusso"}

        dest_finale = os.path.join(target_root, dest_rel)

        if io_service.verifica_esistenza(dest_finale):
            preferenza_conflitto = config.get("approvazione_manuale", {}).get("conflitto", "Salta")

            try:
                dim_sorg = os.path.getsize(percorso)
                dim_dest = os.path.getsize(dest_finale)
                dim_uguale = dim_sorg == dim_dest
            except OSError:
                dim_uguale = False

            if preferenza_conflitto == "Salta" and dim_uguale:
                r["status"] = "Saltato (Esistente)"
                return {"successo": True, "saltato": True}
            
            if preferenza_conflitto != "Sovrascrivi" and callback_ui_conflitto:
                reset_conflitto()

                dettagli = {
                    "percorso_sorgente": percorso,
                    "percorso_destinazione": dest_finale,
                    "dim_sorg_mb": round(dim_sorg / (1024 * 1024), 2),
                    "dim_dest_mb": round(dim_dest / (1024 * 1024), 2),
                    "uguale": dim_uguale,
                    "motivo": "Dimensione diversa" if not dim_uguale else "File già presente",
                }

                callback_ui_conflitto(r, dettagli)
                evento_conflitto.wait()

                decisione = ottieni_decisione_conflitto()
                if decisione == "salta":
                    r["status"] = "Saltato (Esistente)"
                    return {"successo": True, "saltato": True}

        r["status"] = f"{azione} in corso..."

        def _cb(p: dict[str, Any]) -> None:
            if callback_ui_io:
                callback_ui_io(r, p)

        if tipo == "musica":
            res = motore_musica.sposta_file(r, target_root, azione, pulisci, _cb, radice_sorgente)
        elif tipo == "serie":
            res = motore_serie.sposta_file(
                percorso, target_root, r["match_principale"], r["stagione"], r["episodio"], r["info_tecnica"], ext, azione, pulisci, _cb, radice_sorgente, nome_ep
            )
        else:
            m = r["match_principale"]
            res = motore_film.sposta_file(percorso, target_root, m.get("titolo", ""), m, r["info_tecnica"], ext, azione, pulisci, _cb, radice_sorgente)

        if res.get("successo"):
            r["status"] = f"{azione}to"
            if config.get("automazione", {}).get("genera_trickplay_automaticamente") and tipo in ("film", "serie"):
                FileMoverUniversale._avvia_trickplay_automatico(dest_finale)
        else:
            err = res.get("errore", "Errore IO sconosciuto")
            r["status"] = "Errore IO"
            r["errore_dettaglio"] = err
            _log_anomalie.error(f"Errore spostamento/copia file {percorso}: {err}")
        return res

    @staticmethod
    def _avvia_trickplay_automatico(percorso_video: str) -> None:
        try:
            from app.services import trickplay_service  # type: ignore[import-not-found]
            trickplay_service.genera_automatico(percorso_video)
        except ImportError:
            pass
        except Exception as e:
            _log_anomalie.error(f"Errore avvio trickplay automatico per {percorso_video}: {e}")
