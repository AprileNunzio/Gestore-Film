from typing import Optional
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor

class BarraDistribuzione(QWidget):
    """Barra proporzionale film/serie/musica/misto, dipinta manualmente."""

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
