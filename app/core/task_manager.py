import uuid
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional
from PyQt6.QtCore import QObject, pyqtSignal, QMutex, QMutexLocker, QThreadPool, QRunnable

class TaskState(Enum):
    PENDING = "Attesa"
    ALLOCATING_TMP = "Allocazione Tmp"
    RUNNING = "In Corso"
    PAUSED = "In Pausa"
    FINISHING = "Completamento"
    COMPLETED = "Completato"
    FAILED_RETRYING = "Errore (Tentativo...)"
    ABORTED = "Annullato"

class TaskType(Enum):
    IO_DISK = "I/O Disco"
    NETWORK_API = "Rete API"
    DOWNLOAD = "Download"
    EXTRACTION = "Estrazione"

class TaskInfo:
    """Modello dati per un singolo Task."""
    def __init__(self, task_type: TaskType, name: str, payload: Dict[str, Any] = None):
        self.id = f"tsk-{uuid.uuid4().hex[:8]}"
        self.type = task_type
        self.name = name
        self.state = TaskState.PENDING
        self.payload = payload or {}
        
        self.progress_macro = 0.0  # Percentuale globale (0-100)
        self.progress_micro = 0.0  # Percentuale blocco corrente (0-100)
        
        self.current_block = 0
        self.total_blocks = 1
        
        self.processed_bytes = 0
        self.total_bytes = 0
        
        self.speed_bytes_per_sec = 0.0
        self.eta_seconds = 0.0
        
        self.tmp_path = ""
        self.error_message = ""
        
        # Metriche interne per EMA (Exponential Moving Average)
        self._last_time = time.time()
        self._last_bytes = 0

    def update_metrics(self, current_bytes: int):
        """Calcola velocità ed ETA."""
        now = time.time()
        dt = max(now - self._last_time, 0.001)
        
        if current_bytes > self._last_bytes:
            inst_speed = (current_bytes - self._last_bytes) / dt
            # EMA smoothing
            alpha = 0.2
            self.speed_bytes_per_sec = (alpha * inst_speed) + ((1 - alpha) * self.speed_bytes_per_sec)
            
            if self.speed_bytes_per_sec > 0 and self.total_bytes > current_bytes:
                self.eta_seconds = (self.total_bytes - current_bytes) / self.speed_bytes_per_sec
            else:
                self.eta_seconds = 0.0
                
        self.processed_bytes = current_bytes
        self._last_time = now
        self._last_bytes = current_bytes


class TaskManagerSignals(QObject):
    task_added = pyqtSignal(str) # task_id
    task_updated = pyqtSignal(str)
    task_completed = pyqtSignal(str)
    task_failed = pyqtSignal(str, str) # task_id, error
    log_emitted = pyqtSignal(str, str) # task_id, message


class TaskManager(QObject):
    """
    Motore centralizzato per la gestione delle code.
    Fornisce un'architettura thread-safe.
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = TaskManager()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.signals = TaskManagerSignals()
        self._tasks: Dict[str, TaskInfo] = {}
        self._mutex = QMutex()
        
        # Inizializziamo i pool (simulato, per ora usiamo il global pool)
        self._thread_pool = QThreadPool.globalInstance()
        # Idealmente creeremmo QThreadPool separati per I/O e Rete

    def add_task(self, task: TaskInfo) -> str:
        with QMutexLocker(self._mutex):
            self._tasks[task.id] = task
        self.signals.task_added.emit(task.id)
        return task.id

    def update_task_state(self, task_id: str, state: TaskState):
        with QMutexLocker(self._mutex):
            if task_id in self._tasks:
                self._tasks[task_id].state = state
        self.signals.task_updated.emit(task_id)

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        with QMutexLocker(self._mutex):
            return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[TaskInfo]:
        with QMutexLocker(self._mutex):
            return list(self._tasks.values())
