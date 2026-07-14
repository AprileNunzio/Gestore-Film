"""Schermata Pulizia Archivio (Riorganizzazione).

Porta gui/schermata_riorganizzazione.py in stile MVC PyQt6.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QListWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import CardWidget, CaptionLabel, FluentIcon, IconWidget, ListWidget, PrimaryPushButton, ProgressBar, PushButton, StrongBodyLabel

from app.core.app_state import AppState
from app.organizers.film import OrganizzatoreFilm
from app.services.job_queue import CodaLavori
from app.services import io_service
from app.ui import theme
from app.ui.components.intestazione_schermata import IntestazioneSchermata
from app.ui.design_tokens import CATEGORIA, SPAZIATURA
from app.ui.screen_base import PollableScreen

_log = logging.getLogger("gestore_film.pulizia")


class PuliziaArchivioController(QObject):
    stato_cambiato = pyqtSignal(str)
    cartelle_trovate = pyqtSignal(list)
    progresso_globale = pyqtSignal(int, int)  # completati, totali

    def __init__(self, stato: AppState, coda_io: CodaLavori) -> None:
        super().__init__()
        self._stato = stato
        self._coda_io = coda_io
        self._organizzatore = OrganizzatoreFilm()

        self.cartelle_da_spostare: list[tuple[str, str, str, str]] = []  # (nome, sorgente, dest_padre, destinazione_finale)
        self.spostamenti_in_corso = 0
        self.spostamenti_totali = 0

        self._coda_io.evento.connect(self._al_evento_io)

    def scansiona(self) -> None:
        self.cartelle_da_spostare.clear()

        percorsi = self._stato.config_raw.get("destinazioni", {})
        percorso_film = percorsi.get("film")

        if not percorso_film or not os.path.exists(percorso_film):
            self.stato_cambiato.emit("Percorso film non configurato o inaccessibile.")
            self.cartelle_trovate.emit([])
            return

        self.stato_cambiato.emit("Scansione in corso...")
        self.cartelle_trovate.emit([])

        import threading

        def _job_scansione() -> None:
            try:
                risultati = []
                for nome in os.listdir(percorso_film):
                    percorso_completo = os.path.join(percorso_film, nome)
                    if os.path.isdir(percorso_completo):
                        if nome.startswith("Anni "):
                            continue

                        anno_match = re.search(r"\(\d{4}\)", nome)
                        if anno_match:
                            anno = anno_match.group(1)
                            decade = self._organizzatore.ottieni_percorso_decade(anno)
                            sorgente = percorso_completo
                            dest_padre = os.path.join(percorso_film, decade)
                            dest_finale = os.path.join(dest_padre, nome)

                            if not os.path.exists(dest_finale):
                                risultati.append((nome, sorgente, decade, dest_finale))

                self.cartelle_da_spostare = risultati
                self.stato_cambiato.emit(f"Trovate {len(self.cartelle_da_spostare)} cartelle da riorganizzare.")
                self.cartelle_trovate.emit(self.cartelle_da_spostare)

            except Exception as e:
                self.stato_cambiato.emit(f"Errore durante la scansione: {e}")
                self.cartelle_trovate.emit([])

        threading.Thread(target=_job_scansione, daemon=True).start()

    def sposta_singola(self, nome: str, sorgente: str, destinazione: str) -> None:
        self._coda_io.aggiungi_operazione(
            io_service.sposta_directory_con_progresso,
            sorgente, destinazione, None,
            descrizione=f"Sposta dir: {nome}",
            info_file={"nome": nome, "tipo_job": "riorganizzazione"}
        )

    def riorganizza_tutto(self) -> None:
        if not self.cartelle_da_spostare:
            return

        self.spostamenti_totali = len(self.cartelle_da_spostare)
        self.spostamenti_in_corso = 0

        self.progresso_globale.emit(self.spostamenti_in_corso, self.spostamenti_totali)
        self.stato_cambiato.emit("Aggiunta spostamenti in coda...")

        for nome, sorgente, _, destinazione in self.cartelle_da_spostare:
            self.sposta_singola(nome, sorgente, destinazione)

    def _al_evento_io(self, ev) -> None:
        if ev.info_file.get("tipo_job") != "riorganizzazione":
            return

        if ev.azione == "fine":
            self.spostamenti_in_corso += 1
            if self.spostamenti_totali > 0:
                self.progresso_globale.emit(self.spostamenti_in_corso, self.spostamenti_totali)
                self.stato_cambiato.emit(f"Riorganizzazione in corso: {self.spostamenti_in_corso} / {self.spostamenti_totali}")

                if self.spostamenti_in_corso >= self.spostamenti_totali:
                    self.stato_cambiato.emit("Riorganizzazione globale completata!")
                    self.spostamenti_totali = 0
                    self.spostamenti_in_corso = 0
                    self.scansiona()  # Riscansiona alla fine


class CartellaItemWidget(QWidget):
    def __init__(self, nome: str, sorgente: str, decade: str, destinazione: str, on_sposta: callable, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        c = theme.colori_correnti()

        icona = IconWidget(FluentIcon.FOLDER.colored(CATEGORIA.pulizia, CATEGORIA.pulizia))
        icona.setFixedSize(28, 28)

        lbl_nome = StrongBodyLabel(nome)
        lbl_dest = CaptionLabel(f"Destinazione: {decade}")

        btn_sposta = PushButton(FluentIcon.RIGHT_ARROW, "Sposta ora")
        btn_sposta.clicked.connect(lambda: on_sposta(nome, sorgente, destinazione))

        lay_testi = QVBoxLayout()
        lay_testi.addWidget(lbl_nome)
        lay_testi.addWidget(lbl_dest)
        lay_testi.setSpacing(SPAZIATURA.xxs)

        main_lay = QHBoxLayout(self)
        main_lay.setSpacing(SPAZIATURA.md)
        main_lay.addWidget(icona)
        main_lay.addLayout(lay_testi, stretch=1)
        main_lay.addWidget(btn_sposta)
        main_lay.setContentsMargins(SPAZIATURA.md, SPAZIATURA.md, SPAZIATURA.md, SPAZIATURA.md)

        self.setStyleSheet(f"background-color: {c.superficie}; border: 1px solid {c.bordo}; border-radius: 10px;")


class PuliziaArchivioView(PollableScreen):
    def __init__(self, controller: PuliziaArchivioController, parent: Optional[QWidget] = None) -> None:
        super().__init__(intervallo_ms=0, parent=parent)
        self._controller = controller

        self._controller.stato_cambiato.connect(self._set_stato)
        self._controller.cartelle_trovate.connect(self._popola_lista)
        self._controller.progresso_globale.connect(self._aggiorna_progresso)

        intestazione = IntestazioneSchermata("Riorganizzazione Archivio")

        btn_scan = PushButton(FluentIcon.SYNC, "Scansiona")
        btn_scan.clicked.connect(self._controller.scansiona)

        self.btn_all = PrimaryPushButton(FluentIcon.ACCEPT, "Riorganizza tutto")
        self.btn_all.clicked.connect(self._controller.riorganizza_tutto)
        self.btn_all.setEnabled(False)

        top_lay = QHBoxLayout()
        top_lay.addWidget(intestazione)
        top_lay.addStretch()
        top_lay.addWidget(btn_scan)
        top_lay.addSpacing(SPAZIATURA.md)
        top_lay.addWidget(self.btn_all)

        self.lbl_stato = CaptionLabel("Premi Scansiona per trovare i film da organizzare in decadi.")

        self.progresso = ProgressBar()
        self.progresso.setVisible(False)
        self.progresso.setFixedHeight(6)
        self.progresso.setTextVisible(False)

        self.lista = ListWidget()
        self.lista.setStyleSheet("QListWidget { border: none; background: transparent; }")
        self.lista.setSelectionMode(ListWidget.SelectionMode.NoSelection)
        self.lista.setSpacing(SPAZIATURA.sm)

        card = CardWidget()
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(SPAZIATURA.lg, SPAZIATURA.lg, SPAZIATURA.lg, SPAZIATURA.lg)
        card_lay.setSpacing(SPAZIATURA.md)
        card_lay.addWidget(self.lbl_stato)
        card_lay.addWidget(self.progresso)
        card_lay.addWidget(self.lista)

        main_lay = QVBoxLayout(self)
        main_lay.addLayout(top_lay)
        main_lay.addSpacing(SPAZIATURA.xl)
        main_lay.addWidget(card)
        main_lay.setContentsMargins(SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl)

    def _al_tick(self) -> None:
        pass

    def _set_stato(self, testo: str) -> None:
        self.lbl_stato.setText(testo)

    def _popola_lista(self, cartelle: list) -> None:
        self.lista.clear()
        for nome, sorgente, decade, dest in cartelle:
            item = QListWidgetItem(self.lista)
            widget = CartellaItemWidget(nome, sorgente, decade, dest, self._controller.sposta_singola)
            item.setSizeHint(widget.sizeHint())
            self.lista.setItemWidget(item, widget)

        self.btn_all.setEnabled(len(cartelle) > 0)
        self.progresso.setVisible(False)

    def _aggiorna_progresso(self, completati: int, totali: int) -> None:
        if totali > 0:
            self.progresso.setVisible(True)
            self.progresso.setMaximum(totali)
            self.progresso.setValue(completati)
        else:
            self.progresso.setVisible(False)


def crea_schermata_pulizia_archivio(stato: AppState, coda_io: CodaLavori) -> PuliziaArchivioView:
    controller = PuliziaArchivioController(stato, coda_io)
    return PuliziaArchivioView(controller)
