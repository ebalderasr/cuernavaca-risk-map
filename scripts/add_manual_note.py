from __future__ import annotations

"""
OVICUE - add_manual_note.py

Agrega una nota manualmente al dataset del proyecto, usando
la misma lógica determinista que el scraper automático.

Uso:
    python scripts/add_manual_note.py "https://url-de-la-nota"

Qué hace:
1. Descarga la nota
2. La clasifica con reglas (sin IA)
3. Detecta si es:
   - Cuernavaca
   - o conurbado configurado
4. Resuelve ubicación
5. Guarda en data/manual_events.json
6. Si la misma URL existe en data/events.json, la elimina ahí
   para que la versión manual prevalezca
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from scraper import (
    CONURBADO_BUFFER_METERS,
    DEFAULT_BUFFER_METERS,
    MORELOS_EXCLUDED_MUNICIPALITIES,
    build_gazetteer_index,
    detect_conurbado_area,
    event_level,
    extract_article,
    find_colonia_in_text,
    load_gazetteer,
    load_json,
    normalize_date_str,
    normalize_text,
    resolve_gazetteer_name,
    save_json,
    stable_id,
    validate_and_extract,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

EVENTS_PATH = DATA_DIR / "events.json"
MANUAL_EVENTS_PATH = DATA_DIR / "manual_events.json"
GEOCODE_CACHE_PATH = DATA_DIR / "geocode_cache.json"


# =============================================================================
# UTILIDADES
# =============================================================================

def remove_same_url_from_scraped_events(
    url: str,
    scraped_events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """
    Elimina de events.json cualquier evento con la misma URL.
    """
    filtered = [event for event in scraped_events if event.get("fuente") != url]
    removed = len(filtered) != len(scraped_events)
    return filtered, removed


def upsert_manual_event(
    event: dict[str, Any],
    manual_events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    """
    Inserta o actualiza un evento manual.

    Si la misma URL ya existe, la reemplaza.
    """
    url = event.get("fuente")
    if not url:
        return manual_events, "inserted"

    updated = []
    replaced = False

    for existing in manual_events:
        if existing.get("fuente") == url:
            updated.append(event)
            replaced = True
        else:
            updated.append(existing)

    if not replaced:
        updated.append(event)
        return updated, "inserted"

    return updated, "updated"


# =============================================================================
# FLUJO PRINCIPAL
# =============================================================================

def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit('Uso: python scripts/add_manual_note.py "<url>"')

    url = sys.argv[1].strip()
    if not url:
        raise SystemExit("⚠️ Debes proporcionar una URL válida.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    manual_events = load_json(MANUAL_EVENTS_PATH, [])
    scraped_events = load_json(EVENTS_PATH, [])
    gazetteer = load_gazetteer()
    gazetteer_index = build_gazetteer_index(gazetteer)

    article = extract_article(url)

    extracted = validate_and_extract(
        title=article["title"],
        article_text=article["text"],
    )

    print("🧠 Resultado de extracción determinista:")
    print(json.dumps(extracted, ensure_ascii=False, indent=2))

    if not extracted.get("es_violento"):
        print("⚠️ La nota no fue clasificada como violenta. No se agregará.")
        return

    full_text_for_scope = f"{article['title']}\n{article['text']}"
    conurbado = detect_conurbado_area(full_text_for_scope)
    text_norm_full = normalize_text(full_text_for_scope)

    if (
        not extracted.get("es_en_cuernavaca")
        and conurbado is None
        and any(excl in text_norm_full for excl in MORELOS_EXCLUDED_MUNICIPALITIES)
    ):
        print("⚠️ La nota menciona un municipio excluido sin área objetivo.")
        return

    # Algoritmo de ubicación en dos pasos
    coords = None
    geo_source = "none"
    location_name = None
    location_scope = "colonia"
    buffer_meters = DEFAULT_BUFFER_METERS

    if conurbado is not None and not extracted.get("es_en_cuernavaca"):
        coords, geo_source = resolve_gazetteer_name(conurbado, gazetteer)
        location_name = conurbado
        location_scope = "municipio"
        buffer_meters = CONURBADO_BUFFER_METERS
    else:
        colonia_name, colonia_coords = find_colonia_in_text(text_norm_full, gazetteer_index)
        if colonia_name:
            location_name = colonia_name
            coords = colonia_coords
            geo_source = "gazetteer_text"

    if coords is None:
        print(f"⚠️ No se pudo resolver la ubicación para: {location_name!r}")
        print("   Revisa el gazetteer o el texto de la nota.")
        return

    fecha_evento = normalize_date_str(article.get("published_at"))
    if not fecha_evento:
        fecha_evento = datetime.now().strftime("%Y-%m-%d")

    hora_aprox = extracted.get("hora_aprox")

    event = {
        "id": stable_id("manual|" + url),
        "fecha": fecha_evento,
        "hora": hora_aprox,
        "municipio_detectado": conurbado,
        "location_scope": location_scope,
        "location_name": location_name,
        "coordenadas": coords,
        "buffer_meters": buffer_meters,
        "tipo_delito": extracted.get("delito") or "No especificado",
        "nivel_inicial": event_level(hora_aprox),
        "fuente": url,
        "resumen": extracted.get("resumen") or article["title"],
        "source_name": "Manual",
        "source_title": article["title"],
        "published_at": article.get("published_at"),
        "scraped_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "geo_confidence": geo_source,
        "extraction_confidence": extracted.get("confidence", 0.0),
        "source_type": "manual",
    }

    print("\n🧾 Evento manual construido:")
    print(json.dumps(event, ensure_ascii=False, indent=2))

    manual_events, mode = upsert_manual_event(event, manual_events)
    scraped_events, removed_from_scraped = remove_same_url_from_scraped_events(url, scraped_events)

    save_json(MANUAL_EVENTS_PATH, manual_events)
    save_json(EVENTS_PATH, scraped_events)

    if mode == "inserted":
        print("✅ Nota agregada a data/manual_events.json")
    else:
        print("✅ Nota actualizada en data/manual_events.json")

    if removed_from_scraped:
        print("♻️ También se eliminó la versión automática en data/events.json para evitar conflictos.")

    print("ℹ️ Recuerda regenerar el mapa:")
    print("   python scripts/logic.py")


if __name__ == "__main__":
    main()
