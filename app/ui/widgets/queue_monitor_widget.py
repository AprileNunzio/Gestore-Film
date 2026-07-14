from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableView, 
                             QSplitter, QGroupBox, QLabel, QTextEdit, QHeaderView)
from PyQt6.QtCore import Qt, QModelIndex
from app.ui.models.global_queue_model import GlobalQueueTableModel
from app.ui.delegates.queue_delegate import QueueProgressDelegate
from app.core.task_manager import TaskManager, TaskInfo

class QueueMonitorWidget(QWidget):
    """
    Widget UI completo per il monitoraggio avanzato delle code.
    Include la tabella ad alta densità e il pannello ispezione.
    """
    def __init__(self, task_manager: TaskManager, parent=None):
        super().__init__(parent)
        self.task_manager = task_manager
        
        self.setWindowTitle("Monitor Code Attive (Enterprise)")
        self._setup_ui()
        self._setup_connections()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        # Splitter per dividere Tabella e Pannello Dettagli
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        
        # --- PARTE SUPERIORE: Tabella ---
        self.table_view = QTableView()
        self.model = GlobalQueueTableModel(self.task_manager, self)
        self.table_view.setModel(self.model)
        
        # Imposta il delegate custom per le barre di avanzamento
        self.delegate = QueueProgressDelegate(self.table_view)
        self.table_view.setItemDelegate(self.delegate)
        
        # Ottimizzazioni visuali tabella
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_view.setAlternatingRowColors(True)
        
        self.splitter.addWidget(self.table_view)
        
        # --- PARTE INFERIORE: Pannello Ispezione (Detail View) ---
        self.detail_group = QGroupBox("Dettagli Task Selezionato")
        detail_layout = QVBoxLayout(self.detail_group)
        
        # Info rapide (Dimensione, Blocchi, Percorsi)
        info_layout = QHBoxLayout()
        self.lbl_id = QLabel("<b>ID:</b> -")
        self.lbl_size = QLabel("<b>Dimensioni:</b> -")
        self.lbl_blocks = QLabel("<b>Blocchi:</b> -")
        self.lbl_tmp = QLabel("<b>Tmp:</b> -")
        
        info_layout.addWidget(self.lbl_id)
        info_layout.addWidget(self.lbl_size)
        info_layout.addWidget(self.lbl_blocks)
        info_layout.addWidget(self.lbl_tmp)
        
        detail_layout.addLayout(info_layout)
        
        # Console Live Log
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas;")
        self.log_console.setPlaceholderText("Seleziona un task per visualizzarne i log in tempo reale...")
        detail_layout.addWidget(self.log_console)
        
        self.splitter.addWidget(self.detail_group)
        self.splitter.setSizes([400, 200]) # Proporzioni iniziali
        
        main_layout.addWidget(self.splitter)
        self.setLayout(main_layout)

    def _setup_connections(self):
        self.table_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        # In un'app reale, collegheremmo self.task_manager.signals.log_emitted a self._on_log_received

    def _on_selection_changed(self, selected, deselected):
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes:
            self._clear_details()
            return
            
        index = indexes[0]
        # Recupera il task dal ruolo custom
        task: TaskInfo = self.model.data(index, Qt.ItemDataRole.UserRole)
        
        if task:
            self.lbl_id.setText(f"<b>ID:</b> {task.id}")
            
            # Dimensioni: "Elaborati 1.2 GB / 4.5 GB"
            proc_mb = task.processed_bytes / (1024*1024)
            tot_mb = task.total_bytes / (1024*1024)
            self.lbl_size.setText(f"<b>Dimensioni:</b> {proc_mb:.2f} MB / {tot_mb:.2f} MB")
            
            # Blocchi/Chunk: "Elaborazione blocco 12 di 50"
            self.lbl_blocks.setText(f"<b>Blocchi:</b> Elaborazione blocco {task.current_block} di {task.total_blocks}")
            
            # Tmp Path
            tmp_path = task.tmp_path if task.tmp_path else "<i>Nessuna cartella sandbox necessaria</i>"
            self.lbl_tmp.setText(f"<b>Tmp:</b> {tmp_path}")
            
            # Puliamo i log quando cambiamo task
            self.log_console.clear()
            self.log_console.append(f"--- Ispezione iniziata per {task.name} ({task.id}) ---")
            self.log_console.append(f"Stato attuale: {task.state.value}")
            self.log_console.append(f"Payload JSON: {task.payload}")
            if task.error_message:
                self.log_console.append(f"[ERRORE]: {task.error_message}")

    def _clear_details(self):
        self.lbl_id.setText("<b>ID:</b> -")
        self.lbl_size.setText("<b>Dimensioni:</b> -")
        self.lbl_blocks.setText("<b>Blocchi:</b> -")
        self.lbl_tmp.setText("<b>Tmp:</b> -")
        self.log_console.clear()
        self.log_console.setPlaceholderText("Seleziona un task per visualizzarne i log in tempo reale...")
