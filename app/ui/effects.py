"""Piccoli helper di rendering condivisi tra gli screen.

QSS non supporta box-shadow: per dare profondità alle card (altrimenti
percepite come "piatte", indistinguibili dallo sfondo) serve un
QGraphicsDropShadowEffect applicato in codice.
"""
from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QWidget


def applica_ombra_carta(widget: QWidget) -> None:
    ombra = QGraphicsDropShadowEffect(widget)
    ombra.setBlurRadius(24)
    ombra.setOffset(0, 4)
    ombra.setColor(QColor(0, 0, 0, 45))
    widget.setGraphicsEffect(ombra)
