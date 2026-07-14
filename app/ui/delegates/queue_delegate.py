from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionProgressBar, QApplication, QStyle
from PyQt6.QtCore import Qt, QRect, QModelIndex
from PyQt6.QtGui import QPainter, QColor

class QueueProgressDelegate(QStyledItemDelegate):
    """
    Delegate custom per disegnare le barre di avanzamento nella tabella della coda.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter: QPainter, option, index: QModelIndex):
        # Disegniamo la barra di avanzamento nella colonna 4 (Progresso)
        if index.column() == 4:
            task = index.data(Qt.ItemDataRole.UserRole)
            if not task:
                super().paint(painter, option, index)
                return

            progress_macro = task.progress_macro
            progress_micro = task.progress_micro
            
            # Impostiamo le opzioni per la macro-barra (totale)
            progressBarOption = QStyleOptionProgressBar()
            progressBarOption.rect = option.rect
            progressBarOption.minimum = 0
            progressBarOption.maximum = 100
            progressBarOption.progress = int(progress_macro)
            progressBarOption.text = f"{progress_macro:.1f}%"
            progressBarOption.textVisible = True
            
            # Colore base in base allo stato
            from app.core.task_manager import TaskState
            if task.state == TaskState.RUNNING:
                # Colore standard (es. blu del tema di sistema)
                pass
            elif task.state == TaskState.COMPLETED:
                # Tenta di forzare un colore verde (può variare in base allo stile OS)
                pass 
            elif task.state == TaskState.FAILED_RETRYING:
                pass

            # Disegna il controllo tramite lo stile dell'applicazione
            style = QApplication.style()
            style.drawControl(QStyle.ControlElement.CE_ProgressBar, progressBarOption, painter)
            
            # Opzionale: disegnare un piccolo indicatore per il blocco corrente (progress_micro)
            # alla base della cella.
            if progress_micro > 0 and task.state == TaskState.RUNNING:
                micro_rect = QRect(option.rect.left(), option.rect.bottom() - 2, 
                                   int(option.rect.width() * (progress_micro / 100.0)), 2)
                painter.fillRect(micro_rect, QColor(0, 120, 215)) # Blu classico
                
        else:
            # Per tutte le altre colonne, usa il disegno standard
            super().paint(painter, option, index)
