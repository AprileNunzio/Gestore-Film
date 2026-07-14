from typing import Any
from app.services import gemini_service, openai_service

class AiMatcherUniversale:
    """Micro-servizio responsabile per l'integrazione con AI e classificazione."""

    @staticmethod
    def analizza_con_ai(
        r: dict[str, Any],
        provider: str,
        motore_film: Any,
        motore_serie: Any,
        motore_musica: Any,
        analyzer_arricchisci_fn: Any,
        config: dict[str, Any],
        mappa_destinazione: dict[str, Any],
        lock_mappa: Any
    ) -> dict[str, Any]:
        nome = r.get("file_originale", "")
        cartella = r.get("percorso_originale", "")

        if provider == "chatgpt":
            ai_res = openai_service.analizza_con_openai(nome)
        else:
            ai_res = gemini_service.estrai_metadati(nome, contesto=cartella)

        info = {"percorso": r["percorso_originale"], "nome": nome, "estensione": r["estensione"]}

        if ai_res["tipo"] == "serie":
            info["stagione"] = str(ai_res.get("stagione") or "01").zfill(2)
            info["episodio"] = str(ai_res.get("episodio") or "01").zfill(2)
            nuovo = motore_serie.analizza_file(info)
            nuovo["tipo_media"] = "serie"
        elif ai_res["tipo"] == "musica":
            nuovo = motore_musica.analizza_file(info)
            nuovo["tipo_media"] = "musica"
        else:
            nuovo = motore_film.analizza_file(info)
            nuovo["tipo_media"] = "film"

        nuovo["confidenza"] = ai_res.get("confidenza", 0.8)
        nuovo["gemini"] = ai_res

        return analyzer_arricchisci_fn(nuovo, info, config, motore_film, motore_serie, motore_musica, mappa_destinazione, lock_mappa)
