from typing import Optional
from PyQt6.QtWidgets import QHBoxLayout, QListWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import (
    CardWidget,
    CaptionLabel,
    CheckBox,
    ComboBox,
    FluentIcon,
    ListWidget,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    ScrollArea,
    StrongBodyLabel,
)

from app.services.trickplay_service import ImpostazioniTrickplay, StatisticheTrickplay, GeneratoreTrickplay
from app.ui import theme
from app.ui.components.intestazione_schermata import IntestazioneSchermata
from app.ui.design_tokens import CATEGORIA, SPAZIATURA
from app.ui.widgets.directory_picker import SelettoreCartella
from app.controllers.trickplay_controller import TrickplayController
from app.ui.components.video_item_widget import VideoItemWidget


class TrickplayView(QWidget):
    def __init__(self, controller: TrickplayController, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._controller = controller

        self._controller.stato_cambiato.connect(self._set_stato)
        self._controller.lista_aggiornata.connect(self._popola_lista)
        self._controller.progresso_globale.connect(self._aggiorna_progresso)
        self._controller.statistiche_aggiornate.connect(self._aggiorna_statistiche)
        self._controller.completato.connect(self._al_completato)

        intestazione = IntestazioneSchermata(
            "Generatore Trickplay", "Genera le anteprime di scrubbing per Jellyfin sfruttando la potenza della tua CPU"
        )

        self.sel_cartella = SelettoreCartella()
        self.sel_cartella.imposta_percorso(self._controller._stato.percorsi.get("film", ""))

        carta_parametri = CardWidget()
        lay_parametri = QVBoxLayout(carta_parametri)
        lay_parametri.setContentsMargins(SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl)
        lay_parametri.setSpacing(SPAZIATURA.md)

        lbl_param = StrongBodyLabel("PARAMETRI GENERAZIONE")
        lbl_param.setStyleSheet(f"color: {CATEGORIA.trickplay};")
        lay_parametri.addWidget(lbl_param)

        lay_riga1 = QHBoxLayout()
        lay_riga1.setSpacing(SPAZIATURA.sm)
        self.cb_intervallo = ComboBox()
        self.cb_intervallo.addItems(["5", "10", "15", "20", "30"])
        self.cb_intervallo.setCurrentText("10")
        lay_riga1.addWidget(StrongBodyLabel("Intervallo (s):"))
        lay_riga1.addWidget(self.cb_intervallo)

        self.cb_risoluzione = ComboBox()
        self.cb_risoluzione.addItems(["160", "320", "480"])
        self.cb_risoluzione.setCurrentText("320")
        lay_riga1.addWidget(StrongBodyLabel("Larghezza (px):"))
        lay_riga1.addWidget(self.cb_risoluzione)

        self.cb_qualita = ComboBox()
        self.cb_qualita.addItems(["70", "80", "85", "90", "95"])
        self.cb_qualita.setCurrentText("85")
        lay_riga1.addWidget(StrongBodyLabel("Qualità JPEG:"))
        lay_riga1.addWidget(self.cb_qualita)

        lay_parametri.addLayout(lay_riga1)

        lay_riga2 = QHBoxLayout()
        lay_riga2.setSpacing(SPAZIATURA.sm)
        self.cb_griglia = ComboBox()
        self.cb_griglia.addItems(["5x5", "10x10", "8x8"])
        self.cb_griglia.setCurrentText("10x10")
        lay_riga2.addWidget(StrongBodyLabel("Griglia:"))
        lay_riga2.addWidget(self.cb_griglia)

        self.cb_thread = ComboBox()
        self.cb_thread.addItems(["1", "0", "2", "4", "8", "16"])
        self.cb_thread.setCurrentText("1")
        lay_riga2.addWidget(StrongBodyLabel("Thread paralleli:"))
        lay_riga2.addWidget(self.cb_thread)

        lay_parametri.addLayout(lay_riga2)

        self.chk_keyframe = CheckBox("Estrai solo keyframe (veloce)")
        self.chk_keyframe.setChecked(True)
        lay_parametri.addWidget(self.chk_keyframe)

        self.chk_sovrascrivi = CheckBox("Sovrascrivi esistenti")
        lay_parametri.addWidget(self.chk_sovrascrivi)

        lay_azioni = QHBoxLayout()
        lay_azioni.setSpacing(SPAZIATURA.sm)
        self.btn_analizza = PushButton(FluentIcon.SEARCH, "Analizza cartella")
        self.btn_analizza.setMinimumWidth(160)
        self.btn_analizza.setFixedHeight(44)
        self.btn_analizza.clicked.connect(self._al_click_analizza)

        self.btn_genera = PrimaryPushButton(FluentIcon.PLAY, "Genera trickplay")
        self.btn_genera.setMinimumWidth(160)
        self.btn_genera.setFixedHeight(44)
        self.btn_genera.clicked.connect(self._al_click_genera)
        self.btn_genera.setVisible(False)

        self.btn_ferma = PushButton(FluentIcon.PAUSE, "Interrompi")
        self.btn_ferma.setMinimumWidth(160)
        self.btn_ferma.setFixedHeight(44)
        self.btn_ferma.setStyleSheet(
            self.btn_ferma.styleSheet()
            + f"PushButton {{ background-color: {theme.colori_correnti().errore}; color: white; }}"
        )
        self.btn_ferma.clicked.connect(self._controller.ferma)
        self.btn_ferma.setVisible(False)

        self.lbl_stato = CaptionLabel("Pronto")

        lay_azioni.addWidget(self.btn_analizza)
        lay_azioni.addWidget(self.lbl_stato, stretch=1)
        lay_azioni.addWidget(self.btn_genera)
        lay_azioni.addWidget(self.btn_ferma)

        self.progresso = ProgressBar()
        self.progresso.setVisible(False)
        self.progresso.setFixedHeight(6)
        self.progresso.setTextVisible(False)

        self.lbl_stats = StrongBodyLabel("")

        self.lista = ListWidget()
        self.lista.setStyleSheet("QListWidget { border: none; background: transparent; }")
        self.lista.setSelectionMode(ListWidget.SelectionMode.NoSelection)
        self.lista.setSpacing(SPAZIATURA.sm)

        carta_lista = CardWidget()
        lay_lista = QVBoxLayout(carta_lista)
        lay_lista.setContentsMargins(SPAZIATURA.lg, SPAZIATURA.lg, SPAZIATURA.lg, SPAZIATURA.lg)
        lay_lista.setSpacing(SPAZIATURA.md)
        lay_lista.addWidget(self.progresso)
        lay_lista.addWidget(self.lbl_stats)
        lay_lista.addWidget(self.lista)

        contenuto = QWidget()
        lay_cont = QVBoxLayout(contenuto)
        lay_cont.setContentsMargins(SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl)
        lay_cont.setSpacing(SPAZIATURA.lg)
        lay_cont.addWidget(intestazione)
        lay_cont.addWidget(self.sel_cartella)
        lay_cont.addWidget(carta_parametri)
        lay_cont.addLayout(lay_azioni)
        lay_cont.addWidget(carta_lista)

        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(contenuto)
        scroll.enableTransparentBackground()

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.addWidget(scroll)

    def _costruisci_impostazioni(self) -> ImpostazioniTrickplay:
        g = self.cb_griglia.currentText().split("x")
        try:
            colonne, righe = int(g[0]), int(g[1])
        except Exception:
            colonne, righe = 10, 10

        return ImpostazioniTrickplay(
            intervallo_secondi=int(self.cb_intervallo.currentText()),
            larghezza_tile=int(self.cb_risoluzione.currentText()),
            qualita_jpeg=int(self.cb_qualita.currentText()),
            colonne_griglia=colonne,
            righe_griglia=righe,
            thread_paralleli=int(self.cb_thread.currentText()),
            solo_keyframe=self.chk_keyframe.isChecked()
        )

    def _al_click_analizza(self) -> None:
        cartella = self.sel_cartella.percorso()
        if cartella:
            self.btn_genera.setVisible(False)
            self._controller.analizza(
                cartella,
                self._costruisci_impostazioni(),
                self.chk_sovrascrivi.isChecked()
            )

    def _al_click_genera(self) -> None:
        self.btn_genera.setVisible(False)
        self.btn_ferma.setVisible(True)
        self.btn_analizza.setEnabled(False)
        self.progresso.setVisible(True)
        self.progresso.setValue(0)
        self._controller._generatore.impostazioni = self._costruisci_impostazioni()
        self._controller.genera()

    def _al_completato(self) -> None:
        self.btn_ferma.setVisible(False)
        self.btn_analizza.setEnabled(True)

    def _set_stato(self, testo: str) -> None:
        self.lbl_stato.setText(testo)

    def _popola_lista(self, video_list: list) -> None:
        if not hasattr(self, '_widgets_mappa'):
            self._widgets_mappa = {}

        if len(video_list) == 0 or (video_list and video_list[0].nome not in self._widgets_mappa and len(self._widgets_mappa) > 0):
            self.lista.clear()
            self._widgets_mappa.clear()

        da_generare = 0
        for v in video_list:
            if v.stato != "Già generato":
                if v.nome not in self._widgets_mappa:
                    item = QListWidgetItem(self.lista)
                    widget = VideoItemWidget(v)
                    item.setSizeHint(widget.sizeHint())
                    self.lista.setItemWidget(item, widget)
                    self._widgets_mappa[v.nome] = widget
                else:
                    self._widgets_mappa[v.nome].aggiorna(v)

            if not v.ha_trickplay:
                da_generare += 1

        if da_generare > 0 and not self._controller._generatore.in_esecuzione:
            self.btn_genera.setVisible(True)

    def _aggiorna_progresso(self, completati: int, totali: int) -> None:
        if totali > 0:
            self.progresso.setMaximum(totali)
            self.progresso.setValue(completati)

    def _aggiorna_statistiche(self, stats: StatisticheTrickplay) -> None:
        dim = GeneratoreTrickplay.formatta_dimensione(stats.dimensione_totale)
        tempo = GeneratoreTrickplay.formatta_durata(stats.tempo_trascorso)
        self.lbl_stats.setText(
            f"{stats.video_completati} completati  |  {stats.video_errore} errori  |  "
            f"{stats.video_saltati} esistenti  |  {dim}  |  {tempo}"
        )


def crea_schermata_trickplay(stato) -> TrickplayView:
    controller = TrickplayController(stato)
    return TrickplayView(controller)
