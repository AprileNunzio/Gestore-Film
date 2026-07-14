"""Card statistica riusabile: titolo + barra di progresso opzionale + info.

Prima di questo componente, `dashboard_screen.py` costruiva a mano lo stesso
identico pattern due volte (`_crea_card_disco` per Film e Serie) — l'esempio
di duplicazione citato nel piano di refactoring UI.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CardWidget, FluentIconBase, IconWidget, ProgressBar, StrongBodyLabel

from app.ui.design_tokens import SPAZIATURA


class SchedaStatistica(CardWidget):
    def __init__(
        self,
        titolo: str,
        colore: str = "#8F87E8",
        icona: Optional[FluentIconBase] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._colore = colore

        self._lbl_titolo = StrongBodyLabel(titolo, self)
        self._lbl_titolo.setStyleSheet(f"color: {colore};")
        self._progresso = ProgressBar(self)
        self._progresso.setFixedHeight(6)
        self._progresso.setCustomBarColor(colore, colore)
        self._lbl_info = BodyLabel("—", self)

        riga_titolo = QHBoxLayout()
        riga_titolo.setSpacing(SPAZIATURA.xs)
        if icona is not None:
            icona_widget = IconWidget(icona.colored(colore, colore), self)
            icona_widget.setFixedSize(18, 18)
            riga_titolo.addWidget(icona_widget)
        riga_titolo.addWidget(self._lbl_titolo)
        riga_titolo.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPAZIATURA.lg, SPAZIATURA.lg, SPAZIATURA.lg, SPAZIATURA.lg)
        layout.setSpacing(SPAZIATURA.xs)
        layout.addLayout(riga_titolo)
        layout.addWidget(self._progresso)
        layout.addWidget(self._lbl_info)

    def imposta_valore(self, percentuale: int, info: str) -> None:
        self._progresso.setValue(percentuale)
        self._lbl_info.setText(info)

    def imposta_titolo(self, titolo: str) -> None:
        self._lbl_titolo.setText(titolo)
