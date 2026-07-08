"""Identificazione audio via fingerprint AcoustID/Chromaprint. Porta servizio_acoustid.py.

Va inizializzato con configura(api_key, fpcalc_exe) prima dell'uso: fpcalc.exe
è ora risolto tramite AppPaths invece che derivato da config.FFMPEG_PATH.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

_log = logging.getLogger("gestore_film.principale")

_api_key = ""
_fpcalc_exe: Path | None = None


def configura(api_key: str, fpcalc_exe: Path) -> None:
    global _api_key, _fpcalc_exe
    _api_key = api_key
    _fpcalc_exe = fpcalc_exe


def identifica_audio(percorso_file: str) -> Optional[dict[str, Any]]:
    if not _api_key or _fpcalc_exe is None or not _fpcalc_exe.exists():
        return None

    try:
        import acoustid

        risultati = acoustid.match(_api_key, percorso_file, parse=True, fpcalc=str(_fpcalc_exe))

        for score, recording_id, title, artist in risultati:
            if score > 0.5:
                return {"mbid": recording_id, "titolo": title, "artista": artist, "confidenza": score}
    except Exception as e:
        _log.warning(f"AcoustID fallito per {percorso_file}: {e}")

    return None
