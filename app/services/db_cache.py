"""Cache SQLite delle risposte TMDB. Porta servizio_tmdb.DatabaseCache di Script_Film.

Fix di portabilità: il costruttore richiede un db_path esplicito (Path), invece
del default relativo bare "cache_elite.db" dell'originale (che dipendeva dalla
cwd del processo).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_log = logging.getLogger("gestore_film.principale")


class DatabaseCache:
    """Cache con TTL per le risposte dell'API TMDB, thread-safe (usata da molti worker)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._inizializza_db()

    def _inizializza_db(self) -> None:
        with self._lock:
            self._inizializza_db_nolock()

    def _inizializza_db_nolock(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS api_cache (
                        hash_query TEXT PRIMARY KEY,
                        endpoint TEXT,
                        json_response TEXT,
                        timestamp REAL,
                        ttl INTEGER
                    )
                    """
                )
        except sqlite3.Error as e:
            _log.error(f"Errore inizializzazione db cache: {e}")

    def leggi_cache(self, hash_query: str) -> dict[str, Any] | None:
        with self._lock:
            try:
                self._inizializza_db_nolock()
                with sqlite3.connect(self.db_path) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT json_response, timestamp, ttl FROM api_cache WHERE hash_query=?",
                        (hash_query,),
                    )
                    row = cur.fetchone()
                    if row:
                        j_resp, ts, ttl = row
                        if time.time() < ts + ttl:
                            return json.loads(j_resp)
                        conn.execute("DELETE FROM api_cache WHERE hash_query=?", (hash_query,))
            except (sqlite3.Error, json.JSONDecodeError) as e:
                _log.error(f"Errore lettura cache: {e}")
            return None

    def scrivi_cache(self, hash_query: str, endpoint: str, dati: dict[str, Any], ttl: int) -> None:
        with self._lock:
            try:
                self._inizializza_db_nolock()
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO api_cache "
                        "(hash_query, endpoint, json_response, timestamp, ttl) VALUES (?, ?, ?, ?, ?)",
                        (hash_query, endpoint, json.dumps(dati), time.time(), ttl),
                    )
            except sqlite3.Error as e:
                _log.error(f"Errore scrittura cache: {e}")

    def svuota(self) -> None:
        with self._lock:
            try:
                self._inizializza_db_nolock()
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("DELETE FROM api_cache")
                    conn.execute("VACUUM")
            except sqlite3.Error as e:
                _log.error(f"Errore svuotamento cache: {e}")

    def dimensione_mb(self) -> float:
        try:
            path = Path(self.db_path)
            if path.exists():
                return round(path.stat().st_size / (1024 * 1024), 2)
        except OSError:
            pass
        return 0.0
