"""Servizio di generazione Trickplay. Porta Script_Film/generatore_trickplay.py.

Si appoggia a ffmpeg e ffprobe preconfigurati tramite AppPaths.
"""
from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app.core.config import ESTENSIONI_VIDEO

_log = logging.getLogger("gestore_film.trickplay")

_ffmpeg_exe: Path | None = None
_ffprobe_exe: Path | None = None

def configura(ffmpeg_exe: Path, ffprobe_exe: Path) -> None:
    global _ffmpeg_exe, _ffprobe_exe
    _ffmpeg_exe = ffmpeg_exe
    _ffprobe_exe = ffprobe_exe


@dataclass
class ImpostazioniTrickplay:
    intervallo_secondi: int = 10
    larghezza_tile: int = 320
    colonne_griglia: int = 10
    righe_griglia: int = 10
    thread_paralleli: int = 1
    solo_keyframe: bool = True
    qualita_jpeg: int = 85

    @property
    def frame_per_tile(self) -> int:
        return self.colonne_griglia * self.righe_griglia

    @property
    def thread_effettivi(self) -> int:
        if self.thread_paralleli <= 0:
            return max(1, os.cpu_count() or 4)
        return self.thread_paralleli


@dataclass
class InfoVideo:
    percorso: str
    nome: str = ""
    durata_secondi: float = 0.0
    ha_trickplay: bool = False
    stato: str = "In attesa"
    progresso: float = 0.0
    errore: str = ""
    frame_totali_stimati: int = 0
    frame_generati: int = 0
    dimensione_generata: int = 0

    def __post_init__(self):
        if not self.nome:
            self.nome = os.path.splitext(os.path.basename(self.percorso))[0]


@dataclass
class StatisticheTrickplay:
    video_totali: int = 0
    video_completati: int = 0
    video_saltati: int = 0
    video_errore: int = 0
    dimensione_totale: int = 0
    tempo_trascorso: float = 0.0


class GeneratoreTrickplay:
    def __init__(self, impostazioni: Optional[ImpostazioniTrickplay] = None):
        self.impostazioni = impostazioni or ImpostazioniTrickplay()
        self._stop = threading.Event()
        self._in_esecuzione = False
        self._callback_progresso: Optional[Callable] = None
        self._callback_stato: Optional[Callable] = None
        self._statistiche = StatisticheTrickplay()
        self._lock = threading.Lock()

    def ferma(self) -> None:
        self._stop.set()

    @property
    def in_esecuzione(self) -> bool:
        return self._in_esecuzione

    def _ottieni_durata(self, percorso_video: str) -> float:
        if not _ffprobe_exe:
            return 0.0
        try:
            cmd = [
                str(_ffprobe_exe),
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                percorso_video
            ]
            risultato = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                encoding="utf-8", errors="replace"
            )
            dati = json.loads(risultato.stdout)
            return float(dati.get("format", {}).get("duration", 0))
        except Exception as e:
            _log.warning(f"Impossibile ottenere durata per {percorso_video}: {e}")
            return 0.0

    def _percorso_trickplay(self, percorso_video: str) -> str:
        cartella_video = os.path.dirname(percorso_video)
        nome_video = os.path.splitext(os.path.basename(percorso_video))[0]
        nome_sottocartella = f"{self.impostazioni.larghezza_tile} - {self.impostazioni.colonne_griglia}x{self.impostazioni.righe_griglia}"
        return os.path.join(
            cartella_video,
            f"{nome_video}.trickplay",
            nome_sottocartella
        )

    def _ha_trickplay_esistente(self, percorso_video: str) -> bool:
        cartella_video = os.path.dirname(percorso_video)
        nome_video = os.path.splitext(os.path.basename(percorso_video))[0]
        cartella_trickplay = os.path.join(cartella_video, f"{nome_video}.trickplay")
        if not os.path.isdir(cartella_trickplay):
            return False
        for sotto in os.listdir(cartella_trickplay):
            percorso_sotto = os.path.join(cartella_trickplay, sotto)
            if os.path.isdir(percorso_sotto):
                file_jpg = [f for f in os.listdir(percorso_sotto) if f.lower().endswith(".jpg")]
                if len(file_jpg) > 0:
                    return True
        return False

    def scansiona_cartella(self, cartella: str) -> list[InfoVideo]:
        risultati = []
        if not os.path.isdir(cartella):
            return risultati

        for radice, _, file in os.walk(cartella):
            if ".trickplay" in radice:
                continue
            for nome_file in sorted(file):
                estensione = os.path.splitext(nome_file)[1].lower()
                if estensione not in ESTENSIONI_VIDEO:
                    continue

                percorso = os.path.join(radice, nome_file)
                info = InfoVideo(percorso=percorso)
                info.ha_trickplay = self._ha_trickplay_esistente(percorso)

                if info.ha_trickplay:
                    info.stato = "Già generato"
                    info.progresso = 1.0
                else:
                    info.durata_secondi = self._ottieni_durata(percorso)
                    if info.durata_secondi > 0:
                        info.frame_totali_stimati = max(1, int(
                            info.durata_secondi / self.impostazioni.intervallo_secondi
                        ))

                risultati.append(info)

        return risultati

    def _estrai_sprite_diretto(self, percorso_video: str, cartella_dest: str, info: InfoVideo) -> bool:
        if not _ffmpeg_exe:
            info.errore = "FFmpeg non configurato"
            return False
        try:
            durata = info.durata_secondi or self._ottieni_durata(percorso_video)
            if durata > 0:
                frame_totali = max(1, int(durata / self.impostazioni.intervallo_secondi))
                frame_per_tile = self.impostazioni.frame_per_tile
                info.frame_totali_stimati = math.ceil(frame_totali / frame_per_tile)
            else:
                info.frame_totali_stimati = 1

            filtro_fps = f"fps=1/{self.impostazioni.intervallo_secondi}"
            filtro_scala = f"scale={self.impostazioni.larghezza_tile}:-1"
            filtro_griglia = f"tile={self.impostazioni.colonne_griglia}x{self.impostazioni.righe_griglia}"

            cmd = [str(_ffmpeg_exe), "-y", "-v", "error", "-nostdin", "-nostats", "-hwaccel", "auto"]

            if self.impostazioni.solo_keyframe:
                cmd.extend(["-skip_frame", "nokey"])

            cmd.extend([
                "-i", percorso_video,
                "-threads", "0",
                "-vf", f"{filtro_fps},{filtro_scala},{filtro_griglia}",
                "-q:v", str(max(1, min(31, int((100 - self.impostazioni.qualita_jpeg) * 31 / 100)))),
                "-start_number", "0",
                os.path.join(cartella_dest, "%d.jpg")
            ])

            processo = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )

            ultimo_aggiornamento = time.time()

            while processo.poll() is None:
                if self._stop.is_set():
                    processo.kill()
                    return False
                    
                ora = time.time()
                if ora - ultimo_aggiornamento > 0.5:
                    file_generati = [f for f in os.listdir(cartella_dest) if f.endswith(".jpg")]
                    info.frame_generati = len(file_generati)
                    
                    if info.frame_totali_stimati > 0:
                        info.progresso = min(0.99, info.frame_generati / info.frame_totali_stimati)
                        
                    if self._callback_progresso:
                        self._callback_progresso(info)
                        
                    ultimo_aggiornamento = ora

                time.sleep(0.1)

            processo.communicate()

            if processo.returncode != 0:
                info.errore = f"FFMpeg terminato con codice {processo.returncode}"
                _log.error(f"Errore FFMpeg per {percorso_video} (Code {processo.returncode})")
                return False

            return True

        except Exception as e:
            info.errore = str(e)
            _log.error(f"Errore generazione diretta {percorso_video}: {e}")
            return False

    def _processa_video(self, info: InfoVideo) -> bool:
        if self._stop.is_set():
            return False

        if info.ha_trickplay:
            info.stato = "Già generato"
            info.progresso = 1.0
            with self._lock:
                self._statistiche.video_saltati += 1
            return True

        info.stato = "In elaborazione"
        info.progresso = 0.0
        if self._callback_stato:
            self._callback_stato(info)

        cartella_dest = self._percorso_trickplay(info.percorso)
        os.makedirs(cartella_dest, exist_ok=True)

        try:
            info.stato = "Generazione trickplay..."
            if self._callback_stato:
                self._callback_stato(info)

            successo = self._estrai_sprite_diretto(info.percorso, cartella_dest, info)
            
            if not successo:
                info.stato = "Errore"
                if os.path.isdir(cartella_dest):
                    shutil.rmtree(cartella_dest, ignore_errors=True)
                if self._callback_stato:
                    self._callback_stato(info)
                with self._lock:
                    self._statistiche.video_errore += 1
                return False

            info.stato = "Completato"
            info.progresso = 1.0
            info.ha_trickplay = True
            
            file_finali = [f for f in os.listdir(cartella_dest) if f.endswith('.jpg')]
            info.frame_generati = len(file_finali)
            info.frame_totali_stimati = len(file_finali)
            dimensione = sum(os.path.getsize(os.path.join(cartella_dest, f)) for f in file_finali)
            info.dimensione_generata = dimensione
            
            if self._callback_stato:
                self._callback_stato(info)

            with self._lock:
                self._statistiche.video_completati += 1
                self._statistiche.dimensione_totale += info.dimensione_generata

            return True

        except Exception as e:
            info.errore = str(e)
            info.stato = "Errore"
            if self._callback_stato:
                self._callback_stato(info)
            with self._lock:
                self._statistiche.video_errore += 1
            return False

    def genera(
        self,
        lista_video: list[InfoVideo],
        callback_progresso: Optional[Callable] = None,
        callback_stato: Optional[Callable] = None,
        callback_completamento: Optional[Callable] = None
    ) -> None:
        self._stop.clear()
        self._in_esecuzione = True
        self._callback_progresso = callback_progresso
        self._callback_stato = callback_stato

        da_processare = [v for v in lista_video if not v.ha_trickplay]
        self._statistiche = StatisticheTrickplay(
            video_totali=len(da_processare),
            video_saltati=len(lista_video) - len(da_processare)
        )

        inizio = time.time()

        def _esegui():
            try:
                num_thread = min(
                    self.impostazioni.thread_effettivi,
                    len(da_processare)
                ) if da_processare else 1

                if num_thread <= 1:
                    for video in da_processare:
                        if self._stop.is_set():
                            break
                        self._processa_video(video)
                else:
                    with ThreadPoolExecutor(max_workers=num_thread) as pool:
                        futures = {
                            pool.submit(self._processa_video, video): video
                            for video in da_processare
                        }
                        for future in as_completed(futures):
                            if self._stop.is_set():
                                pool.shutdown(wait=False, cancel_futures=True)
                                break
                            try:
                                future.result()
                            except Exception as e:
                                video = futures[future]
                                video.stato = "Errore"
                                video.errore = str(e)
                                _log.error(f"Errore thread per {video.nome}: {e}")

                self._statistiche.tempo_trascorso = time.time() - inizio

            finally:
                self._in_esecuzione = False
                if callback_completamento:
                    callback_completamento(self._statistiche)

        thread = threading.Thread(target=_esegui, daemon=True)
        thread.start()

    @property
    def statistiche(self) -> StatisticheTrickplay:
        return self._statistiche

    @staticmethod
    def formatta_dimensione(byte: int) -> str:
        if byte < 1024:
            return f"{byte} B"
        elif byte < 1024 ** 2:
            return f"{byte / 1024:.1f} KB"
        elif byte < 1024 ** 3:
            return f"{byte / 1024**2:.1f} MB"
        else:
            return f"{byte / 1024**3:.2f} GB"

    @staticmethod
    def formatta_durata(secondi: float) -> str:
        if secondi < 60:
            return f"{int(secondi)}s"
        elif secondi < 3600:
            m = int(secondi // 60)
            s = int(secondi % 60)
            return f"{m}m {s}s"
        else:
            h = int(secondi // 3600)
            m = int((secondi % 3600) // 60)
            return f"{h}h {m}m"
