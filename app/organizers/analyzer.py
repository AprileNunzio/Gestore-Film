import logging
import os
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from app.core.config import ESTENSIONI_AUDIO
from app.services import ffmpeg_service, gemini_service, media_parsing, tmdb_service

_log_non_riconosciuti = logging.getLogger("gestore_film.non_riconosciuti")
_PATTERN_TMDB_ID = re.compile(r"\[tmdbid-(\d+)\]", re.I)

class AnalyzerUniversale:
    """Micro-servizio responsabile unicamente per l'analisi e classificazione dei media."""

    @staticmethod
    def _estrai_contesto_percorso(percorso: str) -> tuple[str, str]:
        if percorso.lower().startswith("ftp://"):
            p_fisico = unquote(urlparse(percorso).path or "/")
            parti = [p for p in p_fisico.replace("\\", "/").split("/") if p]
            padre = parti[-2] if len(parti) > 1 else ""
            nonno = parti[-3] if len(parti) > 2 else ""
        else:
            path_obj = Path(percorso)
            padre = path_obj.parent.name
            nonno = path_obj.parent.parent.name
        return padre, nonno

    @classmethod
    def analizza_file(
        cls,
        info: dict[str, Any],
        config: dict[str, Any],
        motore_film: Any,
        motore_serie: Any,
        motore_musica: Any,
        mappa_destinazione: dict[str, Any],
        lock_mappa: Any,
        usa_ai: bool = False
    ) -> dict[str, Any]:
        nome = info["nome"]
        percorso = info["percorso"]
        est = info["estensione"]

        if est in ESTENSIONI_AUDIO:
            res = motore_musica.analizza_file(info)
            res["tipo_media"] = "musica"
            return cls._arricchisci_e_controlla(res, info, config, motore_film, motore_serie, motore_musica, mappa_destinazione, lock_mappa)

        id_suggerito, tipo_suggerito = media_parsing.cerca_id_tmdb_locale(percorso)
        tmdb_match = _PATTERN_TMDB_ID.search(percorso)
        tid = id_suggerito or (int(tmdb_match.group(1)) if tmdb_match else None)

        if tid:
            if not tipo_suggerito:
                s, e, f = media_parsing.estrai_stagione_episodio(nome)
                if s and e and f != "debole":
                    tipo_suggerito = "serie"

            info_tmdb = tmdb_service.recupera_da_id(tid, tipo_richiesto=tipo_suggerito)
            if not info_tmdb and tipo_suggerito:
                info_tmdb = tmdb_service.recupera_da_id(tid)

            if info_tmdb:
                if info_tmdb["tipo"] == "film":
                    res = motore_film.analizza_file(info)
                    res["tipo_media"] = "film"
                    res["confidenza"] = 1.0
                    res["match_principale"] = {
                        "tmdb_id": tid,
                        "titolo": info_tmdb.get("titolo_it_tmdb", ""),
                        "anno": info_tmdb.get("anno", ""),
                        "tipo": "film",
                    }
                    return cls._arricchisci_e_controlla(res, info, config, motore_film, motore_serie, motore_musica, mappa_destinazione, lock_mappa)
                if info_tmdb["tipo"] == "serie":
                    stag, ep, _forza = media_parsing.estrai_stagione_episodio(nome)
                    info["stagione"] = stag or "01"
                    info["episodio"] = ep or "01"
                    res = motore_serie.analizza_file(info)
                    res["tipo_media"] = "serie"
                    res["confidenza"] = 1.0
                    res["match_principale"] = {
                        "tmdb_id": tid,
                        "titolo": info_tmdb.get("titolo_it_tmdb", ""),
                        "anno": info_tmdb.get("anno", ""),
                        "tipo": "serie",
                    }
                    return cls._arricchisci_e_controlla(res, info, config, motore_film, motore_serie, motore_musica, mappa_destinazione, lock_mappa)

        dati_locali = media_parsing.estrai_info_locali(nome, percorso)
        tipo = dati_locali.get("tipo_indovinato", "movie")
        info["titolo_guessit"] = dati_locali.get("titolo", "")
        info["anno_guessit"] = dati_locali.get("anno", "")

        s_reg, e_reg, forza_reg = media_parsing.estrai_stagione_episodio(nome)

        if tipo == "episode" or (s_reg and e_reg and forza_reg != "debole"):
            tipo = "episode"
            info["forza_match_serie"] = forza_reg
            stag = dati_locali.get("stagione")
            ep = dati_locali.get("episodio")
            info["stagione"] = str(stag).zfill(2) if stag else (s_reg or "01")
            info["episodio"] = str(ep).zfill(2) if ep else (e_reg or "01")

            res = motore_serie.analizza_file(info)
            res["tipo_media"] = "serie"
            forza = info.get("forza_match_serie", "debole")
            soglia_sicurezza = 0.85 if forza == "debole" else (0.6 if forza == "media" else 0.4)

            if res.get("confidenza", 0) < soglia_sicurezza:
                res_film = motore_film.analizza_file(info)
                bonus_serie = 0.20 if forza == "forte" else (0.10 if forza == "media" else 0.0)
                if res_film.get("confidenza", 0) > (res.get("confidenza", 0) + bonus_serie):
                    res = res_film
                    res["tipo_media"] = "film"

            if usa_ai and res.get("confidenza", 0) < 0.8:
                padre, _nonno = cls._estrai_contesto_percorso(percorso)
                ai_res = gemini_service.estrai_metadati(nome, contesto=padre)
                if ai_res["tipo"] == "serie":
                    info["stagione"] = str(ai_res.get("stagione") or info["stagione"]).zfill(2)
                    info["episodio"] = str(ai_res.get("episodio") or info["episodio"]).zfill(2)
                    res = motore_serie.analizza_file(info, dati_ai=ai_res)
                    res["tipo_media"] = "serie"
                else:
                    res = motore_film.analizza_file(info)
                    res["tipo_media"] = "film"
                res["confidenza"] = max(res.get("confidenza", 0), ai_res.get("confidenza", 0))
                res["gemini"] = ai_res
        else:
            res = motore_film.analizza_file(info)
            res["tipo_media"] = "film"
            soglia_sicurezza = config.get("automazione", {}).get("soglia", 0.85)
            if res.get("confidenza", 0) < soglia_sicurezza and dati_locali.get("episodio"):
                res_serie = motore_serie.analizza_file(info)
                if res_serie.get("confidenza", 0) > res.get("confidenza", 0):
                    res = res_serie
                    res["tipo_media"] = "serie"

            if usa_ai and res.get("confidenza", 0) < 0.8:
                padre, _nonno = cls._estrai_contesto_percorso(percorso)
                ai_res = gemini_service.estrai_metadati(nome, contesto=padre)
                if ai_res["tipo"] == "serie":
                    info["stagione"] = str(ai_res.get("stagione") or "01").zfill(2)
                    info["episodio"] = str(ai_res.get("episodio") or "01").zfill(2)
                    res = motore_serie.analizza_file(info, dati_ai=ai_res)
                    res["tipo_media"] = "serie"
                res["confidenza"] = max(res.get("confidenza", 0), ai_res.get("confidenza", 0))
                res["gemini"] = ai_res

        return cls._arricchisci_e_controlla(res, info, config, motore_film, motore_serie, motore_musica, mappa_destinazione, lock_mappa)

    @classmethod
    def _arricchisci_e_controlla(
        cls, res: dict[str, Any], info: dict[str, Any], config: dict[str, Any],
        motore_film: Any, motore_serie: Any, motore_musica: Any,
        mappa_destinazione: dict[str, Any], lock_mappa: Any
    ) -> dict[str, Any]:
        tipo = res.get("tipo_media", "film")
        percorso = info["percorso"]
        nome = info["nome"]
        est = info["estensione"]

        res["info_tecnica"] = ffmpeg_service.analizza_tecnico(percorso)

        m = res.get("match_principale") or {}
        nome_ep = res.get("nome_episodio", "")
        if tipo == "serie":
            struttura = motore_serie.costruisci_nome_jellyfin(
                m, res.get("stagione", "01"), res.get("episodio", "01"), res.get("info_tecnica", {}), est, nome_ep
            )
        elif tipo == "musica":
            struttura = motore_musica.costruisci_nome_jellyfin(res.get("info_id3", {}), est)
        else:
            struttura = motore_film.costruisci_nome_jellyfin(m.get("titolo", "Sconosciuto"), m, res.get("info_tecnica", {}), est)

        res["nome_jellyfin"] = struttura

        target_root = config.get("destinazioni", {}).get(tipo)
        if target_root:
            if tipo == "serie":
                dest_rel = os.path.join(struttura["cartella_serie"], struttura["cartella_stagione"], struttura["nome_file"])
            elif tipo == "musica":
                dest_rel = os.path.join(struttura["cartella_artista"], struttura["cartella_album"], struttura["nome_file"])
            else:
                dest_rel = os.path.join(struttura.get("decade", ""), struttura["cartella"], struttura["nome_file"])

            dest_finale = os.path.join(target_root, dest_rel)

            duplicato_trovato = False
            if os.path.exists(dest_finale):
                try:
                    if os.path.getsize(percorso) == os.path.getsize(dest_finale):
                        duplicato_trovato = True
                except OSError:
                    pass

            if not duplicato_trovato and nome in mappa_destinazione:
                with lock_mappa:
                    info_mappa = mappa_destinazione.get(nome)
                    if info_mappa:
                        try:
                            if os.path.getsize(percorso) == info_mappa.get("dimensione"):
                                duplicato_trovato = True
                        except OSError:
                            pass

            if duplicato_trovato:
                res["status"] = "Duplicato (Gia presente)"
                res["confidenza"] = 1.0

        soglia = config.get("automazione", {}).get("soglia", 0.85)
        if res.get("confidenza", 0) < soglia:
            _log_non_riconosciuti.info(f"File non riconosciuto o bassa confidenza: {nome} (Percorso: {percorso})")

        return res
