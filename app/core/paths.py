"""Risoluzione centralizzata di tutti i percorsi su disco usati dall'app.

`base_dir` (cartella dell'eseguibile in build PyInstaller, radice del
sorgente in sviluppo) resta la sede dei soli asset **portati con l'app**
(ffmpeg/bin, resources) e del `.env` di sviluppo — mai basato sulla
directory di lavoro corrente (os.getcwd()).

I **dati dell'utente** (config, cache, log, database, chiavi API) vivono
invece in `dati_dir`, dentro `%APPDATA%\\NunzioTech\\GestoreFilmPortable`:
cosi' sopravvivono a un aggiornamento dell'eseguibile (nuovo download, nuova
cartella, nuovo nome file) invece di richiedere di riconfigurare tutto ad
ogni versione — il prezzo e' che l'app non e' piu' "senza traccia" sul
sistema: disinstallarla del tutto richiede anche di cancellare quella
cartella a mano.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


class AppPaths:
    """Espone ogni file/cartella persistente dell'app come proprietà."""

    def __init__(self) -> None:
        if getattr(sys, "frozen", False):
            self.base_dir = Path(sys.executable).resolve().parent
        else:
            self.base_dir = Path(__file__).resolve().parent.parent.parent

        appdata = os.getenv("APPDATA")
        self.dati_dir = Path(appdata) / "NunzioTech" / "GestoreFilmPortable" if appdata else self.base_dir
        self.dati_dir.mkdir(parents=True, exist_ok=True)

    @property
    def settings_file(self) -> Path:
        return self.dati_dir / "settings.json"

    @property
    def recent_paths_file(self) -> Path:
        return self.dati_dir / "dati_recenti.json"

    @property
    def logs_dir(self) -> Path:
        return self.dati_dir / "logs"

    @property
    def error_log_file(self) -> Path:
        return self.dati_dir / "error_log.txt"

    @property
    def cache_db_file(self) -> Path:
        return self.dati_dir / "cache_elite.db"

    @property
    def registry_db_file(self) -> Path:
        return self.dati_dir / "file_registry.db"

    @property
    def env_file(self) -> Path:
        return self.base_dir / ".env"

    @property
    def ffmpeg_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(getattr(sys, "_MEIPASS", self.base_dir)) / "ffmpeg" / "bin"
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
