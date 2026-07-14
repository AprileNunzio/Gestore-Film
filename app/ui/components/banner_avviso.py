"""Banner di avviso persistente e riusabile (non un toast: resta finché la
schermata non lo nasconde esplicitamente).

Prima di questo componente, ogni schermata ricostruiva a mano un QLabel con
sfondo/bordo/colore hardcoded per lo stesso pattern (banner "configura le
destinazioni", messaggi di successo/errore dopo un salvataggio, ecc. — vedi
diagnosi nel piano di refactoring UI).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CardWidget, IconWidget, InfoBarIcon

from app.ui import theme
from app.ui.design_tokens import RAGGIO, SPAZIATURA


class Severita(Enum):
    INFO = "info"
    SUCCESSO = "successo"
    AVVISO = "avviso"
    ERRORE = "errore"


_ICONA_PER_SEVERITA = {
    Severita.INFO: InfoBarIcon.INFORMATION,
    Severita.SUCCESSO: InfoBarIcon.SUCCESS,
    Severita.AVVISO: InfoBarIcon.WARNING,
    Severita.ERRORE: InfoBarIcon.ERROR,
}


class BannerAvviso(CardWidget):
    def __init__(
        self,
        testo: str = "",
        severita: Severita = Severita.AVVISO,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._severita = severita

        self._icona = IconWidget(_ICONA_PER_SEVERITA[severita], self)
        self._icona.setFixedSize(20, 20)

        self._etichetta = BodyLabel(testo, self)
        self._etichetta.setWordWrap(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPAZIATURA.md, SPAZIATURA.sm, SPAZIATURA.md, SPAZIATURA.sm)
        layout.setSpacing(SPAZIATURA.sm)
        layout.addWidget(self._icona, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._etichetta, 1)

        self._ridisegna()
        theme.bus.cambiato.connect(lambda _: self._ridisegna())

    def imposta_testo(self, testo: str, severita: Optional[Severita] = None) -> None:
        self._etichetta.setText(testo)
        if severita is not None and severita != self._severita:
            self._severita = severita
            self._icona.setIcon(_ICONA_PER_SEVERITA[severita])
            self._ridisegna()

    def _ridisegna(self) -> None:
        c = theme.colori_correnti()
        colore_bordo = {
            Severita.INFO: c.accento,
            Severita.SUCCESSO: c.successo,
            Severita.AVVISO: c.avviso,
            Severita.ERRORE: c.errore,
        }[self._severita]
        sfondo = {
            Severita.INFO: c.superficie_alt,
            Severita.SUCCESSO: c.successo_sfondo,
            Severita.AVVISO: c.avviso_sfondo,
            Severita.ERRORE: c.errore_sfondo,
        }[self._severita]
        self.setStyleSheet(
            f"BannerAvviso {{ background-color: {sfondo}; border-radius: {RAGGIO.md}px; "
            f"border-left: 3px solid {colore_bordo}; }}"
        )
        self._etichetta.setStyleSheet(f"color: {c.testo};")
