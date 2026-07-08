"""Integrazione Google Gemini per disambiguazione AI di nomi file. Porta servizio_gemini.py.

Va inizializzato con configura(api_key) prima dell'uso. Fix rispetto
all'originale: il client viene creato pigramente solo se la chiave è
presente, invece che eagerly all'import (evita di costruire un client con
una chiave vuota/invalida).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from pydantic import BaseModel, ValidationError

_log = logging.getLogger("gestore_film.principale")

_api_key = ""
_client: Any = None


def configura(api_key: str) -> None:
    global _api_key, _client
    _api_key = api_key
    _client = None  # ricreato pigramente al prossimo uso


def _ottieni_client() -> Any:
    global _client
    if _client is None and _api_key:
        from google import genai

        _client = genai.Client(api_key=_api_key)
    return _client


class EsitoAI(BaseModel):
    id_tmdb: int
    livello_sicurezza: float
    motivo: str
    tipo: Optional[str] = "sconosciuto"
    titolo_italiano: Optional[str] = ""
    titolo_originale: Optional[str] = ""
    anno: Optional[int] = None
    stagione: Optional[int] = None
    episodio: Optional[int] = None
    confidenza: Optional[float] = 0.0
    note: Optional[str] = ""


_PROMPT_REASONING = """Sei un esperto di catalogazione media. Analizza il nome del file e il contesto del percorso per identificare correttamente l'opera.
Nome file: "{nome_file}"
Percorso/Cartella: "{contesto}"

Rispondimi SOLO con un JSON valido strutturato esattamente come il seguente modello:
{{
  "id_tmdb": 0,
  "livello_sicurezza": 0.95,
  "motivo": "spiegazione",
  "tipo": "film" oppure "serie" oppure "musica" oppure "sconosciuto",
  "titolo_italiano": "titolo completo in italiano",
  "titolo_originale": "titolo originale",
  "anno": 1994,
  "stagione": 1,
  "episodio": 1,
  "confidenza": 0.95,
  "note": "spiegazione della scelta basata sul contesto"
}}
"""

_VUOTO: dict[str, Any] = {
    "id_tmdb": 0,
    "livello_sicurezza": 0.0,
    "motivo": "",
    "tipo": "sconosciuto",
    "titolo_italiano": "",
    "titolo_originale": "",
    "anno": None,
    "stagione": None,
    "episodio": None,
    "confidenza": 0.0,
    "note": "",
}


def analizza_nome_file(nome_file: str, contesto: str = "") -> dict[str, Any]:
    client = _ottieni_client()
    if client is None:
        return dict(_VUOTO)
    try:
        prompt = _PROMPT_REASONING.format(nome_file=nome_file, contesto=contesto)
        risposta = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        testo_raw = risposta.text.strip()

        testo = re.sub(r"^```(?:json)?", "", testo_raw).strip()
        testo = re.sub(r"```$", "", testo).strip()

        esito = EsitoAI.model_validate_json(testo)
        return esito.model_dump()
    except ValidationError as ve:
        _log.error(f"Pydantic Validation Error per '{nome_file}': {ve}")
        return dict(_VUOTO)
    except Exception as e:
        _log.error(f"Gemini errore per '{nome_file}': {e}")
        return dict(_VUOTO)


def estrai_metadati(nome_file: str, contesto: str = "") -> dict[str, Any]:
    return analizza_nome_file(nome_file, contesto)


def trova_titolo_italiano_episodio(serie: str, stagione: int, episodio: int) -> str:
    client = _ottieni_client()
    if client is None:
        return ""
    try:
        prompt = (
            f"Sei un esperto di serie TV e anime. Rispondi SOLO con il titolo italiano ufficiale "
            f"dell'episodio {episodio} della stagione {stagione} della serie '{serie}'. "
            "Non aggiungere commenti o spiegazioni."
        )
        risposta = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        return risposta.text.strip().replace('"', "")
    except Exception:
        return ""
