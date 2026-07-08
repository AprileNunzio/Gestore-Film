"""Motore di background job basato su QThreadPool, sostituisce servizio_coda.GestoreCoda.

Differenza chiave rispetto all'originale: GestoreCoda aveva un singolo slot
`callback_stato` che le schermate si "rubavano" a vicenda registrandosi in
sequenza (bug osservato durante l'analisi di Script_Film). Qui gli
aggiornamenti sono un segnale Qt (`CodaLavori.evento`), che supporta
nativamente più subscriber.

Il segnale è emesso da un metodo *bound* di CodaLavori (un QObject creato sul
thread GUI): questo è ciò che permette a Qt di riconoscere il mismatch di
thread quando il job gira su un worker del QThreadPool e di marshalare
automaticamente la notifica sul thread GUI (connessione queued automatica).
Collegare il segnale a una funzione lambda/anonima invece di un bound method
romperebbe questa garanzia (Qt non saprebbe a quale thread appartiene il
ricevente e chiamerebbe lo slot direttamente sul worker thread).
"""
from __future__ import annotations

import logging
import os
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

_log = logging.getLogger("gestore_film.principale")


@dataclass
class RisultatoJob:
    successo: bool
    valore: Any = None
    errore: str = ""


@dataclass
class EventoCoda:
    azione: str  # "aggiunto" | "inizio" | "fine" | "svuotata"
    coda_nome: str
    descrizione: str = ""
    info_file: dict = field(default_factory=dict)
    risultato: Optional[RisultatoJob] = None
    coda_lunghezza: int = 0


@dataclass
class _JobEsito:
    job_id: int
    coda_nome: str
    descrizione: str
    info_file: dict


class _JobSignals(QObject):
    finito = pyqtSignal(object, object)  # (_JobEsito, RisultatoJob)


class _Job(QRunnable):
    def __init__(
        self,
        coda_nome: str,
        funzione: Callable[..., Any],
        args: tuple,
        kwargs: dict,
        descrizione: str,
        info_file: dict,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)  # la vita del job è gestita da CodaLavori._job_in_volo
        self.coda_nome = coda_nome
        self.funzione = funzione
        self.args = args
        self.kwargs = kwargs
        self.descrizione = descrizione
        self.info_file = info_file
        self.signals = _JobSignals()

    def run(self) -> None:
        esito = _JobEsito(id(self), self.coda_nome, self.descrizione, self.info_file)
        try:
            valore = self.funzione(*self.args, **self.kwargs)
            self.signals.finito.emit(esito, RisultatoJob(successo=True, valore=valore))
        except Exception as e:
            _log.error(f"Errore job '{self.descrizione}': {e}\n{traceback.format_exc()}")
            self.signals.finito.emit(esito, RisultatoJob(successo=False, errore=str(e)))


class CodaLavori(QObject):
    """Una coda di job con un pool di worker dedicato e segnali multi-subscriber."""

    evento = pyqtSignal(object)  # EventoCoda

    def __init__(self, nome: str, num_workers: int, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.nome = nome
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(max(1, num_workers))
        self._operazioni_attive = 0
        self._job_in_volo: dict[int, _Job] = {}

    @property
    def operazioni_attive(self) -> int:
        return self._operazioni_attive

    def aggiungi_operazione(
        self,
        funzione: Callable[..., Any],
        *args: Any,
        descrizione: str = "Operazione generica",
        info_file: Optional[dict] = None,
        **kwargs: Any,
    ) -> None:
        info_file = info_file or {}
        job = _Job(self.nome, funzione, args, kwargs, descrizione, info_file)
        job.signals.finito.connect(self._al_completamento)

        self._job_in_volo[id(job)] = job
        self._operazioni_attive += 1

        self.evento.emit(
            EventoCoda(
                azione="aggiunto",
                coda_nome=self.nome,
                descrizione=descrizione,
                info_file=info_file,
                coda_lunghezza=self._operazioni_attive,
            )
        )
        self.evento.emit(
            EventoCoda(azione="inizio", coda_nome=self.nome, descrizione=descrizione, info_file=info_file)
        )
        self._pool.start(job)

    def _al_completamento(self, esito: _JobEsito, risultato: RisultatoJob) -> None:
        self._job_in_volo.pop(esito.job_id, None)
        self._operazioni_attive = max(0, self._operazioni_attive - 1)
        self.evento.emit(
            EventoCoda(
                azione="fine",
                coda_nome=esito.coda_nome,
                descrizione=esito.descrizione,
                info_file=esito.info_file,
                risultato=risultato,
                coda_lunghezza=self._operazioni_attive,
            )
        )

    def svuota(self) -> None:
        """Rimuove i job non ancora avviati; quelli già in esecuzione completano comunque."""
        self._pool.clear()
        self._job_in_volo.clear()
        self._operazioni_attive = 0
        self.evento.emit(EventoCoda(azione="svuotata", coda_nome=self.nome, coda_lunghezza=0))

    def attendi_completamento(self, timeout_ms: int = -1) -> bool:
        return self._pool.waitForDone(timeout_ms)


_cpu_count = max(4, os.cpu_count() or 4)


def crea_code(parent: Optional[QObject] = None) -> tuple[CodaLavori, CodaLavori]:
    """Crea le due code standard dell'app: analisi (network/CPU bound) e IO (limitata)."""
    coda_analisi = CodaLavori("Analisi", num_workers=_cpu_count * 2, parent=parent)
    coda_io = CodaLavori("IO", num_workers=min(4, _cpu_count), parent=parent)
    return coda_analisi, coda_io
