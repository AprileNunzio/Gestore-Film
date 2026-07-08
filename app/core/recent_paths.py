"""Persistenza dei percorsi sorgente usati di recente (dati_recenti.json).

Porta _carica_recenti/_salva_recenti/_aggiungi_recente di gui/schermata_io.py
in Script_Film, che duplicavano localmente logica in parte già presente
(in forma diversa) in ConfigManager.
"""
from __future__ import annotations

import json

from app.core.paths import AppPaths

MAX_RECENTI = 5


class RecentPathsStore:
    def __init__(self, paths: AppPaths) -> None:
        self._file = paths.recent_paths_file

    def carica(self) -> list[str]:
        try:
            if self._file.exists():
                dati = json.loads(self._file.read_text(encoding="utf-8"))
                return list(dati.get("sorgenti", []))
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def aggiungi(self, percorso: str) -> list[str]:
        sorgenti = self.carica()
        if percorso in sorgenti:
            sorgenti.remove(percorso)
        sorgenti.insert(0, percorso)
        sorgenti = sorgenti[:MAX_RECENTI]
        self._salva(sorgenti)
        return sorgenti

    def _salva(self, sorgenti: list[str]) -> None:
        try:
            self._file.write_text(
                json.dumps({"sorgenti": sorgenti}, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
