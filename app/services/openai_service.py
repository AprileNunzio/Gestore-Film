"""Integrazione OpenAI ChatGPT, provider AI alternativo a Gemini. Porta servizio_openai.py.

Va inizializzato con configura(api_key) prima dell'uso.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

_log = logging.getLogger("gestore_film.principale")

_api_key = ""


def configura(api_key: str) -> None:
    global _api_key
    _api_key = api_key


def chiave_configurata() -> bool:
    return bool(_api_key)


_PROMPT_FILM = """Sei un esperto cinematografico e di serie TV. Analizza il seguente nome file e identifica di quale opera si tratta.

Nome file: "{nome_file}"

Rispondimi SOLO con un JSON valido, senza markdown, senza commenti, senza testo aggiuntivo.
Il JSON deve avere esattamente questi campi:

{{
  "tipo": "film" oppure "serie" oppure "sconosciuto",
  "titolo_italiano": "titolo completo in italiano (se esiste una traduzione ufficiale italiana, altrimenti usa il titolo originale)",
  "titolo_originale": "titolo originale nella lingua originale",
  "anno": 1994,
  "stagione": null,
  "episodio": null,
  "confidenza": 0.95,
  "note": "breve descrizione: regista, cast principale, genere",
  "modello": "chatgpt"
}}
"""

_VUOTO: dict[str, Any] = {
    "tipo": "sconosciuto",
    "titolo_italiano": "",
    "titolo_originale": "",
    "anno": None,
    "stagione": None,
    "episodio": None,
    "confidenza": 0.0,
    "note": "ChatGPT non configurato",
    "modello": "chatgpt",
}


def analizza_con_openai(nome_file: str) -> dict[str, Any]:
    if not _api_key:
        return dict(_VUOTO)

    try:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": _PROMPT_FILM.format(nome_file=nome_file)}],
            "temperature": 0.1,
        }

        r = requests.post(url, headers=headers, json=payload, timeout=15)
        r.raise_for_status()

        testo_raw = r.json()["choices"][0]["message"]["content"].strip()
        testo = re.sub(r"^```(?:json)?", "", testo_raw).strip()
        testo = re.sub(r"```$", "", testo).strip()

        dati = json.loads(testo)

        return {
            "tipo": dati.get("tipo", "sconosciuto"),
            "titolo_italiano": str(dati.get("titolo_italiano", "") or ""),
            "titolo_originale": str(dati.get("titolo_originale", "") or ""),
            "anno": dati.get("anno"),
            "stagione": dati.get("stagione"),
            "episodio": dati.get("episodio"),
            "confidenza": float(dati.get("confidenza", 0.0)),
            "note": str(dati.get("note", "") or ""),
            "modello": "chatgpt",
        }
    except Exception as e:
        _log.error(f"OpenAI errore per '{nome_file}': {e}")
        return dict(_VUOTO)
