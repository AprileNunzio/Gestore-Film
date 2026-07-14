import logging
import os
import threading
from typing import Any, Optional
import requests
from PyQt6.QtCore import QObject, pyqtSignal

from app.core.app_state import AppState, film_sotto_risoluzione_minima
from app.organizers.universale import OrganizzatoreUniversale
from app.services.job_queue import CodaLavori

_log = logging.getLogger("gestore_film.approvazione")
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w300"


class ApprovazioneController(QObject):
    statistiche_cambiate = pyqtSignal()
    elemento_cambiato = pyqtSignal()
    messaggio_notifica = pyqtSignal(str, str)
    immagine_scaricata = pyqtSignal(bytes)

    def __init__(self, stato: AppState, coda_analisi: CodaLavori, coda_io: CodaLavori) -> None:
        super().__init__()
        self._stato = stato
        self._coda_analisi = coda_analisi
        self._coda_io = coda_io
        self._indice = 0
        self._stati: dict[int, str] = {}
        self._lista_filtrata: list[dict[str, Any]] = []

    @property
    def stato(self) -> AppState:
        return self._stato

    @property
    def indice_corrente(self) -> int:
        return self._indice

    @property
    def totale_elementi(self) -> int:
        return len(self._lista_filtrata)

    @property
    def elemento_corrente(self) -> Optional[dict[str, Any]]:
        if 0 <= self._indice < self.totale_elementi:
            return self._lista_filtrata[self._indice]
        return None

    def ricalcola_lista(self) -> None:
        risultati_tutti = self._stato.risultati
        automazione_attiva = self._stato.automazione.get("attiva", False)
        soglia = self._stato.automazione.get("soglia", 0.85)

        nuova_lista = []
        for r in risultati_tutti:
            status = r.get("status", "")
            if "Duplicato" in status or "presente" in status.lower():
                continue
            if film_sotto_risoluzione_minima(r.get("tipo_media", "film"), r, self._stato.automazione):
                continue
            if automazione_attiva and r.get("confidenza", 0.0) >= soglia:
                continue
            nuova_lista.append(r)

        if len(self._lista_filtrata) == len(nuova_lista):
            uguali = True
            for a, b in zip(self._lista_filtrata, nuova_lista):
                if a.get("file_originale") != b.get("file_originale"):
                    uguali = False
                    break
            if uguali:
                return

        nome_file_corrente = ""
        if self.elemento_corrente:
            nome_file_corrente = self.elemento_corrente.get("file_originale", "")

        self._lista_filtrata = nuova_lista
        
        nuovo_indice = 0
        if nome_file_corrente:
            for i, r in enumerate(self._lista_filtrata):
                if r.get("file_originale") == nome_file_corrente:
                    nuovo_indice = i
                    break
                    
        self.vai_a_indice(nuovo_indice)
        self.statistiche_cambiate.emit()

    def vai_a_indice(self, indice: int) -> None:
        if self.totale_elementi == 0:
            self._indice = 0
            self.elemento_cambiato.emit()
            return

        self._indice = max(0, min(indice, self.totale_elementi - 1))
        self.elemento_cambiato.emit()
        self._carica_immagine_corrente()

    def naviga(self, delta: int) -> None:
        self.vai_a_indice(self._indice + delta)

    def _rimuovi_corrente(self, esito: str) -> None:
        if 0 <= self._indice < self.totale_elementi:
            r = self._lista_filtrata.pop(self._indice)
            if r in self._stato.risultati:
                self._stato.risultati.remove(r)
            
        self.vai_a_indice(self._indice)
        self.statistiche_cambiate.emit()

    def _carica_immagine_corrente(self) -> None:
        el = self.elemento_corrente
        if not el:
            self.immagine_scaricata.emit(b"")
            return
        
        match = el.get("match_principale", {})
        poster = match.get("poster_path", "")
        if not poster:
            self.immagine_scaricata.emit(b"")
            return
        
        url = f"{TMDB_IMAGE_BASE}{poster}"
        
        def _scarica_su_thread():
            try:
                risposta = requests.get(url, timeout=5)
                risposta.raise_for_status()
                self.immagine_scaricata.emit(risposta.content)
            except Exception as e:
                _log.error(f"Impossibile scaricare poster da {url}: {e}")
                self.immagine_scaricata.emit(b"")
                
        threading.Thread(target=_scarica_su_thread, daemon=True).start()

    def sposta_corrente(self, percorso_override: str = "") -> None:
        self.esegui_azione_corrente("Sposta", percorso_override)

    def copia_corrente(self, percorso_override: str = "") -> None:
        self.esegui_azione_corrente("Copia", percorso_override)

    def rinomina_corrente(self) -> None:
        el = self.elemento_corrente
        if not el: return
        target = os.path.dirname(el.get("percorso_originale", ""))
        self.esegui_azione_corrente("Sposta", target)

    def esegui_azione_corrente(self, azione_override: str, percorso_override: str = "") -> None:
        el = self.elemento_corrente
        if not el:
            return

        config_org = {
            "automazione": self._stato.automazione,
            "approvazione_manuale": self._stato.approvazione_manuale,
            "destinazioni": self._stato.percorsi,
        }
        org = OrganizzatoreUniversale(config=config_org)
        
        tipo = el.get("tipo_media", "film")
        target = percorso_override.strip() or self._stato.percorsi.get(tipo, "")
        
        if not target:
            self.messaggio_notifica.emit("Percorso di destinazione non configurato!", "error")
            return

        impostazioni_manuali = self._stato.approvazione_manuale
        azione = azione_override
        pulisci = impostazioni_manuali.get("pulisci_vuote", False)

        from app.ui.background import TransferBridge
        bridge = TransferBridge()

        def _al_progresso_io(r: dict[str, Any], p: dict[str, Any]) -> None:
            pass
            
        def _al_conflitto(r: dict[str, Any], dettagli: dict[str, Any]) -> None:
            from app.ui.dialogs import mostra_dialogo_conflitto
            mostra_dialogo_conflitto(org, dettagli)

        try:
            self._temp_bridge = bridge 
            self._temp_bridge.progresso_io.connect(_al_progresso_io)
            self._temp_bridge.conflitto_richiesto.connect(_al_conflitto)
            
            self._stato.pipeline.in_coda += 1
            self._stato.pipeline.revisione -= 1
            
            self._coda_io.aggiungi_operazione(
                org.sposta_file,
                el, target, azione, pulisci, self._temp_bridge.progresso_io.emit, self._temp_bridge.conflitto_richiesto.emit,
                descrizione=f"Manuale: {azione} {el.get('file_originale')}",
                info_file={"nome": el.get("file_originale")},
            )
            self.messaggio_notifica.emit(f"Task di {azione.lower()} aggiunto alla coda di ingestion!", "success")
            self._rimuovi_corrente("processato")
        except Exception as ex:
            self.messaggio_notifica.emit(f"Errore inserimento coda: {ex}", "error")

    def salta_corrente(self) -> None:
        el = self.elemento_corrente
        if not el: return
        self._stato.pipeline.revisione -= 1
        self._rimuovi_corrente("saltato")
        self.messaggio_notifica.emit("File saltato", "warning")

    def elimina_corrente(self) -> None:
        el = self.elemento_corrente
        if not el: return
        percorso = el.get("percorso_originale", "")
        try:
            if percorso and os.path.exists(percorso):
                os.remove(percorso)
            self._stato.pipeline.revisione -= 1
            self._rimuovi_corrente("eliminato")
            self.messaggio_notifica.emit("File eliminato dal disco", "error")
        except Exception as ex:
            self.messaggio_notifica.emit(f"Errore eliminazione: {ex}", "error")

    def rianalizza_tecnico_corrente(self) -> None:
        """Ritenta l'analisi ffmpeg per il file corrente (es. dopo un fallimento
        di rete transitorio durante la scansione originale — vedi
        app/services/ffmpeg_service.py, che ora ritenta da solo ma può comunque
        esaurire i tentativi su una condivisione di rete lenta/instabile)."""
        el = self.elemento_corrente
        if not el:
            return

        percorso = el.get("percorso_originale", "")
        self.messaggio_notifica.emit("Rianalisi tecnica in corso...", "info")

        def _rianalizza_su_thread() -> None:
            from app.services import ffmpeg_service
            info_tecnica = ffmpeg_service.analizza_tecnico(percorso)
            el["info_tecnica"] = info_tecnica
            if info_tecnica.get("larghezza"):
                self.messaggio_notifica.emit("Analisi tecnica completata", "success")
            else:
                self.messaggio_notifica.emit("Analisi tecnica ancora non riuscita per questo file", "error")
            self.elemento_cambiato.emit()

        threading.Thread(target=_rianalizza_su_thread, daemon=True).start()

    def cambia_variante(self, index: int, data: str) -> None:
        el = self.elemento_corrente
        if not el: return
        
        varianti = el.get("varianti", [])
        for v in varianti:
            if str(v.get("tmdb_id", "")) == data:
                el["match_principale"] = v
                config_org = {
                    "automazione": self._stato.automazione,
                    "approvazione_manuale": self._stato.approvazione_manuale,
                    "destinazioni": self._stato.percorsi,
                }
                org = OrganizzatoreUniversale(config=config_org)
                g = el.get("gemini", {})
                titolo_it = g.get("titolo_italiano", "") or v.get("titolo", "")
                nome_ep = el.get("nome_episodio", "")
                
                tipo_media = el.get("tipo_media", "film")
                if tipo_media == "serie" and v.get("tmdb_id"):
                    try:
                        from app.services import tmdb_service
                        stagione = el.get("stagione", "01")
                        episodio = el.get("episodio", "01")
                        nome_ep = tmdb_service.recupera_nome_episodio(int(v["tmdb_id"]), int(stagione), int(episodio))
                        el["nome_episodio"] = nome_ep
                    except Exception:
                        pass
                
                nm = org.costruisci_nome_jellyfin(
                    titolo_it, v, el.get("info_tecnica", {}), el.get("estensione", ""),
                    tipo_media=tipo_media, nome_episodio=nome_ep,
                    stagione=el.get("stagione", "01"), episodio=el.get("episodio", "01")
                )
                el["nome_jellyfin"] = nm
                self.elemento_cambiato.emit()
                self._carica_immagine_corrente()
                break


    def applica_risultato_manuale(self, risultato: dict[str, Any]) -> None:
        el = self.elemento_corrente
        if not el: return
        el["match_principale"] = risultato
        
        varianti = el.get("varianti", [])
        if not any(v.get("tmdb_id") == risultato.get("tmdb_id") for v in varianti):
            varianti.insert(0, risultato)
            el["varianti"] = varianti
            
        config_org = {
            "automazione": self._stato.automazione,
            "approvazione_manuale": self._stato.approvazione_manuale,
            "destinazioni": self._stato.percorsi,
        }
        org = OrganizzatoreUniversale(config=config_org)
        
        g = el.get("gemini", {})
        titolo_it = g.get("titolo_italiano", "") or risultato.get("titolo", "")
        nome_ep = el.get("nome_episodio", "")
        tipo_media = risultato.get("tipo", "film")
        el["tipo_media"] = tipo_media
        
        nm = org.costruisci_nome_jellyfin(
            titolo_it, risultato, el.get("info_tecnica", {}), el.get("estensione", ""),
            tipo_media=tipo_media, nome_episodio=nome_ep,
            stagione=el.get("stagione", "01"), episodio=el.get("episodio", "01")
        )
        el["nome_jellyfin"] = nm
        self.elemento_cambiato.emit()
        self._carica_immagine_corrente()
