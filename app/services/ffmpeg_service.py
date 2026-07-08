"""Analisi tecnica (risoluzione/codec) via ffprobe. Porta servizio_ffmpeg.py.

Va inizializzato con configura(ffprobe_exe) prima dell'uso: il percorso
dell'eseguibile ffprobe è ora ancorato ad AppPaths, non a config.FFPROBE_PATH.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import TypedDict

_log = logging.getLogger("gestore_film.principale")

_ffprobe_exe: Path | None = None


def configura(ffprobe_exe: Path) -> None:
    global _ffprobe_exe
    _ffprobe_exe = ffprobe_exe


_RISOLUZIONI = [
    (3840, "2160p"),
    (2560, "1440p"),
    (1920, "1080p"),
    (1280, "720p"),
    (854, "480p"),
]

_MAPPA_CODEC = {
    "hevc": "H.265",
    "h264": "H.264",
    "av1": "AV1",
    "vp9": "VP9",
    "mpeg4": "MPEG4",
    "mpeg2video": "MPEG2",
}


class InfoTecnica(TypedDict):
    risoluzione: str
    codec_video: str
    codec_audio: str
    larghezza: int
    etichetta: str


_VUOTO: InfoTecnica = {"risoluzione": "", "codec_video": "", "codec_audio": "", "larghezza": 0, "etichetta": ""}


def _mappa_risoluzione(larghezza: int) -> str:
    for soglia, etichetta in _RISOLUZIONI:
        if larghezza >= soglia:
            return etichetta
    return "SD"


def _mappa_codec(codec: str) -> str:
    return _MAPPA_CODEC.get(codec.lower(), codec.upper())


def analizza_tecnico(percorso: str) -> InfoTecnica:
    if percorso.lower().startswith("ftp://") or _ffprobe_exe is None:
        return dict(_VUOTO)
    try:
        cmd = [str(_ffprobe_exe), "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", percorso]
        risultato = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        info = json.loads(risultato.stdout)

        flusso_video = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
        flusso_audio = next((s for s in info["streams"] if s.get("codec_type") == "audio"), None)

        if not flusso_video:
            return dict(_VUOTO)

        larghezza = int(flusso_video.get("width", 0))
        codec_audio = flusso_audio.get("codec_name", "") if flusso_audio else ""

        risoluzione = _mappa_risoluzione(larghezza)
        codec_v = _mappa_codec(flusso_video.get("codec_name", ""))

        return {
            "risoluzione": risoluzione,
            "codec_video": codec_v,
            "codec_audio": codec_audio.upper(),
            "larghezza": larghezza,
            "etichetta": f"{risoluzione} {codec_v}".strip(),
        }
    except Exception as e:
        _log.warning(f"ffprobe fallito per {percorso}: {e}")
        return dict(_VUOTO)
