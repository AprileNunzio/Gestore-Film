"""Schermata "Impostazioni": destinazioni della libreria, chiavi API e
preferenze per l'approvazione manuale. Porta gui/schermata_impostazioni.py
di Script_Film.

Completa (insieme a percorsi_screen.py) il fix del bug di navigazione
dell'originale: Script_Film mandava l'utente su vai_a(4) ("Pulizia
Archivio") quando le destinazioni non erano configurate, ma solo questa
schermata leggeva/consumava redirect_post_config — quindi il redirect
arrivava nel posto sbagliato. Ora Percorsi naviga qui correttamente, e da
qui, dopo un salvataggio riuscito con redirect_post_config attivo, si torna
a Scansione con la scansione già pronta a partire (stato.scan_da_avviare).

Le chiavi API (TMDB/Gemini/OpenAI/AcoustID) erano leggibili solo da un file
`.env` creato a mano accanto all'eseguibile — nessuna UI le esponeva. Questa
schermata le rende modificabili anche a runtime: `ImpostazioniController.salva`
le persiste in settings.json e le applica immediatamente ai servizi tramite
`app.core.secrets.applica_api_keys`, senza richiedere un riavvio dell'app.

Schermata pilota della migrazione al design system qfluentwidgets (vedi
piano di refactoring UI): usa i componenti condivisi di
`app/ui/components/` invece di ricostruire banner/intestazione a mano, e i
widget Fluent (CardWidget, RadioButton, CheckBox, PrimaryPushButton) al
posto dei controlli Qt grezzi.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    CardWidget,
    CaptionLabel,
    CheckBox,
    FluentIcon,
    LineEdit,
    MessageBox,
    PasswordLineEdit,
    PrimaryPushButton,
    PushButton,
    RadioButton,
    ScrollArea,
    StrongBodyLabel,
)

from app.core.app_state import AppState
from app.core.config import ConfigManager
from app.core.paths import AppPaths
from app.core.secrets import ApiKeys, applica_api_keys
from app.ui.components.banner_avviso import BannerAvviso, Severita
from app.ui.components.intestazione_schermata import IntestazioneSchermata
from app.ui.design_tokens import CATEGORIA, SPAZIATURA
from app.ui.widgets.directory_picker import SelettoreCartella


class ImpostazioniController(QObject):
    avviso = pyqtSignal(str, bool)  # (messaggio, e_errore)
    richiesta_ritorno_scansione = pyqtSignal()

    def __init__(
        self,
        stato: AppState,
        config_manager: ConfigManager,
        paths: AppPaths,
        api_keys_iniziali: ApiKeys,
    ) -> None:
        super().__init__()
        self._stato = stato
        self._config = config_manager
        self._paths = paths
        self.api_keys_iniziali = api_keys_iniziali

    @property
    def stato(self) -> AppState:
        return self._stato

    def salva(
        self,
        film: str,
        serie: str,
        musica: str,
        erotici: str,
        azione: str,
        conflitto: str,
        pulisci_vuote: bool,
        tmdb: str,
        gemini: str,
        openai: str,
        acoustid: str,
        lingua_default: str,
        tmdb_lingua: str,
    ) -> None:
        film, serie, musica, erotici = film.strip(), serie.strip(), musica.strip(), erotici.strip()

        if not film or not serie or not musica:
            self.avviso.emit("Compila i percorsi principali della libreria prima di salvare.", True)
            return

        self._stato.percorsi["film"] = film
        self._stato.percorsi["serie"] = serie
        self._stato.percorsi["musica"] = musica
        self._stato.percorsi["film_erotici"] = erotici

        self._stato.approvazione_manuale["azione"] = azione
        self._stato.approvazione_manuale["conflitto"] = conflitto
        self._stato.approvazione_manuale["pulisci_vuote"] = pulisci_vuote
        self._stato.automazione["conflitto"] = conflitto

        chiavi = ApiKeys(
            tmdb=tmdb.strip(),
            gemini=gemini.strip(),
            openai=openai.strip(),
            acoustid=acoustid.strip(),
            lingua_default=lingua_default.strip() or "it",
            tmdb_lingua=tmdb_lingua.strip() or "it-IT",
        )

        self._config.salva(
            {
                "destinazioni": self._stato.percorsi,
                "automazione": self._stato.automazione,
                "approvazione_manuale": self._stato.approvazione_manuale,
                "api_keys": {
                    "tmdb": chiavi.tmdb,
                    "gemini": chiavi.gemini,
                    "openai": chiavi.openai,
                    "acoustid": chiavi.acoustid,
                    "lingua_default": chiavi.lingua_default,
                    "tmdb_lingua": chiavi.tmdb_lingua,
                },
            }
        )
        applica_api_keys(self._paths, chiavi)
        self.api_keys_iniziali = chiavi

        self.avviso.emit("Tutte le impostazioni sono state salvate.", False)

        if self._stato.redirect_post_config:
            self._stato.redirect_post_config = False
            self._stato.scan_da_avviare = True
            self.richiesta_ritorno_scansione.emit()

    def dimensione_cache_mb(self) -> float:
        return self._config.dimensione_cache_mb()

    def dimensione_database_mb(self) -> float:
        return self._config.dimensione_database_mb()

    def dimensione_log_mb(self) -> float:
        return self._config.dimensione_log_mb()

    def svuota_cache(self) -> bool:
        return self._config.svuota_cache()

    def svuota_database(self) -> bool:
        return self._config.svuota_database()

    def svuota_log(self) -> bool:
        return self._config.svuota_log()


class ImpostazioniView(QWidget):
    def __init__(self, controller: ImpostazioniController, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._controller = controller
        controller.avviso.connect(self._mostra_avviso)

        intestazione = IntestazioneSchermata(
            "Impostazioni", "Percorsi della libreria, chiavi API e preferenze per l'approvazione manuale"
        )

        self._banner_redirect = BannerAvviso(
            "Configura le directory di destinazione per procedere con la scansione.", Severita.AVVISO
        )
        self._banner_redirect.setVisible(controller.stato.redirect_post_config)

        percorsi = controller.stato.percorsi

        carta_destinazioni = CardWidget()
        layout_destinazioni = QVBoxLayout(carta_destinazioni)
        layout_destinazioni.setContentsMargins(SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl)
        layout_destinazioni.setSpacing(SPAZIATURA.md)

        layout_destinazioni.addWidget(self._etichetta_sezione("DESTINAZIONI LIBRERIA JELLYFIN", CATEGORIA.scansione))

        self._sel_film = self._riga_percorso(layout_destinazioni, "Film", percorsi.get("film", ""))
        self._sel_serie = self._riga_percorso(layout_destinazioni, "Serie TV", percorsi.get("serie", ""))
        self._sel_erotici = self._riga_percorso(layout_destinazioni, "Film Erotici (+18)", percorsi.get("film_erotici", ""))
        self._sel_musica = self._riga_percorso(layout_destinazioni, "Musica", percorsi.get("musica", ""))

        # --- Chiavi API e lingua ---
        chiavi = controller.api_keys_iniziali

        carta_chiavi = CardWidget()
        layout_chiavi = QVBoxLayout(carta_chiavi)
        layout_chiavi.setContentsMargins(SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl)
        layout_chiavi.setSpacing(SPAZIATURA.md)

        layout_chiavi.addWidget(self._etichetta_sezione("CHIAVI API", CATEGORIA.automazione))
        nota_chiavi = CaptionLabel(
            "Salvate solo in locale (settings.json accanto all'app), mai condivise. Lascia vuoto un campo per "
            "disattivare la funzionalità corrispondente: l'app continua a funzionare, semplicemente non la usa."
        )
        nota_chiavi.setWordWrap(True)
        layout_chiavi.addWidget(nota_chiavi)

        self._campo_tmdb = self._riga_chiave(layout_chiavi, "TMDB (identificazione film/serie)", chiavi.tmdb)
        self._campo_gemini = self._riga_chiave(layout_chiavi, "Google Gemini (opzionale, rinforzo AI)", chiavi.gemini)
        self._campo_openai = self._riga_chiave(layout_chiavi, "OpenAI (opzionale, rinforzo AI)", chiavi.openai)
        self._campo_acoustid = self._riga_chiave(layout_chiavi, "AcoustID (opzionale, riconoscimento musica)", chiavi.acoustid)

        riga_lingua = QHBoxLayout()
        riga_lingua.setSpacing(SPAZIATURA.md)
        blocco_lingua_default = QVBoxLayout()
        blocco_lingua_default.addWidget(StrongBodyLabel("Lingua interfaccia/metadati"))
        self._campo_lingua_default = LineEdit()
        self._campo_lingua_default.setText(chiavi.lingua_default)
        self._campo_lingua_default.setPlaceholderText("it")
        blocco_lingua_default.addWidget(self._campo_lingua_default)
        blocco_tmdb_lingua = QVBoxLayout()
        blocco_tmdb_lingua.addWidget(StrongBodyLabel("Lingua risultati TMDB"))
        self._campo_tmdb_lingua = LineEdit()
        self._campo_tmdb_lingua.setText(chiavi.tmdb_lingua)
        self._campo_tmdb_lingua.setPlaceholderText("it-IT")
        blocco_tmdb_lingua.addWidget(self._campo_tmdb_lingua)
        riga_lingua.addLayout(blocco_lingua_default)
        riga_lingua.addLayout(blocco_tmdb_lingua)
        layout_chiavi.addLayout(riga_lingua)

        manuale = controller.stato.approvazione_manuale

        carta_approvazione = CardWidget()
        layout_approvazione = QVBoxLayout(carta_approvazione)
        layout_approvazione.setContentsMargins(SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl)
        layout_approvazione.setSpacing(SPAZIATURA.md)

        layout_approvazione.addWidget(self._etichetta_sezione("GESTIONE APPROVAZIONE MANUALE", CATEGORIA.approvazione))

        layout_approvazione.addWidget(StrongBodyLabel("Azione predefinita dopo approvazione"))
        riga_azione = QHBoxLayout()
        riga_azione.setSpacing(SPAZIATURA.md)
        self._gruppo_azione = QButtonGroup(self)
        self._radio_sposta = RadioButton("Sposta file")
        self._radio_copia = RadioButton("Copia file")
        for radio, valore in ((self._radio_sposta, "Sposta"), (self._radio_copia, "Copia")):
            self._gruppo_azione.addButton(radio)
            riga_azione.addWidget(radio)
            if manuale.get("azione", "Sposta") == valore:
                radio.setChecked(True)
        riga_azione.addStretch(1)
        layout_approvazione.addLayout(riga_azione)

        layout_approvazione.addWidget(StrongBodyLabel("In caso di file già esistente"))
        riga_conflitto = QHBoxLayout()
        riga_conflitto.setSpacing(SPAZIATURA.md)
        self._gruppo_conflitto = QButtonGroup(self)
        self._radio_chiedi = RadioButton("Chiedi ogni volta")
        self._radio_sovrascrivi = RadioButton("Sovrascrivi sempre")
        self._radio_salta = RadioButton("Salta file esistenti")
        for radio, valore in (
            (self._radio_chiedi, "Chiedi"),
            (self._radio_sovrascrivi, "Sovrascrivi"),
            (self._radio_salta, "Salta"),
        ):
            self._gruppo_conflitto.addButton(radio)
            riga_conflitto.addWidget(radio)
            if manuale.get("conflitto", "Salta") == valore:
                radio.setChecked(True)
        riga_conflitto.addStretch(1)
        layout_approvazione.addLayout(riga_conflitto)

        self._checkbox_pulisci = CheckBox("Elimina cartelle sorgenti se rimangono vuote dopo lo spostamento")
        self._checkbox_pulisci.setChecked(bool(manuale.get("pulisci_vuote", False)))
        layout_approvazione.addWidget(self._checkbox_pulisci)

        carta_manutenzione = CardWidget()
        layout_manutenzione = QVBoxLayout(carta_manutenzione)
        layout_manutenzione.setContentsMargins(SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl)
        layout_manutenzione.setSpacing(SPAZIATURA.md)

        layout_manutenzione.addWidget(self._etichetta_sezione("MANUTENZIONE", CATEGORIA.pulizia))

        self._lbl_dim_cache = self._riga_manutenzione(
            layout_manutenzione, "Cache TMDB", controller.dimensione_cache_mb(), self._al_click_svuota_cache
        )
        self._lbl_dim_database = self._riga_manutenzione(
            layout_manutenzione, "Database file processati", controller.dimensione_database_mb(), self._al_click_svuota_database
        )
        self._lbl_dim_log = self._riga_manutenzione(
            layout_manutenzione, "Log applicazione", controller.dimensione_log_mb(), self._al_click_svuota_log
        )

        self._banner_esito = BannerAvviso()
        self._banner_esito.setVisible(False)

        self._pulsante_salva = PrimaryPushButton(FluentIcon.SAVE, "Salva tutte le impostazioni")
        self._pulsante_salva.setFixedHeight(44)
        self._pulsante_salva.clicked.connect(self._al_click_salva)

        contenuto = QWidget()
        layout_contenuto = QVBoxLayout(contenuto)
        layout_contenuto.setContentsMargins(
            SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl
        )
        layout_contenuto.setSpacing(SPAZIATURA.lg)
        layout_contenuto.addWidget(intestazione)
        layout_contenuto.addWidget(self._banner_redirect)
        layout_contenuto.addWidget(carta_destinazioni)
        layout_contenuto.addWidget(carta_chiavi)
        layout_contenuto.addWidget(carta_approvazione)
        layout_contenuto.addWidget(carta_manutenzione)
        layout_contenuto.addWidget(self._banner_esito)
        layout_contenuto.addWidget(self._pulsante_salva, alignment=Qt.AlignmentFlag.AlignRight)
        layout_contenuto.addStretch(1)

        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(contenuto)
        scroll.enableTransparentBackground()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    @staticmethod
    def _etichetta_sezione(testo: str, colore: str) -> StrongBodyLabel:
        etichetta = StrongBodyLabel(testo)
        etichetta.setStyleSheet(f"color: {colore};")
        return etichetta

    def _riga_percorso(self, layout_padre: QVBoxLayout, etichetta_testo: str, valore_iniziale: str) -> SelettoreCartella:
        layout_padre.addWidget(StrongBodyLabel(etichetta_testo))
        selettore = SelettoreCartella()
        selettore.imposta_percorso(valore_iniziale)
        layout_padre.addWidget(selettore)
        return selettore

    def _riga_manutenzione(
        self, layout_padre: QVBoxLayout, etichetta_testo: str, dimensione_mb: float, gestore_click
    ) -> CaptionLabel:
        riga = QHBoxLayout()
        riga.setSpacing(SPAZIATURA.md)
        blocco_testo = QVBoxLayout()
        blocco_testo.addWidget(StrongBodyLabel(etichetta_testo))
        etichetta_dimensione = CaptionLabel(f"{dimensione_mb} MB")
        blocco_testo.addWidget(etichetta_dimensione)
        riga.addLayout(blocco_testo)
        riga.addStretch(1)
        pulsante = PushButton(FluentIcon.DELETE, "Svuota")
        pulsante.clicked.connect(gestore_click)
        riga.addWidget(pulsante)
        layout_padre.addLayout(riga)
        return etichetta_dimensione

    def _riga_chiave(self, layout_padre: QVBoxLayout, etichetta_testo: str, valore_iniziale: str) -> PasswordLineEdit:
        layout_padre.addWidget(StrongBodyLabel(etichetta_testo))
        campo = PasswordLineEdit()
        campo.setText(valore_iniziale)
        campo.setPlaceholderText("Non configurata")
        layout_padre.addWidget(campo)
        return campo

    @property
    def controller(self) -> ImpostazioniController:
        return self._controller

    def showEvent(self, event) -> None:  # noqa: N802 (nome imposto da Qt)
        super().showEvent(event)
        self._banner_redirect.setVisible(self._controller.stato.redirect_post_config)

    def _al_click_salva(self) -> None:
        self._controller.salva(
            film=self._sel_film.percorso(),
            serie=self._sel_serie.percorso(),
            musica=self._sel_musica.percorso(),
            erotici=self._sel_erotici.percorso(),
            azione="Copia" if self._radio_copia.isChecked() else "Sposta",
            conflitto=self._testo_valore_conflitto(),
            pulisci_vuote=self._checkbox_pulisci.isChecked(),
            tmdb=self._campo_tmdb.text(),
            gemini=self._campo_gemini.text(),
            openai=self._campo_openai.text(),
            acoustid=self._campo_acoustid.text(),
            lingua_default=self._campo_lingua_default.text(),
            tmdb_lingua=self._campo_tmdb_lingua.text(),
        )

    def _al_click_svuota_cache(self) -> None:
        self._conferma_e_svuota(
            "Svuota cache TMDB",
            "Verranno eliminate tutte le risposte TMDB salvate in cache. Verranno riscaricate alla prossima richiesta. Continuare?",
            self._controller.svuota_cache,
            self._lbl_dim_cache,
            self._controller.dimensione_cache_mb,
            "Cache svuotata.",
        )

    def _al_click_svuota_database(self) -> None:
        self._conferma_e_svuota(
            "Svuota database file processati",
            "Verrà eliminato il registro dei file già copiati: l'app potrebbe non riconoscere più come duplicati file già archiviati in precedenza. Continuare?",
            self._controller.svuota_database,
            self._lbl_dim_database,
            self._controller.dimensione_database_mb,
            "Database svuotato.",
        )

    def _al_click_svuota_log(self) -> None:
        self._conferma_e_svuota(
            "Svuota log",
            "Verranno eliminati tutti i file di log dell'applicazione. Continuare?",
            self._controller.svuota_log,
            self._lbl_dim_log,
            self._controller.dimensione_log_mb,
            "Log svuotati.",
        )

    def _conferma_e_svuota(self, titolo: str, messaggio: str, azione, etichetta: CaptionLabel, dimensione_fn, msg_successo: str) -> None:
        conferma = MessageBox(titolo, messaggio, self)
        conferma.yesButton.setText("Svuota")
        conferma.cancelButton.setText("Annulla")
        if not conferma.exec():
            return
        riuscito = azione()
        etichetta.setText(f"{dimensione_fn()} MB")
        self._mostra_avviso(msg_successo if riuscito else "Operazione non riuscita.", not riuscito)

    def _testo_valore_conflitto(self) -> str:
        if self._radio_chiedi.isChecked():
            return "Chiedi"
        if self._radio_sovrascrivi.isChecked():
            return "Sovrascrivi"
        return "Salta"

    def _mostra_avviso(self, messaggio: str, e_errore: bool) -> None:
        self._banner_esito.imposta_testo(messaggio, Severita.ERRORE if e_errore else Severita.SUCCESSO)
        self._banner_esito.setVisible(True)


def crea_schermata_impostazioni(
    stato: AppState, config_manager: ConfigManager, paths: AppPaths, api_keys_iniziali: ApiKeys
) -> ImpostazioniView:
    controller = ImpostazioniController(stato, config_manager, paths, api_keys_iniziali)
    return ImpostazioniView(controller)
