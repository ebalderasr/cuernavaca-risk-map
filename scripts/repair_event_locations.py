from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

EVENTS_PATH = DATA_DIR / "events.json"
GAZETTEER_PATH = DATA_DIR / "colonias_cuernavaca.json"

CUERNAVACA_COORDS = [18.9218, -99.2347]
LOW_PRECISION = {"morelos"}
MUNICIPAL_NAMES = {"cuernavaca", "jiutepec", "yautepec", "emiliano zapata", "temixco", "civac"}


def normalize_text(text: str | None) -> str:
    text = text or ""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def find_best_gazetteer_match(text: str, gazetteer: list[dict[str, Any]]) -> dict[str, Any] | None:
    text_norm = f" {normalize_text(text)} "
    best_item = None
    best_score = -1

    for item in gazetteer:
        coords = item.get("coords")
        if not isinstance(coords, list) or len(coords) != 2:
            continue

        canonical = normalize_text(item.get("name"))
        if not canonical or canonical in LOW_PRECISION or canonical in MUNICIPAL_NAMES:
            continue

        for variant in [item.get("name"), *(item.get("aliases") or [])]:
            variant_norm = normalize_text(variant)
            if not variant_norm or variant_norm in LOW_PRECISION:
                continue

            if f" {variant_norm} " not in text_norm:
                continue

            score = len(variant_norm)
            if variant_norm == canonical:
                score += 10
            if score > best_score:
                best_item = item
                best_score = score

    return best_item


def main() -> None:
    events = load_json(EVENTS_PATH, [])
    gazetteer = load_json(GAZETTEER_PATH, [])
    gazette_by_norm = {
        normalize_text(item.get("name")): item
        for item in gazetteer
        if item.get("name")
    }

    updated = 0

    for event in events:
        text = "\n".join(
            str(event.get(key) or "")
            for key in ("source_title", "resumen")
        )
        current_name = normalize_text(event.get("location_name") or event.get("colonia"))
        current_scope = event.get("location_scope", "colonia")

        best_match = find_best_gazetteer_match(text, gazetteer)
        if best_match:
            best_name = best_match["name"]
            best_norm = normalize_text(best_name)
            if best_norm != current_name or current_scope != "colonia":
                event["colonia"] = best_name
                event["location_scope"] = "colonia"
                event["location_name"] = best_name
                event["coordenadas"] = best_match["coords"]
                event["geo_confidence"] = "gazetteer_repaired"
                updated += 1
                continue

        if current_name in LOW_PRECISION and "cuernavaca" in normalize_text(text):
            event["location_scope"] = "municipio"
            event["location_name"] = "Cuernavaca"
            event["coordenadas"] = CUERNAVACA_COORDS
            event["geo_confidence"] = "municipio_repaired"
            updated += 1

    save_json(EVENTS_PATH, events)
    print(f"Eventos corregidos: {updated}")


if __name__ == "__main__":
    main()
