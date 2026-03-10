from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from scraper import (
    extract_article,
    validate_and_extract,
    resolve_location,
    load_gazetteer,
    load_json,
    save_json,
    stable_id,
    event_level,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MANUAL_EVENTS_PATH = DATA_DIR / "manual_events.json"
GEOCODE_CACHE_PATH = DATA_DIR / "geocode_cache.json"


def main():
    if len(sys.argv) < 2:
        raise SystemExit('Uso: python scripts/add_manual_note.py "<url>"')

    url = sys.argv[1]

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    manual_events = load_json(MANUAL_EVENTS_PATH, [])
    geocode_cache = load_json(GEOCODE_CACHE_PATH, {})
    gazetteer = load_gazetteer()

    existing_urls = {e.get("fuente") for e in manual_events if e.get("fuente")}
    if url in existing_urls:
        print("ℹ️ Esa nota ya existe en manual_events.json")
        return

    article = extract_article(url)
    extracted = validate_and_extract(
        title=article["title"],
        article_text=article["text"],
    )

    print(json.dumps(extracted, ensure_ascii=False, indent=2))

    if not extracted.get("es_violento"):
        print("⚠️ La nota no fue clasificada como violenta.")
        return

    if not extracted.get("es_en_cuernavaca"):
        print("⚠️ La nota no fue clasificada como ocurrida en Cuernavaca.")
        return

    colonia = extracted.get("colonia")
    coords, geo_source = resolve_location(colonia, gazetteer, geocode_cache)

    if coords is None:
        print(f"⚠️ No se pudo resolver la colonia: {colonia!r}")
        print("   Puedes agregarla al gazetteer o capturar el evento manualmente.")
        save_json(GEOCODE_CACHE_PATH, geocode_cache)
        return

    fecha_evento = article.get("published_at")
    if fecha_evento:
        fecha_evento = str(fecha_evento)[:10]
    else:
        fecha_evento = datetime.now().strftime("%Y-%m-%d")

    hora_aprox = extracted.get("hora_aprox")

    event = {
        "id": stable_id("manual|" + url),
        "fecha": fecha_evento,
        "hora": hora_aprox,
        "colonia": colonia,
        "coordenadas": coords,
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

    manual_events.append(event)
    save_json(MANUAL_EVENTS_PATH, manual_events)
    save_json(GEOCODE_CACHE_PATH, geocode_cache)

    print("✅ Nota agregada a data/manual_events.json")


if __name__ == "__main__":
    main()