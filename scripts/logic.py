from __future__ import annotations

"""
OVICUE - logic.py

Este script toma los eventos de entrada y genera la capa geoespacial
final que consume el mapa web.

Entradas:
- data/events.json          -> eventos obtenidos automáticamente
- data/manual_events.json   -> eventos agregados manualmente por el administrador

Salida:
- data/map_layers.json      -> GeoJSON con celdas y propiedades agregadas

Idea general:
1. Cargar eventos automáticos y manuales
2. Unificarlos y quitar duplicados
3. Calcular el nivel actual según el tiempo transcurrido
4. Convertir eventos puntuales en buffers de 500 m
5. Construir una grilla regular sobre el área cubierta por los buffers
6. Para cada celda, calcular:
   - nivel final
   - número de eventos
   - colonias
   - delitos
   - fuentes
7. Exportar el resultado como GeoJSON
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

# Archivo de salida
OUTPUT_PATH = DATA_DIR / "map_layers.json"

# Sistemas de referencia
WGS84 = "EPSG:4326"     # lat/lon para web
UTM14N = "EPSG:32614"   # metros reales para Cuernavaca

# Parámetros del modelo espacial
BUFFER_METERS = 500
CELL_SIZE_METERS = 120


# =============================================================================
# UTILIDADES DE CARGA
# =============================================================================

def load_json_list(path: Path) -> list[dict[str, Any]]:
    """
    Carga un archivo JSON que debe contener una lista.
    Si el archivo no existe o no contiene una lista, regresa [].
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

    También elimina duplicados.
    La prioridad de deduplicación es:
    1. fuente (URL)
    2. id

    Esto permite que una nota manual y una automática no se dupliquen
    si ambas apuntan a la misma URL.
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

    Acepta formatos comunes:
    - YYYY-MM-DD
    - YYYY/MM/DD
    - ISO datetime

    Si no puede interpretar la fecha, usa la fecha actual.
    """
    if not value:
        return date.today()

    value = str(value).strip()

    # Intento 1: formatos simples de fecha
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            continue

    # Intento 2: formato ISO completo
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except Exception:
        return date.today()


def calculate_decay(event: dict[str, Any], today: date | None = None) -> int:
    """
    Calcula el nivel actual del evento aplicando decaimiento temporal.

    Regla:
    nivel_actual = max(0, nivel_inicial - floor(días_transcurridos / 30))

    Ejemplo:
    - nivel_inicial = 5
    - pasaron 45 días
    - nivel_actual = 4
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

    Filtra eventos con problemas como:
    - coordenadas ausentes
    - coordenadas mal formadas
    - nivel actual <= 0

    También convierte cada evento en un punto geográfico.
    """
    rows: list[dict[str, Any]] = []

    for event in events:
        coords = event.get("coordenadas")

        # Deben venir como [lat, lon]
        if not isinstance(coords, (list, tuple)) or len(coords) != 2:
            continue

        try:
            lat = float(coords[0])
            lon = float(coords[1])
        except Exception:
            continue

        # Nivel actual con decaimiento
        level = calculate_decay(event)
        if level <= 0:
            continue

        try:
            nivel_inicial = int(event.get("nivel_inicial", 5))
        except Exception:
            nivel_inicial = 5

        rows.append(
            {
                "id": event.get("id"),
                "fecha": event.get("fecha"),
                "hora": event.get("hora"),
                "colonia": event.get("colonia", "No especificada"),
                "tipo_delito": event.get("tipo_delito", "No especificado"),
                "fuente": event.get("fuente"),
                "source_title": event.get("source_title"),
                "source_name": event.get("source_name"),
                "resumen": event.get("resumen"),
                "geo_confidence": event.get("geo_confidence"),
                "nivel_inicial": nivel_inicial,
                "nivel_actual": level,
                "geometry": Point(lon, lat),  # shapely usa (x, y) = (lon, lat)
            }
        )

    return pd.DataFrame(rows)


# =============================================================================
# CONSTRUCCIÓN DE GRILLA
# =============================================================================

def make_grid(bounds: tuple[float, float, float, float], cell_size: int) -> list:
    """
    Construye una grilla rectangular regular sobre el bounding box.

    bounds = (minx, miny, maxx, maxy)
    cell_size = tamaño de lado de la celda en metros
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
# AGREGACIÓN POR CELDA
# =============================================================================

def summarize_covering_events(covering: pd.DataFrame) -> dict[str, Any]:
    """
    Resume los eventos que intersectan una celda.

    Reglas:
    - nivel base de la celda = máximo nivel_actual de los eventos que la tocan
    - sinergia pública por celda:
      +1 por cada evento adicional con nivel >= 5
    - tope máximo = 10

    También compila:
    - delitos
    - colonias
    - fuentes
    """
    levels = covering["nivel_actual"].astype(int).tolist()
    max_level = max(levels)
    high_risk_count = sum(level >= 5 for level in levels)

    # Sinergia estable y pública
    final_level = min(10, max_level + max(0, high_risk_count - 1))

    delitos = sorted({str(x) for x in covering["tipo_delito"].dropna().tolist()})
    colonias = sorted({str(x) for x in covering["colonia"].dropna().tolist()})

    # Guardamos hasta 5 fuentes únicas para la celda
    fuentes: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for _, row in covering.head(5).iterrows():
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

    info = f"{len(covering)} evento(s) activo(s)"

    return {
        "nivel": int(final_level),
        "max_nivel_base": int(max_level),
        "n_eventos": int(len(covering)),
        "n_eventos_ge5": int(high_risk_count),
        "delitos": delitos,
        "colonias": colonias,
        "fuentes": fuentes,
        "info": info,
    }


# =============================================================================
# PROCESAMIENTO PRINCIPAL
# =============================================================================

def process_risk_zones() -> dict[str, Any]:
    """
    Función principal del pipeline geoespacial.

    Flujo:
    1. Carga eventos
    2. Normaliza y filtra
    3. Convierte a GeoDataFrame
    4. Genera buffers de 500 m
    5. Une geometrías para obtener el área total cubierta
    6. Crea grilla
    7. Evalúa qué eventos cubren cada celda
    8. Exporta GeoJSON final
    """
    events = load_events()
    df = normalize_events(events)

    # Caso 1: no hay eventos activos
    if df.empty:
        feature_collection = {"type": "FeatureCollection", "features": []}
        OUTPUT_PATH.write_text(
            json.dumps(feature_collection, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("ℹ️ No hay eventos activos. Se generó un GeoJSON vacío.")
        return feature_collection

    # Convertimos de DataFrame a GeoDataFrame y pasamos a sistema métrico
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs=WGS84).to_crs(UTM14N)

    # Cada evento se vuelve un buffer de 500 metros
    gdf["geometry"] = gdf.geometry.buffer(BUFFER_METERS)

    # Geometría total cubierta por todos los buffers
    union_geom = unary_union(list(gdf.geometry))

    # Construimos grilla sobre toda el área cubierta
    grid_cells = make_grid(union_geom.bounds, CELL_SIZE_METERS)
    grid = gpd.GeoDataFrame({"geometry": grid_cells}, crs=UTM14N)

    # Nos quedamos solo con celdas que tocan al menos una zona de riesgo
    grid = grid[grid.intersects(union_geom)].copy()

    features: list[dict[str, Any]] = []

    for cell in grid.geometry:
        # Eventos cuyos buffers intersectan esta celda
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

    # Caso 2: hubo eventos, pero ninguna celda quedó con cobertura útil
    if not features:
        feature_collection = {"type": "FeatureCollection", "features": []}
        OUTPUT_PATH.write_text(
            json.dumps(feature_collection, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("ℹ️ No se generaron celdas con cobertura.")
        return feature_collection

    # Convertimos las celdas de vuelta a WGS84 para uso web
    result = gpd.GeoDataFrame(features, geometry="geometry", crs=UTM14N).to_crs(WGS84)

    # Exportamos como GeoJSON estándar
    geojson = json.loads(result.to_json(drop_id=True))
    OUTPUT_PATH.write_text(
        json.dumps(geojson, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"✅ {len(geojson['features'])} celdas exportadas a {OUTPUT_PATH}")
    return geojson


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    process_risk_zones()