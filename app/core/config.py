"""Impostazioni utente persistenti (settings.json) e costanti applicative.

Porta config.py + config_manager.py di Script_Film, ancorati ad AppPaths
invece che a os.path.dirname(__file__)/cwd.
"""
from __future__ import annotations

import json
import os
from typing import Any

from app.core.paths import AppPaths

ESTENSIONI_VIDEO = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v", ".flv"}
ESTENSIONI_AUDIO = {".mp3", ".flac", ".aac", ".ogg", ".wav", ".m4a", ".opus"}

TMDB_BASE_URL = "https://api.themoviedb.org/3"

COLORE_PRIMARIO = "#5B35A8"
COLORE_SECONDARIO = "#7C5CBF"
COLORE_SFONDO = "#F4F2F8"
COLORE_SUPERFICIE = "#FFFFFF"
COLORE_TESTO = "#1C1B1F"
COLORE_TESTO_SEC = "#49454F"
COLORE_BORDO = "#D0CCE0"
COLORE_SUCCESS = "#1B7A4E"
COLORE_WARNING = "#B45309"
COLORE_ERROR = "#B91C1C"

_DESTINAZIONI_DEFAULT = {"film": "", "serie": "", "musica": "", "film_erotici": ""}
_AUTOMAZIONE_DEFAULT = {
    "attiva": False,
    "usa_ai_scansione": False,
    "soglia": 0.8,
    "azione": "Sposta",
    "pulisci_vuote": False,
    "conflitto": "Salta",
    "genera_trickplay_automaticamente": False,
}
_APPROVAZIONE_MANUALE_DEFAULT = {"azione": "Sposta", "pulisci_vuote": False, "conflitto": "Salta"}


def normalizza_percorso(base: str, *parti: str) -> str:
    """Unisce un percorso base con dei segmenti, gestendo sia path locali che ftp://."""
    if not base:
        return ""
    if base.startswith("ftp://"):
        risultato = base.rstrip("/")
        for parte in parti:
            if parte:
                risultato += "/" + str(parte).replace("\\", "/").strip("/")
        return risultato
    return os.path.join(base, *parti)


class ConfigManager:
    """Persiste le impostazioni utente in settings.json, ancorato ad AppPaths."""

    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths

    def carica(self) -> dict[str, Any]:
        default: dict[str, Any] = {
            "destinazioni": dict(_DESTINAZIONI_DEFAULT),
            "automazione": dict(_AUTOMAZIONE_DEFAULT),
            "approvazione_manuale": dict(_APPROVAZIONE_MANUALE_DEFAULT),
        }
        try:
            if self._paths.settings_file.exists():
                dati = json.loads(self._paths.settings_file.read_text(encoding="utf-8"))
                for chiave, valore in default.items():
                    if chiave in dati:
                        if isinstance(valore, dict):
                            valore.update(dati[chiave])
                        else:
                            default[chiave] = dati[chiave]
        except (OSError, json.JSONDecodeError):
            pass
        return default

    def salva(self, impostazioni: dict[str, Any]) -> None:
        self._paths.settings_file.write_text(
            json.dumps(impostazioni, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def destinazioni_configurate(self) -> bool:
        dest = self.carica().get("destinazioni", {})
        return bool(dest.get("film") and dest.get("serie") and dest.get("musica"))

    def dimensione_cache_mb(self) -> float:
        totale = 0.0
        for percorso in (self._paths.cache_db_file, self._paths.registry_db_file):
            if percorso.exists():
                totale += percorso.stat().st_size / (1024 * 1024)
        return round(totale, 2)

    def dimensione_log_mb(self) -> float:
        totale = 0.0
        if self._paths.logs_dir.is_dir():
            for f in self._paths.logs_dir.iterdir():
                if f.is_file():
                    totale += f.stat().st_size / (1024 * 1024)
        return round(totale, 2)

    def numero_recenti(self) -> int:
        try:
            if self._paths.recent_paths_file.exists():
                dati = json.loads(self._paths.recent_paths_file.read_text(encoding="utf-8"))
                return len(dati.get("sorgenti", []))
        except (OSError, json.JSONDecodeError):
            pass
        return 0

    def svuota_cache(self) -> bool:
        try:
            for percorso in (self._paths.cache_db_file, self._paths.registry_db_file):
                percorso.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def svuota_log(self) -> bool:
        try:
            if self._paths.logs_dir.is_dir():
                for f in self._paths.logs_dir.iterdir():
                    if f.is_file():
                        try:
                            f.unlink()
                        except OSError:
                            f.write_text("", encoding="utf-8")
            return True
        except OSError:
            return False

    def svuota_recenti(self) -> bool:
        try:
            self._paths.recent_paths_file.write_text(
                json.dumps({"sorgenti": [], "destinazioni": []}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True
        except OSError:
            return False

    def ultimo_percorso_usato(self) -> str:
        try:
            if self._paths.recent_paths_file.exists():
                dati = json.loads(self._paths.recent_paths_file.read_text(encoding="utf-8"))
                sorgenti = dati.get("sorgenti", [])
                if sorgenti:
                    return sorgenti[0]
        except (OSError, json.JSONDecodeError):
            pass
        return ""
