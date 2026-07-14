import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from app.core.app_state import AppState, PipelineStats, applica_progresso_trasferimento, film_sotto_risoluzione_minima
from app.organizers.universale import OrganizzatoreUniversale
from app.services.job_queue import CodaLavori, EventoCoda, RisultatoJob
from app.services.watchdog_service import SorveglianteDirectory
from app.ui.background import TransferBridge
from app.ui.dialogs import mostra_dialogo_conflitto
from app.ui.models.coda_table_model import ModelloCodaElaborazione

_log = logging.getLogger("gestore_film.principale")

def _analizza_job(organizzatore: OrganizzatoreUniversale, info: dict[str, Any], usa_ai: bool) -> dict[str, Any]:
    """Eseguito su un worker thread di coda_analisi: pura logica, nessun accesso alla UI."""
    return organizzatore.analizza_file(info, usa_ai=usa_ai)


@dataclass
class CanaleStats:
    trovati: int = 0
    riconosciuti: int = 0
    non_riconosciuti: int = 0


class ScansioneController(QObject):
    log_emesso = pyqtSignal(str)
    statistiche_cambiate = pyqtSignal()
    scansione_avviata = pyqtSignal()
    scansione_fermata = pyqtSignal()

    _richiesta_stato_fermo = pyqtSignal()

    def __init__(self, stato: AppState, coda_analisi: CodaLavori, coda_io: CodaLavori) -> None:
        super().__init__()
        self._stato = stato
        self._coda_analisi = coda_analisi
        self._coda_io = coda_io
        self._bridge = TransferBridge()

        self._modello = ModelloCodaElaborazione()
        self._canali: dict[str, CanaleStats] = {"film": CanaleStats(), "serie": CanaleStats(), "musica": CanaleStats()}
        self._righe_per_nome: dict[str, int] = {}
        self._trasferimenti_attivi: set[str] = set()
        self._progresso_corrente: Optional[dict[str, Any]] = None

        self._organizzatore: Optional[OrganizzatoreUniversale] = None
        self._watchdog: Optional[SorveglianteDirectory] = None
        self._interrompi = False
        self._scansione_in_corso = False

        self._coda_analisi.evento.connect(self._al_evento_analisi)
        self._coda_io.evento.connect(self._al_evento_trasferimento)
        self._bridge.progresso_io.connect(self._al_progresso_io)
        self._bridge.conflitto_richiesto.connect(self._al_conflitto)
        self._richiesta_stato_fermo.connect(self._al_scansione_fermata)

    @property
    def stato(self) -> AppState:
        return self._stato

    @property
    def modello(self) -> ModelloCodaElaborazione:
        return self._modello

    @property
    def pipeline(self) -> PipelineStats:
        return self._stato.pipeline

    @property
    def canali(self) -> dict[str, CanaleStats]:
        return self._canali

    @property
    def scansione_in_corso(self) -> bool:
        return self._scansione_in_corso

    @property
    def in_arresto(self) -> bool:
        return self._interrompi and self._scansione_in_corso

    @property
    def progresso_trasferimento_corrente(self) -> Optional[dict[str, Any]]:
        return self._progresso_corrente

    @property
    def totale_risultati(self) -> int:
        return len(self._stato.risultati)

    def avvia_o_ferma(self) -> None:
        if self._scansione_in_corso:
            self.ferma_scansione()
        else:
            self.avvia_scansione()

    def avvia_scansione(self) -> None:
        sorgente = self._stato.sorgente
        if not sorgente:
            self.log_emesso.emit("Nessuna sorgente selezionata: torna alla schermata Percorsi.")
            return

        config_org = {
            "automazione": self._stato.automazione,
            "approvazione_manuale": self._stato.approvazione_manuale,
            "destinazioni": self._stato.percorsi,
        }
        self._organizzatore = OrganizzatoreUniversale(config=config_org)
        self._organizzatore.imposta_callback_log(self.log_emesso.emit)

        self._stato.risultati = []
        self._modello.svuota()
        self._stato.pipeline = PipelineStats()
        self._canali = {"film": CanaleStats(), "serie": CanaleStats(), "musica": CanaleStats()}
        self._righe_per_nome.clear()
        self._trasferimenti_attivi.clear()
        self._progresso_corrente = None
        self._interrompi = False
        self._scansione_in_corso = True
        self.scansione_avviata.emit()
        self.statistiche_cambiate.emit()

        try:
            self._watchdog = SorveglianteDirectory(sorgente, self._al_file_watchdog)
            self._watchdog.avvia()
        except Exception as e:
            self.log_emesso.emit(f"Attenzione: watchdog non avviato: {e}")
            self._watchdog = None

        threading.Thread(target=self._job_scansione, args=(sorgente,), daemon=True).start()

    def ferma_scansione(self) -> None:
        self.log_emesso.emit("Richiesta interruzione scansione inviata...")
        self._interrompi = True

        if self._watchdog:
            try:
                self._watchdog.ferma()
            except Exception:
                pass

        self._coda_analisi.svuota()
        threading.Thread(target=self._attendi_arresto, daemon=True).start()

    def _attendi_arresto(self) -> None:
        while self._coda_analisi.operazioni_attive > 0:
            time.sleep(0.5)
        self._richiesta_stato_fermo.emit()

    def _job_scansione(self, sorgente: str) -> None:
        assert self._organizzatore is not None
        for info in self._organizzatore.scansiona_directory(sorgente):
            if self._interrompi:
                break
            self._coda_analisi.aggiungi_operazione(
                _analizza_job, self._organizzatore, info, self._stato.automazione.get("usa_ai_scansione", False),
                descrizione=f"Analisi {info['nome']}", info_file=info,
            )
        if not self._interrompi:
            self._richiesta_stato_fermo.emit()

    def _al_scansione_fermata(self) -> None:
        self._scansione_in_corso = False
        self._interrompi = False
        self._watchdog = None
        self.log_emesso.emit("Scansione completata/interrotta. Sistema pronto.")
        self.scansione_fermata.emit()
        self.statistiche_cambiate.emit()

    def _al_file_watchdog(self, percorso_nuovo: str) -> None:
        info_file = {
            "nome": os.path.basename(percorso_nuovo),
            "percorso": percorso_nuovo,
            "estensione": os.path.splitext(percorso_nuovo)[1].lower(),
        }
        self.log_emesso.emit(f"Watchdog elabora: {percorso_nuovo}")
        self._coda_analisi.aggiungi_operazione(
            _analizza_job, self._organizzatore, info_file, self._stato.automazione.get("usa_ai_scansione", False),
            descrizione=f"Analisi {info_file['nome']}", info_file=info_file,
        )

    def _aggiorna_riga(self, nome: str, **campi: Any) -> None:
        indice = self._righe_per_nome.get(nome)
        if indice is not None:
            self._modello.aggiorna(indice, campi)

    def _al_evento_analisi(self, evento: EventoCoda) -> None:
        nome = evento.info_file.get("nome", "")
        if evento.azione == "aggiunto":
            self._stato.pipeline.indicizzati += 1
            self._righe_per_nome[nome] = self._modello.aggiungi(
                {"nome": nome, "status": "In attesa", "conf": 0.0, "tipo": "—", "nuovo_nome": "—"}
            )
            self.statistiche_cambiate.emit()
        elif evento.azione == "inizio":
            self._aggiorna_riga(nome, status="Analisi")
        elif evento.azione == "fine" and evento.risultato is not None:
            self._gestisci_fine_analisi(nome, evento.risultato)

    def _gestisci_fine_analisi(self, nome: str, risultato: RisultatoJob) -> None:
        self._stato.pipeline.identificati += 1

        if not risultato.successo:
            self._stato.pipeline.anomalie += 1
            self._aggiorna_riga(nome, status="Anomalia", errore=risultato.errore)
            self.log_emesso.emit(f"Anomalia su {nome}: {risultato.errore}")
            self.statistiche_cambiate.emit()
            return

        r = risultato.valore
        self._stato.risultati.append(r)

        tipo = r.get("tipo_media", "film")
        if tipo not in self._canali:
            tipo = "film"
        canale = self._canali[tipo]
        canale.trovati += 1
        conf = r.get("confidenza", 0.0)
        nuovo_nome = r.get("nome_jellyfin", {}).get("nome_file", "—")

        if "Duplicato" in r.get("status", "") or "presente" in r.get("status", "").lower():
            self._aggiorna_riga(nome, status="Saltato (Esistente)", conf=conf, tipo=tipo, nuovo_nome=nuovo_nome)
            self.log_emesso.emit(f"Saltato (duplicato): {nome}")
            self.statistiche_cambiate.emit()
            return

        if film_sotto_risoluzione_minima(tipo, r, self._stato.automazione):
            self._aggiorna_riga(nome, status="Scartato (Risoluzione bassa)", conf=conf, tipo=tipo, nuovo_nome=nuovo_nome)
            self.log_emesso.emit(f"Scartato (risoluzione insufficiente): {nome}")
            self.statistiche_cambiate.emit()
            return

        auto = self._stato.automazione
        soglia_auto = auto.get("soglia", 0.85)
        if conf >= soglia_auto:
            canale.riconosciuti += 1
        else:
            canale.non_riconosciuti += 1

        if auto.get("attiva") and conf >= soglia_auto:
            dest = self._stato.percorsi.get(tipo)
            if dest:
                azione_nome = auto.get("azione", "Sposta")
                self._stato.pipeline.in_coda += 1
                self._aggiorna_riga(nome, status=f"In Ingestion ({azione_nome})", conf=conf, tipo=tipo, nuovo_nome=nuovo_nome)
                self._coda_io.aggiungi_operazione(
                    self._organizzatore.sposta_file,
                    r, dest, azione_nome, auto.get("pulisci_vuote", True),
                    self._bridge.progresso_io.emit, self._bridge.conflitto_richiesto.emit,
                    descrizione=f"{azione_nome} {nome}", info_file={"nome": nome},
                )
            else:
                self._stato.pipeline.revisione += 1
                self._aggiorna_riga(nome, status="In Revisione", conf=conf, tipo=tipo, nuovo_nome=nuovo_nome)
                self.log_emesso.emit(f"Destinazione {tipo} non configurata per: {nome}")
        else:
            self._stato.pipeline.revisione += 1
            self._aggiorna_riga(nome, status="In Revisione", conf=conf, tipo=tipo, nuovo_nome=nuovo_nome)
            self.log_emesso.emit(f"Revisione manuale: {nome} (Conf: {int(conf * 100)}%)")

        self.statistiche_cambiate.emit()

    def _al_evento_trasferimento(self, evento: EventoCoda) -> None:
        if evento.azione == "inizio":
            self.log_emesso.emit(f"[IO] Inizio: {evento.descrizione}")
        elif evento.azione == "fine" and evento.risultato is not None and not evento.risultato.successo:
            self.log_emesso.emit(f"[IO] Errore: {evento.risultato.errore}")

    def _al_progresso_io(self, r: dict[str, Any], p: dict[str, Any]) -> None:
        nome = r.get("file_originale", "")
        percentuale = p.get("percentuale", 0.0)
        self._progresso_corrente = {
            "nome": nome,
            "percentuale": percentuale,
            "velocita": p.get("velocita", 0.0),
            "etr": p.get("etr", 0.0),
        }
        self._aggiorna_riga(nome, status=f"IO ({int(percentuale * 100)}%)")

        completato = applica_progresso_trasferimento(self._stato.pipeline, self._trasferimenti_attivi, nome, percentuale)
        if completato:
            self._aggiorna_riga(nome, status="Archiviato")
            self._progresso_corrente = None
            self.log_emesso.emit(f"Archiviato: {nome}")

        self.statistiche_cambiate.emit()

    def _al_conflitto(self, r: dict[str, Any], dettagli: dict[str, Any]) -> None:
        if self._organizzatore:
            mostra_dialogo_conflitto(self._organizzatore, dettagli)
