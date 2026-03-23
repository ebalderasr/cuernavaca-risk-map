from __future__ import annotations

"""
OVICUE - import_colonias_geojson.py

Importa un GeoJSON de colonias de Cuernavaca y genera:
1. data/colonias_cuernavaca.json
2. data/colonias_cuernavaca_polygons.geojson

Uso:
    python scripts/import_colonias_geojson.py /ruta/al/archivo.geojson
"""

import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

from shapely.geometry import shape, mapping


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

GAZETTEER_PATH = DATA_DIR / "colonias_cuernavaca.json"
POLYGONS_PATH = DATA_DIR / "colonias_cuernavaca_polygons.geojson"

NAME_FIELDS = (
    "location_name",
    "name",
    "nombre",
    "colonia",
    "nom_col",
    "NOMBRE",
    "NOM_COL",
    "asentamiento",
)

ALIAS_FIELDS = (
    "aliases",
    "alias",
    "alternates",
    "alternate_names",
)


def normalize_text(text: str | None) -> str:
    text = text or ""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().split())


def title_case_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split())


def load_geojson(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_existing_aliases() -> dict[str, set[str]]:
    if not GAZETTEER_PATH.exists():
        return {}

    data = json.loads(GAZETTEER_PATH.read_text(encoding="utf-8"))
    aliases_by_name: dict[str, set[str]] = {}

    for item in data:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        aliases_by_name[normalize_text(name)] = {
            str(alias).strip()
            for alias in item.get("aliases", [])
            if str(alias).strip()
        }

    return aliases_by_name


def extract_name(properties: dict[str, Any]) -> str | None:
    for field in NAME_FIELDS:
        value = properties.get(field)
        if value:
            return str(value).strip()
    return None


def extract_aliases(properties: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for field in ALIAS_FIELDS:
        value = properties.get(field)
        if isinstance(value, list):
            aliases.update(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, str) and value.strip():
            aliases.add(value.strip())
    return aliases


def build_default_aliases(name: str) -> set[str]:
    aliases = {
        name,
        name.upper(),
        name.lower(),
        f"Colonia {name}",
        f"COLONIA {name.upper()}",
        f"Col. {name}",
        f"COL. {name.upper()}",
        f"Col {name}",
        f"COL {name.upper()}",
    }
    return aliases


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit('Uso: python scripts/import_colonias_geojson.py "/ruta/al/archivo.geojson"')

    source_path = Path(sys.argv[1]).expanduser().resolve()
    if not source_path.exists():
        raise SystemExit(f"⚠️ No existe el archivo: {source_path}")

    source = load_geojson(source_path)
    features = source.get("features", []) if isinstance(source, dict) else []
    existing_aliases = load_existing_aliases()

    gazetteer: list[dict[str, Any]] = []
    polygon_features: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for feature in features:
        if not isinstance(feature, dict):
            continue

        properties = feature.get("properties") or {}
        geometry = feature.get("geometry")
        if not geometry:
            continue

        raw_name = extract_name(properties)
        if not raw_name:
            continue

        normalized_name = normalize_text(raw_name)
        if not normalized_name or normalized_name in seen_names:
            continue

        try:
            geom = shape(geometry)
        except Exception:
            continue

        representative_point = geom.representative_point()
        canonical_name = title_case_name(raw_name.strip())

        aliases = set()
        aliases.update(build_default_aliases(canonical_name))
        aliases.update(extract_aliases(properties))
        aliases.update(existing_aliases.get(normalized_name, set()))
        aliases.discard("")

        gazetteer.append(
            {
                "name": canonical_name,
                "aliases": sorted(aliases),
                "coords": [round(representative_point.y, 7), round(representative_point.x, 7)],
                "geometry_source": source_path.name,
            }
        )

        polygon_features.append(
            {
                "type": "Feature",
                "geometry": mapping(geom),
                "properties": {
                    "name": canonical_name,
                    "location_name": canonical_name,
                    "aliases": sorted(aliases),
                    "geometry_source": source_path.name,
                },
            }
        )

        seen_names.add(normalized_name)

    gazetteer.sort(key=lambda item: normalize_text(item["name"]))
    polygon_geojson = {"type": "FeatureCollection", "features": polygon_features}

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GAZETTEER_PATH.write_text(json.dumps(gazetteer, ensure_ascii=False, indent=2), encoding="utf-8")
    POLYGONS_PATH.write_text(json.dumps(polygon_geojson, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ Colonias importadas: {len(gazetteer)}")
    print(f"📍 Gazetteer actualizado: {GAZETTEER_PATH}")
    print(f"🗺️ Polígonos guardados: {POLYGONS_PATH}")


if __name__ == "__main__":
    main()
