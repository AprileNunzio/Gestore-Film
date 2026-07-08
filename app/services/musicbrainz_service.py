"""Ricerca testuale MusicBrainz, fallback quando i tag ID3 sono assenti/incompleti.

Porta servizio_musicbrainz.py.
"""
from __future__ import annotations

from typing import Any, Optional

import musicbrainzngs

musicbrainzngs.set_useragent("GestoreFilmPortable", "1.0", "https://github.com/nunziotech")


def cerca_musica(titolo: str, artista: Optional[str] = None) -> list[dict[str, Any]]:
    try:
        query: dict[str, str] = {"recording": titolo}
        if artista:
            query["artist"] = artista

        risultati = musicbrainzngs.search_recordings(limit=5, **query)

        lista_metadata = []
        for rec in risultati.get("recording-list", []):
            score = int(rec.get("ext:score", 0))
            if score < 70:
                continue

            match = {
                "titolo": rec.get("title", ""),
                "artista": rec.get("artist-credit-phrase", ""),
                "album": "",
                "anno": "",
                "mbid": rec.get("id", ""),
                "confidenza": score / 100.0,
            }

            release_list = rec.get("release-list", [])
            if release_list:
                release = release_list[0]
                match["album"] = release.get("title", "")
                data = release.get("date", "")
                if data:
                    match["anno"] = data[:4]

            lista_metadata.append(match)

        return sorted(lista_metadata, key=lambda x: x["confidenza"], reverse=True)
    except Exception:
        return []


def ottieni_metadata_da_mbid(mbid: str) -> Optional[dict[str, Any]]:
    try:
        rec = musicbrainzngs.get_recording_by_id(mbid, includes=["artists", "releases"])
        rec = rec.get("recording", {})

        match = {
            "titolo": rec.get("title", ""),
            "artista": rec.get("artist-credit-phrase", ""),
            "album": "",
            "anno": "",
            "mbid": mbid,
            "confidenza": 1.0,
        }

        release_list = rec.get("release-list", [])
        if release_list:
            release = release_list[0]
            match["album"] = release.get("title", "")
            data = release.get("date", "")
            if data:
                match["anno"] = data[:4]

        return match
    except Exception:
        return None
