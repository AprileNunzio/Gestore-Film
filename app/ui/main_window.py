"""Finestra principale: barra di navigazione laterale + area schermate.

Sostituisce il router vai_a()/NavigationRail di main.py in Script_Film. Le
schermate non ancora portate in questa milestone appaiono come voci di
navigazione disabilitate (schermata=None) invece che mancare del tutto,
cosi' la struttura finale della app è visibile fin da subito.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QStackedWidget, QWidget

from app.ui.screen_base import PollableScreen


@dataclass
class VoceNavigazione:
    titolo: str
    schermata: Optional[QWidget]  # None = non ancora implementata in questa milestone
    abilitata: bool = True


class MainWindow(QMainWindow):
    def __init__(
        self,
        voci: list[VoceNavigazione],
        puo_chiudere: Optional[Callable[[], tuple[bool, str]]] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Gestore Film Portable")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)
        self._puo_chiudere = puo_chiudere

        self._nav = QListWidget()
        self._nav.setObjectName("barraNavigazione")
        self._nav.setFixedWidth(220)
        self._stack = QStackedWidget()

        indice_iniziale = 0
        for i, voce in enumerate(voci):
            item = QListWidgetItem(voce.titolo)
            disponibile = voce.abilitata and voce.schermata is not None
            if not disponibile:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            else:
                indice_iniziale = indice_iniziale or i
            self._nav.addItem(item)
            self._stack.addWidget(voce.schermata if voce.schermata is not None else QWidget())

        self._nav.currentRowChanged.connect(self._vai_a)

        centrale = QWidget()
        layout = QHBoxLayout(centrale)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._nav)
        layout.addWidget(self._stack, stretch=1)
        self.setCentralWidget(centrale)

        self._nav.setCurrentRow(indice_iniziale)

    def vai_a_indice(self, indice: int) -> None:
        self._nav.setCurrentRow(indice)

    def _vai_a(self, indice: int) -> None:
        if indice < 0:
            return
        precedente = self._stack.currentWidget()
        if isinstance(precedente, PollableScreen):
            precedente.stop_polling()

        self._stack.setCurrentIndex(indice)

        nuova = self._stack.currentWidget()
        if isinstance(nuova, PollableScreen):
            nuova.start_polling()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (nome imposto da Qt)
        if self._puo_chiudere:
            ok, motivo = self._puo_chiudere()
            if not ok:
                risposta = QMessageBox.question(
                    self,
                    "Operazioni in corso",
                    f"{motivo}\n\nChiudere comunque l'applicazione?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if risposta != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
        event.accept()
