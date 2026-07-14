"""Dialog condivisi tra le schermate che possono innescare uno spostamento file."""
from __future__ import annotations

import os
import threading
from typing import Any

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QMessageBox,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QComboBox,
    QApplication,
)

from app.organizers.universale import OrganizzatoreUniversale
from app.services import tmdb_service


def mostra_dialogo_conflitto(organizzatore: OrganizzatoreUniversale, dettagli: dict[str, Any]) -> None:
    """Mostra il dialog di risoluzione conflitto e chiama organizzatore.risolvi_conflitto().

    Va invocato da uno slot Qt sul thread GUI (il worker di coda_io resta
    bloccato in attesa su un threading.Event finché non chiamiamo
    risolvi_conflitto — vedi OrganizzatoreUniversale.sposta_file).
    """
    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Risoluzione conflitto")
    box.setText(f"File già presente: {os.path.basename(dettagli['percorso_destinazione'])}")
    box.setInformativeText(
        f"Motivo: {dettagli['motivo']}\n"
        f"Sorgente: {dettagli['dim_sorg_mb']} MB — Destinazione: {dettagli['dim_dest_mb']} MB"
    )
    salta_btn = box.addButton("Salta (mantieni esistente)", QMessageBox.ButtonRole.RejectRole)
    box.addButton("Sovrascrivi", QMessageBox.ButtonRole.DestructiveRole)
    box.exec()
    scelta = "salta" if box.clickedButton() is salta_btn else "sovrascrivi"
    organizzatore.risolvi_conflitto(scelta)


class DialogoRicercaTMDB(QDialog):
    risultati_pronti = pyqtSignal(list)

    def __init__(self, parent=None, titolo_iniziale: str = "", tipo_media: str = "film") -> None:
        super().__init__(parent)
        self.setWindowTitle("Ricerca Manuale TMDB")
        self.setMinimumSize(500, 400)
        self.risultato_scelto: dict[str, Any] | None = None
        self._varianti_trovate: list[dict[str, Any]] = []

        self.risultati_pronti.connect(self._mostra_risultati)

        lay = QVBoxLayout(self)

        form_lay = QHBoxLayout()
        self.edit_titolo = QLineEdit(titolo_iniziale)
        self.edit_titolo.setPlaceholderText("Titolo da cercare...")
        
        self.edit_anno = QLineEdit()
        self.edit_anno.setPlaceholderText("Anno (opz)")
        self.edit_anno.setFixedWidth(80)

        self.combo_tipo = QComboBox()
        self.combo_tipo.addItems(["Film", "Serie TV"])
        if tipo_media == "serie":
            self.combo_tipo.setCurrentText("Serie TV")

        btn_cerca = QPushButton("Cerca")
        btn_cerca.clicked.connect(self._avvia_ricerca)

        form_lay.addWidget(QLabel("Titolo:"))
        form_lay.addWidget(self.edit_titolo)
        form_lay.addWidget(QLabel("Anno:"))
        form_lay.addWidget(self.edit_anno)
        form_lay.addWidget(self.combo_tipo)
        form_lay.addWidget(btn_cerca)

        self.lista_risultati = QListWidget()
        self.lista_risultati.currentRowChanged.connect(self._selezione_cambiata)

        lay.addLayout(form_lay)
        lay.addWidget(self.lista_risultati)

        btn_lay = QHBoxLayout()
        self.btn_conferma = QPushButton("Conferma Selezione")
        self.btn_conferma.setEnabled(False)
        self.btn_conferma.clicked.connect(self.accept)
        
        btn_annulla = QPushButton("Annulla")
        btn_annulla.clicked.connect(self.reject)
        
        btn_lay.addStretch()
        btn_lay.addWidget(btn_annulla)
        btn_lay.addWidget(self.btn_conferma)
        lay.addLayout(btn_lay)

    def _avvia_ricerca(self) -> None:
        titolo = self.edit_titolo.text().strip()
        if not titolo:
            return
            
        anno = self.edit_anno.text().strip()
        tipo = self.combo_tipo.currentText()
        
        self.lista_risultati.clear()
        self.lista_risultati.addItem("Ricerca in corso...")
        self.btn_conferma.setEnabled(False)
        self._varianti_trovate = []

        def _cerca_bg():
            try:
                if tipo == "Serie TV":
                    res = tmdb_service.cerca_serie(titolo, anno=anno, fallback_film=False)
                else:
                    res = tmdb_service.cerca_film(titolo, anno=anno, fallback_serie=False)
                self.risultati_pronti.emit(res)
            except Exception:
                self.risultati_pronti.emit([])

        threading.Thread(target=_cerca_bg, daemon=True).start()

    def _mostra_risultati(self, risultati: list[dict[str, Any]]) -> None:
        self.lista_risultati.clear()
        self._varianti_trovate = risultati
        if not risultati:
            self.lista_risultati.addItem("Nessun risultato trovato.")
            return

        for r in risultati:
            t = r.get("titolo", "Sconosciuto")
            a = r.get("anno", "????")
            tipo = r.get("tipo", "media").upper()
            self.lista_risultati.addItem(f"{t} ({a}) - [{tipo}]")

    def _selezione_cambiata(self, riga: int) -> None:
        if 0 <= riga < len(self._varianti_trovate):
            self.risultato_scelto = self._varianti_trovate[riga]
            self.btn_conferma.setEnabled(True)
        else:
            self.risultato_scelto = None
            self.btn_conferma.setEnabled(False)
