"""Estrazione locale (senza rete) di titolo/anno/stagione/episodio dai nomi file.

Consolida in un unico modulo le 3 implementazioni parallele trovate in
Script_Film: servizio_parser_locale.MotoreIbrido (guessit + euristiche),
il regex bank di OrganizzatoreSerie._estrai_stagione_episodio, e le chiamate
guessit inline sparse in organizzatore_universale.py. `estrai_stagione_episodio`
è ora l'unico punto di verità per stagione/episodio (era già trattato come
"autoritativo" dal codice originale, che lo richiamava direttamente bypassando
servizio_parser_locale); guessit viene usato solo per titolo/anno/tipo.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, NamedTuple

import guessit

_log = logging.getLogger("gestore_film.principale")


def normalizza_nome_windows(nome_file: str) -> str:
    """Normalizza rimuovendo caratteri non validi per Windows/SMB e tag qualità/codec."""
    nome = unicodedata.normalize("NFC", nome_file)
    nome = re.sub(r"[\x00-\x1F\x7F]", "", nome)

    base, est = os.path.splitext(nome)
    base = re.sub(r'[<>:"/\\|\?\*]', "", base)
    base = re.sub(
        r"(?i)\b(1080p|720p|2160p|4k|uhd|10bit|h\.?26[45]|x\.?26[45]|hevc|aac|ac3|dts|web.?dl|bdrip|brrip|2\.0|5\.1|7\.1)\b",
        " ",
        base,
    )
    base = re.sub(r"[\.\_\-]", " ", base)
    return f"{base.strip()}{est}"


class StagioneEpisodio(NamedTuple):
    stagione: str
    episodio: str
    forza: str  # "forte" | "media" | "debole" | "" (nessun match)


# Pattern in ordine di priorità/affidabilità: i primi (indici 0-2) sono i più
# specifici ("forte"), 3-4 "media", 5 (catch-all numero nudo) "debole".
_PATTERNS_STAGIONE_EPISODIO = [
    re.compile(r"(?<!\d)[Ss](\d{1,2})[Ee](\d{1,4})(?!\d)", re.I),
    re.compile(r"(?<!\d)(\d{1,2})[xX](\d{1,4})(?!\d)", re.I),
    re.compile(r"\[(\d{1,2})[xX](\d{1,4})\]", re.I),
    re.compile(r"\b(?:episodio|episode|ep\.?)\b\s*(\d{1,3})", re.I),
    re.compile(r"\((\d{1,3})\)", re.I),
    re.compile(r"(?<![\d\.])(\d{1,4})(?![\d\.])", re.I),
]

_PATTERN_PULIZIA_SERIE = [
    r"[Ss]\d{1,2}[Ee]\d{1,4}.*$",
    r"\d{1,2}[xX]\d{1,4}.*$",
    r"(?:episodio|episode|ep\.?)\s*\d{1,3}.*$",
    r"\d{1,2}°\s+(?:serie|stagione|st)\b",
    r"\b(?:serie|stagione|st)\.?\s*\d{1,2}\b",
    r"\b(ita|eng|spa|fra|deu|por)\b",
    r"\b(bluray|blu-ray|bdrip|brrip|webrip|web-dl|webdl|hdtv|dvdrip|dvdscr|hdcam)\b",
    r"\b(1080p|720p|2160p|480p|4k|uhd)\b",
    r"\b(x264|x265|hevc|h264|h265|xvid|divx|avc|av1)\b",
    r"\b(aac|ac3|dts|truehd|mp3|eac3|flac|atmos)\b",
    r"\b(hdr|hdr10|hlg|dv|dolby|vision)\b",
    r"(?<!\d)\d{1,3}(?!\d)",
    r"\b(19|20)\d{2}\b",
    r"[\(\)\[\]]",
    r"[\.\-\_]",
    r"\s{2,}",
]


def estrai_stagione_episodio(nome_file: str) -> StagioneEpisodio:
    """Unico punto di verità per stagione/episodio: prova i pattern in ordine di forza."""
    nome_senza_estensione = os.path.splitext(nome_file)[0]
    for indice, pattern in enumerate(_PATTERNS_STAGIONE_EPISODIO):
        for match in pattern.finditer(nome_senza_estensione):
            gruppi = match.groups()
            forza = "forte" if indice <= 2 else ("media" if indice <= 4 else "debole")

            if len(gruppi) == 2:
                return StagioneEpisodio(str(int(gruppi[0])).zfill(2), str(int(gruppi[1])).zfill(2), forza)
            if len(gruppi) == 1:
                valore = int(gruppi[0])
                if 1900 <= valore <= 2100 and len(gruppi[0]) == 4:
                    continue
                return StagioneEpisodio("01", str(valore).zfill(2), forza)
    return StagioneEpisodio("", "", "")


def pulisci_titolo_serie(nome_file: str, cartella_padre: str = "") -> tuple[str, str]:
    """Deriva (titolo_pulito, anno) da un nome file di serie tramite sostituzioni regex aggressive."""
    nome = Path(nome_file).stem

    titolo_temp = nome
    for pattern in _PATTERN_PULIZIA_SERIE:
        titolo_temp = re.sub(pattern, " ", titolo_temp, flags=re.IGNORECASE)

    if len(titolo_temp.strip()) < 3 and cartella_padre:
        nome = cartella_padre

    anno_match = re.search(r"\b(19|20)\d{2}\b", nome)
    anno = anno_match.group(0) if anno_match else ""

    for pattern in _PATTERN_PULIZIA_SERIE:
        nome = re.sub(pattern, " ", nome, flags=re.IGNORECASE)

    return nome.strip(), anno


class MotoreIbrido:
    """Estrae titolo/anno/tipo tramite guessit, con context injection dalla cartella padre."""

    def estrai_info(self, nome_file: str, percorso_assoluto: str = "") -> dict[str, Any]:
        nome_pulito = normalizza_nome_windows(nome_file)
        _log.debug(f"Parsing [Hybrid]: '{nome_file}' -> '{nome_pulito}'")

        risorsa = guessit.guessit(nome_pulito)
        _log.debug(f"Guessit ha restituito: {risorsa}")

        tipo_indovinato = risorsa.get("type")
        titolo = risorsa.get("title", "")
        anno = risorsa.get("year")

        stagione_ep = estrai_stagione_episodio(nome_file)
        stagione = int(stagione_ep.stagione) if stagione_ep.stagione else None
        episodio = int(stagione_ep.episodio) if stagione_ep.episodio else None

        dati_estratti: dict[str, Any] = {
            "titolo": titolo,
            "titolo_secondario": None,
            "anno": anno,
            "stagione": stagione,
            "episodio": episodio,
            "tipo_indovinato": tipo_indovinato,
            "raw_guessit": dict(risorsa),
        }

        if not dati_estratti.get("anno"):
            match_anno = re.search(r"(?:\(|\[)?(19|20)\d{2}(?:\)|\])?", nome_file)
            if match_anno:
                solo_numeri = re.search(r"(19|20)\d{2}", match_anno.group(0))
                if solo_numeri:
                    dati_estratti["anno"] = int(solo_numeri.group(0))
                    _log.debug(f"Fallback recupero anno: {dati_estratti['anno']}")

        if percorso_assoluto:
            directory = os.path.dirname(percorso_assoluto)
            match_stagione = re.search(r"(?i)(?:season|stagione)\s+(\d+)", directory)
            if match_stagione and not dati_estratti.get("stagione"):
                dati_estratti["stagione"] = int(match_stagione.group(1))
                dati_estratti["tipo_indovinato"] = "episode"
                _log.debug(f"Context injection: Stagione {dati_estratti['stagione']} forzata dal percorso")

        return dati_estratti


_motore = MotoreIbrido()


def estrai_info_locali(nome_file: str, percorso_assoluto: str = "") -> dict[str, Any]:
    return _motore.estrai_info(nome_file, percorso_assoluto)


_FILE_SIDECAR_TMDB = [
    ("tvshow.nfo", "serie"),
    ("tmdb.tv", "serie"),
    ("movie.nfo", "film"),
    ("tmdb.movie", "film"),
    ("tmdb.id", None),
    ("info.txt", None),
]

_PATTERN_ID_SIDECAR = re.compile(
    r"(?:tmdbid-|tmdb\.com/tv/|tmdb\.com/movie/|tmdbid>|id[:=]\s*)(\d+)", re.I
)


def cerca_id_tmdb_locale(percorso_file: str) -> tuple[int | None, str | None]:
    """Cerca un ID TMDB in file sidecar locali (.nfo, tmdb.id, ...) nella cartella del file."""
    if not percorso_file:
        return None, None

    directory = os.path.dirname(percorso_file)
    if not directory or not os.path.isdir(directory):
        return None, None

    for nome_f, tipo_suggerito in _FILE_SIDECAR_TMDB:
        percorso = os.path.join(directory, nome_f)
        if not os.path.exists(percorso):
            continue
        try:
            with open(percorso, "r", encoding="utf-8-sig", errors="replace") as file:
                contenuto = file.read().strip()
                contenuto = "".join(ch for ch in contenuto if ch.isprintable() or ch.isspace())

                match_id = _PATTERN_ID_SIDECAR.search(contenuto)
                if match_id:
                    return int(match_id.group(1)), tipo_suggerito

                solo_numero = re.search(r"(\d{1,10})", contenuto)
                if solo_numero and len(contenuto.split()) < 5:
                    return int(solo_numero.group(1)), tipo_suggerito
        except OSError:
            pass
    return None, None
