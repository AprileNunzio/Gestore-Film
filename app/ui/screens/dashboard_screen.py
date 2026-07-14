"""Schermata Dashboard: panoramica statistica del sistema.

Visualizza metriche di archiviazione e dello stato delle code.
"""
from __future__ import annotations

import os
import shutil
from typing import Optional

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CardWidget, FluentIcon, StrongBodyLabel, TitleLabel

from app.core.app_state import AppState
from app.services.job_queue import CodaLavori
from app.ui.components.intestazione_schermata import IntestazioneSchermata
from app.ui.components.scheda_statistica import SchedaStatistica
from app.ui.design_tokens import CATEGORIA, SPAZIATURA
from app.ui.screen_base import PollableScreen


class DashboardController(QObject):
    def __init__(self, stato: AppState, coda_analisi: CodaLavori, coda_io: CodaLavori) -> None:
        super().__init__()
        self.stato = stato
        self.coda_analisi = coda_analisi
        self.coda_io = coda_io

    def ottieni_spazio(self, percorso: str) -> tuple[int, int, int]:
        """Ritorna totale, usato, libero in bytes."""
        if not percorso or not os.path.exists(percorso):
            return 0, 0, 0
        total, used, free = shutil.disk_usage(percorso)
        return total, used, free


class DashboardView(PollableScreen):
    def __init__(self, controller: DashboardController, parent: Optional[QWidget] = None) -> None:
        super().__init__(intervallo_ms=2000, parent=parent)
        self._controller = controller

        intestazione = IntestazioneSchermata("Dashboard", "Panoramica del tuo Media Manager")

        self._card_film = SchedaStatistica("Archivio Film", CATEGORIA.film, FluentIcon.MOVIE)
        self._card_serie = SchedaStatistica("Archivio Serie TV", CATEGORIA.serie, FluentIcon.ALBUM)

        # Labels Motore
        self._lbl_coda_analisi = self._numero_grande(CATEGORIA.film)
        self._lbl_coda_io = self._numero_grande(CATEGORIA.scansione)
        
        # Labels Pipeline
        self._lbl_indicizzati = self._numero_grande("#4CAF50")
        self._lbl_identificati = self._numero_grande(CATEGORIA.serie)
        self._lbl_in_coda = self._numero_grande("#FF9800")
        self._lbl_revisione = self._numero_grande(CATEGORIA.scansione)
        self._lbl_trasferimento = self._numero_grande("#2196F3")
        self._lbl_archiviati = self._numero_grande(CATEGORIA.film)
        self._lbl_anomalie = self._numero_grande("#F44336")

        # Card Motore
        card_motore = CardWidget()
        lay_motore = QVBoxLayout(card_motore)
        lay_motore.setContentsMargins(SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl)
        lay_motore.setSpacing(SPAZIATURA.sm)
        lay_motore.addWidget(StrongBodyLabel("Motore di Sistema"))

        riga_motore = QHBoxLayout()
        riga_motore.setSpacing(SPAZIATURA.xl)
        for etichetta, numero in (
            ("Analisi AI in coda", self._lbl_coda_analisi),
            ("Trasferimenti I/O in coda", self._lbl_coda_io),
        ):
            blocco = QVBoxLayout()
            blocco.setSpacing(SPAZIATURA.xxs)
            blocco.addWidget(numero)
            blocco.addWidget(BodyLabel(etichetta))
            riga_motore.addLayout(blocco)
        riga_motore.addStretch(1)
        lay_motore.addLayout(riga_motore)

        # Card Pipeline
        card_pipeline = CardWidget()
        lay_pipeline = QVBoxLayout(card_pipeline)
        lay_pipeline.setContentsMargins(SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl)
        lay_pipeline.setSpacing(SPAZIATURA.sm)
        lay_pipeline.addWidget(StrongBodyLabel("Statistiche Pipeline"))

        # Divido in due righe per non sovraffollare
        riga_pipeline_1 = QHBoxLayout()
        riga_pipeline_1.setSpacing(SPAZIATURA.xl)
        for etichetta, numero in (
            ("Indicizzati", self._lbl_indicizzati),
            ("Identificati", self._lbl_identificati),
            ("In Coda Appr.", self._lbl_in_coda),
            ("In Revisione", self._lbl_revisione),
        ):
            blocco = QVBoxLayout()
            blocco.setSpacing(SPAZIATURA.xxs)
            blocco.addWidget(numero)
            blocco.addWidget(BodyLabel(etichetta))
            riga_pipeline_1.addLayout(blocco)
        riga_pipeline_1.addStretch(1)
        
        riga_pipeline_2 = QHBoxLayout()
        riga_pipeline_2.setSpacing(SPAZIATURA.xl)
        for etichetta, numero in (
            ("In Trasferimento", self._lbl_trasferimento),
            ("Archiviati", self._lbl_archiviati),
            ("Anomalie", self._lbl_anomalie),
        ):
            blocco = QVBoxLayout()
            blocco.setSpacing(SPAZIATURA.xxs)
            blocco.addWidget(numero)
            blocco.addWidget(BodyLabel(etichetta))
            riga_pipeline_2.addLayout(blocco)
        riga_pipeline_2.addStretch(1)

        lay_pipeline.addLayout(riga_pipeline_1)
        lay_pipeline.addLayout(riga_pipeline_2)

        lay_dischi = QHBoxLayout()
        lay_dischi.setSpacing(SPAZIATURA.lg)
        lay_dischi.addWidget(self._card_film)
        lay_dischi.addWidget(self._card_serie)

        # Griglia o due layout orizzontali per lo stato
        lay_stato = QHBoxLayout()
        lay_stato.setSpacing(SPAZIATURA.lg)
        lay_stato.addWidget(card_motore)
        lay_stato.addWidget(card_pipeline)

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl)
        main_lay.setSpacing(SPAZIATURA.lg)
        main_lay.addWidget(intestazione)
        main_lay.addLayout(lay_dischi)
        main_lay.addLayout(lay_stato)
        main_lay.addStretch()

    @staticmethod
    def _numero_grande(colore: str) -> TitleLabel:
        etichetta = TitleLabel("0")
        etichetta.setStyleSheet(f"color: {colore};")
        return etichetta

    def _formatta_bytes(self, b: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if b < 1024.0:
                return f"{b:.1f} {unit}"
            b /= 1024.0
        return f"{b:.1f} PB"

    def _aggiorna_card_disco(self, card: SchedaStatistica, percorso: str) -> None:
        t, u, f = self._controller.ottieni_spazio(percorso)
        if t == 0:
            card.imposta_valore(0, "Percorso non configurato o non trovato")
            return

        perc = int((u / t) * 100)
        card.imposta_valore(perc, f"Usato: {self._formatta_bytes(u)} su {self._formatta_bytes(t)} ({perc}%)")

    def _al_tick(self) -> None:
        p_film = self._controller.stato.percorsi.get("film", "")
        p_serie = self._controller.stato.percorsi.get("serie", "")

        self._aggiorna_card_disco(self._card_film, p_film)
        self._aggiorna_card_disco(self._card_serie, p_serie)

        self._lbl_coda_analisi.setText(str(self._controller.coda_analisi.operazioni_attive))
        self._lbl_coda_io.setText(str(self._controller.coda_io.operazioni_attive))

        pipe = self._controller.stato.pipeline
        self._lbl_indicizzati.setText(str(pipe.indicizzati))
        self._lbl_identificati.setText(str(pipe.identificati))
        self._lbl_in_coda.setText(str(pipe.in_coda))
        self._lbl_revisione.setText(str(pipe.revisione))
        self._lbl_trasferimento.setText(str(pipe.in_trasferimento))
        self._lbl_archiviati.setText(str(pipe.archiviati))
        self._lbl_anomalie.setText(str(pipe.anomalie))


def crea_schermata_dashboard(stato: AppState, coda_analisi: CodaLavori, coda_io: CodaLavori) -> DashboardView:
    controller = DashboardController(stato, coda_analisi, coda_io)
    return DashboardView(controller)
