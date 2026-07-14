"""Schermata Code: Monitoraggio in stile Torrent/eMule delle code di analisi e I/O.

Porta gui/schermata_code.py in stile MVC PyQt6.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QListWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import CardWidget, CaptionLabel, FluentIcon, IconWidget, ListWidget, ProgressBar, StrongBodyLabel

from app.core.app_state import AppState
from app.services.job_queue import CodaLavori, EventoCoda
from app.ui import theme
from app.ui.components.intestazione_schermata import IntestazioneSchermata
from app.ui.design_tokens import CATEGORIA, SPAZIATURA
from app.ui.screen_base import PollableScreen

_log = logging.getLogger("gestore_film.code")


@dataclass
class JobInCoda:
    nome: str
    stato: str
    tipo: str = "—"
    progresso: float = 0.0
    errore: str = ""
    completato: bool = False


class CodeController(QObject):
    jobs_analisi_cambiati = pyqtSignal()
    jobs_io_cambiati = pyqtSignal()

    def __init__(self, stato: AppState, coda_analisi: CodaLavori, coda_io: CodaLavori) -> None:
        super().__init__()
        self._stato = stato
        self._coda_analisi = coda_analisi
        self._coda_io = coda_io

        self.jobs_analisi: dict[str, JobInCoda] = {}
        self.jobs_io: dict[str, JobInCoda] = {}

        self._coda_analisi.evento.connect(self._al_evento_analisi)
        self._coda_io.evento.connect(self._al_evento_io)

    def _al_evento_analisi(self, ev: EventoCoda) -> None:
        nome = ev.info_file.get("nome", "Sconosciuto")
        if ev.azione == "aggiunto":
            self.jobs_analisi[nome] = JobInCoda(nome=nome, stato="In coda", tipo="Analisi")
        elif ev.azione == "inizio":
            if nome in self.jobs_analisi:
                self.jobs_analisi[nome].stato = "In analisi..."
        elif ev.azione == "fine":
            if nome in self.jobs_analisi:
                if ev.risultato and ev.risultato.successo:
                    self.jobs_analisi[nome].stato = "Completato"
                    self.jobs_analisi[nome].progresso = 1.0
                    self.jobs_analisi[nome].completato = True
                else:
                    self.jobs_analisi[nome].stato = "Errore"
                    self.jobs_analisi[nome].errore = ev.risultato.errore if ev.risultato else "Errore ignoto"
                    self.jobs_analisi[nome].completato = True
        elif ev.azione == "svuotata":
            self.jobs_analisi.clear()

        self.jobs_analisi_cambiati.emit()

    def _al_evento_io(self, ev: EventoCoda) -> None:
        nome = ev.info_file.get("nome", "Sconosciuto")
        if ev.azione == "aggiunto":
            self.jobs_io[nome] = JobInCoda(nome=nome, stato="In coda", tipo="I/O")
        elif ev.azione == "inizio":
            if nome in self.jobs_io:
                self.jobs_io[nome].stato = "Trasferimento..."
        elif ev.azione == "fine":
            if nome in self.jobs_io:
                if ev.risultato and ev.risultato.successo:
                    if isinstance(ev.risultato.valore, dict) and ev.risultato.valore.get("saltato"):
                        self.jobs_io[nome].stato = "Saltato"
                    else:
                        self.jobs_io[nome].stato = "Archiviato"
                    self.jobs_io[nome].progresso = 1.0
                    self.jobs_io[nome].completato = True
                else:
                    self.jobs_io[nome].stato = "Errore"
                    self.jobs_io[nome].errore = ev.risultato.errore if ev.risultato else "Errore ignoto"
                    self.jobs_io[nome].completato = True
        elif ev.azione == "svuotata":
            self.jobs_io.clear()

        self.jobs_io_cambiati.emit()

    def pulisci_completati(self) -> None:
        """Rimuove i job completati da tempo dalle liste"""
        # Per ora le manteniamo, ma potremmo filtrarle in futuro
        pass


class JobItemWidget(QWidget):
    def __init__(self, job: JobInCoda, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.job = job
        c = theme.colori_correnti()

        if not job.completato:
            icona = FluentIcon.SYNC
        elif job.errore:
            icona = FluentIcon.CANCEL
        else:
            icona = FluentIcon.COMPLETED
        self._icona = IconWidget(icona)
        self._icona.setFixedSize(18, 18)

        self._lbl_nome = StrongBodyLabel(job.nome)
        self._lbl_nome.setMinimumWidth(150)

        self._lbl_tipo = CaptionLabel(job.tipo.upper())

        self._progress = ProgressBar()
        self._progress.setMinimum(0)
        self._progress.setMaximum(100)
        self._progress.setValue(int(job.progresso * 100))
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)

        if job.errore:
            colore_barra = c.errore
        elif job.tipo == "Analisi":
            colore_barra = CATEGORIA.film if not job.completato else c.successo
        else:
            colore_barra = c.accento if not job.completato else c.successo

        self._progress.setCustomBarColor(colore_barra, colore_barra)

        self._lbl_stato = CaptionLabel(job.stato if not job.errore else f"Errore: {job.errore}")
        self._lbl_stato.setStyleSheet(f"color: {colore_barra}; font-weight: 600;")

        layout_top = QHBoxLayout()
        layout_top.setSpacing(SPAZIATURA.sm)
        layout_top.addWidget(self._icona)
        layout_top.addWidget(self._lbl_nome, stretch=1)
        layout_top.addWidget(self._lbl_tipo)
        layout_top.setContentsMargins(0, 0, 0, 0)

        layout_mid = QHBoxLayout()
        layout_mid.addWidget(self._progress)
        layout_mid.setContentsMargins(0, SPAZIATURA.xxs, 0, SPAZIATURA.xxs)

        layout_bot = QHBoxLayout()
        layout_bot.addWidget(self._lbl_stato)
        layout_bot.addStretch()
        layout_bot.setContentsMargins(0, 0, 0, 0)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(layout_top)
        main_layout.addLayout(layout_mid)
        main_layout.addLayout(layout_bot)
        main_layout.setContentsMargins(SPAZIATURA.md, SPAZIATURA.md, SPAZIATURA.md, SPAZIATURA.md)
        main_layout.setSpacing(SPAZIATURA.xs)

        self.setStyleSheet(f"background-color: {c.superficie}; border: 1px solid {c.bordo}; border-radius: 10px;")


class CodeView(PollableScreen):
    def __init__(self, controller: CodeController, parent: Optional[QWidget] = None) -> None:
        super().__init__(intervallo_ms=1000, parent=parent)
        self._controller = controller

        self._timer_ui = QTimer(self)
        self._timer_ui.setSingleShot(True)
        self._timer_ui.setInterval(250)
        self._timer_ui.timeout.connect(self._esegui_aggiornamenti)

        self._controller.jobs_analisi_cambiati.connect(self._richiedi_aggiornamento)
        self._controller.jobs_io_cambiati.connect(self._richiedi_aggiornamento)

        intestazione = IntestazioneSchermata("Monitor Code Attive", "Stile Torrent/eMule Live")

        self._list_analisi = ListWidget()
        self._list_analisi.setSelectionMode(ListWidget.SelectionMode.NoSelection)
        self._list_analisi.setStyleSheet("QListWidget { border: none; background: transparent; }")
        self._list_analisi.setSpacing(SPAZIATURA.sm)

        self._list_io = ListWidget()
        self._list_io.setSelectionMode(ListWidget.SelectionMode.NoSelection)
        self._list_io.setStyleSheet("QListWidget { border: none; background: transparent; }")
        self._list_io.setSpacing(SPAZIATURA.sm)

        card_an = CardWidget()
        lay_an = QVBoxLayout(card_an)
        lay_an.setContentsMargins(SPAZIATURA.lg, SPAZIATURA.lg, SPAZIATURA.lg, SPAZIATURA.lg)
        lay_an.setSpacing(SPAZIATURA.md)
        lbl_an = StrongBodyLabel("CODA ANALISI")
        lbl_an.setStyleSheet(f"color: {CATEGORIA.film};")
        lay_an.addWidget(lbl_an)
        lay_an.addWidget(self._list_analisi)

        card_io = CardWidget()
        lay_io = QVBoxLayout(card_io)
        lay_io.setContentsMargins(SPAZIATURA.lg, SPAZIATURA.lg, SPAZIATURA.lg, SPAZIATURA.lg)
        lay_io.setSpacing(SPAZIATURA.md)
        lbl_io = StrongBodyLabel("CODA TRASFERIMENTI")
        lbl_io.setStyleSheet(f"color: {theme.colori_correnti().accento};")
        lay_io.addWidget(lbl_io)
        lay_io.addWidget(self._list_io)

        lists_layout = QHBoxLayout()
        lists_layout.setSpacing(SPAZIATURA.lg)
        lists_layout.addWidget(card_an)
        lists_layout.addWidget(card_io)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(intestazione)
        main_layout.addSpacing(SPAZIATURA.xl)
        main_layout.addLayout(lists_layout)
        main_layout.setContentsMargins(SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl)

        self._aggiorna_lista_analisi()
        self._aggiorna_lista_io()

    def start_polling(self) -> None:
        super().start_polling()
        self._esegui_aggiornamenti()

    def _al_tick(self) -> None:
        pass  # La view è aggiornata soprattutto via segnali; qui si potrebbe fare pulizia periodica

    def _richiedi_aggiornamento(self) -> None:
        if self.isVisible() and not self._timer_ui.isActive():
            self._timer_ui.start()

    def _esegui_aggiornamenti(self) -> None:
        if not self.isVisible():
            return
        self._aggiorna_lista_analisi()
        self._aggiorna_lista_io()

    def _aggiorna_lista_analisi(self) -> None:
        self._list_analisi.clear()
        jobs = list(self._controller.jobs_analisi.values())
        for job in reversed(jobs[-100:]):  # Mostra solo gli ultimi 100 per non freezare la UI
            item = QListWidgetItem(self._list_analisi)
            widget = JobItemWidget(job)
            item.setSizeHint(widget.sizeHint())
            self._list_analisi.setItemWidget(item, widget)

    def _aggiorna_lista_io(self) -> None:
        self._list_io.clear()
        jobs = list(self._controller.jobs_io.values())
        for job in reversed(jobs[-100:]):
            item = QListWidgetItem(self._list_io)
            widget = JobItemWidget(job)
            item.setSizeHint(widget.sizeHint())
            self._list_io.setItemWidget(item, widget)


def crea_schermata_code(stato: AppState, coda_analisi: CodaLavori, coda_io: CodaLavori) -> CodeView:
    controller = CodeController(stato, coda_analisi, coda_io)
    return CodeView(controller)
