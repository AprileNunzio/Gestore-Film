"""Schermata "Impostazioni": destinazioni della libreria e preferenze per
l'approvazione manuale. Porta gui/schermata_impostazioni.py di Script_Film.

Completa (insieme a percorsi_screen.py) il fix del bug di navigazione
dell'originale: Script_Film mandava l'utente su vai_a(4) ("Pulizia
Archivio") quando le destinazioni non erano configurate, ma solo questa
schermata leggeva/consumava redirect_post_config — quindi il redirect
arrivava nel posto sbagliato. Ora Percorsi naviga qui correttamente, e da
qui, dopo un salvataggio riuscito con redirect_post_config attivo, si torna
a Scansione con la scansione già pronta a partire (stato.scan_da_avviare).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.app_state import AppState
from app.core.config import ConfigManager
from app.ui import theme
from app.ui.effects import applica_ombra_carta
from app.ui.widgets.directory_picker import SelettoreCartella


class ImpostazioniController(QObject):
    avviso = pyqtSignal(str, bool)  # (messaggio, e_errore)
    richiesta_ritorno_scansione = pyqtSignal()

    def __init__(self, stato: AppState, config_manager: ConfigManager) -> None:
        super().__init__()
        self._stato = stato
        self._config = config_manager

    @property
    def stato(self) -> AppState:
        return self._stato

    def salva(
        self,
        film: str,
        serie: str,
        musica: str,
        erotici: str,
        azione: str,
        conflitto: str,
        pulisci_vuote: bool,
    ) -> None:
        film, serie, musica, erotici = film.strip(), serie.strip(), musica.strip(), erotici.strip()

        if not film or not serie or not musica:
            self.avviso.emit("Compila i percorsi principali della libreria prima di salvare.", True)
            return

        self._stato.percorsi["film"] = film
        self._stato.percorsi["serie"] = serie
        self._stato.percorsi["musica"] = musica
        self._stato.percorsi["film_erotici"] = erotici

        self._stato.approvazione_manuale["azione"] = azione
        self._stato.approvazione_manuale["conflitto"] = conflitto
        self._stato.approvazione_manuale["pulisci_vuote"] = pulisci_vuote
        self._stato.automazione["conflitto"] = conflitto

        self._config.salva(
            {
                "destinazioni": self._stato.percorsi,
                "automazione": self._stato.automazione,
                "approvazione_manuale": self._stato.approvazione_manuale,
            }
        )

        self.avviso.emit("Tutte le impostazioni sono state salvate.", False)

        if self._stato.redirect_post_config:
            self._stato.redirect_post_config = False
            self._stato.scan_da_avviare = True
            self.richiesta_ritorno_scansione.emit()


class ImpostazioniView(QWidget):
    def __init__(self, controller: ImpostazioniController, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._controller = controller
        controller.avviso.connect(self._mostra_avviso)
        theme.bus.cambiato.connect(lambda _: self._ridisegna())

        titolo = QLabel("Impostazioni")
        titolo.setObjectName("titoloSchermata")
        sottotitolo = QLabel("Percorsi della libreria e preferenze per l'approvazione manuale")
        sottotitolo.setObjectName("sottotitoloSchermata")

        self._banner = QLabel("⚠ Configura le directory di destinazione per procedere con la scansione.")
        self._banner.setWordWrap(True)
        self._banner.setContentsMargins(12, 8, 12, 8)
        self._banner.setVisible(controller.stato.redirect_post_config)

        percorsi = controller.stato.percorsi

        carta_destinazioni = QFrame()
        carta_destinazioni.setObjectName("cartaContenuto")
        applica_ombra_carta(carta_destinazioni)
        layout_destinazioni = QVBoxLayout(carta_destinazioni)
        layout_destinazioni.setContentsMargins(22, 22, 22, 22)
        layout_destinazioni.setSpacing(12)

        self._etichetta_sezione1 = QLabel("DESTINAZIONI LIBRERIA JELLYFIN")
        layout_destinazioni.addWidget(self._etichetta_sezione1)

        self._sel_film = self._riga_percorso(layout_destinazioni, "Film", percorsi.get("film", ""))
        self._sel_serie = self._riga_percorso(layout_destinazioni, "Serie TV", percorsi.get("serie", ""))
        self._sel_erotici = self._riga_percorso(layout_destinazioni, "Film Erotici (+18)", percorsi.get("film_erotici", ""))
        self._sel_musica = self._riga_percorso(layout_destinazioni, "Musica", percorsi.get("musica", ""))

        manuale = controller.stato.approvazione_manuale

        carta_approvazione = QFrame()
        carta_approvazione.setObjectName("cartaContenuto")
        applica_ombra_carta(carta_approvazione)
        layout_approvazione = QVBoxLayout(carta_approvazione)
        layout_approvazione.setContentsMargins(22, 22, 22, 22)
        layout_approvazione.setSpacing(12)

        self._etichetta_sezione2 = QLabel("GESTIONE APPROVAZIONE MANUALE")
        layout_approvazione.addWidget(self._etichetta_sezione2)

        self._etichetta_azione = QLabel("Azione predefinita dopo approvazione")
        layout_approvazione.addWidget(self._etichetta_azione)
        riga_azione = QHBoxLayout()
        self._gruppo_azione = QButtonGroup(self)
        self._radio_sposta = QRadioButton("Sposta file")
        self._radio_copia = QRadioButton("Copia file")
        for radio, valore in ((self._radio_sposta, "Sposta"), (self._radio_copia, "Copia")):
            self._gruppo_azione.addButton(radio)
            riga_azione.addWidget(radio)
            if manuale.get("azione", "Sposta") == valore:
                radio.setChecked(True)
        riga_azione.addStretch(1)
        layout_approvazione.addLayout(riga_azione)

        self._etichetta_conflitto = QLabel("In caso di file già esistente")
        layout_approvazione.addWidget(self._etichetta_conflitto)
        riga_conflitto = QHBoxLayout()
        self._gruppo_conflitto = QButtonGroup(self)
        self._radio_chiedi = QRadioButton("Chiedi ogni volta")
        self._radio_sovrascrivi = QRadioButton("Sovrascrivi sempre")
        self._radio_salta = QRadioButton("Salta file esistenti")
        for radio, valore in (
            (self._radio_chiedi, "Chiedi"),
            (self._radio_sovrascrivi, "Sovrascrivi"),
            (self._radio_salta, "Salta"),
        ):
            self._gruppo_conflitto.addButton(radio)
            riga_conflitto.addWidget(radio)
            if manuale.get("conflitto", "Salta") == valore:
                radio.setChecked(True)
        riga_conflitto.addStretch(1)
        layout_approvazione.addLayout(riga_conflitto)

        self._checkbox_pulisci = QCheckBox("Elimina cartelle sorgenti se rimangono vuote dopo lo spostamento")
        self._checkbox_pulisci.setChecked(bool(manuale.get("pulisci_vuote", False)))
        layout_approvazione.addWidget(self._checkbox_pulisci)

        self._avviso_label = QLabel()
        self._avviso_label.setWordWrap(True)
        self._avviso_label.setVisible(False)

        self._pulsante_salva = QPushButton("SALVA TUTTE LE IMPOSTAZIONI")
        self._pulsante_salva.setFixedHeight(46)
        self._pulsante_salva.clicked.connect(self._al_click_salva)

        contenuto = QWidget()
        layout_contenuto = QVBoxLayout(contenuto)
        layout_contenuto.setContentsMargins(40, 40, 40, 40)
        layout_contenuto.addWidget(titolo)
        layout_contenuto.addWidget(sottotitolo)
        layout_contenuto.addSpacing(16)
        layout_contenuto.addWidget(self._banner)
        layout_contenuto.addSpacing(8)
        layout_contenuto.addWidget(carta_destinazioni)
        layout_contenuto.addSpacing(16)
        layout_contenuto.addWidget(carta_approvazione)
        layout_contenuto.addSpacing(20)
        layout_contenuto.addWidget(self._avviso_label)
        layout_contenuto.addWidget(self._pulsante_salva)
        layout_contenuto.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(contenuto)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        self._ridisegna()

    def _riga_percorso(self, layout_padre: QVBoxLayout, etichetta_testo: str, valore_iniziale: str) -> SelettoreCartella:
        etichetta = QLabel(etichetta_testo)
        selettore = SelettoreCartella()
        selettore.imposta_percorso(valore_iniziale)
        layout_padre.addWidget(etichetta)
        layout_padre.addWidget(selettore)
        return selettore

    @property
    def controller(self) -> ImpostazioniController:
        return self._controller

    def showEvent(self, event) -> None:  # noqa: N802 (nome imposto da Qt)
        super().showEvent(event)
        self._banner.setVisible(self._controller.stato.redirect_post_config)

    def _ridisegna(self) -> None:
        c = theme.colori_correnti()
        for etichetta in (self._etichetta_sezione1, self._etichetta_sezione2):
            etichetta.setStyleSheet(f"color: {c.accento}; font-weight: 700; font-size: 9.5pt;")
        for etichetta in (self._etichetta_azione, self._etichetta_conflitto):
            etichetta.setStyleSheet(f"color: {c.testo}; font-weight: 600;")
        self._banner.setStyleSheet(
            f"background-color: {c.avviso_sfondo}; color: {c.avviso}; "
            f"border: 1px solid {c.avviso}; border-radius: 10px;"
        )

    def _al_click_salva(self) -> None:
        self._controller.salva(
            film=self._sel_film.percorso(),
            serie=self._sel_serie.percorso(),
            musica=self._sel_musica.percorso(),
            erotici=self._sel_erotici.percorso(),
            azione="Copia" if self._radio_copia.isChecked() else "Sposta",
            conflitto=self._testo_valore_conflitto(),
            pulisci_vuote=self._checkbox_pulisci.isChecked(),
        )

    def _testo_valore_conflitto(self) -> str:
        if self._radio_chiedi.isChecked():
            return "Chiedi"
        if self._radio_sovrascrivi.isChecked():
            return "Sovrascrivi"
        return "Salta"

    def _mostra_avviso(self, messaggio: str, e_errore: bool) -> None:
        c = theme.colori_correnti()
        colore = c.errore if e_errore else c.successo
        self._avviso_label.setStyleSheet(f"color: {colore}; font-weight: 600;")
        self._avviso_label.setText(messaggio)
        self._avviso_label.setVisible(True)


def crea_schermata_impostazioni(stato: AppState, config_manager: ConfigManager) -> ImpostazioniView:
    controller = ImpostazioniController(stato, config_manager)
    return ImpostazioniView(controller)
