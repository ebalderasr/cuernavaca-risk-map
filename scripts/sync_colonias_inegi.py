from __future__ import annotations

"""
Sincroniza el gazetteer local con el catálogo oficial de asentamientos de INEGI
para Cuernavaca y completa coordenadas con Nominatim sesgado al municipio.

Uso:
    python scripts/sync_colonias_inegi.py
"""

import json
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

GAZETTEER_PATH = DATA_DIR / "colonias_cuernavaca.json"
GEOCODE_CACHE_PATH = DATA_DIR / "geocode_cache.json"
INEGI_URL = "https://gaia.inegi.org.mx/wscatgeo/v2/asentamientos/17/007"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_VIEWBOX = "-99.33,19.01,-99.11,18.79"

HEADERS = {
    "User-Agent": "OVICUE/0.6 (Cuernavaca gazetteer sync)"
}

TYPE_LABELS = {
    "AMPLIACION": "Ampliacion",
    "BARRIO": "Barrio",
    "COLONIA": "",
    "CONDOMINIO": "Condominio",
    "FRACCIONAMIENTO": "Fraccionamiento",
    "RINCONADA": "Rinconada",
    "SECCION": "Seccion",
    "UNIDAD HABITACIONAL": "Unidad Habitacional",
    "ZONA MILITAR": "Zona Militar",
}

TYPE_PREFIXES = {
    "AMPLIACION": ("Ampliacion",),
    "BARRIO": ("Barrio",),
    "COLONIA": ("Colonia", "Col.", "Col"),
    "CONDOMINIO": ("Condominio",),
    "FRACCIONAMIENTO": ("Fraccionamiento", "Fracc.", "Fracc"),
    "RINCONADA": ("Rinconada",),
    "SECCION": ("Seccion",),
    "UNIDAD HABITACIONAL": ("Unidad Habitacional", "Unidad"),
    "ZONA MILITAR": ("Zona Militar",),
}

PREFERRED_RESULT_TYPES = {
    "borough",
    "city_block",
    "hamlet",
    "isolated_dwelling",
    "locality",
    "neighbourhood",
    "quarter",
    "residential",
    "suburb",
    "village",
}


def normalize_text(text: str | None) -> str:
    text = text or ""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().split())


def title_case_name(name: str) -> str:
    return " ".join(part.capitalize() for part in normalize_text(name).split())


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def canonical_name(base_name: str, settlement_type: str) -> str:
    label = TYPE_LABELS.get(settlement_type, title_case_name(settlement_type))
    return f"{label} {base_name}".strip()


def build_aliases(base_name: str, settlement_type: str, existing_aliases: set[str]) -> list[str]:
    aliases = set(existing_aliases)
    aliases.add(base_name)
    aliases.add(base_name.upper())
    aliases.add(base_name.lower())

    canonical = canonical_name(base_name, settlement_type)
    aliases.add(canonical)
    aliases.add(canonical.upper())
    aliases.add(canonical.lower())

    for prefix in TYPE_PREFIXES.get(settlement_type, ()):
        aliases.add(f"{prefix} {base_name}")

    if settlement_type == "SECCION":
        aliases.add(base_name.replace(" Seccion ", " Seccion "))
        aliases.add(base_name.replace(" Seccion ", " Sección "))

    return sorted(alias for alias in aliases if alias.strip())


def load_existing_gazetteer() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    gazetteer = load_json(GAZETTEER_PATH, [])
    by_norm: dict[str, dict[str, Any]] = {}

    for item in gazetteer:
        names = [item.get("name"), *(item.get("aliases", []) or [])]
        for name in names:
            norm = normalize_text(name)
            if norm:
                by_norm[norm] = item

    return gazetteer, by_norm


def load_geocode_cache() -> dict[str, Any]:
    cache = load_json(GEOCODE_CACHE_PATH, {})
    return cache if isinstance(cache, dict) else {}


def fetch_inegi_settlements() -> list[dict[str, Any]]:
    response = requests.get(INEGI_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("datos", []) if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def query_nominatim(query: str) -> list[dict[str, Any]]:
    response = requests.get(
        NOMINATIM_URL,
        params=query,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def score_nominatim_result(target_norm: str, candidate: dict[str, Any]) -> int:
    display_norm = normalize_text(candidate.get("display_name"))
    result_name = normalize_text(candidate.get("name"))
    result_type = normalize_text(candidate.get("type"))
    address = candidate.get("address") or {}
    score = 0

    if "cuernavaca" in display_norm or normalize_text(address.get("city")) == "cuernavaca":
        score += 40
    if normalize_text(address.get("state")) == "morelos":
        score += 10
    if result_type in PREFERRED_RESULT_TYPES:
        score += 20
    if result_name == target_norm:
        score += 30
    elif target_norm and target_norm in result_name:
        score += 15

    importance = candidate.get("importance")
    if isinstance(importance, (int, float)):
        score += int(importance * 10)

    return score


def geocode_place(canonical: str, base_name: str, settlement_type: str, cache: dict[str, Any]) -> tuple[list[float] | None, str]:
    cache_keys = [
        normalize_text(canonical),
        normalize_text(base_name),
    ]
    for key in cache_keys:
        if key in cache and cache[key].get("coords"):
            cached = cache[key]
            return cached.get("coords"), cached.get("geo_confidence", "cache")

    queries = [
        f"{canonical}, Cuernavaca, Morelos, Mexico",
        f"{base_name}, Cuernavaca, Morelos, Mexico",
    ]
    if settlement_type == "COLONIA":
        queries.insert(1, f"Colonia {base_name}, Cuernavaca, Morelos, Mexico")

    best_coords = None
    best_confidence = "none"
    best_score = -1

    for query in queries:
        for bounded in (True, False):
            params = {
                "q": query,
                "format": "jsonv2",
                "limit": 5,
                "addressdetails": 1,
                "countrycodes": "mx",
                "dedupe": 1,
            }
            if bounded:
                params["viewbox"] = NOMINATIM_VIEWBOX
                params["bounded"] = 1

            try:
                candidates = query_nominatim(params)
            except Exception:
                candidates = []
            finally:
                time.sleep(1.1)

            for candidate in candidates:
                score = score_nominatim_result(normalize_text(base_name), candidate)
                if score <= best_score:
                    continue
                try:
                    coords = [float(candidate["lat"]), float(candidate["lon"])]
                except (KeyError, TypeError, ValueError):
                    continue
                best_coords = coords
                best_confidence = "nominatim_bounded" if bounded else "nominatim_context"
                best_score = score

            if best_score >= 55 and best_coords:
                break

    if best_coords:
        payload = {"coords": best_coords, "geo_confidence": best_confidence}
        for key in cache_keys:
            cache[key] = payload
        return best_coords, best_confidence

    payload = {"coords": None, "geo_confidence": "none"}
    for key in cache_keys:
        cache[key] = payload
    return None, "none"


def build_official_entries(
    rows: list[dict[str, Any]],
    existing_by_norm: dict[str, dict[str, Any]],
    cache: dict[str, Any],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    for row in rows:
        raw_type = str(row.get("tipo_asen") or "").strip()
        raw_name = str(row.get("nom_asen") or "").strip()
        if not raw_type or not raw_name:
            continue

        settlement_type = normalize_text(raw_type).upper()
        base_name = title_case_name(raw_name)
        canonical = canonical_name(base_name, settlement_type)
        norm = normalize_text(canonical)

        entry = grouped.setdefault(
            norm,
            {
                "name": canonical,
                "base_name": base_name,
                "settlement_type": raw_type.title(),
                "inegi_rows": [],
                "aliases": set(),
            },
        )
        entry["inegi_rows"].append(
            {
                "cvegeo": row.get("cvegeo"),
                "cve_asen": row.get("cve_asen"),
                "tipo_asen": raw_type,
                "nom_asen": raw_name,
            }
        )

    results: list[dict[str, Any]] = []
    for entry in sorted(grouped.values(), key=lambda item: normalize_text(item["name"])):
        names_to_match = [
            entry["name"],
            entry["base_name"],
            *(TYPE_PREFIXES.get(normalize_text(entry["settlement_type"]).upper(), ())),
        ]
        existing = None
        for candidate_name in names_to_match:
            existing = existing_by_norm.get(normalize_text(candidate_name))
            if existing:
                break

        existing_aliases = set(existing.get("aliases", [])) if existing else set()
        aliases = build_aliases(
            base_name=entry["base_name"],
            settlement_type=normalize_text(entry["settlement_type"]).upper(),
            existing_aliases=existing_aliases,
        )
        coords = existing.get("coords") if existing else None
        geo_confidence = existing.get("geometry_source") or existing.get("geo_confidence") if existing else None

        if not (isinstance(coords, list) and len(coords) == 2):
            coords, geo_confidence = geocode_place(
                canonical=entry["name"],
                base_name=entry["base_name"],
                settlement_type=normalize_text(entry["settlement_type"]).upper(),
                cache=cache,
            )

        results.append(
            {
                "name": entry["name"],
                "aliases": aliases,
                "coords": coords,
                "geometry_source": "inegi_asentamientos_2023",
                "geo_confidence": geo_confidence or "none",
                "settlement_type": entry["settlement_type"],
                "source": "INEGI",
                "inegi_rows": entry["inegi_rows"],
            }
        )

    return results


def merge_existing_extras(
    official_entries: list[dict[str, Any]],
    existing_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    known = {normalize_text(item.get("name")) for item in official_entries}
    extras = []

    for item in existing_entries:
        norm = normalize_text(item.get("name"))
        if not norm or norm in known:
            continue
        extras.append(item)

    merged = official_entries + extras
    merged.sort(key=lambda item: normalize_text(item.get("name")))
    return merged


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing_entries, existing_by_norm = load_existing_gazetteer()
    cache = load_geocode_cache()
    official_rows = fetch_inegi_settlements()
    official_entries = build_official_entries(official_rows, existing_by_norm, cache)
    merged_entries = merge_existing_extras(official_entries, existing_entries)

    save_json(GAZETTEER_PATH, merged_entries)
    save_json(GEOCODE_CACHE_PATH, cache)

    with_coords = sum(1 for item in merged_entries if isinstance(item.get("coords"), list) and len(item["coords"]) == 2)
    print(f"INEGI rows: {len(official_rows)}")
    print(f"Gazetteer entries: {len(merged_entries)}")
    print(f"Entries with coords: {with_coords}")


if __name__ == "__main__":
    main()
