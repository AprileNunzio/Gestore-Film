from typing import Optional
import os
import re
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    CaptionLabel,
    ComboBox,
    FluentIcon,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
    TitleLabel,
)

from app.ui import theme
from app.ui.components.banner_avviso import BannerAvviso, Severita
from app.ui.design_tokens import CATEGORIA, SPAZIATURA
from app.ui.screen_base import PollableScreen
from app.controllers.approvazione_controller import ApprovazioneController


class ApprovazioneView(PollableScreen):
    def __init__(self, controller: ApprovazioneController, parent: Optional[QWidget] = None) -> None:
        super().__init__(intervallo_ms=1000, parent=parent)
        self._controller = controller

        self._controller.statistiche_cambiate.connect(self._ridisegna_barra_superiore)
        self._controller.elemento_cambiato.connect(self._aggiorna_vista)
        self._controller.messaggio_notifica.connect(self._mostra_notifica)
        self._controller.immagine_scaricata.connect(self._mostra_immagine)

        # Intestazione
        self._lbl_titolo = TitleLabel("Staging & Approvazione")
        self._lbl_rev = StrongBodyLabel("0")
        lbl_da_rev = BodyLabel("Da revisionare:")

        top_layout = QHBoxLayout()
        top_layout.addWidget(self._lbl_titolo)
        top_layout.addStretch()
        top_layout.addWidget(lbl_da_rev)
        top_layout.addWidget(self._lbl_rev)

        # Navigazione
        self._lbl_pos = BodyLabel("0 / 0")
        btn_prev = PushButton(FluentIcon.LEFT_ARROW, "Precedente")
        btn_prev.clicked.connect(lambda: self._controller.naviga(-1))
        btn_next = PushButton(FluentIcon.RIGHT_ARROW, "Successivo")
        btn_next.clicked.connect(lambda: self._controller.naviga(1))

        nav_layout = QHBoxLayout()
        nav_layout.addStretch()
        nav_layout.addWidget(btn_prev)
        nav_layout.addSpacing(SPAZIATURA.md)
        nav_layout.addWidget(self._lbl_pos)
        nav_layout.addSpacing(SPAZIATURA.md)
        nav_layout.addWidget(btn_next)
        nav_layout.addStretch()

        # Splitter principale
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)

        # --- Pannello sinistro: file originale ---
        self._pannello_sx = CardWidget()
        lay_sx = QVBoxLayout(self._pannello_sx)
        lay_sx.setContentsMargins(SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl)
        lay_sx.setSpacing(SPAZIATURA.sm)

        lay_sx.addWidget(self._etichetta_sezione(FluentIcon.FOLDER, "INFORMAZIONI FILE ORIGINALE", CATEGORIA.scansione))

        self._lbl_file_nome = StrongBodyLabel("—")
        self._lbl_file_nome.setWordWrap(True)
        lay_sx.addWidget(self._lbl_file_nome)

        self._lbl_file_path = CaptionLabel("—")
        self._lbl_file_path.setWordWrap(True)
        self._lbl_file_path.setStyleSheet("font-family: 'Consolas', monospace;")
        lay_sx.addWidget(self._lbl_file_path)

        lay_sx.addSpacing(SPAZIATURA.xs)

        # Righe tecniche in griglia label:valore — più compatto e robusto
        # dello stacking libero di QLabel (che con molte righe e poco spazio
        # verticale finiva per sovrapporsi invece di andare a capo).
        griglia_tecnica = QFormLayout()
        griglia_tecnica.setHorizontalSpacing(SPAZIATURA.md)
        griglia_tecnica.setVerticalSpacing(SPAZIATURA.xxs)
        griglia_tecnica.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._lbl_val_dim = BodyLabel("—")
        self._lbl_val_durata = BodyLabel("—")
        self._lbl_val_contenitore = BodyLabel("—")
        self._lbl_val_risoluzione = BodyLabel("—")
        self._lbl_val_video = BodyLabel("—")
        self._lbl_val_bitrate_fps = BodyLabel("—")
        for etichetta, valore in (
            ("Dimensione", self._lbl_val_dim),
            ("Durata", self._lbl_val_durata),
            ("Contenitore", self._lbl_val_contenitore),
            ("Risoluzione", self._lbl_val_risoluzione),
            ("Video", self._lbl_val_video),
            ("Bitrate/FPS", self._lbl_val_bitrate_fps),
        ):
            griglia_tecnica.addRow(CaptionLabel(etichetta), valore)
        self._griglia_tecnica_widget = QWidget()
        self._griglia_tecnica_widget.setLayout(griglia_tecnica)
        lay_sx.addWidget(self._griglia_tecnica_widget)

        riga_tecnica_assente = QHBoxLayout()
        riga_tecnica_assente.setSpacing(SPAZIATURA.sm)
        self._lbl_tecnica_assente = CaptionLabel("Analisi tecnica (ffmpeg) non disponibile per questo file.")
        self._lbl_tecnica_assente.setWordWrap(True)
        self._btn_rianalizza = PushButton(FluentIcon.SYNC, "Rianalizza")
        self._btn_rianalizza.clicked.connect(self._controller.rianalizza_tecnico_corrente)
        riga_tecnica_assente.addWidget(self._lbl_tecnica_assente, 1)
        riga_tecnica_assente.addWidget(self._btn_rianalizza, 0)
        self._widget_tecnica_assente = QWidget()
        self._widget_tecnica_assente.setLayout(riga_tecnica_assente)
        self._widget_tecnica_assente.setVisible(False)
        lay_sx.addWidget(self._widget_tecnica_assente)

        lay_sx.addSpacing(SPAZIATURA.xs)
        self._lbl_file_audio = BodyLabel("—")
        self._lbl_file_audio.setWordWrap(True)
        self._lbl_file_sub = CaptionLabel("Sottotitoli: —")
        self._lbl_file_sub.setWordWrap(True)
        lay_sx.addWidget(self._lbl_file_audio)
        lay_sx.addWidget(self._lbl_file_sub)

        lay_sx.addSpacing(SPAZIATURA.sm)
        lay_sx.addWidget(self._etichetta_sezione(FluentIcon.ROBOT, "ANALISI AI", CATEGORIA.automazione))
        self._lbl_ai_stato = CaptionLabel("Nessuna analisi AI richiesta per questo file.")
        self._lbl_ai_stato.setWordWrap(True)
        lay_sx.addWidget(self._lbl_ai_stato)

        lay_sx.addStretch()

        # --- Pannello destro: metadati TMDB ---
        self._pannello_dx = CardWidget()
        lay_dx = QVBoxLayout(self._pannello_dx)
        lay_dx.setContentsMargins(SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl, SPAZIATURA.xl)
        lay_dx.setSpacing(SPAZIATURA.sm)

        lay_dx.addWidget(self._etichetta_sezione(FluentIcon.MOVIE, "METADATI TMDB", CATEGORIA.approvazione))

        lay_dx_top = QHBoxLayout()
        lay_dx_top.setSpacing(SPAZIATURA.md)
        self._lbl_immagine = QLabel("Nessun poster")
        self._lbl_immagine.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_immagine.setFixedSize(150, 225)
        self._lbl_immagine_info = CaptionLabel("")
        self._lbl_immagine_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        col_immagine = QVBoxLayout()
        col_immagine.setSpacing(SPAZIATURA.xxs)
        col_immagine.addWidget(self._lbl_immagine)
        col_immagine.addWidget(self._lbl_immagine_info)
        col_immagine.addStretch(1)

        self._lbl_tmdb_titolo = SubtitleLabel("—")
        self._lbl_tmdb_titolo.setWordWrap(True)

        griglia_tmdb = QFormLayout()
        griglia_tmdb.setHorizontalSpacing(SPAZIATURA.md)
        griglia_tmdb.setVerticalSpacing(SPAZIATURA.xxs)
        griglia_tmdb.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._lbl_val_titolo_orig = CaptionLabel("—")
        self._lbl_val_anno_id_tipo = CaptionLabel("—")
        self._lbl_val_genere = CaptionLabel("—")
        self._lbl_val_genere.setWordWrap(True)
        self._lbl_val_voto = BodyLabel("—")
        self._lbl_confidenza = StrongBodyLabel("—")
        self._lbl_val_strategia = CaptionLabel("—")
        griglia_tmdb.addRow(CaptionLabel("Titolo originale"), self._lbl_val_titolo_orig)
        for etichetta, valore in (
            ("Anno / ID / Tipo", self._lbl_val_anno_id_tipo),
            ("Generi", self._lbl_val_genere),
            ("Voto TMDB", self._lbl_val_voto),
            ("Confidenza AI", self._lbl_confidenza),
            ("Strategia ricerca", self._lbl_val_strategia),
        ):
            griglia_tmdb.addRow(CaptionLabel(etichetta), valore)

        col_info = QVBoxLayout()
        col_info.setSpacing(SPAZIATURA.xs)
        col_info.addWidget(self._lbl_tmdb_titolo)
        col_info.addLayout(griglia_tmdb)
        col_info.addStretch(1)

        lay_dx_top.addLayout(col_immagine)
        lay_dx_top.addLayout(col_info, 1)
        lay_dx.addLayout(lay_dx_top)

        self._lbl_tmdb_sinossi = BodyLabel("—")
        self._lbl_tmdb_sinossi.setWordWrap(True)
        self._lbl_tmdb_sinossi.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lay_dx.addWidget(self._lbl_tmdb_sinossi)

        # Varianti e ricerca manuale
        lay_varianti = QHBoxLayout()
        lay_varianti.setSpacing(SPAZIATURA.sm)
        self._combo_varianti = ComboBox()
        self._combo_varianti.currentIndexChanged.connect(self._al_cambio_variante)
        btn_cerca_manuale = PushButton(FluentIcon.SEARCH, "Cerca manuale")
        btn_cerca_manuale.clicked.connect(self._apri_ricerca_manuale)

        lay_varianti.addWidget(BodyLabel("Altre varianti:"), 0)
        lay_varianti.addWidget(self._combo_varianti, 1)
        lay_varianti.addWidget(btn_cerca_manuale, 0)
        lay_dx.addLayout(lay_varianti)

        # Override destinazione
        lay_dest = QHBoxLayout()
        lay_dest.setSpacing(SPAZIATURA.sm)
        self._edit_dest_override = LineEdit()
        self._edit_dest_override.setPlaceholderText("Override cartella di destinazione (opzionale)...")
        self._edit_dest_override.textChanged.connect(lambda _: self._aggiorna_anteprima_destinazione())
        btn_browse = PushButton(FluentIcon.FOLDER, "Sfoglia")
        btn_browse.clicked.connect(self._sfoglia_dest)
        lay_dest.addWidget(self._edit_dest_override)
        lay_dest.addWidget(btn_browse)

        lay_dx.addWidget(BodyLabel("Destinazione personalizzata:"))
        lay_dx.addLayout(lay_dest)

        self._splitter.addWidget(self._pannello_sx)
        self._splitter.addWidget(self._pannello_dx)
        self._splitter.setStretchFactor(0, 4)
        self._splitter.setStretchFactor(1, 6)

        # Anteprima destinazione finale — dove finirà il file, esattamente
        self._carta_destinazione = CardWidget()
        lay_dest_finale = QVBoxLayout(self._carta_destinazione)
        lay_dest_finale.setContentsMargins(SPAZIATURA.xl, SPAZIATURA.md, SPAZIATURA.xl, SPAZIATURA.md)
        lay_dest_finale.setSpacing(SPAZIATURA.xxs)
        lay_dest_finale.addWidget(self._etichetta_sezione(FluentIcon.SAVE_AS, "DESTINAZIONE FINALE (JELLYFIN)", CATEGORIA.pulizia))
        self._lbl_dest_cartella = CaptionLabel("Cartella: —")
        self._lbl_dest_nomefile = CaptionLabel("Nome file: —")
        self._lbl_dest_percorso = BodyLabel("—")
        self._lbl_dest_percorso.setWordWrap(True)
        self._lbl_dest_percorso.setStyleSheet("font-family: 'Consolas', monospace;")
        lay_dest_finale.addWidget(self._lbl_dest_cartella)
        lay_dest_finale.addWidget(self._lbl_dest_nomefile)
        lay_dest_finale.addWidget(self._lbl_dest_percorso)
        
        self._lbl_versioni_esistenti = CaptionLabel("")
        self._lbl_versioni_esistenti.setWordWrap(True)
        self._lbl_versioni_esistenti.setStyleSheet("color: #d97706; font-weight: bold;")
        lay_dest_finale.addWidget(self._lbl_versioni_esistenti)
        self._lbl_versioni_esistenti.setVisible(False)

        # Barra azioni
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(SPAZIATURA.sm)

        self.btn_elimina = self._pulsante_azione(FluentIcon.DELETE, "Elimina file", "errore")
        self.btn_elimina.clicked.connect(self._controller.elimina_corrente)

        self.btn_salta = self._pulsante_azione(FluentIcon.SKIP_FORWARD, "Salta (per ora)", "testo_secondario")
        self.btn_salta.clicked.connect(self._controller.salta_corrente)

        self.btn_rinomina = self._pulsante_azione(FluentIcon.EDIT, "Rinomina sul posto", "avviso")
        self.btn_rinomina.clicked.connect(self._controller.rinomina_corrente)

        self.btn_copia = self._pulsante_azione(FluentIcon.COPY, "Copia in libreria", "accento")
        self.btn_copia.clicked.connect(lambda: self._controller.copia_corrente(self._edit_dest_override.text()))

        self.btn_sposta = PrimaryPushButton(FluentIcon.MOVE, "Sposta in libreria")
        self.btn_sposta.setMinimumHeight(44)
        self.btn_sposta.clicked.connect(lambda: self._controller.sposta_corrente(self._edit_dest_override.text()))

        self.btn_apri = PushButton(FluentIcon.PLAY, "Apri file")
        self.btn_apri.setMinimumHeight(44)
        self.btn_apri.clicked.connect(self._apri_file_corrente)

        btn_layout.addWidget(self.btn_apri)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_elimina)
        btn_layout.addWidget(self.btn_salta)
        btn_layout.addWidget(self.btn_rinomina)
        btn_layout.addWidget(self.btn_copia)
        btn_layout.addWidget(self.btn_sposta)

        # Notifica
        self._notifica = BannerAvviso()
        self._notifica.setVisible(False)

        contenuto = QWidget()
        contenuto_layout = QVBoxLayout(contenuto)
        contenuto_layout.setContentsMargins(SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl, SPAZIATURA.xxl)
        contenuto_layout.setSpacing(SPAZIATURA.md)
        contenuto_layout.addLayout(top_layout)
        contenuto_layout.addLayout(nav_layout)
        contenuto_layout.addWidget(self._splitter)
        contenuto_layout.addWidget(self._carta_destinazione)
        contenuto_layout.addLayout(btn_layout)
        contenuto_layout.addWidget(self._notifica)

        # L'intero contenuto scorre invece di essere schiacciato sotto la sua
        # dimensione naturale quando non entra nell'altezza della finestra:
        # senza scroll, con molte informazioni Qt comprime le etichette sotto
        # il loro sizeHint e il testo finisce per sovrapporsi (bug osservato).
        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(contenuto)
        scroll.enableTransparentBackground()

        layout_principale = QVBoxLayout(self)
        layout_principale.setContentsMargins(0, 0, 0, 0)
        layout_principale.addWidget(scroll)

        self._ridisegna_confidenza(0.0)

    @staticmethod
    def _etichetta_sezione(icona: FluentIcon, testo: str, colore: str) -> QWidget:
        contenitore = QWidget()
        lay = QHBoxLayout(contenitore)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(SPAZIATURA.xs)
        icona_widget = QLabel()
        icona_widget.setPixmap(icona.colored(colore, colore).icon().pixmap(18, 18))
        lay.addWidget(icona_widget)
        etichetta = StrongBodyLabel(testo)
        etichetta.setStyleSheet(f"color: {colore};")
        lay.addWidget(etichetta)
        lay.addStretch(1)
        return contenitore

    def _pulsante_azione(self, icona: FluentIcon, testo: str, token_colore: str) -> PushButton:
        pulsante = PushButton(icona, testo)
        pulsante.setMinimumHeight(44)
        c = theme.colori_correnti()
        colore = getattr(c, token_colore)
        pulsante.setStyleSheet(
            pulsante.styleSheet()
            + f"PushButton {{ background-color: {colore}; color: white; border: none; }}"
            + f"PushButton:hover {{ background-color: {colore}; }}"
        )
        return pulsante

    def start_polling(self) -> None:
        super().start_polling()
        self._controller.ricalcola_lista()

    def _al_tick(self) -> None:
        self._controller.ricalcola_lista()

    def _ridisegna_barra_superiore(self) -> None:
        self._lbl_rev.setText(str(self._controller.totale_elementi))
        if self._controller.totale_elementi > 0:
            self._lbl_pos.setText(f"{self._controller.indice_corrente + 1} / {self._controller.totale_elementi}")
        else:
            self._lbl_pos.setText("0 / 0")

    def _al_cambio_variante(self, idx: int) -> None:
        if idx >= 0:
            data = self._combo_varianti.itemData(idx)
            if data:
                self._controller.cambia_variante(idx, data)

    def _mostra_immagine(self, dati_immagine: bytes) -> None:
        if not dati_immagine:
            self._lbl_immagine.setText("Nessun poster")
            self._lbl_immagine.setPixmap(QPixmap())
            self._lbl_immagine_info.setText("")
        else:
            pixmap = QPixmap()
            pixmap.loadFromData(dati_immagine)
            if pixmap.isNull():
                self._lbl_immagine.setText("Nessun poster")
                self._lbl_immagine_info.setText("")
            else:
                self._lbl_immagine.setPixmap(
                    pixmap.scaled(
                        self._lbl_immagine.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                peso_kb = len(dati_immagine) / 1024
                self._lbl_immagine_info.setText(f"{pixmap.width()}×{pixmap.height()}px · {peso_kb:.0f} KB")

    def _ridisegna_confidenza(self, conf: float) -> None:
        c = theme.colori_correnti()
        colore = c.successo if conf >= 0.85 else c.avviso if conf >= 0.5 else c.errore
        self._lbl_confidenza.setStyleSheet(f"color: {colore};")

    def _aggiorna_vista(self) -> None:
        self._ridisegna_barra_superiore()
        el = self._controller.elemento_corrente
        if not el:
            self._lbl_file_nome.setText("Nessun elemento da revisionare")
            self._lbl_file_path.setText("—")
            self._griglia_tecnica_widget.setVisible(False)
            self._widget_tecnica_assente.setVisible(True)
            self._lbl_file_audio.setText("—")
            self._lbl_file_sub.setText("Sottotitoli: —")
            self._lbl_ai_stato.setText("Nessuna analisi AI richiesta per questo file.")

            self._lbl_tmdb_titolo.setText("—")
            self._lbl_val_titolo_orig.setText("—")
            self._lbl_val_anno_id_tipo.setText("—")
            self._lbl_val_genere.setText("—")
            self._lbl_val_voto.setText("—")
            self._lbl_confidenza.setText("—")
            self._lbl_val_strategia.setText("—")
            self._lbl_tmdb_sinossi.setText("—")

            self._lbl_dest_cartella.setText("Cartella: —")
            self._lbl_dest_nomefile.setText("Nome file: —")
            self._lbl_dest_percorso.setText("—")
            self._lbl_versioni_esistenti.setVisible(False)

            self._combo_varianti.clear()
            self._pannello_sx.setEnabled(False)
            self._pannello_dx.setEnabled(False)
            self._carta_destinazione.setEnabled(False)
            return

        self._pannello_sx.setEnabled(True)
        self._pannello_dx.setEnabled(True)
        self._carta_destinazione.setEnabled(True)

        # Dati file originale
        percorso_orig = el.get("percorso_originale", "")
        self._lbl_file_nome.setText(os.path.basename(percorso_orig) if percorso_orig else el.get("file_originale", "—"))
        self._lbl_file_path.setText(percorso_orig or "—")

        info_tecnica = el.get("info_tecnica", {})
        analisi_disponibile = bool(info_tecnica.get("larghezza"))
        self._griglia_tecnica_widget.setVisible(analisi_disponibile)
        self._widget_tecnica_assente.setVisible(not analisi_disponibile)

        if analisi_disponibile:
            dim_mb = info_tecnica.get("dimensione_mb", 0)
            self._lbl_val_dim.setText(f"{dim_mb / 1024:.2f} GB" if dim_mb >= 1024 else f"{dim_mb:.1f} MB")

            durata = info_tecnica.get("durata_min", 0)
            if durata:
                ore, minuti = divmod(int(durata), 60)
                self._lbl_val_durata.setText(f"{ore}h {minuti:02d}min" if ore else f"{minuti}min")
            else:
                self._lbl_val_durata.setText("Sconosciuta")

            self._lbl_val_contenitore.setText(info_tecnica.get("contenitore") or "Sconosciuto")

            larghezza = info_tecnica.get("larghezza", 0)
            altezza = info_tecnica.get("altezza", 0)
            dimensioni_px = f" ({larghezza}×{altezza})" if larghezza and altezza else ""
            self._lbl_val_risoluzione.setText(f"{info_tecnica.get('risoluzione', 'Sconosciuta')}{dimensioni_px}")
            self._lbl_val_video.setText(info_tecnica.get("codec_video") or "Sconosciuto")

            bitrate = info_tecnica.get("bitrate_kbps", 0)
            fps = info_tecnica.get("fps", 0)
            self._lbl_val_bitrate_fps.setText(f"{bitrate} kbps · {fps} fps" if bitrate or fps else "Sconosciuto")

        tracce_audio = info_tecnica.get("tracce_audio", [])
        if tracce_audio:
            audio_text = "Tracce audio: " + " · ".join(
                f"{a.get('lingua', 'und')} ({a.get('codec', '?')}, {a.get('canali', '?')}ch)" for a in tracce_audio
            )
        else:
            audio_text = "Tracce audio: nessuna / sconosciuta"
        self._lbl_file_audio.setText(audio_text)

        sottotitoli = info_tecnica.get("tracce_sottotitoli", [])
        self._lbl_file_sub.setText(f"Sottotitoli: {', '.join(sottotitoli)}" if sottotitoli else "Sottotitoli: nessuno")

        # Analisi AI (Gemini/OpenAI), se mai richiesta per questo file
        gemini = el.get("gemini", {})
        if gemini and gemini.get("note") != "Analisi AI non richiesta":
            note = gemini.get("note", "")
            conf_ai = gemini.get("confidenza", 0.0)
            tipo_ai = gemini.get("tipo", "")
            pezzi = [p for p in (tipo_ai, f"confidenza {int(conf_ai * 100)}%" if conf_ai else "", note) if p]
            self._lbl_ai_stato.setText(" · ".join(pezzi) or "Analisi AI eseguita, nessun dettaglio disponibile.")
        else:
            self._lbl_ai_stato.setText("Nessuna analisi AI richiesta per questo file.")

        # Dati TMDB
        match = el.get("match_principale", {})
        self._lbl_tmdb_titolo.setText(match.get("titolo", "Titolo Sconosciuto"))

        titolo_orig = match.get("titolo_originale", "")
        self._lbl_val_titolo_orig.setText(titolo_orig or "—")

        self._lbl_val_anno_id_tipo.setText(
            f"{match.get('anno', '—')} / {match.get('tmdb_id', '—')} / {el.get('tipo_media', 'film').upper()}"
        )
        self._lbl_val_genere.setText(match.get("genere", "—") or "—")

        voto = match.get("voto_medio", 0.0)
        stars = "★" * int(voto / 2) + "☆" * (5 - int(voto / 2))
        self._lbl_val_voto.setText(f"{voto} {stars}")

        conf = el.get("confidenza", 0)
        self._lbl_confidenza.setText(f"{int(conf * 100)}%")
        self._ridisegna_confidenza(conf)
        self._lbl_val_strategia.setText(match.get("strategia_vincente", "—") or "—")

        sinossi = match.get("sinossi", "Nessuna trama disponibile.")
        if len(sinossi) > 400:
            sinossi = sinossi[:397] + "..."
        self._lbl_tmdb_sinossi.setText(sinossi)

        # Varianti
        self._combo_varianti.blockSignals(True)
        self._combo_varianti.clear()
        varianti = el.get("varianti", [])
        for v in varianti:
            testo = f"{v.get('titolo', '')} ({v.get('anno', '')}) [{int(v.get('confidenza_tmdb', 0) * 100)}%]"
            self._combo_varianti.addItem(testo, userData=str(v.get("tmdb_id", "")))

        curr_id = str(match.get("tmdb_id", ""))
        idx = self._combo_varianti.findData(curr_id)
        if idx >= 0:
            self._combo_varianti.setCurrentIndex(idx)
        self._combo_varianti.blockSignals(False)

        self._edit_dest_override.setText("")
        self._aggiorna_anteprima_destinazione()

    def _aggiorna_anteprima_destinazione(self) -> None:
        """Mostra esattamente dove finirà il file: cartella, nome file e percorso completo."""
        el = self._controller.elemento_corrente
        if not el:
            return

        struttura = el.get("nome_jellyfin", {})
        nome_file = struttura.get("nome_file", "—")
        self._lbl_dest_nomefile.setText(f"Nome file: {nome_file}")

        override = self._edit_dest_override.text().strip()
        tipo_media = el.get("tipo_media", "film")
        radice = override or self._controller.stato.percorsi.get(tipo_media, "")

        if "cartella_serie" in struttura:
            sottocartelle = [struttura.get("cartella_serie", ""), struttura.get("cartella_stagione", "")]
            self._lbl_dest_cartella.setText(f"Cartella: {' / '.join(p for p in sottocartelle if p)}")
        elif "decade" in struttura:
            sottocartelle = [struttura.get("decade", ""), struttura.get("cartella", "")]
            self._lbl_dest_cartella.setText(f"Cartella: {' / '.join(p for p in sottocartelle if p)}")
        else:
            sottocartelle = []
            self._lbl_dest_cartella.setText("Cartella: —")

        if radice and nome_file != "—":
            percorso_completo = os.path.join(radice, *[p for p in sottocartelle if p], nome_file)
            self._lbl_dest_percorso.setText(percorso_completo)
            
            cartella_dest = os.path.dirname(percorso_completo)
            versioni = []
            if os.path.exists(cartella_dest):
                estensioni_video = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"}
                try:
                    for f in os.listdir(cartella_dest):
                        if os.path.isfile(os.path.join(cartella_dest, f)):
                            _, est_file = os.path.splitext(f)
                            if est_file.lower() in estensioni_video:
                                versioni.append(f)
                except Exception:
                    pass
            
            if versioni:
                testo = "⚠️ Versioni già presenti in questa cartella:\n" + "\n".join(f"• {v}" for v in versioni)
                self._lbl_versioni_esistenti.setText(testo)
                self._lbl_versioni_esistenti.setVisible(True)
            else:
                self._lbl_versioni_esistenti.setText("")
                self._lbl_versioni_esistenti.setVisible(False)
        else:
            self._lbl_dest_percorso.setText("Configura una destinazione (Impostazioni o override qui sopra) per vedere il percorso completo.")
            self._lbl_versioni_esistenti.setVisible(False)

    def _sfoglia_dest(self) -> None:
        percorso = QFileDialog.getExistingDirectory(self, "Seleziona cartella di destinazione")
        if percorso:
            self._edit_dest_override.setText(percorso)

    def _apri_ricerca_manuale(self) -> None:
        el = self._controller.elemento_corrente
        if not el:
            return

        titolo_iniziale = el.get("file_originale", "")
        titolo_iniziale = re.sub(r"\.[a-z0-9]{2,4}$", "", titolo_iniziale, flags=re.I)
        titolo_iniziale = titolo_iniziale.replace(".", " ").replace("_", " ")

        from app.ui.dialogs import DialogoRicercaTMDB
        dlg = DialogoRicercaTMDB(self, titolo_iniziale, el.get("tipo_media", "film"))
        if dlg.exec():
            if dlg.risultato_scelto:
                self._controller.applica_risultato_manuale(dlg.risultato_scelto)

    def _mostra_notifica(self, testo: str, colore: str) -> None:
        severita = Severita.SUCCESSO if colore == "success" else Severita.ERRORE if colore == "error" else Severita.INFO
        self._notifica.imposta_testo(testo, severita)
        self._notifica.setVisible(True)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(3000, lambda: self._notifica.setVisible(False))

    def _apri_file_corrente(self) -> None:
        el = self._controller.elemento_corrente
        if not el:
            return
        percorso_orig = el.get("percorso_originale", "")
        if percorso_orig and os.path.exists(percorso_orig):
            try:
                os.startfile(percorso_orig)
            except Exception as e:
                self._mostra_notifica(f"Impossibile aprire il file: {e}", "error")
        else:
            self._mostra_notifica("Il file originale non esiste o il percorso non è valido.", "error")


def crea_schermata_approvazione(stato, coda_analisi, coda_io) -> ApprovazioneView:
    controller = ApprovazioneController(stato, coda_analisi, coda_io)
    return ApprovazioneView(controller)
