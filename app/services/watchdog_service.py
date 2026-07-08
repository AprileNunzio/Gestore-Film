"""Monitoraggio filesystem in tempo reale per l'ingest continuo. Porta servizio_watchdog.py.

Fix rispetto all'originale: le estensioni monitorate ora derivano da
app.core.config.ESTENSIONI_VIDEO/ESTENSIONI_AUDIO invece di essere duplicate
in una lista hardcoded (che poteva andare fuori sincrono con config.py).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.core.config import ESTENSIONI_AUDIO, ESTENSIONI_VIDEO

_log = logging.getLogger("gestore_film.principale")

_ESTENSIONI_MONITORATE = ESTENSIONI_VIDEO | ESTENSIONI_AUDIO


class _Handler(FileSystemEventHandler):
    def __init__(self, callback_file: Callable[[str], None]) -> None:
        super().__init__()
        self.callback_file = callback_file
        self.in_elaborazione: set[str] = set()
        self._lock = threading.Lock()

    def on_created(self, event) -> None:
        if not event.is_directory:
            self._processa(event.src_path)

    def on_moved(self, event) -> None:
        if not event.is_directory:
            self._processa(event.dest_path)

    def _processa(self, percorso: str) -> None:
        with self._lock:
            if percorso in self.in_elaborazione:
                return
            self.in_elaborazione.add(percorso)

        estensione = os.path.splitext(percorso)[1].lower()
        if estensione in _ESTENSIONI_MONITORATE:
            threading.Thread(target=self._debounce_file, args=(percorso,), daemon=True).start()
        else:
            with self._lock:
                self.in_elaborazione.discard(percorso)

    def _debounce_file(self, percorso: str) -> None:
        """Attende che la dimensione del file si stabilizzi (fine copia) prima di notificare."""
        try:
            dim_precedente = -1
            while True:
                if not os.path.exists(percorso):
                    return

                dim_attuale = os.path.getsize(percorso)
                if dim_attuale == dim_precedente and dim_attuale > 0:
                    try:
                        with open(percorso, "ab"):
                            pass
                        _log.info(f"Watchdog trigger: {percorso} PRONTO")
                        self.callback_file(percorso)
                        break
                    except (IOError, PermissionError):
                        pass

                dim_precedente = dim_attuale
                time.sleep(3)
        finally:
            with self._lock:
                self.in_elaborazione.discard(percorso)


class SorveglianteDirectory:
    def __init__(self, directory: str, callback_elaborazione: Callable[[str], None]) -> None:
        self.directory = directory
        self.callback = callback_elaborazione
        self.observer: Optional[Observer] = None

    def avvia(self) -> None:
        if not self.directory or not os.path.exists(self.directory):
            _log.error("Watchdog fallito: directory sorgente non valida")
            return

        if self.observer:
            self.ferma()

        handler = _Handler(self.callback)
        self.observer = Observer()
        self.observer.schedule(handler, self.directory, recursive=True)
        self.observer.start()
        _log.info(f"Sorvegliante attivato su: {self.directory}")

    def ferma(self) -> None:
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            _log.info("Sorvegliante fermato")
