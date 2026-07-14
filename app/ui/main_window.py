"""Finestra principale: FluentWindow di qfluentwidgets con barra di navigazione
laterale in stile Fluent Design.

Sostituisce la precedente QMainWindow con QListWidget ed emoji come icone di
navigazione (vedi piano di refactoring UI): barra di navigazione, icone
vettoriali ed effetto mica (Windows 11) sono forniti da qfluentwidgets.
Tutte le 9 schermate dell'app sono ormai implementate (vedi main.py), quindi
non serve più il precedente supporto per voci di navigazione "non ancora
portate" (schermata=None, disabilitata).
"""
from __future__ import annotations

from typing import Callable, NamedTuple, Optional

from PyQt6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt
from qfluentwidgets import (
    FluentIcon, FluentWindow, MessageBox, NavigationItemPosition,
    MessageBoxBase, SubtitleLabel, BodyLabel, PushButton, PrimaryPushButton
)

from app.ui.screen_base import PollableScreen

class CloseWarningDialog(MessageBoxBase):
    """Dialog personalizzato con 3 opzioni: Forza Uscita, Tray, Annulla."""
    def __init__(self, parent=None, motivo: str = ""):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("Operazioni in corso")
        self.contentLabel = BodyLabel(f"{motivo}\n\nCosa vuoi fare?")
        
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.contentLabel)

        # Rinominiamo i pulsanti standard e ne aggiungiamo un terzo
        self.yesButton.setText("Forza Uscita")
        self.cancelButton.setText("Annulla")
        
        self.trayButton = PushButton("Continua in Background")
        self.buttonLayout.insertWidget(1, self.trayButton)
        
        self.trayButton.clicked.connect(self._on_tray_clicked)
        self.scelta = "annulla"
        
    def _on_tray_clicked(self):
        self.scelta = "tray"
        self.accept()
        
    def accept(self):
        if self.scelta != "tray":
            self.scelta = "forza_uscita"
        super().accept()
        
    def reject(self):
        self.scelta = "annulla"
        super().reject()



class VoceNavigazione(NamedTuple):
    titolo: str
    schermata: QWidget
    icona: FluentIcon


class MainWindow(FluentWindow):
    def __init__(
        self,
        voci: list[VoceNavigazione],
        puo_chiudere: Optional[Callable[[], tuple[bool, str]]] = None,
        update_service: Optional[object] = None,
    ) -> None:
        super().__init__()
        # L'effetto Mica nativo di Windows 11 delega il disegno dello sfondo
        # al compositor DWM: con il tema scuro il risultato non è affidabile
        # in ogni condizione di rendering (verificato durante lo sviluppo).
        # Uno sfondo scuro pieno, disegnato da Qt stesso, è più prevedibile.
        self.setMicaEffectEnabled(False)
        self.setWindowTitle("Gestore Film Portable")
        self.setMinimumSize(1000, 640)
        self._puo_chiudere = puo_chiudere
        self._update_service = update_service
        self._indice_precedente = -1

        self._setup_tray_icon()

        for voce in voci:
            voce.schermata.setObjectName(voce.titolo.replace(" ", ""))
            self.addSubInterface(voce.schermata, voce.icona, voce.titolo, position=NavigationItemPosition.SCROLL)

        # Barra di navigazione responsive: collassa a sole icone sotto i 900px
        # di larghezza finestra, invece di restare fissa a larghezza intera.
        self.navigationInterface.setCollapsible(True)
        self.navigationInterface.setMinimumExpandWidth(900)

        self.stackedWidget.currentChanged.connect(self._al_cambio_schermata)
        self._al_cambio_schermata(self.stackedWidget.currentIndex())

        if self._update_service:
            self._update_service.aggiornamento_disponibile.connect(self._al_aggiornamento_disponibile)
            self._update_service.progresso_download.connect(self._al_progresso_download)
            self._update_service.download_completato.connect(self._al_download_completato)
            self._update_service.errore.connect(self._al_errore_update)
            self._update_service.controlla_aggiornamenti()

    def vai_a_indice(self, indice: int) -> None:
        self.stackedWidget.setCurrentIndex(indice)

    def _al_cambio_schermata(self, indice: int) -> None:
        if self._indice_precedente >= 0:
            precedente = self.stackedWidget.widget(self._indice_precedente)
            if isinstance(precedente, PollableScreen):
                precedente.stop_polling()

        nuova = self.stackedWidget.widget(indice)
        if isinstance(nuova, PollableScreen):
            nuova.start_polling()

        self._indice_precedente = indice

    def _setup_tray_icon(self) -> None:
        self.tray_icon = QSystemTrayIcon(self)
        if self.windowIcon().isNull():
            self.tray_icon.setIcon(FluentIcon.MOVIE.icon())
        else:
            self.tray_icon.setIcon(self.windowIcon())
            
        self.tray_menu = QMenu(self)
        
        mostra_action = QAction("Mostra Gestore Film", self)
        mostra_action.triggered.connect(self._mostra_da_tray)
        
        esci_action = QAction("Esci", self)
        esci_action.triggered.connect(QApplication.instance().quit)
        
        self.tray_menu.addAction(mostra_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(esci_action)
        
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._su_tray_attivata)
        
    def _mostra_da_tray(self):
        self.show()
        self.activateWindow()
        self.tray_icon.hide()

    def _su_tray_attivata(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._mostra_da_tray()

    def closeEvent(self, event) -> None:  # noqa: N802 (nome imposto da Qt)
        if self._puo_chiudere:
            ok, motivo = self._puo_chiudere()
            if not ok:
                conferma = CloseWarningDialog(self, motivo)
                if conferma.exec():
                    if conferma.scelta == "forza_uscita":
                        event.accept()
                        QApplication.instance().quit()
                    elif conferma.scelta == "tray":
                        event.ignore()
                        self.hide()
                        self.tray_icon.show()
                        self.tray_icon.showMessage(
                            "Esecuzione in background",
                            "L'applicazione continua le operazioni in background.",
                            QSystemTrayIcon.MessageIcon.Information,
                            2000
                        )
                    return
                else:
                    event.ignore()
                    return
        event.accept()
        QApplication.instance().quit()

    def _al_aggiornamento_disponibile(self, versione: str, changelog: str) -> None:
        conferma = MessageBox(
            "Aggiornamento disponibile",
            f"È disponibile la nuova versione {versione}!\n\nVuoi scaricarla e installarla ora?\n\nChangelog:\n{changelog[:200]}...",
            self,
        )
        conferma.yesButton.setText("Scarica e installa")
        conferma.cancelButton.setText("Non ora")
        if conferma.exec():
            self._finestra_progresso = MessageBox("Scaricamento...", "Download in corso: 0%", self)
            self._finestra_progresso.hideCancelButton()
            self._finestra_progresso.yesButton.hide()
            self._finestra_progresso.show()
            self._update_service.scarica_aggiornamento()

    def _al_progresso_download(self, percent: int) -> None:
        if hasattr(self, "_finestra_progresso"):
            self._finestra_progresso.contentLabel.setText(f"Download in corso: {percent}%")

    def _al_download_completato(self, file_path: str) -> None:
        if hasattr(self, "_finestra_progresso"):
            self._finestra_progresso.accept()
        info = MessageBox(
            "Download completato",
            "L'applicazione verrà ora riavviata per applicare l'aggiornamento.",
            self,
        )
        info.hideCancelButton()
        info.exec()
        self._update_service.applica_aggiornamento(file_path)

    def _al_errore_update(self, errore: str) -> None:
        if hasattr(self, "_finestra_progresso"):
            self._finestra_progresso.accept()
        avviso = MessageBox("Errore aggiornamento", f"Si è verificato un errore:\n{errore}", self)
        avviso.hideCancelButton()
        avviso.exec()
