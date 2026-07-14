"""Schermata Code: Monitoraggio in stile Enterprise delle code di analisi e I/O.
"""
from __future__ import annotations
import logging
from typing import Optional
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from app.core.app_state import AppState
from app.services.job_queue import CodaLavori, EventoCoda
from app.ui.components.intestazione_schermata import IntestazioneSchermata
from app.ui.design_tokens import SPAZIATURA
from app.ui.screen_base import PollableScreen

from app.core.task_manager import TaskManager, TaskInfo, TaskState, TaskType
from app.ui.widgets.queue_monitor_widget import QueueMonitorWidget

_log = logging.getLogger("gestore_film.code")


class CodeController:
    """Adattatore che collega il vecchio CodaLavori al nuovo TaskManager."""
    def __init__(self, stato: AppState, coda_analisi: CodaLavori, coda_io: CodaLavori) -> None:
        self._stato = stato
        self._coda_analisi = coda_analisi
        self._coda_io = coda_io
        self.task_manager = TaskManager.get_instance()

        self._coda_analisi.evento.connect(self._al_evento_analisi)
        self._coda_io.evento.connect(self._al_evento_io)
        
        # Mappa nomi file a task_id
        self._mappa_task = {}

    def _al_evento_analisi(self, ev: EventoCoda) -> None:
        nome = ev.info_file.get("nome", "Sconosciuto")
        task_id = self._mappa_task.get(f"analisi_{nome}")
        
        if ev.azione == "aggiunto":
            task = TaskInfo(TaskType.NETWORK_API, nome, ev.info_file)
            task_id = self.task_manager.add_task(task)
            self._mappa_task[f"analisi_{nome}"] = task_id
        elif ev.azione == "inizio" and task_id:
            self.task_manager.update_task_state(task_id, TaskState.RUNNING)
        elif ev.azione == "fine" and task_id:
            if ev.risultato and ev.risultato.successo:
                self.task_manager.update_task_state(task_id, TaskState.COMPLETED)
                task = self.task_manager.get_task(task_id)
                task.progress_macro = 100.0
                self.task_manager.signals.task_updated.emit(task_id)
            else:
                self.task_manager.update_task_state(task_id, TaskState.FAILED_RETRYING)
                task = self.task_manager.get_task(task_id)
                task.error_message = ev.risultato.errore if ev.risultato else "Errore ignoto"
                self.task_manager.signals.task_updated.emit(task_id)

    def _al_evento_io(self, ev: EventoCoda) -> None:
        nome = ev.info_file.get("nome", "Sconosciuto")
        task_id = self._mappa_task.get(f"io_{nome}")
        
        if ev.azione == "aggiunto":
            task = TaskInfo(TaskType.IO_DISK, nome, ev.info_file)
            task_id = self.task_manager.add_task(task)
            self._mappa_task[f"io_{nome}"] = task_id
        elif ev.azione == "inizio" and task_id:
            self.task_manager.update_task_state(task_id, TaskState.RUNNING)
        elif ev.azione == "fine" and task_id:
            if ev.risultato and ev.risultato.successo:
                self.task_manager.update_task_state(task_id, TaskState.COMPLETED)
                task = self.task_manager.get_task(task_id)
                task.progress_macro = 100.0
                self.task_manager.signals.task_updated.emit(task_id)
            else:
                self.task_manager.update_task_state(task_id, TaskState.FAILED_RETRYING)
                task = self.task_manager.get_task(task_id)
                task.error_message = ev.risultato.errore if ev.risultato else "Errore ignoto"
                self.task_manager.signals.task_updated.emit(task_id)


class CodeView(PollableScreen):
    def __init__(self, controller: CodeController, parent: Optional[QWidget] = None) -> None:
        super().__init__(intervallo_ms=1000, parent=parent)
        self._controller = controller

        intestazione = IntestazioneSchermata("Monitor Code Attive", "Architettura Enterprise Unificata")

        self.monitor_widget = QueueMonitorWidget(self._controller.task_manager)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(intestazione)
        main_layout.addSpacing(SPAZIATURA.lg)
        main_layout.addWidget(self.monitor_widget, 1) # Il monitor prende tutto lo spazio rimanente
        main_layout.setContentsMargins(SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl)

    def start_polling(self) -> None:
        super().start_polling()

    def _al_tick(self) -> None:
        pass


def crea_schermata_code(stato: AppState, coda_analisi: CodaLavori, coda_io: CodaLavori) -> CodeView:
    controller = CodeController(stato, coda_analisi, coda_io)
    return CodeView(controller)
