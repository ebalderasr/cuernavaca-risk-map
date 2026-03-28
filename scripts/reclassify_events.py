from __future__ import annotations

"""
OVICUE - reclassify_events.py

Reclasifica todos los eventos existentes (events.json + unresolved_events.json)
usando la lógica actual del scraper.

Útil cuando se actualiza el algoritmo de detección o el gazetteer y se quiere
que los registros históricos reflejen las reglas nuevas.

Uso:
    python scripts/reclassify_events.py
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
sys.path.insert(0, str(ROOT / "scripts"))

from scraper import (
    CONURBADO_BUFFER_METERS,
    DEFAULT_BUFFER_METERS,
    MORELOS_EXCLUDED_MUNICIPALITIES,
    build_gazetteer_index,
    dedupe_group_id,
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

EVENTS_PATH = DATA_DIR / "events.json"
UNRESOLVED_PATH = DATA_DIR / "unresolved_events.json"
MANUAL_EVENTS_PATH = DATA_DIR / "manual_events.json"


def reclassify(url: str, evt: dict[str, Any], gazetteer, gazetteer_index) -> tuple[str, dict[str, Any] | None]:
    """
    Re-descarga y reclasifica un artículo.
    Devuelve ('valid', event), ('unresolved', stub) o ('rejected', None).
    """
    article = extract_article(url)
    if not article["text"]:
        return "rejected", None

    title = article["title"] or evt.get("source_title", "")
    extracted = validate_and_extract(title=title, article_text=article["text"])

    if not extracted.get("es_violento"):
        print(f"  ❌ No violento")
        return "rejected", None

    full_text = f"{title}\n{article['text']}"
    conurbado = detect_conurbado_area(full_text)
    text_norm = normalize_text(full_text)

    if (
        not extracted.get("es_en_cuernavaca")
        and conurbado is None
        and any(excl in text_norm for excl in MORELOS_EXCLUDED_MUNICIPALITIES)
    ):
        print(f"  ❌ Municipio excluido")
        return "rejected", None

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
        colonia_name, colonia_coords = find_colonia_in_text(text_norm, gazetteer_index)
        if colonia_name:
            location_name = colonia_name
            coords = colonia_coords
            geo_source = "gazetteer_text"

    fecha_evento = (
        normalize_date_str(article.get("published_at"))
        or evt.get("fecha")
        or datetime.now().strftime("%Y-%m-%d")
    )
    delito = extracted.get("delito") or "No especificado"
    hora_aprox = extracted.get("hora_aprox")
    source_name = evt.get("source_name", "Diario de Morelos")

    if coords is None:
        print(f"  ⚠️ Sin ubicación: {location_name!r}")
        return "unresolved", {
            "id": stable_id(url),
            "source_name": source_name,
            "source_title": title,
            "fuente": url,
            "resumen": extracted.get("resumen") or title,
            "tipo_delito": delito,
            "hora": hora_aprox,
            "es_violento": True,
            "es_en_cuernavaca": extracted.get("es_en_cuernavaca"),
            "location_scope": location_scope,
            "location_name": location_name,
            "municipio_detectado": conurbado,
            "geo_confidence": geo_source,
            "extraction_confidence": extracted.get("confidence", 0.0),
            "article_excerpt": article.get("text", "")[:2000],
            "published_at": article.get("published_at"),
            "scraped_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }

    group_id = dedupe_group_id(delito, location_name, fecha_evento)
    print(f"  ✅ {location_scope}: {location_name} [{geo_source}]")
    return "valid", {
        "id": stable_id(url),
        "fecha": fecha_evento,
        "hora": hora_aprox,
        "municipio_detectado": conurbado,
        "location_scope": location_scope,
        "location_name": location_name,
        "coordenadas": coords,
        "buffer_meters": buffer_meters,
        "tipo_delito": delito,
        "nivel_inicial": event_level(hora_aprox),
        "fuente": url,
        "resumen": extracted.get("resumen") or title,
        "source_name": source_name,
        "source_title": title,
        "published_at": article.get("published_at"),
        "scraped_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "geo_confidence": geo_source,
        "extraction_confidence": extracted.get("confidence", 0.0),
        "dedupe_group_id": group_id,
    }


def main() -> None:
    gazetteer = load_gazetteer()
    gazetteer_index = build_gazetteer_index(gazetteer)

    existing = load_json(EVENTS_PATH, [])
    unresolved = load_json(UNRESOLVED_PATH, [])
    manual = load_json(MANUAL_EVENTS_PATH, [])
    manual_urls = {e.get("fuente") for e in manual if e.get("fuente")}

    # Combinar eventos + no resueltos, sin duplicar URLs
    seen_urls: set[str] = set()
    to_process: list[dict[str, Any]] = []
    for evt in existing + unresolved:
        url = evt.get("fuente")
        if url and url not in seen_urls and url not in manual_urls:
            seen_urls.add(url)
            to_process.append(evt)

    print(f"🔄 Reclasificando {len(to_process)} eventos...\n")

    new_events: list[dict[str, Any]] = []
    new_unresolved: list[dict[str, Any]] = []
    seen_groups: set[str] = set()

    for evt in to_process:
        url = evt.get("fuente", "")
        print(f"→ {url[:75]}")
        try:
            outcome, data = reclassify(url, evt, gazetteer, gazetteer_index)
            if outcome == "valid" and data:
                gid = data.get("dedupe_group_id", "")
                if gid and gid in seen_groups:
                    print(f"  ℹ️ Duplicado omitido")
                else:
                    if gid:
                        seen_groups.add(gid)
                    new_events.append(data)
            elif outcome == "unresolved" and data:
                new_unresolved.append(data)
            # "rejected" → se descarta silenciosamente (ya se imprimió el motivo)
        except Exception as exc:
            print(f"  ❌ Error: {exc}")

    save_json(EVENTS_PATH, new_events)
    save_json(UNRESOLVED_PATH, new_unresolved)

    print(f"\n✅ Listo: {len(new_events)} válidos, {len(new_unresolved)} sin geocodificación")
    if new_unresolved:
        print("   Revisa data/unresolved_events.json para corregir manualmente.")


if __name__ == "__main__":
    main()
