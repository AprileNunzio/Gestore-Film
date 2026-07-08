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
