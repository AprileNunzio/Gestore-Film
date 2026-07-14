"""Intestazione titolo+sottotitolo riusabile per ogni schermata.

Prima di questo componente, ogni schermata ricostruiva la stessa coppia di
QLabel con lo stesso object name (`titoloSchermata`/`sottotitoloSchermata`) a
mano — vedi diagnosi nel piano di refactoring UI.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, TitleLabel

from app.ui import theme


class IntestazioneSchermata(QWidget):
    def __init__(self, titolo: str, sottotitolo: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lbl_titolo = TitleLabel(titolo, self)
        self._lbl_sottotitolo = CaptionLabel(sottotitolo, self)
        self._lbl_sottotitolo.setVisible(bool(sottotitolo))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._lbl_titolo)
        layout.addWidget(self._lbl_sottotitolo)

        self._ridisegna()
        theme.bus.cambiato.connect(lambda _: self._ridisegna())

    def imposta_sottotitolo(self, testo: str) -> None:
        self._lbl_sottotitolo.setText(testo)
        self._lbl_sottotitolo.setVisible(bool(testo))

    def _ridisegna(self) -> None:
        c = theme.colori_correnti()
        self._lbl_sottotitolo.setStyleSheet(f"color: {c.testo_secondario};")
