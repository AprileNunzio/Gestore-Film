"""Finestra principale: barra di navigazione laterale + area schermate.

Sostituisce il router vai_a()/NavigationRail di main.py in Script_Film. Le
schermate non ancora portate in questa milestone appaiono come voci di
navigazione disabilitate (schermata=None) invece che mancare del tutto,
cosi' la struttura finale della app è visibile fin da subito.

Si avvia sempre massimizzata (vedi main.py, showMaximized()) e i layout usano
stretch/size policy invece di dimensioni fisse, cosi' l'interfaccia resta
utilizzabile sia su un piccolo laptop sia su un monitor 4K.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme
from app.ui.screen_base import PollableScreen


@dataclass
class VoceNavigazione:
    titolo: str
    schermata: Optional[QWidget]  # None = non ancora implementata in questa milestone
    icona: str = "•"
    abilitata: bool = True


class MainWindow(QMainWindow):
    def __init__(
        self,
        voci: list[VoceNavigazione],
        puo_chiudere: Optional[Callable[[], tuple[bool, str]]] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Gestore Film Portable")
        self.setMinimumSize(1000, 640)
        self._puo_chiudere = puo_chiudere

        pannello_nav = QWidget()
        pannello_nav.setObjectName("barraNavigazione")
        pannello_nav.setFixedWidth(232)
        layout_nav = QVBoxLayout(pannello_nav)
        layout_nav.setContentsMargins(0, 0, 0, 0)
        layout_nav.setSpacing(0)

        intestazione = QLabel("🎬  Gestore Film")
        intestazione.setStyleSheet("font-size: 13pt; font-weight: 700; padding: 18px 16px 12px 16px;")
        layout_nav.addWidget(intestazione)

        self._nav = QListWidget()
        self._nav.setObjectName("listaNavigazione")
        self._nav.setFrameShape(QListWidget.Shape.NoFrame)
        self._stack = QStackedWidget()

        indice_iniziale = 0
        for i, voce in enumerate(voci):
            item = QListWidgetItem(f"{voce.icona}   {voce.titolo}")
            disponibile = voce.abilitata and voce.schermata is not None
            if not disponibile:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            else:
                indice_iniziale = indice_iniziale or i
            self._nav.addItem(item)
            self._stack.addWidget(voce.schermata if voce.schermata is not None else QWidget())

        self._nav.currentRowChanged.connect(self._vai_a)
        layout_nav.addWidget(self._nav, stretch=1)

        self._pulsante_tema = QPushButton()
        self._pulsante_tema.setObjectName("pulsanteSecondario")
        self._pulsante_tema.clicked.connect(self._alterna_tema)
        riga_tema = QHBoxLayout()
        riga_tema.setContentsMargins(12, 12, 12, 12)
        riga_tema.addWidget(self._pulsante_tema)
        layout_nav.addLayout(riga_tema)

        self._aggiorna_etichetta_tema()

        centrale = QWidget()
        layout = QHBoxLayout(centrale)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(pannello_nav)
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

    def _alterna_tema(self) -> None:
        from PyQt6.QtWidgets import QApplication

        nuova_modalita = "dark" if theme.modalita_corrente() == "light" else "light"
        app = QApplication.instance()
        if app is not None:
            theme.applica_tema(app, nuova_modalita)
        self._aggiorna_etichetta_tema()

    def _aggiorna_etichetta_tema(self) -> None:
        if theme.modalita_corrente() == "light":
            self._pulsante_tema.setText("🌙  Tema scuro")
        else:
            self._pulsante_tema.setText("☀️  Tema chiaro")

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
