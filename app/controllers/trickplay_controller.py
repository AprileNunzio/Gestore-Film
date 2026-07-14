import threading
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from app.core.app_state import AppState
from app.services.trickplay_service import GeneratoreTrickplay, ImpostazioniTrickplay, InfoVideo, StatisticheTrickplay

class TrickplayController(QObject):
    stato_cambiato = pyqtSignal(str)
    progresso_globale = pyqtSignal(int, int)
    lista_aggiornata = pyqtSignal(list)
    statistiche_aggiornate = pyqtSignal(object)
    completato = pyqtSignal()

    def __init__(self, stato: AppState) -> None:
        super().__init__()
        self._stato = stato
        self._generatore = GeneratoreTrickplay()
        self.lista_video: list[InfoVideo] = []
        self.scansione_in_corso = False

        self._timer_ui = QTimer()
        self._timer_ui.timeout.connect(self._al_tick_ui)

    def analizza(self, cartella: str, impostazioni: ImpostazioniTrickplay, sovrascrivi: bool) -> None:
        self.scansione_in_corso = True
        self.stato_cambiato.emit("Scansione cartella in corso...")
        self.lista_video.clear()
        self.lista_aggiornata.emit(self.lista_video)
        
        self._generatore.impostazioni = impostazioni

        def _scan() -> None:
            try:
                risultati = self._generatore.scansiona_cartella(cartella)
                if sovrascrivi:
                    for v in risultati:
                        v.ha_trickplay = False
                        v.stato = "In attesa"
                        v.progresso = 0.0
                
                self.lista_video = risultati
                
                da_generare = sum(1 for v in self.lista_video if not v.ha_trickplay)
                gia_ok = sum(1 for v in self.lista_video if v.ha_trickplay)
                
                msg = f"{len(self.lista_video)} video trovati — {gia_ok} già generati, {da_generare} da generare."
                
                self.lista_aggiornata.emit(self.lista_video)
                self.stato_cambiato.emit(msg)
            except Exception as e:
                self.stato_cambiato.emit(f"Errore scansione: {e}")
            finally:
                self.scansione_in_corso = False

        threading.Thread(target=_scan, daemon=True).start()

    def genera(self) -> None:
        if not self.lista_video:
            self.stato_cambiato.emit("Nessun video da processare.")
            return

        self.stato_cambiato.emit("Avvio generazione in corso...")
        self._timer_ui.start(1000)

        def _al_completamento(stats: StatisticheTrickplay) -> None:
            self._timer_ui.stop()
            self.completato.emit()
            self.lista_aggiornata.emit(self.lista_video)
            self.statistiche_aggiornate.emit(stats)
            self.stato_cambiato.emit("Generazione completata!")

        self._generatore.genera(
            self.lista_video,
            callback_completamento=_al_completamento
        )

    def ferma(self) -> None:
        self.stato_cambiato.emit("Interruzione in corso...")
        self._generatore.ferma()

    def _al_tick_ui(self) -> None:
        if self._generatore.in_esecuzione:
            self.lista_aggiornata.emit(self.lista_video)
            stats = self._generatore.statistiche
            tot = stats.video_totali
            compl = stats.video_completati + stats.video_errore
            self.progresso_globale.emit(compl, tot)
            self.statistiche_aggiornate.emit(stats)
