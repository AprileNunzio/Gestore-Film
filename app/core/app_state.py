"""Stato condiviso tra le schermate, versione tipizzata dello `stato: dict`
passato per riferimento a ogni schermata in main.py di Script_Film. In questa
milestone contiene solo i campi usati da Percorsi e Scansione; verrà esteso
mano a mano che le altre schermate vengono portate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppState:
    sorgente: str = ""
    percorsi: dict[str, str] = field(
        default_factory=lambda: {"film": "", "serie": "", "musica": "", "film_erotici": ""}
    )
    automazione: dict[str, Any] = field(default_factory=dict)
    approvazione_manuale: dict[str, Any] = field(default_factory=dict)
    scan_da_avviare: bool = False
    risultati: list[dict[str, Any]] = field(default_factory=list)
    redirect_post_config: bool = False
