"""Caricamento delle chiavi API da .env, ancorato ad AppPaths (mai a ricerca cwd-based)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from app.core.paths import AppPaths


@dataclass(frozen=True)
class ApiKeys:
    tmdb: str
    gemini: str
    openai: str
    acoustid: str
    lingua_default: str
    tmdb_lingua: str


def carica_api_keys(paths: AppPaths) -> ApiKeys:
    if paths.env_file.exists():
        load_dotenv(paths.env_file)
    return ApiKeys(
        tmdb=os.getenv("TMDB_API_KEY", ""),
        gemini=os.getenv("GEMINI_API_KEY", ""),
        openai=os.getenv("OPENAI_API_KEY", ""),
        acoustid=os.getenv("ACOUSTID_API_KEY", ""),
        lingua_default=os.getenv("LINGUA_DEFAULT", "it"),
        tmdb_lingua=os.getenv("TMDB_LINGUA", "it-IT"),
    )


def applica_api_keys(paths: AppPaths, chiavi: ApiKeys) -> None:
    """(Ri)configura tutti i servizi che dipendono da una chiave API.

    Richiamabile sia all'avvio sia a runtime (es. dalla schermata
    Impostazioni dopo che l'utente ha salvato nuove chiavi), cosi' un cambio
    di chiave ha effetto immediato senza dover riavviare l'app.
    """
    from app.services import acoustid_service, db_cache, gemini_service, metadata_service, openai_service, tmdb_service

    tmdb_service.configura(db_cache.DatabaseCache(paths.cache_db_file), chiavi.tmdb, chiavi.tmdb_lingua)
    gemini_service.configura(chiavi.gemini)
    openai_service.configura(chiavi.openai)
    acoustid_service.configura(chiavi.acoustid, paths.fpcalc_exe)
    metadata_service.configura(chiavi.tmdb_lingua)
