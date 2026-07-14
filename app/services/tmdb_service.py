"""Integrazione TMDB: ricerca fuzzy film/serie, dettagli, cache, scoring di confidenza.

Va inizializzato con configura(cache, api_key, lingua) prima dell'uso, cosi'
niente legge più le chiavi API a livello di modulo/import (erano lette da
config.py con os.getenv() al momento dell'import, accoppiamento rimosso qui
per testabilità e per rispettare l'ordine di avvio: AppPaths -> secrets ->
servizi).
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Any

import requests
from rapidfuzz import fuzz
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.core.config import TMDB_BASE_URL
from app.services.db_cache import DatabaseCache

_log = logging.getLogger("gestore_film.principale")

_http_session = requests.Session()
_retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
_http_session.mount("https://", HTTPAdapter(max_retries=_retries))
_http_session.mount("http://", HTTPAdapter(max_retries=_retries))

_cache: DatabaseCache | None = None
_api_key = ""
_lingua = "it-IT"


def configura(cache: DatabaseCache, api_key: str, lingua: str) -> None:
    global _cache, _api_key, _lingua
    _cache = cache
    _api_key = api_key
    _lingua = lingua


def _cache_attiva() -> DatabaseCache:
    if _cache is None:
        raise RuntimeError("tmdb_service.configura(...) non è stato chiamato all'avvio")
    return _cache


def intestazioni_autenticazione(parametri: dict[str, Any]) -> dict[str, str]:
    """Header/parametro di autenticazione TMDB, condiviso anche da metadata_service."""
    intestazioni = {"accept": "application/json"}
    if len(_api_key) > 50:
        intestazioni["Authorization"] = f"Bearer {_api_key}"
    else:
        parametri["api_key"] = _api_key
    return intestazioni


_ultimo_accesso_api = 0.0


def _attendi_rate_limit() -> None:
    global _ultimo_accesso_api
    ora = time.time()
    diff = ora - _ultimo_accesso_api
    if diff < 0.1:
        time.sleep(0.1 - diff)
    _ultimo_accesso_api = time.time()


def _hash_query(url: str, parametri: dict[str, Any]) -> str:
    stringa_query = url + "?" + "&".join(f"{k}={v}" for k, v in sorted(parametri.items()))
    return hashlib.md5(stringa_query.encode()).hexdigest()


def _fetch_con_cache(url: str, parametri: dict[str, Any], ttl: int = 2592000) -> dict[str, Any]:
    """GET con cache condivisa, restituisce il payload JSON completo (non troncato a .results)."""
    hash_query = _hash_query(url, parametri)
    risultato_cache = _cache_attiva().leggi_cache(hash_query)
    if risultato_cache is not None:
        return risultato_cache

    intestazioni = intestazioni_autenticazione(parametri)
    _attendi_rate_limit()
    r = _http_session.get(url, headers=intestazioni, params=parametri, timeout=10)
    r.raise_for_status()
    dati = r.json()
    _cache_attiva().scrivi_cache(hash_query, url, dati, ttl)
    return dati


def _esegui_richiesta(url: str, parametri: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        return _fetch_con_cache(url, parametri).get("results", [])
    except Exception as e:
        _log.error(f"Richiesta TMDB fallita: {e}")
        return []


def _recupera_dettagli(tmdb_id: int) -> dict[str, Any]:
    try:
        d = _fetch_con_cache(f"{TMDB_BASE_URL}/movie/{tmdb_id}", {"language": _lingua})
        generi = ", ".join(g["name"] for g in d.get("genres", []))
        return {
            "sinossi": d.get("overview", ""),
            "genere": generi,
            "voto_medio": d.get("vote_average", 0.0),
            "poster_path": d.get("poster_path", ""),
            "titolo_it_tmdb": d.get("title", ""),
            "data_rilascio": d.get("release_date", ""),
        }
    except Exception as e:
        _log.error(f"Recupero dettagli TMDB {tmdb_id} fallito: {e}")
        return {}


def _recupera_dettagli_tv(tmdb_id: int) -> dict[str, Any]:
    try:
        d = _fetch_con_cache(f"{TMDB_BASE_URL}/tv/{tmdb_id}", {"language": _lingua})
        generi = ", ".join(g["name"] for g in d.get("genres", []))
        return {
            "sinossi": d.get("overview", ""),
            "genere": generi,
            "voto_medio": d.get("vote_average", 0.0),
            "poster_path": d.get("poster_path", ""),
            "titolo_it_tmdb": d.get("name", ""),
            "tipo": "serie",
            "tmdb_id": tmdb_id,
            "anno": d.get("first_air_date", "")[:4],
            "data_rilascio": d.get("first_air_date", ""),
        }
    except Exception:
        return {}


def recupera_nome_episodio(tmdb_id: int, stagione: int, episodio: int) -> str:
    try:
        url = f"{TMDB_BASE_URL}/tv/{tmdb_id}/season/{stagione}/episode/{episodio}"
        parametri = {"language": _lingua}
        hash_query = _hash_query(url, parametri)
        risultato_cache = _cache_attiva().leggi_cache(hash_query)
        if risultato_cache is not None:
            return risultato_cache.get("name", "")

        intestazioni = intestazioni_autenticazione(parametri)
        _attendi_rate_limit()
        r = _http_session.get(url, headers=intestazioni, params=parametri, timeout=10)
        if r.status_code == 404:
            return ""
        r.raise_for_status()
        d = r.json()
        _cache_attiva().scrivi_cache(hash_query, url, d, 2592000)
        return d.get("name", "")
    except Exception:
        return ""


def recupera_da_id(tmdb_id: int, tipo_richiesto: str | None = None) -> dict[str, Any]:
    if tipo_richiesto == "serie":
        return _recupera_dettagli_tv(tmdb_id) or {}

    if tipo_richiesto == "film":
        dettagli = _recupera_dettagli(tmdb_id)
        if dettagli:
            return {**dettagli, "tipo": "film", "tmdb_id": tmdb_id, "anno": dettagli.get("data_rilascio", "")[:4]}
        return {}

    dettagli = _recupera_dettagli(tmdb_id)
    if dettagli:
        return {**dettagli, "tipo": "film", "tmdb_id": tmdb_id, "anno": dettagli.get("data_rilascio", "")[:4]}

    return _recupera_dettagli_tv(tmdb_id) or {}


def _normalizza(testo: str) -> str:
    testo = (testo or "").lower()
    testo = re.sub(r"[^a-z0-9àèéìòùü\s]", " ", testo)
    return " ".join(testo.split())


class MotoreConfidenza:
    PESO_TMDB_EXACT = 8.0
    PESO_GUESSIT = 6.0

    @staticmethod
    def calcola(titolo_locale: str, titolo_orig: str, anno_locale: Any, res: dict[str, Any]) -> float:
        t_loc = _normalizza(titolo_locale)
        t_orig = _normalizza(titolo_orig)
        res_titolo = _normalizza(res.get("titolo", ""))
        res_orig = _normalizza(res.get("original_title", "") or res.get("titolo_originale", ""))

        score_titolo_it = fuzz.token_sort_ratio(t_loc, res_titolo) / 100.0 if t_loc and res_titolo else 0.0
        score_titolo_or = fuzz.token_sort_ratio(t_orig, res_orig) / 100.0 if t_orig and res_orig else 0.0
        score_titolo_max = max(score_titolo_it, score_titolo_or)

        def _match_parziale(q: str, r: str) -> bool:
            if not q or not r:
                return False
            return r.startswith(q) or q in r

        if score_titolo_max < 0.9:
            if _match_parziale(t_loc, res_titolo) or _match_parziale(t_orig, res_orig):
                score_titolo_max = max(score_titolo_max, 0.85)

        anno_r = str(res.get("anno", ""))
        anno_c = str(anno_locale) if anno_locale else ""

        score_anno = 0.5
        if anno_c and anno_r:
            if anno_r == anno_c:
                score_anno = 1.0
            elif abs(int(anno_r) - int(anno_c)) <= 1:
                score_anno = 0.8
            elif res.get("tipo", "film") == "serie":
                score_anno = 0.9 if score_titolo_max >= 0.85 else 0.6
            else:
                score_anno = 0.0

        if score_titolo_max < 0.95:
            len_ratio = len(t_loc) / len(res_titolo) if res_titolo and t_loc else 1.0
            if len_ratio < 0.5:
                score_titolo_max *= 0.8

        score_totale = (
            (score_titolo_max * MotoreConfidenza.PESO_TMDB_EXACT) + (score_anno * MotoreConfidenza.PESO_GUESSIT)
        ) / (MotoreConfidenza.PESO_TMDB_EXACT + MotoreConfidenza.PESO_GUESSIT)
        return round(min(score_totale, 1.0), 2)


def _confidenza_tmdb(titolo_locale: str, titolo_orig: str, anno: Any, res: dict[str, Any]) -> float:
    return MotoreConfidenza.calcola(titolo_locale, titolo_orig, anno, res)


def _genera_strategie(
    titolo: str, anno: Any, titolo_originale: str = "", nome_file: str = "", titolo_secondario: str = ""
) -> list[dict[str, Any]]:
    strategie: list[dict[str, Any]] = []

    query_base = titolo_originale.strip() or titolo.strip()
    if query_base:
        if anno:
            strategie.append({"query": query_base, "anno": anno, "etichetta": "base+anno"})
        strategie.append({"query": query_base, "anno": None, "etichetta": "base"})

    if titolo_secondario and titolo_secondario.strip():
        strategie.append({"query": titolo_secondario.strip(), "anno": anno, "etichetta": "secondario+anno"})
        strategie.append({"query": titolo_secondario.strip(), "anno": None, "etichetta": "secondario"})

    if query_base:
        parole = query_base.split()
        if len(parole) > 3:
            strategie.append({"query": " ".join(parole[:3]), "anno": None, "etichetta": "prime3parole"})
            strategie.append({"query": " ".join(parole[1:]), "anno": anno, "etichetta": "rimuovi_testa"})
        if len(parole) > 2:
            strategie.append({"query": " ".join(parole[:2]), "anno": None, "etichetta": "prime2parole"})

    if nome_file:
        pulito = re.sub(r"\.[a-z0-9]{2,4}$", "", nome_file, flags=re.I)
        pulito = pulito.replace(".", " ").replace("_", " ")
        pulito = re.sub(r"\(.*?\)|\[.*?\]", " ", pulito)

        tags_re = (
            r"\d{3,4}p|[hx]\.?\d{3}|HEVC|AVC|AC3|DTS|AAC|BluRay|WEB.?DL|BDRip|DVDRip|HDTV|UHD|"
            r"4K|Remux|DVD|DIVX|XVID|PC|Ita|Eng|Sub|Multi|duplicato|copia|backup|sample|"
            r"walt\s+disn[ae]y"
        )
        pulito = re.sub(tags_re, " ", pulito, flags=re.I)
        pulito = re.sub(r"(19|20)\d{2}", " ", pulito)
        pulito = re.sub(r"\s+", " ", pulito).strip()
        if pulito and pulito.lower() != query_base.lower():
            strategie.append({"query": pulito, "anno": anno, "etichetta": "nomefile_pulito"})

    viste: set[str] = set()
    uniche = []
    for s in strategie:
        chiave = f"{s['query'].lower().strip()}|{s['anno']}"
        if chiave not in viste and len(s["query"].strip()) >= 2:
            viste.add(chiave)
            uniche.append(s)
    return uniche


def cerca_film(
    titolo: str,
    anno: Any = None,
    titolo_originale: str = "",
    nome_file: str = "",
    fallback_serie: bool = True,
    titolo_secondario: str = "",
) -> list[dict[str, Any]]:
    try:
        strategie = _genera_strategie(titolo, anno, titolo_originale, nome_file, titolo_secondario)
        if not strategie:
            _log.warning("Nessuna strategia generata, query vuota")
            return []

        tutti_candidati: dict[int, dict[str, Any]] = {}

        for strategia in strategie:
            parametri = {"query": strategia["query"], "language": _lingua, "include_adult": True}
            if strategia["anno"]:
                parametri["year"] = str(strategia["anno"])

            risultati_raw = _esegui_richiesta(f"{TMDB_BASE_URL}/search/movie", parametri)

            for res in risultati_raw[:20]:
                tmdb_id = res.get("id")
                if tmdb_id in tutti_candidati:
                    esistente = tutti_candidati[tmdb_id]
                    nuovo_score = _confidenza_tmdb(
                        titolo,
                        titolo_originale or titolo,
                        anno,
                        {
                            "titolo": res.get("title", ""),
                            "original_title": res.get("original_title", ""),
                            "anno": res.get("release_date", "")[:4],
                        },
                    )
                    if nuovo_score > esistente["confidenza_tmdb"]:
                        esistente["confidenza_tmdb"] = nuovo_score
                        esistente["strategia_vincente"] = strategia["etichetta"]
                    continue

                v = {
                    "tmdb_id": tmdb_id,
                    "titolo": res.get("title", ""),
                    "titolo_originale": res.get("original_title", ""),
                    "anno": res.get("release_date", "")[:4],
                    "data_rilascio": res.get("release_date", ""),
                    "poster_path": res.get("poster_path", ""),
                    "tipo": "film_erotico" if res.get("adult") else "film",
                    "strategia_vincente": strategia["etichetta"],
                }
                v["confidenza_tmdb"] = _confidenza_tmdb(titolo, titolo_originale or titolo, anno, v)
                tutti_candidati[tmdb_id] = v

        if not tutti_candidati and fallback_serie:
            _log.info("TMDB Multi-Strategy: Nessun Film, provo come SERIE TV...")
            return cerca_serie(titolo, anno, titolo_originale, fallback_film=False, nome_file=nome_file)

        varianti = sorted(tutti_candidati.values(), key=lambda x: x["confidenza_tmdb"], reverse=True)

        for v in varianti[:15]:
            v.update(_recupera_dettagli(v["tmdb_id"]))

        return varianti
    except Exception as e:
        _log.error(f"cerca_film errore: {e}")
        return []


def cerca_serie(
    titolo: str, anno: Any = None, titolo_originale: str = "", fallback_film: bool = True, nome_file: str = ""
) -> list[dict[str, Any]]:
    try:
        strategie = _genera_strategie(titolo, anno, titolo_originale, nome_file)
        if not strategie:
            _log.warning("Nessuna strategia generata per cerca_serie")
            return []

        tutti_candidati: dict[int, dict[str, Any]] = {}

        for strategia in strategie:
            parametri = {"query": strategia["query"], "language": _lingua, "include_adult": True}
            if strategia["anno"]:
                parametri["first_air_date_year"] = str(strategia["anno"])

            risultati_raw = _esegui_richiesta(f"{TMDB_BASE_URL}/search/tv", parametri)

            for res in risultati_raw[:15]:
                tmdb_id = res.get("id")
                if tmdb_id in tutti_candidati:
                    esistente = tutti_candidati[tmdb_id]
                    nuovo_score = _confidenza_tmdb(
                        titolo,
                        titolo_originale or titolo,
                        anno,
                        {
                            "titolo": res.get("name", ""),
                            "original_title": res.get("original_name", ""),
                            "anno": res.get("first_air_date", "")[:4],
                        },
                    )
                    if nuovo_score > esistente["confidenza_tmdb"]:
                        esistente["confidenza_tmdb"] = nuovo_score
                    continue

                v = {
                    "tmdb_id": tmdb_id,
                    "titolo": res.get("name", ""),
                    "titolo_originale": res.get("original_name", ""),
                    "anno": res.get("first_air_date", "")[:4],
                    "data_rilascio": res.get("first_air_date", ""),
                    "poster_path": res.get("poster_path", ""),
                    "tipo": "serie",
                    "strategia_vincente": strategia["etichetta"],
                }
                v["confidenza_tmdb"] = _confidenza_tmdb(titolo, titolo_originale or titolo, anno, v)
                tutti_candidati[tmdb_id] = v

        if not tutti_candidati and fallback_film:
            _log.info("TMDB Serie: Nessun risultato, provo come FILM...")
            return cerca_film(titolo, anno, titolo_originale, fallback_serie=False)

        varianti = sorted(tutti_candidati.values(), key=lambda x: x["confidenza_tmdb"], reverse=True)

        for v in varianti[:10]:
            dettagli = _recupera_dettagli_tv(v["tmdb_id"])
            if dettagli:
                v.update(dettagli)

        return varianti
    except Exception as e:
        _log.error(f"cerca_serie errore: {e}")
        return []
