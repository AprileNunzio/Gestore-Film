"""Design tokens: unica fonte di verità per spaziatura, raggi, tipografia e palette.

Prima di questo modulo, ogni schermata sceglieva a mano margini, dimensioni
font e colori (vedi commento diagnostico nel piano di refactoring UI). Qui la
scala è definita una sola volta; `theme.py` e i componenti condivisi in
`app/ui/components/` consumano questi valori invece di ridefinirli.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _Spaziatura:
    xxs: int = 4
    xs: int = 8
    sm: int = 12
    md: int = 16
    lg: int = 24
    xl: int = 32
    xxl: int = 48


@dataclass(frozen=True)
class _Raggio:
    sm: int = 6
    md: int = 8
    lg: int = 12
    xl: int = 16


@dataclass(frozen=True)
class StileTesto:
    dimensione_pt: float
    peso: int  # valori QFont.Weight (400 normale, 500 medio, 600 semibold, 700 bold)
    maiuscolo: bool = False


@dataclass(frozen=True)
class _Tipografia:
    display: StileTesto = StileTesto(28, 700)
    titolo: StileTesto = StileTesto(24, 700)
    sottotitolo: StileTesto = StileTesto(12, 400)
    etichetta_sezione: StileTesto = StileTesto(10.5, 700, maiuscolo=True)
    corpo: StileTesto = StileTesto(11, 400)
    corpo_enfasi: StileTesto = StileTesto(11, 600)
    didascalia: StileTesto = StileTesto(9.5, 500)

    famiglia: str = '"Segoe UI Variable Text", "Segoe UI", sans-serif'


@dataclass(frozen=True)
class Palette:
    """Token colore semantici. Un solo tema attivo alla volta — vedi piano di
    refactoring UI, sezione 'Decisioni architetturali', per il perché."""

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


@dataclass(frozen=True)
class _ColoriCategoria:
    """Colori distintivi per categoria/schermata — non un solo accento
    ripetuto ovunque, ma un colore diverso a seconda del dominio (richiesta
    esplicita di una UI 'più colorata')."""

    film: str = "#7F77DD"        # viola
    serie: str = "#5DCAA5"       # verde acqua
    musica: str = "#97C459"      # verde
    scansione: str = "#378ADD"   # blu
    approvazione: str = "#D4537E"  # rosa
    code: str = "#EF9F27"        # ambra
    pulizia: str = "#D85A30"     # corallo
    automazione: str = "#BA7517"  # ambra scuro
    trickplay: str = "#D4537E"   # rosa


SPAZIATURA = _Spaziatura()
RAGGIO = _Raggio()
TIPOGRAFIA = _Tipografia()
CATEGORIA = _ColoriCategoria()

PALETTE_CHIARA = Palette(
    sfondo="#F8F9FA",
    superficie="#FFFFFF",
    superficie_alt="#E9ECEF",
    bordo="#DEE2E6",
    testo="#212529",
    testo_secondario="#495057",
    accento="#0D6EFD",
    accento_hover="#0B5ED7",
    accento_testo="#FFFFFF",
    successo="#198754",
    successo_sfondo="#D1E7DD",
    avviso="#FFC107",
    avviso_sfondo="#FFF3CD",
    errore="#DC3545",
    errore_sfondo="#F8D7DA",
)

PALETTE_SCURA = Palette(
    sfondo="#18181F",
    superficie="#222230",
    superficie_alt="#2B2B3A",
    bordo="#38384A",
    testo="#F0F0F5",
    testo_secondario="#A6A6BF",
    accento="#8F87E8",
    accento_hover="#A29AF0",
    accento_testo="#18181F",
    successo="#5DCAA5",
    successo_sfondo="#163B33",
    avviso="#EF9F27",
    avviso_sfondo="#3D2A0E",
    errore="#E8615F",
    errore_sfondo="#3D1414",
)


def stile_qss(stile: StileTesto) -> str:
    """Frammento QSS (font-size/font-weight/text-transform) per uno StileTesto."""
    righe = [f"font-size: {stile.dimensione_pt}pt;", f"font-weight: {stile.peso};"]
    if stile.maiuscolo:
        righe.append("text-transform: uppercase;")
    return " ".join(righe)
