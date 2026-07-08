"""Schermata "Scansione": dashboard live di indicizzazione/identificazione/trasferimento.

Porta gui/schermata_dashboard.py di Script_Film in stile MVC. È la parte più
delicata della migrazione: l'originale (Flet) mutava liberamente lo stato UI
da thread di background e da callback dei worker (`page.update()` è
thread-safe in Flet). In PyQt6 questo NON è sicuro: ogni aggiornamento che
tocca il QAbstractTableModel o altri widget deve arrivare sul thread GUI.

Qui questo è garantito strutturalmente: ScansioneController è un QObject
creato sul thread GUI, e *tutti* i punti che nell'originale mutavano lo stato
da un thread di lavoro (worker di coda_analisi/coda_io, thread di
enumerazione file, thread di watchdog, thread di attesa-arresto) qui si
limitano a: (a) chiamare metodi thread-safe come CodaLavori.aggiungi_operazione,
oppure (b) fare .emit() su un segnale Qt il cui slot connesso è un bound
method di un QObject sul thread GUI — la combinazione che garantisce a Qt di
marshalare automaticamente la consegna sul thread giusto (vedi anche
app/services/job_queue.py per lo stesso pattern).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.core.app_state import AppState
from app.ui import theme
from app.organizers.universale import OrganizzatoreUniversale
from app.services.job_queue import CodaLavori, EventoCoda, RisultatoJob
from app.services.watchdog_service import SorveglianteDirectory
from app.ui.effects import applica_ombra_carta
from app.ui.screen_base import PollableScreen

_log = logging.getLogger("gestore_film.principale")

# Colori categorici della barra di distribuzione film/serie/musica: restano fissi
# tra i due temi (non sono colori semantici di stato, servono solo a distinguere
# visivamente le categorie in modo stabile).
_MAPPA_COLORI_CANALE = {"film": "#7C5CBF", "serie": "#5B35A8", "musica": "#12A484", "misto": "#8A8A94"}


def _analizza_job(organizzatore: OrganizzatoreUniversale, info: dict[str, Any], usa_ai: bool) -> dict[str, Any]:
    """Eseguito su un worker thread di coda_analisi: pura logica, nessun accesso alla UI."""
    return organizzatore.analizza_file(info, usa_ai=usa_ai)


@dataclass
class PipelineStats:
    indicizzati: int = 0
    identificati: int = 0
    revisione: int = 0
    in_coda: int = 0
    in_trasferimento: int = 0
    archiviati: int = 0
    audit_ok: int = 0
    anomalie: int = 0


@dataclass
class CanaleStats:
    trovati: int = 0
    riconosciuti: int = 0
    non_riconosciuti: int = 0


class ModelloCodaElaborazione(QAbstractTableModel):
    COLONNE = ["Stato", "Nome originale", "Nuovo nome", "Tipo", "Confidenza"]

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._righe: list[dict[str, Any]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._righe)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.COLONNE)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.COLONNE[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        el = self._righe[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return el.get("status", "")
            if col == 1:
                return el.get("nome", "")
            if col == 2:
                return el.get("nuovo_nome", "—")
            if col == 3:
                return str(el.get("tipo", "—")).upper()
            if col == 4:
                return f"{int(el.get('conf', 0.0) * 100)}%"
        if role == Qt.ItemDataRole.ToolTipRole and col == 0:
            return el.get("errore") or None
        return None

    def aggiungi(self, elemento: dict[str, Any]) -> int:
        indice = len(self._righe)
        self.beginInsertRows(QModelIndex(), indice, indice)
        self._righe.append(elemento)
        self.endInsertRows()
        return indice

    def aggiorna(self, indice: int, campi: dict[str, Any]) -> None:
        if not (0 <= indice < len(self._righe)):
            return
        self._righe[indice].update(campi)
        self.dataChanged.emit(self.index(indice, 0), self.index(indice, self.columnCount() - 1))

    def svuota(self) -> None:
        self.beginResetModel()
        self._righe.clear()
        self.endResetModel()


class _TransferBridge(QObject):
    """QObject dedicato solo a marshalare in sicurezza i callback di sposta_file sul thread GUI."""

    progresso_io = pyqtSignal(dict, dict)
    conflitto_richiesto = pyqtSignal(dict, dict)


class ScansioneController(QObject):
    log_emesso = pyqtSignal(str)
    statistiche_cambiate = pyqtSignal()
    scansione_avviata = pyqtSignal()
    scansione_fermata = pyqtSignal()

    _richiesta_stato_fermo = pyqtSignal()

    def __init__(self, stato: AppState, coda_analisi: CodaLavori, coda_io: CodaLavori) -> None:
        super().__init__()
        self._stato = stato
        self._coda_analisi = coda_analisi
        self._coda_io = coda_io
        self._bridge = _TransferBridge()

        self._modello = ModelloCodaElaborazione()
        self._pipeline = PipelineStats()
        self._canali: dict[str, CanaleStats] = {"film": CanaleStats(), "serie": CanaleStats(), "musica": CanaleStats()}
        self._righe_per_nome: dict[str, int] = {}
        self._trasferimenti_attivi: set[str] = set()
        self._progresso_corrente: Optional[dict[str, Any]] = None

        self._organizzatore: Optional[OrganizzatoreUniversale] = None
        self._watchdog: Optional[SorveglianteDirectory] = None
        self._interrompi = False
        self._scansione_in_corso = False

        self._coda_analisi.evento.connect(self._al_evento_analisi)
        self._coda_io.evento.connect(self._al_evento_trasferimento)
        self._bridge.progresso_io.connect(self._al_progresso_io)
        self._bridge.conflitto_richiesto.connect(self._al_conflitto)
        self._richiesta_stato_fermo.connect(self._al_scansione_fermata)

    @property
    def stato(self) -> AppState:
        return self._stato

    @property
    def modello(self) -> ModelloCodaElaborazione:
        return self._modello

    @property
    def pipeline(self) -> PipelineStats:
        return self._pipeline

    @property
    def canali(self) -> dict[str, CanaleStats]:
        return self._canali

    @property
    def scansione_in_corso(self) -> bool:
        return self._scansione_in_corso

    @property
    def in_arresto(self) -> bool:
        return self._interrompi and self._scansione_in_corso

    @property
    def progresso_trasferimento_corrente(self) -> Optional[dict[str, Any]]:
        return self._progresso_corrente

    @property
    def totale_risultati(self) -> int:
        return len(self._stato.risultati)

    def avvia_o_ferma(self) -> None:
        if self._scansione_in_corso:
            self.ferma_scansione()
        else:
            self.avvia_scansione()

    def avvia_scansione(self) -> None:
        sorgente = self._stato.sorgente
        if not sorgente:
            self.log_emesso.emit("Nessuna sorgente selezionata: torna alla schermata Percorsi.")
            return

        config_org = {
            "automazione": self._stato.automazione,
            "approvazione_manuale": self._stato.approvazione_manuale,
            "destinazioni": self._stato.percorsi,
        }
        self._organizzatore = OrganizzatoreUniversale(config=config_org)
        self._organizzatore.imposta_callback_log(self.log_emesso.emit)

        self._stato.risultati = []
        self._modello.svuota()
        self._pipeline = PipelineStats()
        self._canali = {"film": CanaleStats(), "serie": CanaleStats(), "musica": CanaleStats()}
        self._righe_per_nome.clear()
        self._trasferimenti_attivi.clear()
        self._progresso_corrente = None
        self._interrompi = False
        self._scansione_in_corso = True
        self.scansione_avviata.emit()
        self.statistiche_cambiate.emit()

        try:
            self._watchdog = SorveglianteDirectory(sorgente, self._al_file_watchdog)
            self._watchdog.avvia()
        except Exception as e:
            self.log_emesso.emit(f"Attenzione: watchdog non avviato: {e}")
            self._watchdog = None

        threading.Thread(target=self._job_scansione, args=(sorgente,), daemon=True).start()

    def ferma_scansione(self) -> None:
        self.log_emesso.emit("Richiesta interruzione scansione inviata...")
        self._interrompi = True

        if self._watchdog:
            try:
                self._watchdog.ferma()
            except Exception:
                pass

        self._coda_analisi.svuota()
        threading.Thread(target=self._attendi_arresto, daemon=True).start()

    def _attendi_arresto(self) -> None:
        while self._coda_analisi.operazioni_attive > 0:
            time.sleep(0.5)
        self._richiesta_stato_fermo.emit()

    def _job_scansione(self, sorgente: str) -> None:
        assert self._organizzatore is not None
        for info in self._organizzatore.scansiona_directory(sorgente):
            if self._interrompi:
                break
            self._coda_analisi.aggiungi_operazione(
                _analizza_job, self._organizzatore, info, self._stato.automazione.get("usa_ai_scansione", False),
                descrizione=f"Analisi {info['nome']}", info_file=info,
            )
        if not self._interrompi:
            self._richiesta_stato_fermo.emit()

    def _al_scansione_fermata(self) -> None:
        self._scansione_in_corso = False
        self._interrompi = False
        self._watchdog = None
        self.log_emesso.emit("Scansione completata/interrotta. Sistema pronto.")
        self.scansione_fermata.emit()
        self.statistiche_cambiate.emit()

    def _al_file_watchdog(self, percorso_nuovo: str) -> None:
        info_file = {
            "nome": os.path.basename(percorso_nuovo),
            "percorso": percorso_nuovo,
            "estensione": os.path.splitext(percorso_nuovo)[1].lower(),
        }
        self.log_emesso.emit(f"Watchdog elabora: {percorso_nuovo}")
        self._coda_analisi.aggiungi_operazione(
            _analizza_job, self._organizzatore, info_file, self._stato.automazione.get("usa_ai_scansione", False),
            descrizione=f"Analisi {info_file['nome']}", info_file=info_file,
        )

    def _aggiorna_riga(self, nome: str, **campi: Any) -> None:
        indice = self._righe_per_nome.get(nome)
        if indice is not None:
            self._modello.aggiorna(indice, campi)

    def _al_evento_analisi(self, evento: EventoCoda) -> None:
        nome = evento.info_file.get("nome", "")
        if evento.azione == "aggiunto":
            self._pipeline.indicizzati += 1
            self._righe_per_nome[nome] = self._modello.aggiungi(
                {"nome": nome, "status": "In attesa", "conf": 0.0, "tipo": "—", "nuovo_nome": "—"}
            )
            self.statistiche_cambiate.emit()
        elif evento.azione == "inizio":
            self._aggiorna_riga(nome, status="Analisi")
        elif evento.azione == "fine" and evento.risultato is not None:
            self._gestisci_fine_analisi(nome, evento.risultato)

    def _gestisci_fine_analisi(self, nome: str, risultato: RisultatoJob) -> None:
        self._pipeline.identificati += 1

        if not risultato.successo:
            self._pipeline.anomalie += 1
            self._aggiorna_riga(nome, status="Anomalia", errore=risultato.errore)
            self.log_emesso.emit(f"Anomalia su {nome}: {risultato.errore}")
            self.statistiche_cambiate.emit()
            return

        r = risultato.valore
        self._stato.risultati.append(r)

        tipo = r.get("tipo_media", "film")
        if tipo not in self._canali:
            tipo = "film"
        canale = self._canali[tipo]
        canale.trovati += 1
        conf = r.get("confidenza", 0.0)
        nuovo_nome = r.get("nome_jellyfin", {}).get("nome_file", "—")

        if "Duplicato" in r.get("status", "") or "presente" in r.get("status", "").lower():
            self._aggiorna_riga(nome, status="Saltato (Esistente)", conf=conf, tipo=tipo, nuovo_nome=nuovo_nome)
            self.log_emesso.emit(f"Saltato (duplicato): {nome}")
            self.statistiche_cambiate.emit()
            return

        auto = self._stato.automazione
        soglia_auto = auto.get("soglia", 0.85)
        if conf >= soglia_auto:
            canale.riconosciuti += 1
        else:
            canale.non_riconosciuti += 1

        if auto.get("attiva") and conf >= soglia_auto:
            dest = self._stato.percorsi.get(tipo)
            if dest:
                azione_nome = auto.get("azione", "Sposta")
                self._pipeline.in_coda += 1
                self._aggiorna_riga(nome, status=f"In Ingestion ({azione_nome})", conf=conf, tipo=tipo, nuovo_nome=nuovo_nome)
                self._coda_io.aggiungi_operazione(
                    self._organizzatore.sposta_file,
                    r, dest, azione_nome, auto.get("pulisci_vuote", True),
                    self._bridge.progresso_io.emit, self._bridge.conflitto_richiesto.emit,
                    descrizione=f"{azione_nome} {nome}", info_file={"nome": nome},
                )
            else:
                self._pipeline.revisione += 1
                self._aggiorna_riga(nome, status="In Revisione", conf=conf, tipo=tipo, nuovo_nome=nuovo_nome)
                self.log_emesso.emit(f"Destinazione {tipo} non configurata per: {nome}")
        else:
            self._pipeline.revisione += 1
            self._aggiorna_riga(nome, status="In Revisione", conf=conf, tipo=tipo, nuovo_nome=nuovo_nome)
            self.log_emesso.emit(f"Revisione manuale: {nome} (Conf: {int(conf * 100)}%)")

        self.statistiche_cambiate.emit()

    def _al_evento_trasferimento(self, evento: EventoCoda) -> None:
        if evento.azione == "inizio":
            self.log_emesso.emit(f"[IO] Inizio: {evento.descrizione}")
        elif evento.azione == "fine" and evento.risultato is not None and not evento.risultato.successo:
            self.log_emesso.emit(f"[IO] Errore: {evento.risultato.errore}")

    def _al_progresso_io(self, r: dict[str, Any], p: dict[str, Any]) -> None:
        nome = r.get("file_originale", "")
        if nome not in self._trasferimenti_attivi:
            self._trasferimenti_attivi.add(nome)
            self._pipeline.in_coda = max(0, self._pipeline.in_coda - 1)
            self._pipeline.in_trasferimento += 1

        percentuale = p.get("percentuale", 0.0)
        self._progresso_corrente = {
            "nome": nome,
            "percentuale": percentuale,
            "velocita": p.get("velocita", 0.0),
            "etr": p.get("etr", 0.0),
        }
        self._aggiorna_riga(nome, status=f"IO ({int(percentuale * 100)}%)")

        if percentuale >= 1.0:
            self._trasferimenti_attivi.discard(nome)
            self._pipeline.in_trasferimento = max(0, self._pipeline.in_trasferimento - 1)
            self._pipeline.archiviati += 1
            self._pipeline.audit_ok += 1
            self._aggiorna_riga(nome, status="Archiviato")
            self._progresso_corrente = None
            self.log_emesso.emit(f"Archiviato: {nome}")

        self.statistiche_cambiate.emit()

    def _al_conflitto(self, r: dict[str, Any], dettagli: dict[str, Any]) -> None:
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Risoluzione conflitto")
        box.setText(f"File già presente: {os.path.basename(dettagli['percorso_destinazione'])}")
        box.setInformativeText(
            f"Motivo: {dettagli['motivo']}\n"
            f"Sorgente: {dettagli['dim_sorg_mb']} MB — Destinazione: {dettagli['dim_dest_mb']} MB"
        )
        salta_btn = box.addButton("Salta (mantieni esistente)", QMessageBox.ButtonRole.RejectRole)
        box.addButton("Sovrascrivi", QMessageBox.ButtonRole.DestructiveRole)
        box.exec()
        scelta = "salta" if box.clickedButton() is salta_btn else "sovrascrivi"
        if self._organizzatore:
            self._organizzatore.risolvi_conflitto(scelta)


class _BarraDistribuzione(QWidget):
    """Barra proporzionale film/serie/musica/misto, dipinta manualmente (nessun equivalente nativo in Flet)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(16)
        self.setMaximumHeight(16)
        self._segmenti: list[tuple[int, QColor]] = []

    def imposta_dati(self, segmenti: list[tuple[int, QColor]]) -> None:
        self._segmenti = segmenti
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = self.rect()
        totale = sum(q for q, _ in self._segmenti) or 1
        x = rect.x()
        for quantita, colore in self._segmenti:
            larghezza = int(rect.width() * quantita / totale)
            painter.fillRect(x, rect.y(), larghezza, rect.height(), colore)
            x += larghezza
        painter.end()


class ScansioneView(PollableScreen):
    def __init__(self, controller: ScansioneController, parent: Optional[QWidget] = None) -> None:
        super().__init__(intervallo_ms=500, parent=parent)
        self._controller = controller
        controller.log_emesso.connect(self._aggiungi_log)
        controller.scansione_avviata.connect(self._al_avvio)
        controller.scansione_fermata.connect(self._al_arresto)
        theme.bus.cambiato.connect(lambda _: self._ridisegna_colori())

        titolo = QLabel("Scansione")
        titolo.setObjectName("titoloSchermata")
        sottotitolo = QLabel("Indicizzazione, identificazione e ingestion dei file sorgente")
        sottotitolo.setObjectName("sottotitoloSchermata")

        self._pulsante_avvia = QPushButton("AVVIA INDICIZZAZIONE")
        self._pulsante_avvia.setFixedHeight(42)
        self._pulsante_avvia.clicked.connect(controller.avvia_o_ferma)

        intestazione = QHBoxLayout()
        blocco_titolo = QVBoxLayout()
        blocco_titolo.addWidget(titolo)
        blocco_titolo.addWidget(sottotitolo)
        intestazione.addLayout(blocco_titolo)
        intestazione.addStretch(1)
        intestazione.addWidget(self._pulsante_avvia)

        self._etichette_kpi: dict[str, QLabel] = {}
        self._etichette_kpi_titolo: list[QLabel] = []
        griglia_kpi = QGridLayout()
        griglia_kpi.setSpacing(12)
        colonne_griglia = 4
        for i, (chiave, titolo_kpi) in enumerate(
            [
                ("indicizzati", "Indicizzati"),
                ("identificati", "Identificati"),
                ("revisione", "In revisione"),
                ("in_coda", "In coda"),
                ("in_trasferimento", "In trasferimento"),
                ("archiviati", "Archiviati"),
                ("anomalie", "Anomalie"),
            ]
        ):
            carta = QFrame()
            carta.setObjectName("cartaContenuto")
            applica_ombra_carta(carta)
            carta.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            layout_carta = QVBoxLayout(carta)
            layout_carta.setContentsMargins(16, 14, 16, 14)
            layout_carta.setSpacing(6)
            etichetta_titolo = QLabel(titolo_kpi.upper())
            valore = QLabel("0")
            layout_carta.addWidget(etichetta_titolo)
            layout_carta.addWidget(valore)
            self._etichette_kpi[chiave] = valore
            self._etichette_kpi_titolo.append(etichetta_titolo)
            griglia_kpi.addWidget(carta, i // colonne_griglia, i % colonne_griglia)

        self._barra_distribuzione = _BarraDistribuzione()
        self._legenda_distribuzione = QLabel()

        carta_distribuzione = QFrame()
        carta_distribuzione.setObjectName("cartaContenuto")
        applica_ombra_carta(carta_distribuzione)
        layout_distribuzione = QVBoxLayout(carta_distribuzione)
        layout_distribuzione.setContentsMargins(18, 16, 18, 16)
        layout_distribuzione.setSpacing(8)
        layout_distribuzione.addWidget(QLabel("Distribuzione per tipo"))
        layout_distribuzione.addWidget(self._barra_distribuzione)
        layout_distribuzione.addWidget(self._legenda_distribuzione)

        self._tabella = QTableView()
        self._tabella.setModel(controller.modello)
        self._tabella.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._tabella.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._tabella.verticalHeader().setVisible(False)
        self._tabella.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._tabella.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._tabella.setAlternatingRowColors(True)
        applica_ombra_carta(self._tabella)
        controller.modello.rowsInserted.connect(lambda *_: self._tabella.scrollToBottom())
        controller.modello.rowsInserted.connect(lambda *_: self._aggiorna_stato_vuoto())
        controller.modello.modelReset.connect(self._aggiorna_stato_vuoto)

        self._placeholder_coda = QLabel(
            "Nessun file in coda.\nPremi «Avvia indicizzazione» per popolare questa vista."
        )
        self._placeholder_coda.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder_coda.setWordWrap(True)

        self._stack_coda = QStackedWidget()
        self._stack_coda.addWidget(self._tabella)
        self._stack_coda.addWidget(self._placeholder_coda)
        self._stack_coda.setCurrentWidget(self._placeholder_coda)

        etichetta_coda = QLabel("Coda elaborazione live")
        etichetta_coda.setStyleSheet("font-weight: 700;")
        colonna_centrale = QVBoxLayout()
        colonna_centrale.addWidget(etichetta_coda)
        colonna_centrale.addWidget(self._stack_coda, stretch=1)

        etichetta_log = QLabel("Log sistema")
        etichetta_log.setStyleSheet("font-weight: 700;")
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(300)
        self._log.setPlaceholderText("I log della scansione appariranno qui...")
        self._log.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        applica_ombra_carta(self._log)

        colonna_destra = QVBoxLayout()
        colonna_destra.addWidget(etichetta_log)
        colonna_destra.addWidget(self._log, stretch=1)

        contenuto_log = QWidget()
        contenuto_log.setLayout(colonna_destra)
        contenuto_log.setFixedWidth(300)

        riga_centrale = QHBoxLayout()
        riga_centrale.addLayout(colonna_centrale, stretch=1)
        riga_centrale.addWidget(contenuto_log)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.addLayout(intestazione)
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

    def _ridisegna_colori(self) -> None:
        c = theme.colori_correnti()
        for etichetta in self._etichette_kpi_titolo:
            etichetta.setStyleSheet(f"color: {c.testo_secondario}; font-size: 8pt; font-weight: 600;")
        for valore in self._etichette_kpi.values():
            valore.setStyleSheet(f"color: {c.testo}; font-size: 18pt; font-weight: 900;")
        self._legenda_distribuzione.setStyleSheet(f"color: {c.testo_secondario}; font-size: 9pt;")
        self._placeholder_coda.setStyleSheet(f"color: {c.testo_secondario}; font-size: 10.5pt;")
        if self._controller.scansione_in_corso:
            self._pulsante_avvia.setStyleSheet(f"background-color: {c.errore};")
        else:
            self._pulsante_avvia.setStyleSheet(f"background-color: {c.successo};")

    def _aggiorna_stato_vuoto(self) -> None:
        vuota = self._controller.modello.rowCount() == 0
        self._stack_coda.setCurrentWidget(self._placeholder_coda if vuota else self._tabella)

    def _al_avvio(self) -> None:
        self._pulsante_avvia.setText("INTERROMPI SCANSIONE")
        self._ridisegna_colori()

    def _al_arresto(self) -> None:
        self._pulsante_avvia.setText("AVVIA INDICIZZAZIONE")
        self._ridisegna_colori()

    def _al_tick(self) -> None:
        self._aggiorna_kpi()
        if self._controller.in_arresto:
            self._pulsante_avvia.setText("ARRESTO IN CORSO...")
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


def crea_schermata_scansione(stato: AppState, coda_analisi: CodaLavori, coda_io: CodaLavori) -> ScansioneView:
    controller = ScansioneController(stato, coda_analisi, coda_io)
    return ScansioneView(controller)
