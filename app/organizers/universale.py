"""Orchestratore principale: scansione, classificazione film/serie/musica,
deduplicazione, risoluzione conflitti, trasferimento. Porta
organizzatori/organizzatore_universale.py — l'unica classe con cui la GUI
interagisce direttamente per analisi/spostamento.

Fix rispetto all'originale:
- `_percorso_sorgente_attuale` inizializzato esplicitamente a None in __init__
  invece di essere un attributo opzionale implicito verificato con hasattr().
- analizza_con_ai ora rispetta davvero il parametro `provider` (gemini/chatgpt),
  invece di usare sempre Gemini indipendentemente dal parametro passato.
- Le 3 estrazioni stagione/episodio duplicate (regex bank di OrganizzatoreSerie
  chiamato direttamente, più una chiamata guessit inline) sono state
  consolidate in un'unica chiamata a media_parsing.estrai_stagione_episodio.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable, Iterator, Optional
from urllib.parse import unquote, urlparse

from app.core.config import ESTENSIONI_AUDIO, ESTENSIONI_VIDEO
from app.organizers.film import OrganizzatoreFilm
from app.organizers.musica import OrganizzatoreMusica
from app.organizers.serie import OrganizzatoreSerie
from app.services import ffmpeg_service, gemini_service, io_service, media_parsing, openai_service, tmdb_service

_log_approvazione = logging.getLogger("gestore_film.approvazione")
_log_non_fatti = logging.getLogger("gestore_film.non_fatti")
_log_non_riconosciuti = logging.getLogger("gestore_film.non_riconosciuti")
_log_anomalie = logging.getLogger("gestore_film.anomalie")

_PATTERN_TMDB_ID = re.compile(r"\[tmdbid-(\d+)\]", re.I)

LogCallback = Callable[[str], None]
ConflittoCallback = Callable[[dict, dict], None]
IoCallback = Callable[[dict, dict], None]


class OrganizzatoreUniversale:
    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        self._config_attuale = config or {}
        self.motore_film = OrganizzatoreFilm()
        self.motore_serie = OrganizzatoreSerie()
        self.motore_musica = OrganizzatoreMusica()
        self._log_callback: Optional[LogCallback] = None
        self.motore_film.imposta_callback_log(self._proxy_log)
        self.motore_serie.imposta_callback_log(self._proxy_log)
        self.motore_musica.imposta_callback_log(self._proxy_log)

        self._evento_conflitto = threading.Event()
        self._decisione_conflitto: Optional[str] = None
        self.mappa_destinazione: dict[str, dict[str, Any]] = {}
        self._lock_mappa = threading.Lock()
        self._percorso_sorgente_attuale: Optional[str] = None

    def imposta_callback_log(self, callback: LogCallback) -> None:
        self._log_callback = callback
        self.motore_film.imposta_callback_log(callback)
        self.motore_serie.imposta_callback_log(callback)
        self.motore_musica.imposta_callback_log(callback)

    def _proxy_log(self, msg: str) -> None:
        if self._log_callback:
            self._log_callback(msg)

    def risolvi_conflitto(self, decisione: str) -> None:
        self._decisione_conflitto = decisione
        self._evento_conflitto.set()

    def _esegui_scansione_destinazione_async(self) -> None:
        for tipo in ("film", "serie", "musica"):
            perc = self._config_attuale.get("destinazioni", {}).get(tipo)
            if perc:
                mappa_parziale = io_service.scansiona_destinazione(perc)
                with self._lock_mappa:
                    self.mappa_destinazione.update(mappa_parziale)

    def scansiona_directory(self, percorso: str) -> Iterator[dict[str, Any]]:
        self._percorso_sorgente_attuale = percorso
        threading.Thread(target=self._esegui_scansione_destinazione_async, daemon=True).start()
        est_tutte = ESTENSIONI_VIDEO.union(ESTENSIONI_AUDIO)

        if percorso.lower().startswith("ftp://"):
            from app.services.ftp_service import ServizioFTP

            ftp = ServizioFTP(percorso, callback_log=self._proxy_log)
            if ftp.connetti():
                yield from ftp.scansiona_ricorsiva(estensioni=est_tutte)
                ftp.chiudi()
            return

        try:
            for radice, _dirs, file in os.walk(percorso):
                for nome in file:
                    est = Path(nome).suffix.lower()
                    if est in est_tutte:
                        yield {"percorso": os.path.join(radice, nome), "nome": nome, "estensione": est}
        except OSError as e:
            msg = f"Errore scansione directory {percorso}: {e}"
            self._proxy_log(msg)
            _log_anomalie.error(msg)

    def _estrai_contesto_percorso(self, percorso: str) -> tuple[str, str]:
        if percorso.lower().startswith("ftp://"):
            p_fisico = unquote(urlparse(percorso).path or "/")
            parti = [p for p in p_fisico.replace("\\", "/").split("/") if p]
            padre = parti[-2] if len(parti) > 1 else ""
            nonno = parti[-3] if len(parti) > 2 else ""
        else:
            path_obj = Path(percorso)
            padre = path_obj.parent.name
            nonno = path_obj.parent.parent.name
        return padre, nonno

    def analizza_file(self, info: dict[str, Any], usa_ai: bool = False) -> dict[str, Any]:
        nome = info["nome"]
        percorso = info["percorso"]
        est = info["estensione"]

        if est in ESTENSIONI_AUDIO:
            res = self.motore_musica.analizza_file(info)
            res["tipo_media"] = "musica"
            return self._arricchisci_e_controlla(res, info)

        id_suggerito, tipo_suggerito = media_parsing.cerca_id_tmdb_locale(percorso)
        tmdb_match = _PATTERN_TMDB_ID.search(percorso)
        tid = id_suggerito or (int(tmdb_match.group(1)) if tmdb_match else None)

        if tid:
            if not tipo_suggerito:
                s, e, f = media_parsing.estrai_stagione_episodio(nome)
                if s and e and f != "debole":
                    tipo_suggerito = "serie"

            info_tmdb = tmdb_service.recupera_da_id(tid, tipo_richiesto=tipo_suggerito)
            if not info_tmdb and tipo_suggerito:
                info_tmdb = tmdb_service.recupera_da_id(tid)

            if info_tmdb:
                if info_tmdb["tipo"] == "film":
                    res = self.motore_film.analizza_file(info)
                    res["tipo_media"] = "film"
                    res["confidenza"] = 1.0
                    res["match_principale"] = {
                        "tmdb_id": tid,
                        "titolo": info_tmdb.get("titolo_it_tmdb", ""),
                        "anno": info_tmdb.get("anno", ""),
                        "tipo": "film",
                    }
                    return self._arricchisci_e_controlla(res, info)
                if info_tmdb["tipo"] == "serie":
                    stag, ep, _forza = media_parsing.estrai_stagione_episodio(nome)
                    info["stagione"] = stag or "01"
                    info["episodio"] = ep or "01"
                    res = self.motore_serie.analizza_file(info)
                    res["tipo_media"] = "serie"
                    res["confidenza"] = 1.0
                    res["match_principale"] = {
                        "tmdb_id": tid,
                        "titolo": info_tmdb.get("titolo_it_tmdb", ""),
                        "anno": info_tmdb.get("anno", ""),
                        "tipo": "serie",
                    }
                    return self._arricchisci_e_controlla(res, info)

        dati_locali = media_parsing.estrai_info_locali(nome, percorso)

        tipo = dati_locali.get("tipo_indovinato", "movie")
        titolo_g = dati_locali.get("titolo", "")

        info["titolo_guessit"] = titolo_g
        info["anno_guessit"] = dati_locali.get("anno", "")

        s_reg, e_reg, forza_reg = media_parsing.estrai_stagione_episodio(nome)

        if tipo == "episode" or (s_reg and e_reg and forza_reg != "debole"):
            tipo = "episode"
            info["forza_match_serie"] = forza_reg

            stag = dati_locali.get("stagione")
            ep = dati_locali.get("episodio")

            info["stagione"] = str(stag).zfill(2) if stag else (s_reg or "01")
            info["episodio"] = str(ep).zfill(2) if ep else (e_reg or "01")

            res = self.motore_serie.analizza_file(info)
            res["tipo_media"] = "serie"

            forza = info.get("forza_match_serie", "debole")
            soglia_sicurezza = 0.85 if forza == "debole" else (0.6 if forza == "media" else 0.4)

            if res.get("confidenza", 0) < soglia_sicurezza:
                res_film = self.motore_film.analizza_file(info)
                bonus_serie = 0.20 if forza == "forte" else (0.10 if forza == "media" else 0.0)
                if res_film.get("confidenza", 0) > (res.get("confidenza", 0) + bonus_serie):
                    res = res_film
                    res["tipo_media"] = "film"

            if usa_ai and res.get("confidenza", 0) < 0.8:
                padre, _nonno = self._estrai_contesto_percorso(percorso)
                ai_res = gemini_service.estrai_metadati(nome, contesto=padre)

                if ai_res["tipo"] == "serie":
                    info["stagione"] = str(ai_res.get("stagione") or info["stagione"]).zfill(2)
                    info["episodio"] = str(ai_res.get("episodio") or info["episodio"]).zfill(2)
                    res = self.motore_serie.analizza_file(info, dati_ai=ai_res)
                    res["tipo_media"] = "serie"
                else:
                    res = self.motore_film.analizza_file(info)
                    res["tipo_media"] = "film"
                res["confidenza"] = max(res.get("confidenza", 0), ai_res.get("confidenza", 0))
                res["gemini"] = ai_res
        else:
            res = self.motore_film.analizza_file(info)
            res["tipo_media"] = "film"

            soglia_sicurezza = self._config_attuale.get("automazione", {}).get("soglia", 0.85)
            if res.get("confidenza", 0) < soglia_sicurezza and dati_locali.get("episodio"):
                res_serie = self.motore_serie.analizza_file(info)
                if res_serie.get("confidenza", 0) > res.get("confidenza", 0):
                    res = res_serie
                    res["tipo_media"] = "serie"

            if usa_ai and res.get("confidenza", 0) < 0.8:
                padre, _nonno = self._estrai_contesto_percorso(percorso)
                ai_res = gemini_service.estrai_metadati(nome, contesto=padre)

                if ai_res["tipo"] == "serie":
                    info["stagione"] = str(ai_res.get("stagione") or "01").zfill(2)
                    info["episodio"] = str(ai_res.get("episodio") or "01").zfill(2)
                    res = self.motore_serie.analizza_file(info, dati_ai=ai_res)
                    res["tipo_media"] = "serie"
                res["confidenza"] = max(res.get("confidenza", 0), ai_res.get("confidenza", 0))
                res["gemini"] = ai_res

        return self._arricchisci_e_controlla(res, info)

    def _arricchisci_e_controlla(self, res: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
        tipo = res.get("tipo_media", "film")
        percorso = info["percorso"]
        nome = info["nome"]
        est = info["estensione"]

        res["info_tecnica"] = ffmpeg_service.analizza_tecnico(percorso)

        m = res.get("match_principale") or {}
        nome_ep = res.get("nome_episodio", "")
        if tipo == "serie":
            struttura = self.motore_serie.costruisci_nome_jellyfin(
                m, res.get("stagione", "01"), res.get("episodio", "01"), res.get("info_tecnica", {}), est, nome_ep
            )
        elif tipo == "musica":
            struttura = self.motore_musica.costruisci_nome_jellyfin(res.get("info_id3", {}), est)
        else:
            struttura = self.motore_film.costruisci_nome_jellyfin(m.get("titolo", "Sconosciuto"), m, res.get("info_tecnica", {}), est)

        res["nome_jellyfin"] = struttura

        target_root = self._config_attuale.get("destinazioni", {}).get(tipo)
        if target_root:
            if tipo == "serie":
                dest_rel = os.path.join(struttura["cartella_serie"], struttura["cartella_stagione"], struttura["nome_file"])
            elif tipo == "musica":
                dest_rel = os.path.join(struttura["cartella_artista"], struttura["cartella_album"], struttura["nome_file"])
            else:
                dest_rel = os.path.join(struttura.get("decade", ""), struttura["cartella"], struttura["nome_file"])

            dest_finale = os.path.join(target_root, dest_rel)

            duplicato_trovato = False
            if os.path.exists(dest_finale):
                try:
                    if os.path.getsize(percorso) == os.path.getsize(dest_finale):
                        duplicato_trovato = True
                except OSError:
                    pass

            if not duplicato_trovato and nome in self.mappa_destinazione:
                with self._lock_mappa:
                    info_mappa = self.mappa_destinazione.get(nome)
                    if info_mappa:
                        try:
                            if os.path.getsize(percorso) == info_mappa.get("dimensione"):
                                duplicato_trovato = True
                        except OSError:
                            pass

            if duplicato_trovato:
                res["status"] = "Duplicato (Gia presente)"
                res["confidenza"] = 1.0

        soglia = self._config_attuale.get("automazione", {}).get("soglia", 0.85)
        if res.get("confidenza", 0) < soglia:
            _log_non_riconosciuti.info(f"File non riconosciuto o bassa confidenza: {nome} (Percorso: {percorso})")

        return res

    def sposta_file(
        self,
        r: dict[str, Any],
        target_root: str,
        azione: str,
        pulisci: bool,
        callback_ui_io: Optional[IoCallback] = None,
        callback_ui_conflitto: Optional[ConflittoCallback] = None,
    ) -> dict[str, Any]:
        tipo = r.get("tipo_media")
        percorso = r["percorso_originale"]
        ext = r["estensione"]

        m = r.get("match_principale") or {}
        nome_ep = r.get("nome_episodio", "")
        if tipo == "serie":
            struttura = self.motore_serie.costruisci_nome_jellyfin(m, r.get("stagione", "01"), r.get("episodio", "01"), r.get("info_tecnica", {}), ext, nome_ep)
            dest_rel = os.path.join(struttura["cartella_serie"], struttura["cartella_stagione"], struttura["nome_file"])
        elif tipo == "musica":
            struttura = self.motore_musica.costruisci_nome_jellyfin(r.get("info_id3", {}), ext)
            dest_rel = os.path.join(struttura["cartella_artista"], struttura["cartella_album"], struttura["nome_file"])
        else:
            struttura = self.motore_film.costruisci_nome_jellyfin(m.get("titolo", "Sconosciuto"), m, r.get("info_tecnica", {}), ext)
            dest_rel = os.path.join(struttura.get("decade", ""), struttura["cartella"], struttura["nome_file"])

        if percorso.lower().startswith("ftp://"):
            return {"successo": False, "errore": "FTP non supportato per questo flusso"}

        dest_finale = os.path.join(target_root, dest_rel)

        if io_service.verifica_esistenza(dest_finale):
            preferenza_conflitto = self._config_attuale.get("approvazione_manuale", {}).get("conflitto", "Salta")

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
                self._evento_conflitto.clear()
                self._decisione_conflitto = None

                dettagli = {
                    "percorso_sorgente": percorso,
                    "percorso_destinazione": dest_finale,
                    "dim_sorg_mb": round(dim_sorg / (1024 * 1024), 2),
                    "dim_dest_mb": round(dim_dest / (1024 * 1024), 2),
                    "uguale": dim_uguale,
                    "motivo": "Dimensione diversa" if not dim_uguale else "File già presente",
                }

                callback_ui_conflitto(r, dettagli)
                self._evento_conflitto.wait()

                if self._decisione_conflitto == "salta":
                    r["status"] = "Saltato (Esistente)"
                    return {"successo": True, "saltato": True}

        r["status"] = f"{azione} in corso..."

        def _cb(p: dict[str, Any]) -> None:
            if callback_ui_io:
                callback_ui_io(r, p)

        radice_sorgente = self._percorso_sorgente_attuale

        if tipo == "musica":
            res = self.motore_musica.sposta_file(r, target_root, azione, pulisci, _cb, radice_sorgente)
        elif tipo == "serie":
            res = self.motore_serie.sposta_file(
                percorso, target_root, r["match_principale"], r["stagione"], r["episodio"], r["info_tecnica"], ext, azione, pulisci, _cb, radice_sorgente, nome_ep
            )
        else:
            m = r["match_principale"]
            res = self.motore_film.sposta_file(percorso, target_root, m.get("titolo", ""), m, r["info_tecnica"], ext, azione, pulisci, _cb, radice_sorgente)

        if res.get("successo"):
            r["status"] = f"{azione}to"
            if self._config_attuale.get("automazione", {}).get("genera_trickplay_automaticamente") and tipo in ("film", "serie"):
                self._avvia_trickplay_automatico(dest_finale)
        else:
            err = res.get("errore", "Errore IO sconosciuto")
            r["status"] = "Errore IO"
            r["errore_dettaglio"] = err
            _log_anomalie.error(f"Errore spostamento/copia file {percorso}: {err}")
        return res

    def _avvia_trickplay_automatico(self, percorso_video: str) -> None:
        # generatore_trickplay verrà portato in una milestone successiva
        # (schermata Trickplay); finché non esiste, questo resta un no-op
        # sicuro invece di sollevare ModuleNotFoundError dal worker IO.
        try:
            from app.services import trickplay_service  # type: ignore[import-not-found]
        except ImportError:
            return
        try:
            trickplay_service.genera_automatico(percorso_video)
        except Exception as e:
            _log_anomalie.error(f"Errore avvio trickplay automatico per {percorso_video}: {e}")

    def costruisci_nome_jellyfin(
        self,
        titolo_it: str,
        match: dict[str, Any],
        info_tecnica: dict[str, Any],
        estensione: str,
        tipo_media: str = "film",
        nome_episodio: str = "",
        stagione: str = "01",
        episodio: str = "01",
    ) -> dict[str, str]:
        if tipo_media == "serie":
            return self.motore_serie.costruisci_nome_jellyfin(match, stagione, episodio, info_tecnica, estensione, nome_episodio)
        if tipo_media == "musica":
            return self.motore_musica.costruisci_nome_jellyfin(match, estensione)
        return self.motore_film.costruisci_nome_jellyfin(titolo_it, match, info_tecnica, estensione)

    def analizza_con_ai(self, r: dict[str, Any], provider: str = "gemini") -> dict[str, Any]:
        nome = r.get("file_originale", "")
        cartella = r.get("percorso_originale", "")

        if provider == "chatgpt":
            ai_res = openai_service.analizza_con_openai(nome)
        else:
            ai_res = gemini_service.estrai_metadati(nome, contesto=cartella)

        info = {"percorso": r["percorso_originale"], "nome": nome, "estensione": r["estensione"]}

        if ai_res["tipo"] == "serie":
            info["stagione"] = str(ai_res.get("stagione") or "01").zfill(2)
            info["episodio"] = str(ai_res.get("episodio") or "01").zfill(2)
            nuovo = self.motore_serie.analizza_file(info)
            nuovo["tipo_media"] = "serie"
        elif ai_res["tipo"] == "musica":
            nuovo = self.motore_musica.analizza_file(info)
            nuovo["tipo_media"] = "musica"
        else:
            nuovo = self.motore_film.analizza_file(info)
            nuovo["tipo_media"] = "film"

        nuovo["confidenza"] = ai_res.get("confidenza", 0.8)
        nuovo["gemini"] = ai_res

        return self._arricchisci_e_controlla(nuovo, info)
