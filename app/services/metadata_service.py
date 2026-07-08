"""Generazione NFO/artwork Jellyfin per film via TMDB. Porta servizio_metadata.py.

Va inizializzato con configura(api_key, lingua). Fix rispetto all'originale:
riusa tmdb_service.intestazioni_autenticazione() e config.TMDB_BASE_URL invece
di duplicare la logica di autenticazione e l'URL base.
"""
from __future__ import annotations

import io
import logging
import os
import xml.etree.ElementTree as ET
from typing import Any

import requests
from PIL import Image, ImageOps

from app.core.config import TMDB_BASE_URL
from app.services import tmdb_service

_log = logging.getLogger("gestore_film.principale")

_lingua = "it-IT"


def configura(lingua: str) -> None:
    global _lingua
    _lingua = lingua


def genera_nfo_jellyfin(dati_tmdb: dict[str, Any], percorso_nfo: str) -> None:
    """Genera il file movie.nfo standard Kodi/Jellyfin."""
    try:
        movie = ET.Element("movie")

        ET.SubElement(movie, "title").text = dati_tmdb.get("title", "")
        ET.SubElement(movie, "originaltitle").text = dati_tmdb.get("original_title", "")
        ET.SubElement(movie, "sorttitle").text = dati_tmdb.get("title", "")
        ET.SubElement(movie, "tmdbid").text = str(dati_tmdb.get("id", ""))
        uniqueid = ET.SubElement(movie, "uniqueid", type="tmdb", default="true")
        uniqueid.text = str(dati_tmdb.get("id", ""))
        ET.SubElement(movie, "plot").text = dati_tmdb.get("overview", "")
        ET.SubElement(movie, "outline").text = dati_tmdb.get("overview", "")

        data_rilascio = dati_tmdb.get("release_date", "")
        if data_rilascio:
            ET.SubElement(movie, "premiered").text = data_rilascio
            ET.SubElement(movie, "releasedate").text = data_rilascio
            ET.SubElement(movie, "year").text = data_rilascio[:4]

        for genere in dati_tmdb.get("genres", []):
            ET.SubElement(movie, "genre").text = genere.get("name", "")

        voto = dati_tmdb.get("vote_average", 0.0)
        ET.SubElement(movie, "rating").text = str(round(voto, 1))

        albero = ET.ElementTree(movie)
        ET.indent(albero, space="  ", level=0)

        with open(percorso_nfo, "wb") as f:
            f.write(b'<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n')
            albero.write(f, encoding="utf-8", xml_declaration=False)

        _log.info(f"Creato NFO in {percorso_nfo}")
    except Exception as e:
        _log.error(f"Errore durante la creazione del NFO: {e}")


def _scarica_e_ridimensiona(
    url: str, percorso_dest: str, width: int, height: int, formato: str = "JPEG", mantieni_trasparenza: bool = False
) -> None:
    """Scarica un'immagine e la forza alla risoluzione esatta (crop/fit)."""
    if not url:
        return

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()

        img = Image.open(io.BytesIO(r.content))

        if mantieni_trasparenza and img.mode != "RGBA":
            img = img.convert("RGBA")
        elif not mantieni_trasparenza and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        img_ridimensionata = ImageOps.fit(img, (width, height), Image.Resampling.LANCZOS)

        if formato.upper() == "PNG":
            img_ridimensionata.save(percorso_dest, format="PNG")
        else:
            img_ridimensionata.save(percorso_dest, format="JPEG", quality=90)

        _log.info(f"Immagine salvata e forzata a {width}x{height}: {os.path.basename(percorso_dest)}")
    except Exception as e:
        _log.error(f"Errore download/resize di {url} in {percorso_dest}: {e}")


def scarica_metadata_jellyfin_film(tmdb_id: int, cartella_dest: str) -> None:
    """Recupera artwork ed NFO da TMDB e li scrive nei formati attesi da Jellyfin."""
    _log.info(f"Scarico metadata automatizzati per film TMDB ID: {tmdb_id}")
    try:
        if not tmdb_id:
            return

        path_nfo = os.path.join(cartella_dest, "movie.nfo")
        path_backdrop = os.path.join(cartella_dest, "backdrop.jpg")
        path_landscape = os.path.join(cartella_dest, "landscape.jpg")
        path_folder = os.path.join(cartella_dest, "folder.jpg")
        path_logo = os.path.join(cartella_dest, "logo.png")

        url = f"{TMDB_BASE_URL}/movie/{tmdb_id}"
        parametri: dict[str, Any] = {
            "language": _lingua,
            "append_to_response": "images",
            "include_image_language": "it,en,null",
        }
        intestazioni = tmdb_service.intestazioni_autenticazione(parametri)

        r = requests.get(url, headers=intestazioni, params=parametri, timeout=10)
        if r.status_code != 200:
            _log.warning(f"Errore nel recupero dei metadati di {tmdb_id} dal server remoto (Code {r.status_code})")
            return

        dati_tmdb = r.json()

        if not os.path.exists(path_nfo):
            genera_nfo_jellyfin(dati_tmdb, path_nfo)

        immagini = dati_tmdb.get("images", {})
        base_img_url = "https://image.tmdb.org/t/p/original"

        backdrops = immagini.get("backdrops", [])
        if backdrops and not os.path.exists(path_backdrop):
            url_backdrop = base_img_url + backdrops[0]["file_path"]
            _scarica_e_ridimensiona(url_backdrop, path_backdrop, 1920, 1080, "JPEG", False)
            if not os.path.exists(path_landscape):
                _scarica_e_ridimensiona(url_backdrop, path_landscape, 1920, 1080, "JPEG", False)

        posters = immagini.get("posters", [])
        if posters and not os.path.exists(path_folder):
            url_poster = base_img_url + posters[0]["file_path"]
            _scarica_e_ridimensiona(url_poster, path_folder, 1000, 1500, "JPEG", False)

        logos = immagini.get("logos", [])
        if logos and not os.path.exists(path_logo):
            url_logo = base_img_url + logos[0]["file_path"]
            _scarica_e_ridimensiona(url_logo, path_logo, 1024, 375, "PNG", True)

        _log.info(f"Completato aggiornamento metadati locale per {dati_tmdb.get('title', 'Film')}!")

    except Exception as e:
        _log.error(f"Errore irreversibile nello scaricamento dei metadati: {e}")
