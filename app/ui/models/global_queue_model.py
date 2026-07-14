from typing import Any, List
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, QObject, pyqtSlot
from app.core.task_manager import TaskManager, TaskInfo, TaskState

class GlobalQueueTableModel(QAbstractTableModel):
    """
    Modello per la tabella ad alta densità delle code unificate.
    """
    COLUMNS = ["ID", "Nome", "Tipo", "Stato", "Progresso", "Velocità", "ETA"]
    
    def __init__(self, task_manager: TaskManager, parent: QObject = None):
        super().__init__(parent)
        self.task_manager = task_manager
        self._task_ids: List[str] = []
        
        # Connessione ai segnali del TaskManager
        self.task_manager.signals.task_added.connect(self.on_task_added)
        self.task_manager.signals.task_updated.connect(self.on_task_updated)
        
        self._refresh_initial_data()

    def _refresh_initial_data(self):
        tasks = self.task_manager.get_all_tasks()
        self.beginResetModel()
        self._task_ids = [t.id for t in tasks]
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._task_ids)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
            
        task_id = self._task_ids[index.row()]
        task = self.task_manager.get_task(task_id)
        if not task:
            return None
            
        col = index.column()
        
        # Passiamo l'intero oggetto task per il custom delegate nel ruolo UserRole
        if role == Qt.ItemDataRole.UserRole:
            return task
            
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return task.id.split('-')[1] # Mostra solo la parte breve dell'UUID
            elif col == 1:
                return task.name
            elif col == 2:
                return task.type.value
            elif col == 3:
                return task.state.value
            elif col == 4:
                return task.progress_macro # Verrà intercettato dal delegate
            elif col == 5:
                # Formattazione velocità
                mb_s = task.speed_bytes_per_sec / (1024 * 1024)
                return f"{mb_s:.2f} MB/s" if task.speed_bytes_per_sec > 0 else "-"
            elif col == 6:
                # Formattazione ETA
                if task.eta_seconds > 0:
                    mins, secs = divmod(int(task.eta_seconds), 60)
                    hrs, mins = divmod(mins, 60)
                    if hrs > 0:
                        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
                    return f"{mins:02d}:{secs:02d}"
                return "-"
                
        # Colori in base allo stato
        if role == Qt.ItemDataRole.ForegroundRole:
            if task.state == TaskState.COMPLETED:
                return Qt.GlobalColor.darkGreen
            elif task.state == TaskState.FAILED_RETRYING:
                return Qt.GlobalColor.darkRed
            elif task.state == TaskState.PAUSED:
                return Qt.GlobalColor.darkYellow
                
        return None

    @pyqtSlot(str)
    def on_task_added(self, task_id: str):
        row = len(self._task_ids)
        self.beginInsertRows(QModelIndex(), row, row)
        self._task_ids.append(task_id)
        self.endInsertRows()

    @pyqtSlot(str)
    def on_task_updated(self, task_id: str):
        try:
            row = self._task_ids.index(task_id)
            idx_start = self.index(row, 0)
            idx_end = self.index(row, self.columnCount() - 1)
            self.dataChanged.emit(idx_start, idx_end)
        except ValueError:
            pass # ID non trovato, potrebbe essere un problema di sincronizzazione
