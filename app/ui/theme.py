"""Sistema di tema light/dark: palette, rilevamento del tema di sistema
Windows, generazione del foglio di stile QSS.

Sostituisce l'unico resources/style.qss statico della prima milestone con una
generazione dinamica a partire da un'unica fonte di verità (ThemeColors), così
light e dark restano sempre coerenti senza dover mantenere due QSS a mano, e
un widget può recuperare a runtime i colori del tema attivo (vedi
`colori_correnti()`) per gli accenti costruiti in codice (badge, pulsanti di
stato) invece di avere colori hex sparsi e non coordinati nei singoli screen.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Literal

from PyQt6.QtCore import QObject, pyqtSignal

Modalita = Literal["light", "dark"]


@dataclass(frozen=True)
class ThemeColors:
    sfondo: str
    superficie: str
    superficie_alt: str
    bordo: str
    testo: str
    testo_secondario: str
    accento: str
    accento_hover: str
    accento_testo: str
    successo: str
    successo_sfondo: str
    avviso: str
    avviso_sfondo: str
    errore: str
    errore_sfondo: str


LIGHT = ThemeColors(
    sfondo="#E9E9EE",
    superficie="#FFFFFF",
    superficie_alt="#F3F3F7",
    bordo="#DCDCE3",
    testo="#1A1A1E",
    testo_secondario="#5C5C66",
    accento="#5B5BD6",
    accento_hover="#4A4AC0",
    accento_testo="#FFFFFF",
    successo="#107C10",
    successo_sfondo="#EAF7EA",
    avviso="#9D5D00",
    avviso_sfondo="#FFF6E5",
    errore="#C42B1C",
    errore_sfondo="#FBEAE9",
)

DARK = ThemeColors(
    sfondo="#17171A",
    superficie="#26262B",
    superficie_alt="#1F1F23",
    bordo="#38383F",
    testo="#F2F2F5",
    testo_secondario="#B4B4BC",
    accento="#8B8BEE",
    accento_hover="#9E9EF1",
    accento_testo="#0F0F12",
    successo="#6CCB5F",
    successo_sfondo="#1D2A1C",
    avviso="#FFB900",
    avviso_sfondo="#2E2510",
    errore="#FF99A4",
    errore_sfondo="#2E1A1C",
)

class _ThemeBus(QObject):
    """Notifica gli screen quando il tema cambia, per rinfrescare i colori inline."""

    cambiato = pyqtSignal(str)


bus = _ThemeBus()

_modalita_corrente: Modalita = "light"


def rileva_tema_sistema() -> Modalita:
    """Legge la preferenza chiaro/scuro di Windows dal registro; 'light' se non rilevabile."""
    if sys.platform != "win32":
        return "light"
    try:
        import winreg

        chiave = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        )
        valore, _ = winreg.QueryValueEx(chiave, "AppsUseLightTheme")
        return "light" if valore else "dark"
    except OSError:
        return "light"


def colori(modalita: Modalita) -> ThemeColors:
    return LIGHT if modalita == "light" else DARK


def colori_correnti() -> ThemeColors:
    return colori(_modalita_corrente)


def modalita_corrente() -> Modalita:
    return _modalita_corrente


def applica_tema(app, modalita: Modalita) -> None:
    """Applica il tema alla QApplication, lo ricorda per colori_correnti() e notifica bus.cambiato."""
    global _modalita_corrente
    _modalita_corrente = modalita
    app.setStyleSheet(costruisci_stylesheet(colori(modalita)))
    bus.cambiato.emit(modalita)


def costruisci_stylesheet(c: ThemeColors) -> str:
    return f"""
QWidget {{
    background-color: {c.sfondo};
    color: {c.testo};
    font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
    font-size: 10.5pt;
}}

QMainWindow {{
    background-color: {c.sfondo};
}}

#barraNavigazione {{
    background-color: {c.superficie};
    border: none;
    border-right: 1px solid {c.bordo};
}}

#listaNavigazione {{
    background-color: transparent;
    border: none;
    outline: 0;
    padding: 4px 8px;
}}

#listaNavigazione::item {{
    padding: 12px 14px;
    margin: 2px 0;
    border-radius: 8px;
    color: {c.testo_secondario};
}}

#listaNavigazione::item:selected {{
    background-color: {c.accento};
    color: {c.accento_testo};
    font-weight: 600;
}}

#listaNavigazione::item:disabled {{
    color: {c.bordo};
}}

#listaNavigazione::item:hover:!selected {{
    background-color: {c.superficie_alt};
}}

QPushButton {{
    background-color: {c.accento};
    color: {c.accento_testo};
    border: none;
    border-radius: 8px;
    padding: 9px 18px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {c.accento_hover};
}}

QPushButton:pressed {{
    background-color: {c.accento};
}}

QPushButton:disabled {{
    background-color: {c.bordo};
    color: {c.testo_secondario};
}}

QPushButton#pulsanteSecondario {{
    background-color: transparent;
    color: {c.accento};
    border: 1px solid {c.accento};
}}

QPushButton#pulsanteSecondario:hover {{
    background-color: {c.superficie_alt};
}}

QPushButton#pulsanteIcona {{
    background-color: transparent;
    color: {c.testo_secondario};
    border-radius: 8px;
    padding: 6px;
}}

QPushButton#pulsanteIcona:hover {{
    background-color: {c.superficie_alt};
}}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background-color: {c.superficie};
    color: {c.testo};
    border: 1px solid {c.bordo};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {c.accento};
    selection-color: {c.accento_testo};
}}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {c.accento};
}}

QLabel#titoloSchermata {{
    font-size: 20pt;
    font-weight: 700;
    color: {c.testo};
}}

QLabel#sottotitoloSchermata {{
    color: {c.testo_secondario};
    font-size: 10.5pt;
}}

QFrame#cartaContenuto {{
    background-color: {c.superficie};
    border: 1px solid {c.bordo};
    border-radius: 12px;
}}

QProgressBar {{
    background-color: {c.superficie_alt};
    border: none;
    border-radius: 6px;
    text-align: center;
    color: {c.testo};
    min-height: 10px;
}}

QProgressBar::chunk {{
    background-color: {c.accento};
    border-radius: 6px;
}}

QTableView, QListView, QListWidget {{
    background-color: {c.superficie};
    alternate-background-color: {c.superficie_alt};
    border: 1px solid {c.bordo};
    border-radius: 10px;
    gridline-color: {c.bordo};
    outline: 0;
}}

QTableView::item, QListView::item, QListWidget::item {{
    padding: 6px;
    border-radius: 6px;
}}

QTableView::item:selected, QListView::item:selected, QListWidget::item:selected {{
    background-color: {c.accento};
    color: {c.accento_testo};
}}

QHeaderView::section {{
    background-color: {c.superficie_alt};
    color: {c.testo_secondario};
    padding: 8px;
    border: none;
    border-bottom: 1px solid {c.bordo};
    font-weight: 600;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: {c.bordo};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: {c.testo_secondario};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}

QScrollBar::handle:horizontal {{
    background: {c.bordo};
    border-radius: 5px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {c.testo_secondario};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QToolTip {{
    background-color: {c.superficie};
    color: {c.testo};
    border: 1px solid {c.bordo};
    padding: 4px 8px;
    border-radius: 6px;
}}

QMessageBox {{
    background-color: {c.superficie};
}}
"""
