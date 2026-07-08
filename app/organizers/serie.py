"""Logica di business per le serie TV. Porta organizzatori/organizzatore_serie.py.

Fix rispetto all'originale: stagione/episodio ora derivano dall'unico servizio
consolidato app.services.media_parsing.estrai_stagione_episodio (il regex bank
locale duplicato è stato rimosso), e pulizia_titolo_serie/normalizzazione
titolo passano dallo stesso modulo. estrai_stagione_episodio è ora un metodo
pubblico (era privato ma già usato come API pubblica da OrganizzatoreUniversale).
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

from app.core.config import ESTENSIONI_VIDEO
from app.services import ffmpeg_service, io_service, media_parsing, tmdb_service

_log = logging.getLogger("gestore_film.principale")

LogCallback = Callable[[str], None]


class OrganizzatoreSerie:
    def __init__(self) -> None:
        self._log_callback: Optional[LogCallback] = None

    def imposta_callback_log(self, callback: LogCallback) -> None:
        self._log_callback = callback

    def _log(self, messaggio: str) -> None:
        if self._log_callback:
            self._log_callback(messaggio)

    def estrai_stagione_episodio(self, nome_file: str) -> tuple[str, str, str]:
        return media_parsing.estrai_stagione_episodio(nome_file)

    def _sanifica_percorso(self, testo: str) -> str:
        for c in r'<>:"/\|?*':
            testo = testo.replace(c, "")
        return testo.strip()

    def scansiona_directory(self, percorso: str) -> list[dict[str, Any]]:
        file_trovati = []
        try:
            for radice, _dirs, file in os.walk(percorso):
                for nome in file:
                    estensione = Path(nome).suffix.lower()
                    if estensione in ESTENSIONI_VIDEO:
                        percorso_completo = os.path.join(radice, nome)
                        stagione, episodio, forza = self.estrai_stagione_episodio(nome)
                        file_trovati.append(
                            {
                                "percorso": percorso_completo,
                                "nome": nome,
                                "estensione": estensione,
                                "stagione": stagione,
                                "episodio": episodio,
                                "forza_match_serie": forza,
                            }
                        )
                        self._log(f"Trovato: {nome}")
        except OSError as e:
            self._log(f"Errore scansione: {e}")
        return file_trovati

    def analizza_file(self, info_file: dict[str, Any], dati_ai: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        nome = info_file["nome"]
        percorso = info_file["percorso"]
        stagione = info_file.get("stagione", "")
        episodio = info_file.get("episodio", "")

        cartella_padre = os.path.basename(os.path.dirname(percorso))
        self._log(f"Analisi locale Serie: {nome} (Cartella: {cartella_padre})")

        titolo_pulito, anno_pulito = media_parsing.pulisci_titolo_serie(nome, cartella_padre)

        titolo_da_usare = (
            (dati_ai.get("titolo_italiano") or dati_ai.get("titolo"))
            if dati_ai
            else (info_file.get("titolo_guessit") or titolo_pulito)
        )
        anno_da_usare = dati_ai.get("anno") if dati_ai else (info_file.get("anno_guessit") or anno_pulito)
        confidenza_ai = dati_ai.get("confidenza", 0.0) if dati_ai else 0.0

        varianti = tmdb_service.cerca_serie(titolo_da_usare, anno_da_usare, nome_file=nome)

        info_tecnica = ffmpeg_service.analizza_tecnico(percorso)

        match_principale = (
            varianti[0] if varianti else {"titolo": titolo_da_usare, "anno": anno_da_usare, "confidenza": confidenza_ai}
        )

        if dati_ai:
            confidenza_complessiva = round(confidenza_ai * 0.3 + match_principale.get("confidenza_tmdb", 0.0) * 0.7, 2)
        else:
            confidenza_complessiva = match_principale.get("confidenza_tmdb", 0.0)

        def _e_generico(t: str) -> bool:
            if not t:
                return True
            t_low = t.lower()
            if t_low.startswith("episodio") or t_low.startswith("episode") or t_low.startswith("ep."):
                if re.match(r"^(?:episodio|episode|ep\.?)\s*\d+", t, re.I):
                    return True
            if t.strip().isdigit():
                return True
            if len(t.strip()) < 3:
                return True
            if match_principale.get("titolo") and t.lower().strip() == match_principale["titolo"].lower().strip():
                return True
            return False

        nome_episodio = ""
        tmdb_id = match_principale.get("tmdb_id")
        if tmdb_id and stagione and episodio:
            try:
                nome_episodio = tmdb_service.recupera_nome_episodio(int(tmdb_id), int(stagione), int(episodio))
            except (ValueError, TypeError):
                pass

        if _e_generico(nome_episodio):
            self._log(f"  Titolo TMDB assente o generico per {match_principale.get('titolo', '')}.")
            if dati_ai and dati_ai.get("titolo_episodio"):
                nome_episodio = dati_ai["titolo_episodio"]
                self._log(f"  Episodio AI (Manuale): {nome_episodio}")
            else:
                nome_episodio = ""
        elif nome_episodio:
            self._log(f"  Episodio TMDB: {nome_episodio}")

        res = {
            "file_originale": nome,
            "percorso_originale": percorso,
            "estensione": info_file["estensione"],
            "stagione": stagione,
            "episodio": episodio,
            "nome_episodio": nome_episodio,
            "match_principale": match_principale,
            "gemini": dati_ai or {"tipo": "serie", "confidenza": 0.0, "note": "Analisi AI non effettuata/richiesta"},
            "varianti": varianti[:3],
            "info_tecnica": info_tecnica,
            "confidenza": confidenza_complessiva,
        }

        if match_principale and match_principale.get("data_rilascio"):
            io_service.imposta_data_file(percorso, match_principale.get("data_rilascio"))

        return res

    def costruisci_nome_jellyfin(
        self, match: dict[str, Any], stagione: str, episodio: str, info_tecnica: dict[str, Any], estensione: str, nome_episodio: str = ""
    ) -> dict[str, str]:
        titolo = self._sanifica_percorso(match.get("titolo", "Sconosciuto"))
        anno = match.get("anno", "")
        tmdb_id = match.get("tmdb_id")
        etichetta = info_tecnica.get("etichetta", "")
        stagione_num = stagione.zfill(2) if stagione else "01"
        episodio_num = episodio.zfill(2) if episodio else "01"

        nome_serie = f"{titolo} ({anno})" if anno else titolo
        id_tag = f" [tmdbid-{tmdb_id}]" if tmdb_id else ""
        cartella_serie = f"{nome_serie}{id_tag}"
        cartella_stagione = f"Season {stagione_num}"

        codice_ep = f"S{stagione_num}E{episodio_num}"
        nome_ep_sanificato = self._sanifica_percorso(nome_episodio) if nome_episodio else ""

        if nome_ep_sanificato:
            nome_file = f"{nome_serie} {codice_ep} {nome_ep_sanificato}"
        else:
            nome_file = f"{nome_serie} {codice_ep}"

        if etichetta:
            nome_file = f"{nome_file} - {etichetta}"
        nome_file = f"{nome_file}{estensione}"

        return {"cartella_serie": cartella_serie, "cartella_stagione": cartella_stagione, "nome_file": nome_file}

    def sposta_file(
        self,
        percorso_sorgente: str,
        destinazione_radice: str,
        match: dict[str, Any],
        stagione: str,
        episodio: str,
        info_tecnica: dict[str, Any],
        estensione: str,
        azione: str = "Sposta",
        rimuovi_vuote: bool = False,
        callback_io: Optional[Callable[[dict], None]] = None,
        radice_stop: Optional[str] = None,
        nome_episodio: str = "",
    ) -> dict[str, Any]:
        try:
            struttura = self.costruisci_nome_jellyfin(match, stagione, episodio, info_tecnica, estensione, nome_episodio)
            cartella_dest = os.path.join(destinazione_radice, struttura["cartella_serie"], struttura["cartella_stagione"])
            os.makedirs(cartella_dest, exist_ok=True)
            percorso_destinazione = os.path.join(cartella_dest, struttura["nome_file"])

            if azione == "Copia":
                esito, msg_io = io_service.copia_con_progresso(percorso_sorgente, percorso_destinazione, callback_io)
                if esito:
                    self._log(f"Copiato: {struttura['nome_file']}")
            else:
                esito, msg_io = io_service.sposta_con_progresso(percorso_sorgente, percorso_destinazione, callback_io)
                if esito:
                    self._log(f"Spostato: {struttura['nome_file']}")
                    if rimuovi_vuote:
                        io_service.rimuovi_directory_vuote_ricorsivo(os.path.dirname(percorso_sorgente), radice_stop)

            if esito:
                data_rilascio = match.get("data_rilascio")
                if data_rilascio:
                    io_service.imposta_data_file(percorso_destinazione, data_rilascio)
                    io_service.imposta_data_file(cartella_dest, data_rilascio)
                    cartella_base_serie = os.path.dirname(cartella_dest)
                    io_service.imposta_data_file(cartella_base_serie, data_rilascio)

            return {"successo": esito, "percorso_finale": percorso_destinazione if esito else None, "errore": msg_io if not esito else None}
        except OSError as e:
            self._log(f"Errore spostamento: {e}")
            return {"successo": False, "errore": str(e)}
