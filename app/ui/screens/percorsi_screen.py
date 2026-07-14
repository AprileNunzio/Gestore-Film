"""Schermata "Percorsi": selezione della cartella sorgente da scansionare.

Porta gui/schermata_io.py di Script_Film in stile MVC: PercorsiController
contiene la logica (validazione, persistenza recenti, verifica destinazioni),
PercorsiView è la sola presentazione.

Fix rispetto all'originale: quando le destinazioni non sono configurate,
Script_Film navigava a vai_a(4) ("Pulizia Archivio" nel router di main.py)
invece che alla schermata "Impostazioni" (indice 6), l'unica che leggeva
davvero redirect_post_config — un mismatch di navigazione confermato durante
l'analisi. Qui il redirect punta correttamente a Impostazioni (vedi
richiesta_configurazione, collegata in main.py).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QListWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import CardWidget, FluentIcon, ListWidget, PrimaryPushButton, StrongBodyLabel

from app.core.app_state import AppState
from app.core.config import ConfigManager
from app.core.recent_paths import RecentPathsStore
from app.ui.components.banner_avviso import BannerAvviso, Severita
from app.ui.components.intestazione_schermata import IntestazioneSchermata
from app.ui.design_tokens import CATEGORIA, SPAZIATURA
from app.ui.widgets.directory_picker import SelettoreCartella


class PercorsiController(QObject):
    richiesta_avvio_scansione = pyqtSignal()
    richiesta_configurazione = pyqtSignal()
    avviso = pyqtSignal(str, bool)  # (messaggio, e_errore)

    def __init__(self, stato: AppState, config_manager: ConfigManager, recenti: RecentPathsStore) -> None:
        super().__init__()
        self._stato = stato
        self._config = config_manager
        self._recenti = recenti

    @property
    def stato(self) -> AppState:
        return self._stato

    def destinazioni_configurate(self) -> bool:
        return self._config.destinazioni_configurate()

    def percorsi_recenti(self) -> list[str]:
        return self._recenti.carica()

    def imposta_sorgente(self, percorso: str) -> None:
        self._stato.sorgente = percorso
        self._recenti.aggiungi(percorso)

    def avvia(self, sorgente: str) -> None:
        sorgente = sorgente.strip()
        if not sorgente:
            self.avviso.emit("Seleziona una directory sorgente prima di procedere.", True)
            return

        self._recenti.aggiungi(sorgente)
        self._stato.sorgente = sorgente

        if not self.destinazioni_configurate():
            self._stato.redirect_post_config = True
            self.richiesta_configurazione.emit()
            return

        config = self._config.carica()
        dest = config["destinazioni"]
        self._stato.percorsi["film"] = dest["film"]
        self._stato.percorsi["serie"] = dest["serie"]
        self._stato.percorsi["musica"] = dest["musica"]
        self._stato.percorsi["film_erotici"] = dest.get("film_erotici", "")
        self._stato.scan_da_avviare = True

        self.richiesta_avvio_scansione.emit()


class PercorsiView(QWidget):
    def __init__(self, controller: PercorsiController, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._controller = controller
        controller.avviso.connect(self._mostra_avviso)

        intestazione = IntestazioneSchermata("Seleziona Sorgente", "Scegli la cartella da scansionare in questa sessione")

        self._badge = BannerAvviso()

        carta = CardWidget()
        layout_carta = QVBoxLayout(carta)
        layout_carta.setContentsMargins(SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl)
        layout_carta.setSpacing(SPAZIATURA.md)

        lbl_sorgente = StrongBodyLabel("Cartella Sorgente (Locale o FTP://)")
        lbl_sorgente.setStyleSheet(f"color: {CATEGORIA.scansione};")
        layout_carta.addWidget(lbl_sorgente)
        self._selettore = SelettoreCartella()
        self._selettore.imposta_percorso(controller.stato.sorgente)
        layout_carta.addWidget(self._selettore)

        layout_carta.addSpacing(SPAZIATURA.sm)
        layout_carta.addWidget(StrongBodyLabel("Recenti"))
        self._lista_recenti = ListWidget()
        self._lista_recenti.setMaximumHeight(180)
        self._lista_recenti.itemClicked.connect(self._al_click_recente)
        layout_carta.addWidget(self._lista_recenti)

        self._banner_esito = BannerAvviso()
        self._banner_esito.setVisible(False)

        self._pulsante_avvia = PrimaryPushButton(FluentIcon.PLAY, "Avvia scansione")
        self._pulsante_avvia.setFixedHeight(44)
        self._pulsante_avvia.clicked.connect(self._al_click_avvia)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl)
        layout.setSpacing(SPAZIATURA.lg)
        layout.addWidget(intestazione)
        layout.addWidget(self._badge)
        layout.addWidget(carta)
        layout.addStretch(1)
        layout.addWidget(self._banner_esito)
        layout.addWidget(self._pulsante_avvia, alignment=Qt.AlignmentFlag.AlignRight)

        self._aggiorna_badge()
        self._aggiorna_recenti()

    @property
    def controller(self) -> PercorsiController:
        return self._controller

    def showEvent(self, event) -> None:  # noqa: N802 (nome imposto da Qt)
        super().showEvent(event)
        self._aggiorna_badge()
        self._aggiorna_recenti()

    def _aggiorna_badge(self) -> None:
        if self._controller.destinazioni_configurate():
            self._badge.imposta_testo("Destinazioni configurate", Severita.SUCCESSO)
        else:
            self._badge.imposta_testo("Destinazioni non ancora configurate", Severita.AVVISO)

    def _aggiorna_recenti(self) -> None:
        self._lista_recenti.clear()
        for percorso in self._controller.percorsi_recenti():
            self._lista_recenti.addItem(QListWidgetItem(percorso))

    def _al_click_recente(self, item: QListWidgetItem) -> None:
        percorso = item.text()
        self._selettore.imposta_percorso(percorso)
        self._controller.imposta_sorgente(percorso)
        self._aggiorna_recenti()

    def _al_click_avvia(self) -> None:
        self._controller.avvia(self._selettore.percorso())

    def _mostra_avviso(self, messaggio: str, e_errore: bool) -> None:
        self._banner_esito.imposta_testo(messaggio, Severita.ERRORE if e_errore else Severita.SUCCESSO)
        self._banner_esito.setVisible(True)


def crea_schermata_percorsi(stato: AppState, config_manager: ConfigManager, recenti: RecentPathsStore) -> PercorsiView:
    controller = PercorsiController(stato, config_manager, recenti)
    return PercorsiView(controller)
