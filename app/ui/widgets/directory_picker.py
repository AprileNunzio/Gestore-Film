"""Riga riusabile per selezionare una cartella: campo testo + pulsante Sfoglia.

Sostituisce i molti ft.FilePicker duplicati per ogni singola destinazione in
Script_Film (10 istanze totali fra le varie schermate, ognuna con la propria
coroutine async get_directory_path()) con un widget sincrono unico.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget


class SelettoreCartella(QWidget):
    percorso_cambiato = pyqtSignal(str)

    def __init__(self, etichetta_pulsante: str = "Sfoglia...", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._campo = QLineEdit()
        self._pulsante = QPushButton(etichetta_pulsante)
        self._pulsante.clicked.connect(self._scegli)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._campo, stretch=1)
        layout.addWidget(self._pulsante)

        self._campo.textChanged.connect(self.percorso_cambiato)

    def percorso(self) -> str:
        return self._campo.text().strip()

    def imposta_percorso(self, percorso: str) -> None:
        self._campo.setText(percorso)

    def _scegli(self) -> None:
        cartella = QFileDialog.getExistingDirectory(self, "Seleziona cartella", self.percorso() or "")
        if cartella:
            self.imposta_percorso(cartella)
