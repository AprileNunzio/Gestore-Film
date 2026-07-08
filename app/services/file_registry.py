"""Registro SQLite dei file già copiati (dedup via hash). Porta servizio_io.RegistroFile.

Fix di portabilità: il costruttore richiede un db_path esplicito (Path), invece
del default relativo bare "file_registry.db" dell'originale.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path

_log = logging.getLogger("gestore_film.principale")


class RegistroFile:
    """Database SQLite per impedire la copia di duplicati (tramite hash veloce)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._inizializza_db()

    def _inizializza_db(self) -> None:
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("PRAGMA journal_mode=WAL;")
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS file_registry (
                            hash_file TEXT PRIMARY KEY,
                            tmdb_id INTEGER,
                            param_qualita TEXT,
                            timestamp REAL
                        )
                        """
                    )
            except sqlite3.Error as e:
                _log.error(f"Errore DB RegistroFile: {e}")

    def controlla_esistenza(self, hash_file: str) -> bool:
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT tmdb_id FROM file_registry WHERE hash_file=?", (hash_file,))
                    return cur.fetchone() is not None
            except sqlite3.Error:
                return False

    def registra_file(self, hash_file: str, tmdb_id: int, param_qualita: str) -> None:
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO file_registry "
                        "(hash_file, tmdb_id, param_qualita, timestamp) VALUES (?, ?, ?, ?)",
                        (hash_file, tmdb_id, param_qualita, time.time()),
                    )
            except sqlite3.Error:
                pass
