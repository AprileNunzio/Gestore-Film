"""Stato condiviso tra le schermate, versione tipizzata dello `stato: dict`
passato per riferimento a ogni schermata in main.py di Script_Film.

`pipeline` è condiviso tra Scansione (che la popola durante l'indicizzazione)
e Approvazione (che la aggiorna quando l'utente processa/salta/elimina un
file in revisione manuale) — nell'originale era lo stesso `stato["pipeline"]`
dict scritto da entrambe le schermate. A differenza dell'originale, qui non
serve un lock esplicito: ogni mutazione avviene solo da uno slot Qt collegato
a un segnale (sempre sul thread GUI), mai da un thread di lavoro grezzo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineStats:
    indicizzati: int = 0
    identificati: int = 0
    revisione: int = 0
    in_coda: int = 0
    in_trasferimento: int = 0
    archiviati: int = 0
    audit_ok: int = 0
    anomalie: int = 0


def applica_progresso_trasferimento(
    pipeline: PipelineStats, trasferimenti_attivi: set[str], nome: str, percentuale: float
) -> bool:
    """Aggiorna i contatori pipeline per un trasferimento IO in corso.

    Condivisa tra ScansioneController (spostamenti automatici) e
    ApprovazioneController (spostamenti manuali), che nell'originale
    duplicavano la stessa logica di conteggio in due punti diversi.
    Ritorna True se il trasferimento si è appena completato.
    """
    if nome not in trasferimenti_attivi:
        trasferimenti_attivi.add(nome)
        pipeline.in_coda = max(0, pipeline.in_coda - 1)
        pipeline.in_trasferimento += 1

    if percentuale >= 1.0:
        trasferimenti_attivi.discard(nome)
        pipeline.in_trasferimento = max(0, pipeline.in_trasferimento - 1)
        pipeline.archiviati += 1
        pipeline.audit_ok += 1
        return True

    return False


ALTEZZA_MINIMA_PER_RISOLUZIONE = {"480p": 480, "720p": 720, "1080p": 1080, "2160p": 2160}


def film_sotto_risoluzione_minima(tipo: str, r: dict[str, Any], automazione: dict[str, Any]) -> bool:
    """Vero se un film e' sotto la risoluzione minima configurata.

    Condivisa tra ScansioneController (esclude in fase di scansione) e
    ApprovazioneController (esclude dalla coda di revisione manuale anche se
    la soglia viene attivata/cambiata dopo la scansione), cosi' un film
    flaggato sotto soglia non resta visibile in nessuna delle due code.
    """
    if tipo != "film":
        return False
    if not automazione.get("risoluzione_minima_attiva", False):
        return False
    soglia_altezza = ALTEZZA_MINIMA_PER_RISOLUZIONE.get(automazione.get("risoluzione_minima_valore", "720p"), 0)
    altezza = r.get("info_tecnica", {}).get("altezza", 0)
    return altezza > 0 and altezza < soglia_altezza


@dataclass
class AppState:
    sorgente: str = ""
    percorsi: dict[str, str] = field(
        default_factory=lambda: {"film": "", "serie": "", "musica": "", "film_erotici": ""}
    )
    automazione: dict[str, Any] = field(default_factory=dict)
    approvazione_manuale: dict[str, Any] = field(default_factory=dict)
    scan_da_avviare: bool = False
    risultati: list[dict[str, Any]] = field(default_factory=list)
    redirect_post_config: bool = False
    pipeline: PipelineStats = field(default_factory=PipelineStats)
