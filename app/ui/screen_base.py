"""Interfaccia per le schermate che eseguono polling periodico mentre visibili.

Sostituisce il pattern duck-typed avvia_loop()/ferma_loop() di Script_Film,
dove main.py verificava con hasattr() se una schermata esponeva quei metodi
(usato da dashboard/code/trickplay, con task asyncio via pagina.run_task).
Qui ogni schermata pollabile eredita da PollableScreen e implementa
_al_tick(); MainWindow chiama start_polling()/stop_polling() in base a quale
schermata è visibile, tramite un QTimer interno (nessun asyncio necessario).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget


class PollableScreen(QWidget):
    def __init__(self, intervallo_ms: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(intervallo_ms)
        self._timer.timeout.connect(self._al_tick)

    def start_polling(self) -> None:
        self._timer.start()
        self._al_tick()

    def stop_polling(self) -> None:
        self._timer.stop()

    def _al_tick(self) -> None:
        raise NotImplementedError
