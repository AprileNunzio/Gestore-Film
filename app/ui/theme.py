"""Sistema di tema: palette scura vivace, generazione del foglio di stile QSS.

Tema scuro con accenti colorati e saturi (vedi `design_tokens.CATEGORIA` per
i colori per categoria/schermata) — sostituisce il precedente tema chiaro ad
alto contrasto su richiesta esplicita di un look più moderno e colorato.

I valori di colore/spaziatura/tipografia non sono più definiti qui: vengono da
`app/ui/design_tokens.py`, unica fonte di verità condivisa anche dai
componenti in `app/ui/components/`. Questo modulo resta responsabile solo
della generazione del QSS globale e della sincronizzazione con il tema di
qfluentwidgets (vedi `applica_tema`).
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from qfluentwidgets import Theme, setTheme, setThemeColor

from app.ui.design_tokens import PALETTE_SCURA, RAGGIO, SPAZIATURA, TIPOGRAFIA, Palette as ThemeColors, stile_qss

DARK = PALETTE_SCURA


class _ThemeBus(QObject):
    """Notifica gli screen quando il tema cambia (attualmente solo init)."""
    cambiato = pyqtSignal(str)


bus = _ThemeBus()


def rileva_tema_sistema() -> str:
    """Ritorna sempre 'dark' per forzare l'app nel tema scuro vivace."""
    return "dark"


def colori(modalita: str = "dark") -> ThemeColors:
    return DARK


def colori_correnti() -> ThemeColors:
    return DARK


def modalita_corrente() -> str:
    return "dark"


def applica_tema(app, modalita: str = "dark") -> None:
    """Applica il tema alla QApplication (QSS custom + tema qfluentwidgets) e notifica bus.cambiato."""
    setTheme(Theme.DARK)
    setThemeColor(DARK.accento)
    app.setStyleSheet(costruisci_stylesheet(DARK))
    bus.cambiato.emit("dark")


def costruisci_stylesheet(c: ThemeColors) -> str:
    return f"""
QWidget {{
    color: {c.testo};
    font-family: {TIPOGRAFIA.famiglia};
    font-size: {TIPOGRAFIA.corpo.dimensione_pt}pt;
}}

QMainWindow, QWidget {{
    background-color: {c.sfondo};
}}

QLabel, QCheckBox, QRadioButton {{
    background-color: transparent;
}}

/* -- Bottoni -- */
QPushButton {{
    background-color: {c.accento};
    color: {c.accento_testo};
    border: none;
    border-radius: {RAGGIO.md}px;
    padding: 10px 20px;
    {stile_qss(TIPOGRAFIA.corpo_enfasi)}
}}

QPushButton:hover {{
    background-color: {c.accento_hover};
}}

QPushButton:pressed {{
    background-color: {c.accento};
}}

QPushButton:disabled {{
    background-color: {c.superficie_alt};
    color: {c.bordo};
}}

QPushButton#pulsanteSecondario {{
    background-color: {c.superficie};
    color: {c.testo};
    border: 1px solid {c.bordo};
}}

QPushButton#pulsanteSecondario:hover {{
    background-color: {c.superficie_alt};
    border: 1px solid {c.testo_secondario};
}}

QPushButton#pulsanteIcona {{
    background-color: transparent;
    color: {c.testo_secondario};
    border-radius: {RAGGIO.sm}px;
    padding: 8px;
}}

QPushButton#pulsanteIcona:hover {{
    background-color: {c.superficie_alt};
    color: {c.testo};
}}

/* -- Input ed Editor -- */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background-color: {c.superficie};
    color: {c.testo};
    border: 1px solid {c.bordo};
    border-radius: {RAGGIO.md}px;
    padding: 10px 14px;
    selection-background-color: {c.accento};
    selection-color: {c.accento_testo};
    font-size: {TIPOGRAFIA.corpo.dimensione_pt}pt;
}}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{
    border: 2px solid {c.accento};
    padding: 9px 13px; /* Compensa il bordo di 2px per non far saltare il testo */
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid {c.testo_secondario};
    margin-right: 10px;
}}

/* -- Testi ed Etichette (Gerarchia) -- */
QLabel#titoloSchermata {{
    {stile_qss(TIPOGRAFIA.titolo)}
    color: {c.testo};
}}

QLabel#sottotitoloSchermata {{
    color: {c.testo_secondario};
    {stile_qss(TIPOGRAFIA.sottotitolo)}
}}

QLabel#testoInfo {{
    color: {c.testo_secondario};
    font-size: {TIPOGRAFIA.corpo.dimensione_pt}pt;
}}

/* -- Card di Layout -- */
QFrame#cartaContenuto {{
    background-color: {c.superficie};
    border: 1px solid {c.bordo};
    border-radius: {RAGGIO.lg}px;
}}

/* -- Progress Bar -- */
QProgressBar {{
    background-color: {c.superficie_alt};
    border: 1px solid {c.bordo};
    border-radius: {RAGGIO.md}px;
    text-align: center;
    color: {c.testo};
    font-weight: 600;
    min-height: 20px;
}}

QProgressBar::chunk {{
    background-color: {c.accento};
    border-radius: {RAGGIO.md}px;
}}

/* -- Table e List -- */
QTableView, QListView, QListWidget {{
    background-color: {c.superficie};
    alternate-background-color: {c.sfondo};
    border: 1px solid {c.bordo};
    border-radius: {RAGGIO.lg}px;
    gridline-color: {c.superficie_alt};
    outline: 0;
}}

QTableView::item, QListView::item, QListWidget::item {{
    padding: 10px;
    border-bottom: 1px solid {c.superficie_alt};
}}

QTableView::item:selected, QListView::item:selected, QListWidget::item:selected {{
    background-color: {c.successo_sfondo};
    color: {c.testo};
}}

QHeaderView::section {{
    background-color: {c.sfondo};
    color: {c.testo_secondario};
    padding: 12px 10px;
    border: none;
    border-bottom: 2px solid {c.bordo};
    {stile_qss(TIPOGRAFIA.etichetta_sezione)}
}}

/* -- Scrollbar spesse e accessibili -- */
QScrollBar:vertical {{
    background: {c.sfondo};
    width: 14px;
    margin: 0px;
    border-left: 1px solid {c.bordo};
}}

QScrollBar::handle:vertical {{
    background: {c.bordo};
    border-radius: 7px;
    min-height: 40px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background: {c.testo_secondario};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {c.sfondo};
    height: 14px;
    margin: 0px;
    border-top: 1px solid {c.bordo};
}}

QScrollBar::handle:horizontal {{
    background: {c.bordo};
    border-radius: 7px;
    min-width: 40px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {c.testo_secondario};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* -- Tooltip e MessageBox -- */
QToolTip {{
    background-color: {c.testo};
    color: {c.superficie};
    border: none;
    padding: 6px 10px;
    border-radius: 4px;
    font-weight: 500;
}}

QMessageBox {{
    background-color: {c.superficie};
}}
"""
