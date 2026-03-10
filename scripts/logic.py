import json
import os
from datetime import datetime
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union

def load_events():
    with open('data/events.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def calculate_decay(event):
    """Aplica la regla de -1 punto cada 30 días."""
    fecha_evento = datetime.strptime(event['fecha'], '%Y-%m-%d')
    dias_pasados = (datetime.now() - fecha_evento).days
    puntos_a_restar = dias_pasados // 30
    nuevo_nivel = max(0, event['nivel_inicial'] - puntos_a_restar)
    return nuevo_nivel

def process_risk_zones():
    events = load_events()
    if not events:
        print("No hay eventos para procesar.")
        return

    # 1. Crear GeoDataFrame con los eventos y aplicar decaimiento
    df = gpd.DataFrame(events)
    df['nivel_actual'] = df.apply(calculate_decay, axis=1)
    
    # Filtrar eventos que ya llegaron a nivel 0
    df = df[df['nivel_actual'] > 0].copy()
    
    # Crear geometría de puntos (WGS84)
    df['geometry'] = df['coordenadas'].apply(lambda x: Point(x[1], x[0]))
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")

    # 2. Proyectar a metros (UTM 14N para Cuernavaca) para calcular el radio de 500m
    gdf_meters = gdf.to_crs(epsg=32614)
    gdf_meters['geometry'] = gdf_meters.buffer(500) # Radio de 500 metros

    # 3. Lógica de Empalmes y Niveles
    # Vamos a iterar para ver qué zonas se intersectan
    final_zones = []
    
    # Ordenamos por nivel para procesar primero los más peligrosos
    gdf_meters = gdf_meters.sort_values(by='nivel_actual', ascending=False)

    for i, row in gdf_meters.iterrows():
        current_geom = row['geometry']
        current_level = row['nivel_actual']
        
        # Revisar si se empalma con zonas ya procesadas
        for zone in final_zones:
            if current_geom.intersects(zone['geometry']):
                # Regla: Si ambos son nivel >= 5, suben +1
                if current_level >= 5 and zone['nivel'] >= 5:
                    zone['nivel'] = min(10, zone['nivel'] + 1)
                # Regla: Si uno es menor a 5 pero el nuevo es 5, se resetea a 5
                elif current_level == 5 and zone['nivel'] < 5:
                    zone['level'] = 5
        
        final_zones.append({
            'geometry': current_geom,
            'nivel': current_level,
            'info': f"{row['tipo_delito']} en {row['colonia']}"
        })

    # 4. Exportar a GeoJSON para Leaflet (Volvemos a Lat/Long)
    result_gdf = gpd.GeoDataFrame(final_zones, crs="EPSG:32614").to_crs(epsg=4326)
    
    # Guardamos como archivo que el mapa podrá leer fácilmente
    result_gdf.to_file("data/map_layers.json", driver='GeoJSON')
    print("✨ Capas de mapa actualizadas en data/map_layers.json")

if __name__ == "__main__":
    process_risk_zones()