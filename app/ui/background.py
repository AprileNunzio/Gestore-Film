"""Utility Qt condivise per eseguire lavoro in background in sicurezza.

Stesso principio di app/services/job_queue.py: un QRunnable emette un segnale
di completamento verso un *bound method* di un QObject sul thread GUI (mai
verso una funzione anonima/lambda, che romperebbe la marshalizzazione
automatica tra thread di Qt). Una volta dentro lo slot — garantito sul thread
GUI — è sicuro richiamare una callback qualunque fornita dal chiamante,
perché a quel punto siamo già sul thread giusto.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


class _TaskSignals(QObject):
    completato = pyqtSignal(int, bool, object)  # (job_id, successo, risultato_o_eccezione)


class _Task(QRunnable):
    def __init__(self, funzione: Callable[..., Any], args: tuple, kwargs: dict) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self._funzione = funzione
        self._args = args
        self._kwargs = kwargs
        self.signals = _TaskSignals()

    def run(self) -> None:
        try:
            risultato = self._funzione(*self._args, **self._kwargs)
            self.signals.completato.emit(id(self), True, risultato)
        except Exception as e:
            self.signals.completato.emit(id(self), False, e)


class TaskRunner(QObject):
    """Esegue callable su QThreadPool.globalInstance(), recapitando l'esito in sicurezza sul thread GUI."""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._in_volo: dict[int, tuple[_Task, Callable[[bool, Any], None]]] = {}

    def esegui(self, funzione: Callable[..., Any], *args: Any, callback: Callable[[bool, Any], None], **kwargs: Any) -> None:
        task = _Task(funzione, args, kwargs)
        self._in_volo[id(task)] = (task, callback)
        task.signals.completato.connect(self._al_completamento)
        QThreadPool.globalInstance().start(task)

    def _al_completamento(self, job_id: int, successo: bool, risultato: Any) -> None:
        voce = self._in_volo.pop(job_id, None)
        if voce is None:
            return
        _task, callback = voce
        callback(successo, risultato)


class TransferBridge(QObject):
    """Marshala in sicurezza sul thread GUI i callback di organizzatore.sposta_file.

    sposta_file gira dentro un worker di CodaLavori e chiama callback_ui_io/
    callback_ui_conflitto direttamente (sincrono, sullo stesso worker thread).
    Passare bridge.progresso_io.emit / bridge.conflitto_richiesto.emit come
    quei callback fa si' che Qt marshali la consegna sul thread GUI, dato che
    i relativi .connect() puntano a bound method di QObject sul thread GUI.
    """

    progresso_io = pyqtSignal(dict, dict)
    conflitto_richiesto = pyqtSignal(dict, dict)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.progresso_io.connect(self._invia_a_task_manager)
        
    def _invia_a_task_manager(self, info_file: dict, progresso: dict) -> None:
        nome = info_file.get("nome", info_file.get("file_originale", ""))
        if not nome:
            return
            
        from app.core.task_manager import TaskManager, TaskState, TaskType
        tm = TaskManager.get_instance()
        
        # Cerca un task I/O attivo o in pausa associato a questo file
        for task in tm.get_all_tasks():
            if task.type == TaskType.IO_DISK and task.name == nome and task.state in (TaskState.RUNNING, TaskState.PAUSED, TaskState.PENDING):
                task.total_bytes = progresso.get("totale", 0)
                task.update_metrics(progresso.get("copiati", 0))
                task.progress_macro = progresso.get("percentuale", 0.0) * 100.0
                if "velocita" in progresso:
                    task.speed_bytes_per_sec = progresso["velocita"]
                if "etr" in progresso:
                    task.eta_seconds = progresso["etr"]
                tm.signals.task_updated.emit(task.id)
                break
