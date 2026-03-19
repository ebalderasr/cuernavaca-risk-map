from __future__ import annotations

"""
OVICUE - logic.py

Sistema de zonas peligrosas con escalación y decaimiento temporal.

Niveles:
  naranja  → 1 hecho violento, activo (< 30 días sin hechos)
  rojo     → 2 hechos en ≤ 3 días, o 3+ hechos, activo
  amarillo → 30–60 días sin hechos (peligro moderado)
  archivado → 60+ días sin hechos → cuadrado negro (registro histórico)

Radio:
  base_radius + max(0, n_incidents - 1) × 50 m  (+100 m de diámetro por hecho adicional)

Archivado individual:
  Eventos con ≥ 60 días se muestran como puntos negros separados,
  aunque su zona siga activa (ej. hecho viejo en zona con incidentes recientes).

Contador:
  dias_sin_hechos_violentos = (hoy − fecha_último_hecho).days

Entradas:
  data/events.json
  data/manual_events.json

Salidas:
  data/map_layers.json      → zonas activas y amarillas (polígonos)
  data/archive_points.json  → zonas archivadas (puntos)
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import Point, mapping


# =============================================================================
# CONFIGURACIÓN GENERAL
# =============================================================================

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

EVENTS_PATH = DATA_DIR / "events.json"
MANUAL_EVENTS_PATH = DATA_DIR / "manual_events.json"
OUTPUT_PATH = DATA_DIR / "map_layers.json"
ARCHIVE_OUTPUT_PATH = DATA_DIR / "archive_points.json"

WGS84 = "EPSG:4326"
UTM14N = "EPSG:32614"

# Parámetros de zonas
DEFAULT_BUFFER_METERS = 500
ESCALATION_DAYS = 3           # Días para escalar de naranja a rojo (2.° hecho)
YELLOW_THRESHOLD = 30         # Días sin hechos → amarillo
ARCHIVE_THRESHOLD = 60        # Días sin hechos → archivado
EXTRA_RADIUS_PER_INCIDENT = 50   # +50 m de radio (+100 m de diámetro) por hecho violento adicional


# =============================================================================
# UTILIDADES DE CARGA
# =============================================================================

def load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def load_events() -> list[dict[str, Any]]:
    """Carga y combina eventos automáticos y manuales, eliminando duplicados."""
    scraped = load_json_list(EVENTS_PATH)
    manual = load_json_list(MANUAL_EVENTS_PATH)

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    for event in scraped + manual:
        key = event.get("fuente") or event.get("id")
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(event)

    return merged


# =============================================================================
# UTILIDADES DE FECHA
# =============================================================================

def parse_event_date(value: str | None) -> date:
    if not value:
        return date.today()

    value = str(value).strip()

    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except Exception:
        return date.today()


# =============================================================================
# LÓGICA DE ZONAS
# =============================================================================

def get_zone_key(event: dict[str, Any]) -> str:
    """Clave única de zona para agrupar eventos en la misma ubicación."""
    scope = event.get("location_scope", "colonia")
    name = str(event.get("location_name") or event.get("colonia") or "").strip()

    if not name or name.lower() in ("no especificada", "no disponible", ""):
        return f"_id_:{event.get('id', 'unknown')}"

    return f"{scope}:{name}"


def compute_zone_level(
    n_incidents: int,
    days_without: int,
    event_dates: list[date],
) -> str:
    """
    Determina el nivel de la zona:

    - archivado : 60+ días sin hechos
    - amarillo  : 30–60 días sin hechos
    - rojo      : activo + (3+ hechos, o 2 hechos en ≤ 3 días)
    - naranja   : activo + 1 hecho (o 2 hechos con > 3 días de diferencia)
    """
    if days_without >= ARCHIVE_THRESHOLD:
        return "archivado"
    if days_without >= YELLOW_THRESHOLD:
        return "amarillo"

    # Zona activa
    if n_incidents >= 3:
        return "rojo"
    if n_incidents >= 2:
        sorted_dates = sorted(event_dates)
        gap_days = (sorted_dates[1] - sorted_dates[0]).days
        if gap_days <= ESCALATION_DAYS:
            return "rojo"

    return "naranja"


def compute_zone_radius(base_radius: int, n_incidents: int) -> int:
    """Radio de la zona: base + (n−1) × 240 m."""
    return base_radius + max(0, n_incidents - 1) * EXTRA_RADIUS_PER_INCIDENT


def _make_archived_entry(event: dict[str, Any], lat: float, lon: float, today: date) -> dict[str, Any]:
    """Crea una entrada archivada individual para un evento viejo (≥ ARCHIVE_THRESHOLD días)."""
    event_date = parse_event_date(event.get("fecha"))
    days_old = max(0, (today - event_date).days)
    url = event.get("fuente")
    fuentes = [{"title": event.get("source_title") or event.get("resumen") or "Fuente", "url": url}] if url else []
    return {
        "level": "archivado",
        "n_incidents": 1,
        "dias_sin_hechos_violentos": days_old,
        "last_incident_date": str(event_date),
        "first_incident_date": str(event_date),
        "location_scope": event.get("location_scope", "colonia"),
        "location_name": str(event.get("location_name") or event.get("colonia") or "No especificada"),
        "delitos": [str(event.get("tipo_delito") or "No especificado")],
        "fuentes": fuentes,
        "radius_meters": 0,
        "centroid": Point(lon, lat),
    }


def group_into_zones(
    events: list[dict[str, Any]],
    today: date,
) -> list[dict[str, Any]]:
    """
    Agrupa los eventos por ubicación y calcula el estado de cada zona.

    Eventos con ≥ ARCHIVE_THRESHOLD días → puntos negros individuales,
    aunque su zona siga activa (p. ej. un hecho antiguo en una zona con
    incidentes recientes).

    Retorna una lista de dicts con:
      level, n_incidents, dias_sin_hechos_violentos,
      last_incident_date, first_incident_date,
      location_scope, location_name,
      delitos, fuentes, radius_meters, centroid (Shapely Point WGS84)
    """
    zone_map: dict[str, dict[str, Any]] = {}
    individual_archived: list[dict[str, Any]] = []

    for event in events:
        coords = event.get("coordenadas")
        if not isinstance(coords, (list, tuple)) or len(coords) != 2:
            continue
        try:
            lat = float(coords[0])
            lon = float(coords[1])
        except Exception:
            continue

        event_date = parse_event_date(event.get("fecha"))
        days_old = max(0, (today - event_date).days)

        # Eventos viejos → punto negro individual (aunque la zona siga activa)
        if days_old >= ARCHIVE_THRESHOLD:
            individual_archived.append(_make_archived_entry(event, lat, lon, today))
            continue

        key = get_zone_key(event)

        if key not in zone_map:
            try:
                buffer_m = int(event.get("buffer_meters", DEFAULT_BUFFER_METERS))
            except Exception:
                buffer_m = DEFAULT_BUFFER_METERS

            zone_map[key] = {
                "location_scope": event.get("location_scope", "colonia"),
                "location_name": str(
                    event.get("location_name") or event.get("colonia") or "No especificada"
                ),
                "buffer_meters": buffer_m,
                "events": [],
                "lons": [],
                "lats": [],
            }

        zone_map[key]["events"].append(event)
        zone_map[key]["lons"].append(lon)
        zone_map[key]["lats"].append(lat)

    zones: list[dict[str, Any]] = []

    for _key, zdata in zone_map.items():
        evs = zdata["events"]
        n = len(evs)

        event_dates = sorted([parse_event_date(e.get("fecha")) for e in evs])
        last_date = event_dates[-1]
        first_date = event_dates[0]
        days_without = max(0, (today - last_date).days)

        level = compute_zone_level(n, days_without, event_dates)
        radius = compute_zone_radius(zdata["buffer_meters"], n)

        lons = zdata["lons"]
        lats = zdata["lats"]
        centroid = Point(sum(lons) / len(lons), sum(lats) / len(lats))

        delitos = sorted(
            {str(e.get("tipo_delito") or "No especificado") for e in evs}
        )

        # Fuentes más recientes primero (hasta 5)
        fuentes: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for e in sorted(evs, key=lambda x: x.get("fecha") or "", reverse=True):
            url = e.get("fuente")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            fuentes.append(
                {
                    "title": e.get("source_title") or e.get("resumen") or "Fuente",
                    "url": url,
                }
            )
            if len(fuentes) >= 5:
                break

        zones.append(
            {
                "level": level,
                "n_incidents": n,
                "dias_sin_hechos_violentos": days_without,
                "last_incident_date": str(last_date),
                "first_incident_date": str(first_date),
                "location_scope": zdata["location_scope"],
                "location_name": zdata["location_name"],
                "delitos": delitos,
                "fuentes": fuentes,
                "radius_meters": radius,
                "centroid": centroid,
            }
        )

    # Eventos viejos individuales siempre al final (puntos negros)
    zones.extend(individual_archived)

    return zones


# =============================================================================
# EXPORTACIÓN DE ZONAS CALIENTES (naranja / rojo / amarillo)
# =============================================================================

def export_hot_zones(zones: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Exporta las zonas activas y en vigilancia como polígonos GeoJSON.
    Cada zona es un círculo (buffer) centrado en el centroide de los eventos.
    """
    hot_zones = [z for z in zones if z["level"] in ("naranja", "rojo", "amarillo")]

    empty = {"type": "FeatureCollection", "features": []}

    if not hot_zones:
        OUTPUT_PATH.write_text(
            json.dumps(empty, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return empty

    # Crear GeoDataFrame de centroides en WGS84 → proyectar a UTM14N para buffer
    gdf = gpd.GeoDataFrame(
        {
            "radius_meters": [z["radius_meters"] for z in hot_zones],
            "geometry": [z["centroid"] for z in hot_zones],
        },
        crs=WGS84,
    ).to_crs(UTM14N)

    gdf["geometry"] = gdf.apply(
        lambda row: row.geometry.buffer(int(row["radius_meters"])),
        axis=1,
    )

    gdf = gdf.to_crs(WGS84)

    # Construir features manualmente para preservar listas
    features: list[dict[str, Any]] = []
    for i, (_, row) in enumerate(gdf.iterrows()):
        z = hot_zones[i]
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(row.geometry),
                "properties": {
                    "level": z["level"],
                    "n_incidents": z["n_incidents"],
                    "dias_sin_hechos_violentos": z["dias_sin_hechos_violentos"],
                    "last_incident_date": z["last_incident_date"],
                    "first_incident_date": z["first_incident_date"],
                    "location_scope": z["location_scope"],
                    "location_name": z["location_name"],
                    "delitos": z["delitos"],
                    "fuentes": z["fuentes"],
                    "radius_meters": z["radius_meters"],
                },
            }
        )

    geojson = {"type": "FeatureCollection", "features": features}
    OUTPUT_PATH.write_text(
        json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return geojson


# =============================================================================
# EXPORTACIÓN DE ZONAS ARCHIVADAS (cuadrados negros)
# =============================================================================

def export_archive_points(zones: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Exporta las zonas archivadas como puntos GeoJSON.
    El frontend los muestra como cuadrados negros (registro histórico).
    """
    archived = [z for z in zones if z["level"] == "archivado"]

    empty = {"type": "FeatureCollection", "features": []}

    if not archived:
        ARCHIVE_OUTPUT_PATH.write_text(
            json.dumps(empty, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return empty

    features: list[dict[str, Any]] = []
    for z in archived:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [z["centroid"].x, z["centroid"].y],
                },
                "properties": {
                    "location_scope": z["location_scope"],
                    "location_name": z["location_name"],
                    "n_incidents": z["n_incidents"],
                    "dias_sin_hechos_violentos": z["dias_sin_hechos_violentos"],
                    "last_incident_date": z["last_incident_date"],
                    "first_incident_date": z["first_incident_date"],
                    "delitos": z["delitos"],
                    "fuentes": z["fuentes"],
                    "marker_type": "archived_square",
                },
            }
        )

    geojson = {"type": "FeatureCollection", "features": features}
    ARCHIVE_OUTPUT_PATH.write_text(
        json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return geojson


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def process_risk_zones() -> dict[str, Any]:
    """
    Flujo principal:
    1. Carga eventos (automáticos + manuales)
    2. Agrupa por zona y calcula nivel, radio y contador
    3. Exporta zonas calientes (naranja/rojo/amarillo) como polígonos
    4. Exporta zonas archivadas como puntos
    """
    today = date.today()
    events = load_events()

    if not events:
        empty = {"type": "FeatureCollection", "features": []}
        OUTPUT_PATH.write_text(
            json.dumps(empty, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        ARCHIVE_OUTPUT_PATH.write_text(
            json.dumps(empty, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("ℹ️ No hay eventos. Se generaron GeoJSONs vacíos.")
        return empty

    zones = group_into_zones(events, today)

    hot_geojson = export_hot_zones(zones)
    archive_geojson = export_archive_points(zones)

    n_rojo = sum(1 for z in zones if z["level"] == "rojo")
    n_naranja = sum(1 for z in zones if z["level"] == "naranja")
    n_amarillo = sum(1 for z in zones if z["level"] == "amarillo")
    n_archivado = sum(1 for z in zones if z["level"] == "archivado")

    print(
        f"✅ {len(hot_geojson['features'])} zonas exportadas "
        f"({n_rojo} rojas, {n_naranja} naranjas, {n_amarillo} amarillas)"
    )
    print(f"🗃️ {n_archivado} zonas archivadas exportadas a {ARCHIVE_OUTPUT_PATH}")

    return hot_geojson


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    process_risk_zones()
