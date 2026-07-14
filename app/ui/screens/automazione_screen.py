"""Schermata Automazione Intelligente.

Porta gui/schermata_automazione.py in stile MVC PyQt6.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    CardWidget,
    CheckBox,
    ComboBox,
    FluentIcon,
    PrimaryPushButton,
    RadioButton,
    ScrollArea,
    Slider,
    StrongBodyLabel,
)

from app.core.app_state import AppState
from app.core.config import ConfigManager
from app.ui.components.banner_avviso import BannerAvviso, Severita
from app.ui.components.intestazione_schermata import IntestazioneSchermata
from app.ui.design_tokens import CATEGORIA, SPAZIATURA
from app.ui.widgets.directory_picker import SelettoreCartella


class AutomazioneController(QObject):
    avviso = pyqtSignal(str, bool)

    def __init__(self, stato: AppState, config_manager: ConfigManager) -> None:
        super().__init__()
        self._stato = stato
        self._config = config_manager

    @property
    def stato(self) -> AppState:
        return self._stato

    def salva(
        self,
        attiva: bool,
        usa_ai_scansione: bool,
        genera_trickplay: bool,
        soglia: float,
        azione: str,
        pulisci_vuote: bool,
        risoluzione_minima_attiva: bool,
        risoluzione_minima_valore: str,
        film: str,
        serie: str,
        erotici: str,
        musica: str,
    ) -> None:
        auto = self._stato.automazione
        auto["attiva"] = attiva
        auto["usa_ai_scansione"] = usa_ai_scansione
        auto["genera_trickplay_automaticamente"] = genera_trickplay
        auto["soglia"] = soglia
        auto["azione"] = azione
        auto["pulisci_vuote"] = pulisci_vuote
        auto["risoluzione_minima_attiva"] = risoluzione_minima_attiva
        auto["risoluzione_minima_valore"] = risoluzione_minima_valore

        perc = self._stato.percorsi
        perc["film"] = film.strip()
        perc["serie"] = serie.strip()
        perc["film_erotici"] = erotici.strip()
        perc["musica"] = musica.strip()

        self._config.salva(
            {
                "destinazioni": perc,
                "automazione": auto,
                "approvazione_manuale": self._stato.approvazione_manuale,
            }
        )

        self.avviso.emit("Configurazioni automazione salvate con successo!", False)


class AutomazioneView(QWidget):
    def __init__(self, controller: AutomazioneController, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._controller = controller
        controller.avviso.connect(self._mostra_avviso)

        intestazione = IntestazioneSchermata(
            "Automazione Intelligente", "Configura le regole per l'elaborazione autonoma senza approvazione manuale"
        )

        auto = controller.stato.automazione

        # --- Sezione regole generali ---
        carta_regole = CardWidget()
        layout_regole = QVBoxLayout(carta_regole)
        layout_regole.setContentsMargins(SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl)
        layout_regole.setSpacing(SPAZIATURA.md)

        layout_regole.addWidget(self._etichetta_sezione("REGOLE GENERALI", CATEGORIA.automazione))

        self._cb_attiva = CheckBox("Abilita elaborazione automatica (Sposta/Copia autonomo)")
        self._cb_attiva.setChecked(auto.get("attiva", False))
        layout_regole.addWidget(self._cb_attiva)

        self._cb_ai_scan = CheckBox("Usa l'Intelligenza Artificiale durante la scansione")
        self._cb_ai_scan.setChecked(auto.get("usa_ai_scansione", False))
        layout_regole.addWidget(self._cb_ai_scan)

        self._cb_trickplay = CheckBox("Genera automaticamente Trickplay a spostamento completato")
        self._cb_trickplay.setChecked(auto.get("genera_trickplay_automaticamente", False))
        layout_regole.addWidget(self._cb_trickplay)

        # Slider soglia
        layout_regole.addWidget(StrongBodyLabel("Accuratezza minima richiesta (solo i file con punteggio superiore verranno processati)"))

        lay_slider = QHBoxLayout()
        lay_slider.setSpacing(SPAZIATURA.md)
        self._slider_soglia = Slider(Qt.Orientation.Horizontal)
        self._slider_soglia.setMinimum(50)
        self._slider_soglia.setMaximum(100)
        self._slider_soglia.setValue(int(auto.get("soglia", 0.9) * 100))
        self._lbl_val_soglia = StrongBodyLabel(f"{self._slider_soglia.value()}%")
        self._slider_soglia.valueChanged.connect(lambda v: self._lbl_val_soglia.setText(f"{v}%"))
        lay_slider.addWidget(self._slider_soglia)
        lay_slider.addWidget(self._lbl_val_soglia)
        layout_regole.addLayout(lay_slider)

        # Azione
        layout_regole.addWidget(StrongBodyLabel("Metodo di gestione file"))

        riga_azione = QHBoxLayout()
        riga_azione.setSpacing(SPAZIATURA.md)
        self._gruppo_azione = QButtonGroup(self)
        self._radio_sposta = RadioButton("Sposta file (Consigliato)")
        self._radio_copia = RadioButton("Copia file (Mantieni originale)")
        for radio, valore in ((self._radio_sposta, "Sposta"), (self._radio_copia, "Copia")):
            self._gruppo_azione.addButton(radio)
            riga_azione.addWidget(radio)
            if auto.get("azione", "Sposta") == valore:
                radio.setChecked(True)
        riga_azione.addStretch(1)
        layout_regole.addLayout(riga_azione)

        self._cb_pulisci = CheckBox("Elimina cartelle sorgenti se rimangono vuote")
        self._cb_pulisci.setChecked(auto.get("pulisci_vuote", False))
        layout_regole.addWidget(self._cb_pulisci)

        # Risoluzione minima (vale sia per l'elaborazione automatica sia per l'approvazione manuale)
        self._cb_risoluzione_minima = CheckBox(
            "Escludi film sotto una risoluzione minima (automatica e approvazione manuale)"
        )
        self._cb_risoluzione_minima.setChecked(auto.get("risoluzione_minima_attiva", False))
        layout_regole.addWidget(self._cb_risoluzione_minima)

        lay_risoluzione = QHBoxLayout()
        lay_risoluzione.setSpacing(SPAZIATURA.md)
        lay_risoluzione.addWidget(StrongBodyLabel("Risoluzione minima richiesta:"))
        self._combo_risoluzione_minima = ComboBox()
        self._combo_risoluzione_minima.addItems(["480p", "720p", "1080p", "2160p"])
        self._combo_risoluzione_minima.setCurrentText(auto.get("risoluzione_minima_valore", "720p"))
        lay_risoluzione.addWidget(self._combo_risoluzione_minima)
        lay_risoluzione.addStretch(1)
        layout_regole.addLayout(lay_risoluzione)

        # --- Sezione destinazioni ---
        percorsi = controller.stato.percorsi
        carta_dest = CardWidget()
        layout_dest = QVBoxLayout(carta_dest)
        layout_dest.setContentsMargins(SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl)
        layout_dest.setSpacing(SPAZIATURA.md)

        layout_dest.addWidget(self._etichetta_sezione("DESTINAZIONI DIFFERENZIATE", CATEGORIA.scansione))

        self._sel_film = self._riga_percorso(layout_dest, "Film", percorsi.get("film", ""))
        self._sel_serie = self._riga_percorso(layout_dest, "Serie TV", percorsi.get("serie", ""))
        self._sel_erotici = self._riga_percorso(layout_dest, "Film Erotici (+18)", percorsi.get("film_erotici", ""))
        self._sel_musica = self._riga_percorso(layout_dest, "Musica", percorsi.get("musica", ""))

        self._banner_esito = BannerAvviso()
        self._banner_esito.setVisible(False)

        self._pulsante_salva = PrimaryPushButton(FluentIcon.SAVE, "Salva configurazioni")
        self._pulsante_salva.setFixedHeight(44)
        self._pulsante_salva.clicked.connect(self._al_click_salva)

        contenuto = QWidget()
        layout_contenuto = QVBoxLayout(contenuto)
        layout_contenuto.setContentsMargins(SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl)
        layout_contenuto.setSpacing(SPAZIATURA.lg)
        layout_contenuto.addWidget(intestazione)
        layout_contenuto.addWidget(carta_regole)
        layout_contenuto.addWidget(carta_dest)
        layout_contenuto.addWidget(self._banner_esito)
        layout_contenuto.addWidget(self._pulsante_salva, alignment=Qt.AlignmentFlag.AlignRight)
        layout_contenuto.addStretch(1)

        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(contenuto)
        scroll.enableTransparentBackground()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    @staticmethod
    def _etichetta_sezione(testo: str, colore: str) -> StrongBodyLabel:
        etichetta = StrongBodyLabel(testo)
        etichetta.setStyleSheet(f"color: {colore};")
        return etichetta

    def _riga_percorso(self, layout_padre: QVBoxLayout, etichetta_testo: str, valore_iniziale: str) -> SelettoreCartella:
        layout_padre.addWidget(StrongBodyLabel(etichetta_testo))
        selettore = SelettoreCartella()
        selettore.imposta_percorso(valore_iniziale)
        layout_padre.addWidget(selettore)
        return selettore

    def _al_click_salva(self) -> None:
        self._controller.salva(
            attiva=self._cb_attiva.isChecked(),
            usa_ai_scansione=self._cb_ai_scan.isChecked(),
            genera_trickplay=self._cb_trickplay.isChecked(),
            soglia=self._slider_soglia.value() / 100.0,
            azione="Copia" if self._radio_copia.isChecked() else "Sposta",
            pulisci_vuote=self._cb_pulisci.isChecked(),
            risoluzione_minima_attiva=self._cb_risoluzione_minima.isChecked(),
            risoluzione_minima_valore=self._combo_risoluzione_minima.currentText(),
            film=self._sel_film.percorso(),
            serie=self._sel_serie.percorso(),
            erotici=self._sel_erotici.percorso(),
            musica=self._sel_musica.percorso(),
        )

    def _mostra_avviso(self, messaggio: str, e_errore: bool) -> None:
        self._banner_esito.imposta_testo(messaggio, Severita.ERRORE if e_errore else Severita.SUCCESSO)
        self._banner_esito.setVisible(True)


def crea_schermata_automazione(stato: AppState, config_manager: ConfigManager) -> AutomazioneView:
    controller = AutomazioneController(stato, config_manager)
    return AutomazioneView(controller)
