"""Risoluzione centralizzata di tutti i percorsi su disco usati dall'app.

Mai basato sulla directory di lavoro corrente (os.getcwd()): tutto è ancorato
alla cartella dell'eseguibile (PyInstaller frozen) o del sorgente (dev), cosi'
l'app resta portable indipendentemente da dove/come viene lanciata.
"""
from __future__ import annotations

import sys
from pathlib import Path


class AppPaths:
    """Espone ogni file/cartella persistente dell'app come proprietà, ancorati a base_dir."""

    def __init__(self) -> None:
        if getattr(sys, "frozen", False):
            self.base_dir = Path(sys.executable).resolve().parent
        else:
            self.base_dir = Path(__file__).resolve().parent.parent.parent

    @property
    def settings_file(self) -> Path:
        return self.base_dir / "settings.json"

    @property
    def recent_paths_file(self) -> Path:
        return self.base_dir / "dati_recenti.json"

    @property
    def logs_dir(self) -> Path:
        return self.base_dir / "logs"

    @property
    def error_log_file(self) -> Path:
        return self.base_dir / "error_log.txt"

    @property
    def cache_db_file(self) -> Path:
        return self.base_dir / "cache_elite.db"

    @property
    def registry_db_file(self) -> Path:
        return self.base_dir / "file_registry.db"

    @property
    def env_file(self) -> Path:
        return self.base_dir / ".env"

    @property
    def ffmpeg_dir(self) -> Path:
        return self.base_dir / "ffmpeg" / "bin"

    @property
    def ffmpeg_exe(self) -> Path:
        return self.ffmpeg_dir / "ffmpeg.exe"

    @property
    def ffprobe_exe(self) -> Path:
        return self.ffmpeg_dir / "ffprobe.exe"

    @property
    def fpcalc_exe(self) -> Path:
        return self.ffmpeg_dir / "fpcalc.exe"

    @property
    def resources_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(getattr(sys, "_MEIPASS", self.base_dir)) / "resources"
        return self.base_dir / "resources"
