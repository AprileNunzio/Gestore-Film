"""Logica di business per la musica. Porta organizzatori/organizzatore_musica.py.

Fix rispetto all'originale: il fallback AI chiamava
servizio_gemini.estrai_metadati(nome, tipo_fallback="musica") — parametro
inesistente (TypeError certo se mai raggiunto) — e leggeva dal risultato
campi mai presenti nello schema EsitoAI (titolo/artista/album/traccia invece
di titolo_italiano/titolo_originale/anno, gli unici che il modello Gemini
espone). Corretto per chiamare la firma reale e leggere solo i campi che
esistono davvero, senza inventare un nuovo prompt/schema music-specific.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

from app.core.config import ESTENSIONI_AUDIO
from app.services import acoustid_service, gemini_service, io_service, musicbrainz_service

_log = logging.getLogger("gestore_film.principale")

LogCallback = Callable[[str], None]

_SEPARATORI = re.compile(r"[\.\-\_]")


class OrganizzatoreMusica:
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

    def _estrai_info_id3(self, percorso: str) -> dict[str, str]:
        try:
            from mutagen import File as MutagenFile

            audio = MutagenFile(percorso, easy=True)
            if audio is None:
                return {}
            return {
                "titolo": str(audio.get("title", [""])[0]),
                "artista": str(audio.get("artist", [""])[0]),
                "album": str(audio.get("album", [""])[0]),
                "anno": str(audio.get("date", [""])[0])[:4],
                "traccia": str(audio.get("tracknumber", [""])[0]).split("/")[0],
            }
        except Exception:
            return {}

    def _fallback_da_nome(self, nome_file: str) -> dict[str, str]:
        nome = Path(nome_file).stem
        parti = [p.strip() for p in _SEPARATORI.split(nome) if p.strip()]
        return {
            "titolo": parti[-1] if parti else nome,
            "artista": parti[0] if len(parti) > 1 else "Artista Sconosciuto",
            "album": "Album Sconosciuto",
            "anno": "",
            "traccia": "",
        }

    def scansiona_directory(self, percorso: str) -> list[dict[str, Any]]:
        file_trovati = []
        try:
            for radice, _dirs, file in os.walk(percorso):
                for nome in file:
                    estensione = Path(nome).suffix.lower()
                    if estensione in ESTENSIONI_AUDIO:
                        file_trovati.append(
                            {"percorso": os.path.join(radice, nome), "nome": nome, "estensione": estensione}
                        )
                        self._log(f"Trovato: {nome}")
        except OSError as e:
            self._log(f"Errore scansione: {e}")
        return file_trovati

    def analizza_file(self, info_file: dict[str, Any], usa_ai: bool = False) -> dict[str, Any]:
        percorso = info_file["percorso"]
        nome = info_file["nome"]
        est = info_file["estensione"]

        self._log(f"Analisi brano: {nome}")

        info_id3 = self._estrai_info_id3(percorso)
        confidenza = 0.0
        fonte = "nessuna"

        if info_id3.get("titolo") and info_id3.get("artista"):
            confidenza = 0.9
            fonte = "tag_id3"
            self._log(f"  Metadati trovati nei tag ID3: {info_id3['artista']} - {info_id3['titolo']}")
        else:
            self._log("  Tag ID3 mancanti o incompleti, provo MusicBrainz...")
            info_nome = self._fallback_da_nome(nome)
            risultati_mb = musicbrainz_service.cerca_musica(info_nome["titolo"], info_nome["artista"])

            if risultati_mb:
                info_id3 = risultati_mb[0]
                confidenza = info_id3["confidenza"]
                fonte = "musicbrainz"
                self._log(f"  Trovato su MusicBrainz: {info_id3['artista']} - {info_id3['titolo']} (Conf: {int(confidenza * 100)}%)")
            else:
                self._log("  Nessun match su MusicBrainz, provo fingerprinting audio...")
                info_audio = acoustid_service.identifica_audio(percorso)
                if info_audio:
                    metadata_completi = musicbrainz_service.ottieni_metadata_da_mbid(info_audio["mbid"])
                    if metadata_completi:
                        info_id3 = metadata_completi
                        confidenza = info_audio["confidenza"]
                        fonte = "acoustid"
                        self._log(f"  Identificato via impronta audio: {info_id3['artista']} - {info_id3['titolo']}")
                    else:
                        info_id3 = info_audio
                        confidenza = info_audio["confidenza"]
                        fonte = "acoustid_parziale"
                elif usa_ai:
                    self._log("  Identificazione audio fallita, uso IA...")
                    ai_res = gemini_service.estrai_metadati(nome, contesto="musica")
                    titolo_ai = ai_res.get("titolo_italiano") or ai_res.get("titolo_originale")
                    if titolo_ai:
                        info_id3 = {
                            "titolo": titolo_ai,
                            "artista": info_nome["artista"],
                            "album": "Album Sconosciuto",
                            "anno": str(ai_res.get("anno", "") or ""),
                            "traccia": "",
                        }
                        confidenza = ai_res.get("confidenza", 0.5)
                        fonte = "ia"
                        self._log(f"  IA ha identificato: {info_id3['artista']} - {info_id3['titolo']}")
                    else:
                        info_id3 = info_nome
                        confidenza = 0.3
                        fonte = "nome_file"
                else:
                    info_id3 = info_nome
                    confidenza = 0.3
                    fonte = "nome_file"

        res = {
            "file_originale": nome,
            "percorso_originale": percorso,
            "estensione": est,
            "info_id3": info_id3,
            "confidenza": round(confidenza, 2),
            "fonte_metadati": fonte,
            "tipo_media": "musica",
        }

        res["nome_jellyfin"] = self.costruisci_nome_jellyfin(info_id3, est)
        return res

    def costruisci_nome_jellyfin(self, info_id3: dict[str, Any], estensione: str) -> dict[str, str]:
        artista = self._sanifica_percorso(info_id3.get("artista", "Artista Sconosciuto") or "Artista Sconosciuto")
        album = self._sanifica_percorso(info_id3.get("album", "Album Sconosciuto") or "Album Sconosciuto")
        titolo = self._sanifica_percorso(info_id3.get("titolo", "Traccia Sconosciuta") or "Traccia Sconosciuta")
        traccia = str(info_id3.get("traccia", "")).zfill(2)
        anno = str(info_id3.get("anno", ""))

        nome_album = f"{album} ({anno})" if anno and len(anno) == 4 else album
        prefisso = f"{traccia} - " if traccia and traccia != "00" else ""
        nome_file = f"{prefisso}{titolo}{estensione}"

        return {"cartella_artista": artista, "cartella_album": nome_album, "nome_file": nome_file}

    def sposta_file(
        self,
        r: dict[str, Any],
        destinazione_radice: str,
        azione: str = "Sposta",
        rimuovi_vuote: bool = False,
        callback_io: Optional[Callable[[dict], None]] = None,
        radice_stop: Optional[str] = None,
    ) -> dict[str, Any]:
        try:
            percorso_sorgente = r["percorso_originale"]
            struttura = r["nome_jellyfin"]

            cartella_dest = os.path.join(destinazione_radice, struttura["cartella_artista"], struttura["cartella_album"])
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

            return {"successo": esito, "percorso_finale": percorso_destinazione if esito else None, "errore": msg_io if not esito else None}
        except OSError as e:
            self._log(f"Errore spostamento: {e}")
            return {"successo": False, "errore": str(e)}
