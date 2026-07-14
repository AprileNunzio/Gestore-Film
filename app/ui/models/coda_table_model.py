from typing import Any, Optional
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, QObject

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
