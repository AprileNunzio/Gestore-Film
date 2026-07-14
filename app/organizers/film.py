"""Logica di business per i film. Porta organizzatori/organizzatore_film.py.

Fix rispetto all'originale: analizza_con_ai referenziava una variabile
`info_file` mai definita nel suo scope (NameError dormiente, mai emerso perché
ai_data non è mai None nei servizi AI attuali — ma un landmine reale). I due
fallback rotti sono stati rimossi: dato che ai_data è sempre un dict, l'unico
ramo raggiungibile era comunque `ai_data.get(...)`.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

from app.core.config import ESTENSIONI_VIDEO, ConfigManager
from app.core.paths import AppPaths
from app.services import ffmpeg_service, gemini_service, io_service, media_parsing, metadata_service, openai_service, tmdb_service

_log = logging.getLogger("gestore_film.principale")

LogCallback = Callable[[str], None]


class OrganizzatoreFilm:
    def __init__(self) -> None:
        self._log_callback: Optional[LogCallback] = None

    def imposta_callback_log(self, callback: LogCallback) -> None:
        self._log_callback = callback

    def _log(self, messaggio: str) -> None:
        if self._log_callback:
            self._log_callback(messaggio)

    def _sanifica_percorso(self, testo: str) -> str:
        for c in r'<>:"/\|?*':
            testo = testo.replace(c, "")
        return testo.strip()

    def scansiona_directory(self, percorso: str) -> list[dict[str, Any]]:
        file_trovati = []
        try:
            for radice, _dirs, file in os.walk(percorso):
                for nome in file:
                    if Path(nome).suffix.lower() in ESTENSIONI_VIDEO:
                        file_trovati.append(
                            {
                                "percorso": os.path.join(radice, nome),
                                "nome": nome,
                                "estensione": Path(nome).suffix.lower(),
                            }
                        )
                        self._log(f"Trovato: {nome}")
        except OSError as e:
            self._log(f"Errore scansione: {e}")
        return file_trovati

    def analizza_file(self, info_file: dict[str, Any]) -> dict[str, Any]:
        nome = info_file["nome"]
        percorso = info_file["percorso"]

        cartella_padre = os.path.basename(os.path.dirname(percorso))
        self._log(f"Analisi locale: {nome} (Contesto: {cartella_padre})")

        info_locali = media_parsing.estrai_info_locali(nome)
        titolo_loc = info_locali["titolo"]
        anno_loc = info_locali["anno"]
        titolo_sec = info_locali.get("titolo_secondario", "")

        if len(titolo_loc.strip()) < 3 and cartella_padre:
            self._log(f"  Nome file generico, eredito titolo da cartella: {cartella_padre}")
            titolo_loc = cartella_padre

        # 1. Analisi tecnica locale (ffprobe)
        info_tecnica = ffmpeg_service.analizza_tecnico(percorso)

        # 2. Controllo Risoluzione Minima
        config = ConfigManager(AppPaths()).carica().get("automazione", {})
        if config.get("risoluzione_minima_attiva", False):
            soglia_valore = config.get("risoluzione_minima_valore", "720p")
            rank = {"SD": 0, "480p": 1, "720p": 2, "1080p": 3, "1440p": 4, "2160p": 5}
            res_corrente = info_tecnica.get("risoluzione") or "SD"
            if rank.get(res_corrente, 0) < rank.get(soglia_valore, 0):
                self._log(f"  Scartato: Risoluzione {res_corrente} inferiore alla soglia {soglia_valore}.")
                res = {
                    "file_originale": nome,
                    "percorso_originale": percorso,
                    "estensione": info_file["estensione"],
                    "gemini": {"tipo": "sconosciuto", "confidenza": 0.0, "note": f"Scartato per risoluzione (< {soglia_valore})"},
                    "match_principale": {"tmdb_id": None, "titolo": titolo_loc, "titolo_originale": "", "anno": anno_loc, "confidenza_tmdb": 0.0},
                    "varianti": [],
                    "info_tecnica": info_tecnica,
                    "confidenza": 0.0,
                    "nome_jellyfin": {"decade": "Altro", "cartella": titolo_loc, "nome_file": nome}
                }
                return res

        # 3. Ricerca TMDB
        varianti = tmdb_service.cerca_film(titolo_loc, anno_loc, nome_file=nome, titolo_secondario=titolo_sec)
        match_principale = varianti[0] if varianti else None
        conf_tmdb = match_principale.get("confidenza_tmdb", 0.0) if match_principale else 0.0

        if conf_tmdb < 0.5 and cartella_padre and cartella_padre.lower() != titolo_loc.lower():
            self._log(f"  Confidenza bassa ({conf_tmdb}), provo con cartella padre: {cartella_padre}")
            varianti_padre = tmdb_service.cerca_film(cartella_padre, anno_loc, fallback_serie=False)
            if varianti_padre and varianti_padre[0].get("confidenza_tmdb", 0) > conf_tmdb:
                varianti = varianti_padre
                match_principale = varianti[0]
                conf_tmdb = match_principale.get("confidenza_tmdb", 0.0)

        t_it = match_principale.get("titolo", "") if match_principale else titolo_loc
        t_orig = match_principale.get("titolo_originale", "") if match_principale else titolo_loc
        a_match = match_principale.get("anno", "") if match_principale else anno_loc

        strategia = match_principale.get("strategia_vincente", "standard") if match_principale else "nessuna"
        self._log(f"  Risultato: '{t_it}' ({a_match}) | Conf: {conf_tmdb} | Strategia: {strategia}")

        res: dict[str, Any] = {
            "file_originale": nome,
            "percorso_originale": percorso,
            "estensione": info_file["estensione"],
            "gemini": {"tipo": "sconosciuto", "confidenza": 0.0, "note": "Analisi AI non richiesta"},
            "match_principale": match_principale
            or {"tmdb_id": None, "titolo": t_it, "titolo_originale": t_orig, "anno": a_match, "confidenza_tmdb": 0.0},
            "varianti": varianti[:5],
            "info_tecnica": info_tecnica,
            "confidenza": round(conf_tmdb, 2),
        }
        res["nome_jellyfin"] = self.costruisci_nome_jellyfin(t_it, res["match_principale"], info_tecnica, info_file["estensione"])

        io_service.imposta_data_attuale(percorso)

        return res

    def analizza_con_ai(self, r: dict[str, Any], provider: str = "gemini") -> dict[str, Any]:
        nome = r["file_originale"]
        self._log(f"Analisi manuale richiesta con {provider.upper()} per: {nome}")

        if provider == "chatgpt":
            ai_data = openai_service.analizza_con_openai(nome)
        else:
            ai_data = gemini_service.analizza_nome_file(nome)

        r["gemini"] = ai_data

        titolo_ai = ai_data.get("titolo_italiano", "")
        titolo_orig_ai = ai_data.get("titolo_originale", "")
        anno_ai = ai_data.get("anno")

        varianti_ai = tmdb_service.cerca_film(titolo_ai, anno_ai, titolo_orig_ai, nome_file=nome)
        if varianti_ai:
            r["varianti"] = varianti_ai[:5]
            r["match_principale"] = varianti_ai[0]
            conf_tmdb = r["match_principale"].get("confidenza_tmdb", 0.0)
            r["confidenza"] = round(max(ai_data.get("confidenza", 0.0), conf_tmdb), 2)

            t_it = r["match_principale"].get("titolo", "") or titolo_ai
            r["nome_jellyfin"] = self.costruisci_nome_jellyfin(t_it, r["match_principale"], r["info_tecnica"], r["estensione"])

            io_service.imposta_data_attuale(r["percorso_originale"])

        return r

    def ottieni_percorso_decade(self, anno: str) -> str:
        if not anno or not str(anno).isdigit():
            return "Altro"
        anno_int = int(anno)
        decade_inizio = (anno_int // 10) * 10
        decade_fine = decade_inizio + 9
        return f"Anni {decade_inizio}-{decade_fine}"

    def costruisci_nome_jellyfin(self, titolo_it: str, match: dict[str, Any], info_tecnica: dict[str, Any], estensione: str) -> dict[str, str]:
        titolo = self._sanifica_percorso(titolo_it or match.get("titolo", "Sconosciuto"))
        anno = str(match.get("anno", ""))
        tmdb_id = match.get("tmdb_id")
        etichetta = info_tecnica.get("etichetta", "")

        decade_folder = self.ottieni_percorso_decade(anno)

        base = f"{titolo} ({anno})" if anno else titolo
        id_tag = f" [tmdbid-{tmdb_id}]" if tmdb_id else ""

        nome_cartella = base
        nome_file = f"{base}{id_tag}"
        if etichetta:
            nome_file = f"{nome_file} - {etichetta}"
        nome_file = f"{nome_file}{estensione}"

        return {"decade": decade_folder, "cartella": nome_cartella, "nome_file": nome_file}

    def sposta_file(
        self,
        percorso_sorgente: str,
        destinazione_radice: str,
        titolo_it: str,
        match: dict[str, Any],
        info_tecnica: dict[str, Any],
        estensione: str,
        azione: str = "Sposta",
        rimuovi_vuote: bool = False,
        callback_io: Optional[Callable[[dict], None]] = None,
        radice_stop: Optional[str] = None,
    ) -> dict[str, Any]:
        try:
            struttura = self.costruisci_nome_jellyfin(titolo_it, match, info_tecnica, estensione)

            cartella_decade = os.path.join(destinazione_radice, struttura["decade"])
            cartella_dest = os.path.join(cartella_decade, struttura["cartella"])

            os.makedirs(cartella_dest, exist_ok=True)
            percorso_dest = os.path.join(cartella_dest, struttura["nome_file"])

            if azione == "Copia":
                esito, msg_io = io_service.copia_con_progresso(percorso_sorgente, percorso_dest, callback_io)
                if esito:
                    self._log(f"Copiato: {struttura['nome_file']}")
            else:
                esito, msg_io = io_service.sposta_con_progresso(percorso_sorgente, percorso_dest, callback_io)
                if esito:
                    self._log(f"Spostato: {struttura['nome_file']}")
                    if rimuovi_vuote:
                        io_service.rimuovi_directory_vuote_ricorsivo(os.path.dirname(percorso_sorgente), radice_stop)

            if esito:
                io_service.imposta_data_attuale(percorso_dest)
                io_service.imposta_data_attuale(cartella_dest)

                tmdb_id = match.get("tmdb_id")
                if tmdb_id:
                    self._log(f"Scaricamento artwork aggiuntivo Jellyfin per: {tmdb_id}")
                    try:
                        metadata_service.scarica_metadata_jellyfin_film(tmdb_id, cartella_dest)
                    except Exception as e:
                        self._log(f"Errore secondario download metadata: {e}")

            return {"successo": esito, "percorso_finale": percorso_dest if esito else None, "errore": msg_io if not esito else None}
        except OSError as e:
            self._log(f"Errore: {e}")
            return {"successo": False, "errore": str(e)}
