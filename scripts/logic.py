from __future__ import annotations

"""
OVICUE - logic.py

Este script transforma los eventos del proyecto en capas geoespaciales
listas para el frontend.

Entradas:
- data/events.json
- data/manual_events.json

Salidas:
- data/map_layers.json      -> capa caliente (zonas activas)
- data/archive_points.json  -> puntos archivados (eventos históricos)

Qué hace:
1. Carga eventos automáticos y manuales
2. Los combina y elimina duplicados
3. Calcula el nivel actual aplicando decaimiento temporal
4. Separa:
   - eventos activos (nivel_actual > 0)
   - eventos archivados (nivel_actual == 0)
5. Los activos se convierten en buffers y luego en celdas agregadas
6. Los archivados se exportan como puntos
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, box
from shapely.ops import unary_union


# =============================================================================
# CONFIGURACIÓN GENERAL
# =============================================================================

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

# Archivos de entrada
EVENTS_PATH = DATA_DIR / "events.json"
MANUAL_EVENTS_PATH = DATA_DIR / "manual_events.json"

# Archivos de salida
OUTPUT_PATH = DATA_DIR / "map_layers.json"
ARCHIVE_OUTPUT_PATH = DATA_DIR / "archive_points.json"

# Sistemas de referencia
WGS84 = "EPSG:4326"      # lat/lon para web
UTM14N = "EPSG:32614"    # metros reales para Cuernavaca

# Parámetros espaciales
DEFAULT_BUFFER_METERS = 500
DEFAULT_CELL_SIZE_METERS = 120


# =============================================================================
# UTILIDADES DE CARGA
# =============================================================================

def load_json_list(path: Path) -> list[dict[str, Any]]:
    """
    Carga un archivo JSON que debe contener una lista.
    Si no existe o es inválido, devuelve [].
    """
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def load_events() -> list[dict[str, Any]]:
    """
    Carga y combina:
    - eventos automáticos
    - eventos manuales

    Elimina duplicados priorizando la URL ('fuente').
    Si no hay URL, usa 'id'.
    """
    scraped = load_json_list(EVENTS_PATH)
    manual = load_json_list(MANUAL_EVENTS_PATH)

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    for event in scraped + manual:
        key = event.get("fuente") or event.get("id")
        if not key:
            continue
        if key in seen:
            continue

        seen.add(key)
        merged.append(event)

    return merged


# =============================================================================
# FECHAS Y DECAIMIENTO
# =============================================================================

def parse_event_date(value: str | None) -> date:
    """
    Convierte una fecha de texto a objeto date.

    Formatos aceptados:
    - YYYY-MM-DD
    - YYYY/MM/DD
    - ISO datetime

    Si no puede interpretarla, usa la fecha actual.
    """
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


def calculate_decay(event: dict[str, Any], today: date | None = None) -> int:
    """
    Calcula el nivel actual del evento.

    Regla:
    nivel_actual = max(0, nivel_inicial - floor(días_transcurridos / 30))
    """
    today = today or date.today()

    event_date = parse_event_date(event.get("fecha"))
    days_elapsed = max(0, (today - event_date).days)

    try:
        initial = int(event.get("nivel_inicial", 5))
    except Exception:
        initial = 5

    return max(0, initial - (days_elapsed // 30))


# =============================================================================
# NORMALIZACIÓN DE EVENTOS
# =============================================================================

def normalize_events(events: list[dict[str, Any]]) -> pd.DataFrame:
    """
    Convierte la lista de eventos en un DataFrame limpio.

    No descarta los eventos archivados:
    - los activos seguirán al mapa caliente
    - los archivados se irán a archive_points.json
    """
    rows: list[dict[str, Any]] = []

    for event in events:
        coords = event.get("coordenadas")

        # Se espera [lat, lon]
        if not isinstance(coords, (list, tuple)) or len(coords) != 2:
            continue

        try:
            lat = float(coords[0])
            lon = float(coords[1])
        except Exception:
            continue

        level = calculate_decay(event)
        is_archived = level <= 0

        try:
            nivel_inicial = int(event.get("nivel_inicial", 5))
        except Exception:
            nivel_inicial = 5

        try:
            buffer_meters = int(event.get("buffer_meters", DEFAULT_BUFFER_METERS))
        except Exception:
            buffer_meters = DEFAULT_BUFFER_METERS

        rows.append(
            {
                "id": event.get("id"),
                "fecha": event.get("fecha"),
                "hora": event.get("hora"),
                "colonia": event.get("colonia", "No especificada"),
                "municipio_detectado": event.get("municipio_detectado"),
                "location_scope": event.get("location_scope", "colonia"),
                "location_name": event.get("location_name") or event.get("colonia", "No especificada"),
                "tipo_delito": event.get("tipo_delito", "No especificado"),
                "fuente": event.get("fuente"),
                "source_title": event.get("source_title"),
                "source_name": event.get("source_name"),
                "resumen": event.get("resumen"),
                "geo_confidence": event.get("geo_confidence"),
                "nivel_inicial": nivel_inicial,
                "nivel_actual": level,
                "archived": is_archived,
                "buffer_meters": buffer_meters,
                "geometry": Point(lon, lat),  # shapely usa (x, y) = (lon, lat)
            }
        )

    return pd.DataFrame(rows)


# =============================================================================
# EXPORTACIÓN DE EVENTOS ARCHIVADOS
# =============================================================================

def export_archive_points(df: pd.DataFrame) -> dict[str, Any]:
    """
    Exporta los eventos archivados (nivel_actual == 0) como puntos GeoJSON.

    El frontend los puede mostrar como pequeños cuadrados negros.
    """
    if df.empty or "archived" not in df.columns:
        archive_geojson = {"type": "FeatureCollection", "features": []}
        ARCHIVE_OUTPUT_PATH.write_text(
            json.dumps(archive_geojson, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return archive_geojson

    archived_df = df[df["archived"]].copy()

    if archived_df.empty:
        archive_geojson = {"type": "FeatureCollection", "features": []}
        ARCHIVE_OUTPUT_PATH.write_text(
            json.dumps(archive_geojson, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return archive_geojson

    archive_gdf = gpd.GeoDataFrame(archived_df, geometry="geometry", crs=WGS84)
    archive_gdf["marker_type"] = "archived_square"

    geojson = json.loads(archive_gdf.to_json(drop_id=True))

    ARCHIVE_OUTPUT_PATH.write_text(
        json.dumps(geojson, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return geojson


# =============================================================================
# CONSTRUCCIÓN DE GRILLA
# =============================================================================

def make_grid(bounds: tuple[float, float, float, float], cell_size: int) -> list:
    """
    Construye una grilla rectangular regular.

    bounds = (minx, miny, maxx, maxy)
    cell_size = tamaño de celda en metros
    """
    minx, miny, maxx, maxy = bounds

    xs = np.arange(minx, maxx + cell_size, cell_size)
    ys = np.arange(miny, maxy + cell_size, cell_size)

    cells = []
    for x in xs[:-1]:
        for y in ys[:-1]:
            cells.append(box(x, y, x + cell_size, y + cell_size))

    return cells


# =============================================================================
# RESUMEN POR CELDA
# =============================================================================

def summarize_covering_events(covering: pd.DataFrame) -> dict[str, Any]:
    """
    Resume los eventos activos que cubren una celda.

    Nivel final:
    - base = máximo nivel_actual
    - sinergia = +1 por cada evento adicional con nivel >= 5
    - tope = 10
    """
    levels = covering["nivel_actual"].astype(int).tolist()
    max_level = max(levels)
    high_risk_count = sum(level >= 5 for level in levels)

    final_level = min(10, max_level + max(0, high_risk_count - 1))

    delitos = sorted({str(x) for x in covering["tipo_delito"].dropna().tolist()})
    colonias = sorted({str(x) for x in covering["colonia"].dropna().tolist() if str(x).strip()})
    municipios = sorted({str(x) for x in covering["municipio_detectado"].dropna().tolist() if str(x).strip()})
    location_scopes = sorted({str(x) for x in covering["location_scope"].dropna().tolist()})
    location_names = sorted({str(x) for x in covering["location_name"].dropna().tolist() if str(x).strip()})

    # Guardar hasta 5 fuentes únicas
    fuentes: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for _, row in covering.iterrows():
        url = row.get("fuente")
        if not url or url in seen_urls:
            continue

        seen_urls.add(url)
        fuentes.append(
            {
                "title": row.get("source_title") or row.get("resumen") or "Fuente",
                "url": url,
            }
        )

        if len(fuentes) >= 5:
            break

    if municipios:
        info = f"{len(covering)} evento(s) activo(s) · área conurbada / municipio"
    else:
        info = f"{len(covering)} evento(s) activo(s) · referencia por colonia"

    return {
        "nivel": int(final_level),
        "max_nivel_base": int(max_level),
        "n_eventos": int(len(covering)),
        "n_eventos_ge5": int(high_risk_count),
        "delitos": delitos,
        "colonias": colonias,
        "municipios": municipios,
        "location_scopes": location_scopes,
        "location_names": location_names,
        "fuentes": fuentes,
        "info": info,
    }


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def process_risk_zones() -> dict[str, Any]:
    """
    Flujo principal:

    1. Carga eventos
    2. Calcula niveles y banderas de archivo
    3. Exporta los eventos archivados como puntos
    4. Procesa solo los activos para construir el mapa caliente
    5. Exporta el GeoJSON final de celdas
    """
    events = load_events()
    df = normalize_events(events)

    # Exportar archivados siempre, aunque no haya activos
    export_archive_points(df)

    # Filtrar activos para el mapa caliente
    active_df = df[~df["archived"]].copy() if not df.empty else df

    # Caso 1: no hay eventos activos
    if active_df.empty:
        feature_collection = {"type": "FeatureCollection", "features": []}
        OUTPUT_PATH.write_text(
            json.dumps(feature_collection, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("ℹ️ No hay eventos activos. Se generó un GeoJSON caliente vacío.")
        print(f"🗃️ Eventos archivados exportados a {ARCHIVE_OUTPUT_PATH}")
        return feature_collection

    # Convertir a GeoDataFrame y proyectar a sistema métrico
    gdf = gpd.GeoDataFrame(active_df, geometry="geometry", crs=WGS84).to_crs(UTM14N)

    # Cada evento usa su propio buffer:
    # - colonia = 500 m
    # - municipio/conurbado = 1000 m
    gdf["geometry"] = gdf.apply(
        lambda row: row.geometry.buffer(int(row["buffer_meters"])),
        axis=1,
    )

    # Unión de todas las áreas activas
    union_geom = unary_union(list(gdf.geometry))

    # Crear grilla regular
    grid_cells = make_grid(union_geom.bounds, DEFAULT_CELL_SIZE_METERS)
    grid = gpd.GeoDataFrame({"geometry": grid_cells}, crs=UTM14N)

    # Solo celdas que tocan alguna zona activa
    grid = grid[grid.intersects(union_geom)].copy()

    features: list[dict[str, Any]] = []

    for cell in grid.geometry:
        covering = gdf[gdf.geometry.intersects(cell)]
        if covering.empty:
            continue

        props = summarize_covering_events(covering)
        features.append(
            {
                "geometry": cell,
                **props,
            }
        )

    # Caso 2: había activos, pero no quedaron celdas útiles
    if not features:
        feature_collection = {"type": "FeatureCollection", "features": []}
        OUTPUT_PATH.write_text(
            json.dumps(feature_collection, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("ℹ️ No se generaron celdas con cobertura.")
        print(f"🗃️ Eventos archivados exportados a {ARCHIVE_OUTPUT_PATH}")
        return feature_collection

    # Regresar a WGS84 para uso web
    result = gpd.GeoDataFrame(features, geometry="geometry", crs=UTM14N).to_crs(WGS84)

    geojson = json.loads(result.to_json(drop_id=True))
    OUTPUT_PATH.write_text(
        json.dumps(geojson, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"✅ {len(geojson['features'])} celdas calientes exportadas a {OUTPUT_PATH}")
    print(f"🗃️ Eventos archivados exportados a {ARCHIVE_OUTPUT_PATH}")
    return geojson


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    process_risk_zones()