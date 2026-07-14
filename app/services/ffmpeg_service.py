"""Analisi tecnica (risoluzione/codec/tracce/dimensione) via ffprobe. Porta servizio_ffmpeg.py.

Va inizializzato con configura(ffprobe_exe) prima dell'uso: il percorso
dell'eseguibile ffprobe è ora ancorato ad AppPaths, non a config.FFPROBE_PATH.

Prima di questa versione mancavano dimensione file, durata, bitrate, fps e
l'elenco completo delle tracce audio/sottotitoli (la UI di Approvazione già
tentava di leggere `dimensione_mb`/`tracce_audio`, ma questo servizio non li
calcolava mai — la vista mostrava sempre "Sconosciuta"/nessuna traccia).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, TypedDict

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


class TracciaAudio(TypedDict):
    lingua: str
    codec: str
    canali: int


class InfoTecnica(TypedDict):
    risoluzione: str
    codec_video: str
    codec_audio: str
    larghezza: int
    altezza: int
    etichetta: str
    dimensione_mb: float
    durata_min: float
    bitrate_kbps: int
    fps: float
    contenitore: str
    tracce_audio: list[TracciaAudio]
    tracce_sottotitoli: list[str]


_VUOTO: InfoTecnica = {
    "risoluzione": "",
    "codec_video": "",
    "codec_audio": "",
    "larghezza": 0,
    "altezza": 0,
    "etichetta": "",
    "dimensione_mb": 0.0,
    "durata_min": 0.0,
    "bitrate_kbps": 0,
    "fps": 0.0,
    "contenitore": "",
    "tracce_audio": [],
    "tracce_sottotitoli": [],
}


def _mappa_risoluzione(larghezza: int) -> str:
    for soglia, etichetta in _RISOLUZIONI:
        if larghezza >= soglia:
            return etichetta
    return "SD"


def _mappa_codec(codec: str) -> str:
    return _MAPPA_CODEC.get(codec.lower(), codec.upper())


def _fps_da_frazione(frazione: str) -> float:
    """ffprobe esprime il framerate come frazione testuale ("24000/1001")."""
    try:
        num, _, den = frazione.partition("/")
        den = den or "1"
        return round(int(num) / int(den), 2) if int(den) else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def _esegui_probe(percorso: str) -> dict[str, Any]:
    cmd = [str(_ffprobe_exe), "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", percorso]
    risultato = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return json.loads(risultato.stdout)


def analizza_tecnico(percorso: str, tentativi: int = 3) -> InfoTecnica:
    """Analizza un file con ffprobe. Su percorsi di rete un singolo tentativo
    può fallire per un intoppo transitorio del server/della condivisione
    (verificato: lo stesso file, testato subito dopo isolatamente, risulta
    perfettamente analizzabile) — si ritenta prima di arrendersi."""
    if percorso.lower().startswith("ftp://") or _ffprobe_exe is None:
        return dict(_VUOTO)

    ultimo_errore: Exception | None = None
    for tentativo in range(1, tentativi + 1):
        try:
            info = _esegui_probe(percorso)
            break
        except Exception as e:
            ultimo_errore = e
            if tentativo < tentativi:
                _log.warning(f"ffprobe tentativo {tentativo}/{tentativi} fallito per {percorso}: {e}, ritento...")
                time.sleep(1.5)
    else:
        _log.warning(f"ffprobe fallito dopo {tentativi} tentativi per {percorso}: {ultimo_errore}")
        return dict(_VUOTO)

    try:
        flusso_video = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
        if not flusso_video:
            return dict(_VUOTO)

        flussi_audio = [s for s in info["streams"] if s.get("codec_type") == "audio"]
        flussi_sottotitoli = [s for s in info["streams"] if s.get("codec_type") == "subtitle"]
        formato: dict[str, Any] = info.get("format", {})

        larghezza = int(flusso_video.get("width", 0))
        altezza = int(flusso_video.get("height", 0))
        codec_audio_principale = flussi_audio[0].get("codec_name", "") if flussi_audio else ""

        risoluzione = _mappa_risoluzione(larghezza)
        codec_v = _mappa_codec(flusso_video.get("codec_name", ""))

        dimensione_bytes = int(formato.get("size") or 0) or os.path.getsize(percorso)
        durata_sec = float(formato.get("duration") or 0.0)
        bitrate_bps = int(formato.get("bit_rate") or 0)
        contenitore = (formato.get("format_name", "") or "").split(",")[0]

        tracce_audio: list[TracciaAudio] = [
            {
                "lingua": s.get("tags", {}).get("language", "und"),
                "codec": _mappa_codec(s.get("codec_name", "")),
                "canali": int(s.get("channels", 0)),
            }
            for s in flussi_audio
        ]
        tracce_sottotitoli = [s.get("tags", {}).get("language", "und") for s in flussi_sottotitoli]

        return {
            "risoluzione": risoluzione,
            "codec_video": codec_v,
            "codec_audio": codec_audio_principale.upper(),
            "larghezza": larghezza,
            "altezza": altezza,
            "etichetta": f"{risoluzione} {codec_v}".strip(),
            "dimensione_mb": round(dimensione_bytes / (1024 * 1024), 1),
            "durata_min": round(durata_sec / 60, 1),
            "bitrate_kbps": round(bitrate_bps / 1000),
            "fps": _fps_da_frazione(flusso_video.get("r_frame_rate", "0/1")),
            "contenitore": contenitore.upper(),
            "tracce_audio": tracce_audio,
            "tracce_sottotitoli": tracce_sottotitoli,
        }
    except Exception as e:
        _log.warning(f"ffprobe fallito per {percorso}: {e}")
        return dict(_VUOTO)
