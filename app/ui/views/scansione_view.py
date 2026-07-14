import time
from typing import Optional
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import CardWidget, CaptionLabel, FluentIcon, PlainTextEdit, PrimaryPushButton, StrongBodyLabel, TableView

from app.ui import theme
from app.ui.components.intestazione_schermata import IntestazioneSchermata
from app.ui.design_tokens import RAGGIO, SPAZIATURA, TIPOGRAFIA
from app.ui.screen_base import PollableScreen
from app.controllers.scansione_controller import ScansioneController
from app.ui.components.barra_distribuzione import BarraDistribuzione

_MAPPA_COLORI_CANALE = {"film": "#9F97F5", "serie": "#7F77DD", "musica": "#5DCAA5", "misto": "#8A8A94"}

_KPI = [
    ("indicizzati", "Indicizzati", "#378ADD"),
    ("identificati", "Identificati", "#7F77DD"),
    ("revisione", "In revisione", "#D4537E"),
    ("in_coda", "In coda", "#EF9F27"),
    ("in_trasferimento", "In trasferimento", "#5DCAA5"),
    ("archiviati", "Archiviati", "#97C459"),
    ("anomalie", "Anomalie", None),  # None = usa il token 'errore' del tema corrente
]


class ScansioneView(PollableScreen):
    def __init__(self, controller: ScansioneController, parent: Optional[QWidget] = None) -> None:
        super().__init__(intervallo_ms=500, parent=parent)
        self._controller = controller
        controller.log_emesso.connect(self._aggiungi_log)
        controller.scansione_avviata.connect(self._al_avvio)
        controller.scansione_fermata.connect(self._al_arresto)
        theme.bus.cambiato.connect(lambda _: self._ridisegna_colori())

        intestazione = IntestazioneSchermata("Scansione", "Indicizzazione, identificazione e ingestion dei file sorgente")

        self._pulsante_avvia = PrimaryPushButton(FluentIcon.PLAY, "Avvia indicizzazione")
        self._pulsante_avvia.setFixedHeight(44)
        self._pulsante_avvia.clicked.connect(controller.avvia_o_ferma)
        self._pulsante_avvia_stylesheet_base = self._pulsante_avvia.styleSheet()

        riga_intestazione = QHBoxLayout()
        riga_intestazione.addWidget(intestazione)
        riga_intestazione.addStretch(1)
        riga_intestazione.addWidget(self._pulsante_avvia, 0, Qt.AlignmentFlag.AlignBottom)

        self._etichette_kpi: dict[str, StrongBodyLabel] = {}
        self._etichette_kpi_titolo: list[CaptionLabel] = []
        griglia_kpi = QGridLayout()
        griglia_kpi.setSpacing(SPAZIATURA.md)
        colonne_griglia = 4
        for i, (chiave, titolo_kpi, colore) in enumerate(_KPI):
            colore = colore or theme.colori_correnti().errore
            carta = CardWidget()
            carta.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            layout_carta = QVBoxLayout(carta)
            layout_carta.setContentsMargins(SPAZIATURA.md, SPAZIATURA.sm, SPAZIATURA.md, SPAZIATURA.sm)
            layout_carta.setSpacing(SPAZIATURA.xxs)
            etichetta_titolo = CaptionLabel(titolo_kpi.upper())
            valore = StrongBodyLabel("0")
            valore.setStyleSheet(f"color: {colore};")
            layout_carta.addWidget(etichetta_titolo)
            layout_carta.addWidget(valore)
            self._etichette_kpi[chiave] = valore
            self._etichette_kpi_titolo.append(etichetta_titolo)
            griglia_kpi.addWidget(carta, i // colonne_griglia, i % colonne_griglia)

        self._barra_distribuzione = BarraDistribuzione()
        self._legenda_distribuzione = CaptionLabel()

        carta_distribuzione = CardWidget()
        layout_distribuzione = QVBoxLayout(carta_distribuzione)
        layout_distribuzione.setContentsMargins(SPAZIATURA.lg, SPAZIATURA.md, SPAZIATURA.lg, SPAZIATURA.md)
        layout_distribuzione.setSpacing(SPAZIATURA.sm)
        layout_distribuzione.addWidget(StrongBodyLabel("Distribuzione per tipo"))
        layout_distribuzione.addWidget(self._barra_distribuzione)
        layout_distribuzione.addWidget(self._legenda_distribuzione)

        self._tabella = TableView()
        self._tabella.setModel(controller.modello)
        self._tabella.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._tabella.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._tabella.verticalHeader().setVisible(False)
        self._tabella.setEditTriggers(TableView.EditTrigger.NoEditTriggers)
        self._tabella.setSelectionBehavior(TableView.SelectionBehavior.SelectRows)
        self._tabella.setAlternatingRowColors(True)

        self._timer_scroll = QTimer(self)
        self._timer_scroll.setSingleShot(True)
        self._timer_scroll.setInterval(100)
        self._timer_scroll.timeout.connect(self._tabella.scrollToBottom)

        controller.modello.rowsInserted.connect(self._richiedi_scroll)
        controller.modello.rowsInserted.connect(self._aggiorna_stato_vuoto)
        controller.modello.modelReset.connect(self._aggiorna_stato_vuoto)

        self._placeholder_coda = CaptionLabel(
            "Nessun file in coda.\nPremi «Avvia indicizzazione» per popolare questa vista."
        )
        self._placeholder_coda.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder_coda.setWordWrap(True)

        self._stack_coda = QStackedWidget()
        self._stack_coda.addWidget(self._tabella)
        self._stack_coda.addWidget(self._placeholder_coda)
        self._stack_coda.setCurrentWidget(self._placeholder_coda)

        colonna_centrale = QVBoxLayout()
        colonna_centrale.setSpacing(SPAZIATURA.sm)
        colonna_centrale.addWidget(StrongBodyLabel("Coda elaborazione live"))
        colonna_centrale.addWidget(self._stack_coda, stretch=1)

        self._log = PlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(300)
        self._log.setPlaceholderText("I log della scansione appariranno qui...")
        self._log.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._log.setStyleSheet(f"font-family: 'Consolas', 'Courier New', monospace; font-size: {TIPOGRAFIA.didascalia.dimensione_pt}pt;")

        colonna_destra = QVBoxLayout()
        colonna_destra.setSpacing(SPAZIATURA.sm)
        colonna_destra.addWidget(StrongBodyLabel("Log sistema"))
        colonna_destra.addWidget(self._log, stretch=1)

        contenuto_log = QWidget()
        contenuto_log.setLayout(colonna_destra)
        contenuto_log.setFixedWidth(360)

        riga_centrale = QHBoxLayout()
        riga_centrale.setSpacing(SPAZIATURA.lg)
        riga_centrale.addLayout(colonna_centrale, stretch=1)
        riga_centrale.addWidget(contenuto_log)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl)
        layout.setSpacing(SPAZIATURA.lg)
        layout.addLayout(riga_intestazione)
        layout.addLayout(griglia_kpi)
        layout.addWidget(carta_distribuzione)
        layout.addLayout(riga_centrale, stretch=1)

        self._aggiorna_kpi()
        self._ridisegna_colori()

    @property
    def controller(self) -> ScansioneController:
        return self._controller

    def _aggiungi_log(self, messaggio: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self._log.appendPlainText(f"[{ts}] {messaggio}")

    def _richiedi_scroll(self) -> None:
        if not self._timer_scroll.isActive():
            self._timer_scroll.start()

    def _ridisegna_colori(self) -> None:
        c = theme.colori_correnti()
        self._legenda_distribuzione.setStyleSheet(f"color: {c.testo_secondario};")
        self._placeholder_coda.setStyleSheet(f"color: {c.testo_secondario};")
        colore = c.errore if self._controller.scansione_in_corso else c.successo
        self._pulsante_avvia.setStyleSheet(
            self._pulsante_avvia_stylesheet_base + f"PrimaryPushButton {{ background-color: {colore}; }}"
        )

    def _aggiorna_stato_vuoto(self) -> None:
        vuota = self._controller.modello.rowCount() == 0
        self._stack_coda.setCurrentWidget(self._placeholder_coda if vuota else self._tabella)

    def _al_avvio(self) -> None:
        self._pulsante_avvia.setText("Interrompi scansione")
        self._pulsante_avvia.setIcon(FluentIcon.PAUSE)
        self._ridisegna_colori()

    def _al_arresto(self) -> None:
        self._pulsante_avvia.setText("Avvia indicizzazione")
        self._pulsante_avvia.setIcon(FluentIcon.PLAY)
        self._ridisegna_colori()

    def _al_tick(self) -> None:
        self._aggiorna_kpi()
        if self._controller.in_arresto:
            self._pulsante_avvia.setText("Arresto in corso...")
            self._pulsante_avvia.setEnabled(False)
        elif not self._controller.scansione_in_corso:
            self._pulsante_avvia.setEnabled(True)

    def _aggiorna_kpi(self) -> None:
        pip = self._controller.pipeline
        self._etichette_kpi["indicizzati"].setText(str(pip.indicizzati))
        self._etichette_kpi["identificati"].setText(str(pip.identificati))
        self._etichette_kpi["revisione"].setText(str(pip.revisione))
        self._etichette_kpi["in_coda"].setText(str(pip.in_coda))
        self._etichette_kpi["in_trasferimento"].setText(str(pip.in_trasferimento))
        self._etichette_kpi["archiviati"].setText(str(pip.archiviati))
        self._etichette_kpi["anomalie"].setText(str(pip.anomalie))

        canali = self._controller.canali
        totale_canali = sum(c.trovati for c in canali.values())
        misto = max(0, self._controller.totale_risultati - totale_canali)
        conteggio = {"film": canali["film"].trovati, "serie": canali["serie"].trovati, "musica": canali["musica"].trovati, "misto": misto}
        totale = sum(conteggio.values())

        if totale > 0:
            segmenti = [(qta, QColor(_MAPPA_COLORI_CANALE[tipo])) for tipo, qta in conteggio.items() if qta > 0]
            self._barra_distribuzione.imposta_dati(segmenti)
            self._legenda_distribuzione.setText(
                "  ·  ".join(f"{tipo.upper()}: {qta} ({int(qta / totale * 100)}%)" for tipo, qta in conteggio.items() if qta > 0)
            )
        else:
            self._barra_distribuzione.imposta_dati([(1, QColor(theme.colori_correnti().bordo))])
            self._legenda_distribuzione.setText("In attesa di scansione...")


def crea_schermata_scansione(stato, coda_analisi, coda_io) -> ScansioneView:
    controller = ScansioneController(stato, coda_analisi, coda_io)
    return ScansioneView(controller)
