from typing import Optional
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, FluentIcon, IconWidget, ProgressBar, StrongBodyLabel

from app.services.trickplay_service import InfoVideo, GeneratoreTrickplay
from app.ui import theme
from app.ui.design_tokens import SPAZIATURA


def _icona_e_colore(stato: str) -> tuple:
    c = theme.colori_correnti()
    if stato in ("Già generato", "Completato"):
        return FluentIcon.COMPLETED, c.successo
    if stato == "Errore":
        return FluentIcon.CANCEL, c.errore
    if stato == "In elaborazione" or "trickplay" in stato:
        return FluentIcon.SYNC, c.accento
    return FluentIcon.PAUSE, c.testo_secondario


class VideoItemWidget(QWidget):
    def __init__(self, info: InfoVideo, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        c = theme.colori_correnti()
        icona, colore = _icona_e_colore(info.stato)

        self.icona = IconWidget(icona)
        self.icona.setFixedSize(16, 16)

        self.lbl_nome = StrongBodyLabel(info.nome)

        self.lbl_stato = CaptionLabel(info.stato)
        self.lbl_stato.setStyleSheet(f"color: {colore};")

        dim_str = GeneratoreTrickplay.formatta_dimensione(info.dimensione_generata) if info.dimensione_generata > 0 else ""
        self.lbl_dim = CaptionLabel(dim_str)

        self.progress = ProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setValue(int(info.progresso * 100))
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setVisible(0 < info.progresso < 1.0)

        self.lbl_errore = CaptionLabel(info.errore if info.errore else "")
        self.lbl_errore.setStyleSheet(f"color: {c.errore};")
        self.lbl_errore.setVisible(bool(info.errore))

        lay_top = QHBoxLayout()
        lay_top.setSpacing(SPAZIATURA.sm)
        lay_top.addWidget(self.icona)
        lay_top.addWidget(self.lbl_nome, stretch=1)
        lay_top.addWidget(self.lbl_dim)

        lay_bot = QVBoxLayout()
        lay_bot.setSpacing(SPAZIATURA.xxs)
        lay_bot.addWidget(self.progress)
        lay_bot.addWidget(self.lbl_stato)
        lay_bot.addWidget(self.lbl_errore)

        main_lay = QVBoxLayout(self)
        main_lay.addLayout(lay_top)
        main_lay.addLayout(lay_bot)
        main_lay.setContentsMargins(SPAZIATURA.sm, SPAZIATURA.sm, SPAZIATURA.sm, SPAZIATURA.sm)
        main_lay.setSpacing(SPAZIATURA.xxs)

        self.setStyleSheet(f"background-color: {c.superficie}; border: 1px solid {c.bordo}; border-radius: 8px;")

    def aggiorna(self, info: InfoVideo) -> None:
        icona, colore = _icona_e_colore(info.stato)

        self.icona.setIcon(icona)
        self.lbl_stato.setText(info.stato)
        self.lbl_stato.setStyleSheet(f"color: {colore};")

        dim_str = GeneratoreTrickplay.formatta_dimensione(info.dimensione_generata) if info.dimensione_generata > 0 else ""
        self.lbl_dim.setText(dim_str)

        self.progress.setValue(int(info.progresso * 100))
        self.progress.setVisible(0 < info.progresso < 1.0)

        if info.errore:
            self.lbl_errore.setText(info.errore)
            self.lbl_errore.setVisible(True)
        else:
            self.lbl_errore.setVisible(False)
