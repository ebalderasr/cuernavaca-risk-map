import os
import json
import requests
import time
import re
from bs4 import BeautifulSoup
from google import genai
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

# --- CONFIGURACIÓN ---
api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    print("❌ ERROR: La variable GOOGLE_API_KEY no está configurada.")
    print("Ejecuta: export GOOGLE_API_KEY='tu_llave_aqui'")
    exit()

client = genai.Client(api_key=api_key)
# Usamos el nombre exacto que salió en tu diagnóstico
GEMINI_MODEL = "models/gemini-2.5-flash" 

geolocator = Nominatim(user_agent="ovicue_app_v1")

SOURCES = [
    {
        "name": "Diario de Morelos", 
        "url": "https://www.diariodemorelos.com/seccion/justicia", 
        "selector": "article h3 a"
    }
]

KEYWORDS = ["homicidio", "muerto", "disparos", "balacera", "secuestro", "feminicidio", "ejecutado", "hallazgo", "cuerpo", "arma"]

def get_coordinates(colonia):
    query = f"{colonia}, Cuernavaca, Morelos, Mexico"
    try:
        location = geolocator.geocode(query, timeout=10)
        if location:
            return [location.latitude, location.longitude]
        return [18.9218, -99.2347]
    except (GeocoderTimedOut, Exception):
        return [18.9218, -99.2347]

def validate_and_extract(title):
    prompt = f"""
    Analiza este titular: "{title}"
    Si es un evento de violencia (homicidio, secuestro, feminicidio, balacera con heridos) en Cuernavaca, 
    responde ÚNICAMENTE con un objeto JSON. 
    Ejemplo: {{"es_violento": true, "delito": "homicidio", "colonia": "Centro", "hora_aprox": "23:00", "resumen": "texto corto"}}
    Si no es violento o no es en Cuernavaca: {{"es_violento": false}}
    """
    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        # Limpieza profunda de la respuesta para extraer solo el JSON
        raw_text = response.text.strip()
        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        
        if json_match:
            data = json.loads(json_match.group())
            # Aseguramos que los campos existan para evitar KeyErrors
            if data.get("es_violento"):
                required = ["delito", "colonia", "hora_aprox", "resumen"]
                for field in required:
                    if field not in data: data[field] = "Desconocido"
            return data
        return {"es_violento": False}
    except Exception as e:
        print(f"⚠️ Error en IA: {e}")
        return {"es_violento": False}

def run_scraper():
    print("🚀 OVICUE: Iniciando búsqueda de datos...")
    new_events = []
    
    # Crear carpeta data si no existe
    if not os.path.exists('data'): os.makedirs('data')
    
    if os.path.exists('data/events.json'):
        with open('data/events.json', 'r', encoding='utf-8') as f:
            try:
                existing_events = json.load(f)
            except: existing_events = []
    else:
        existing_events = []

    existing_urls = [e['fuente'] for e in existing_events]

    for source in SOURCES:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(source["url"], headers=headers, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.select(source["selector"])

            print(f"📊 Analizando {len(links)} noticias en {source['name']}...")

            for link in links:
                url = link['href']
                if not url.startswith('http'):
                    url = "https://www.diariodemorelos.com" + url
                
                title = link.text.strip()

                if url not in existing_urls and any(k in title.lower() for k in KEYWORDS):
                    print(f"🎯 Posible evento: {title[:50]}...")
                    data = validate_and_extract(title)

                    if data.get("es_violento"):
                        print(f"📍 Ubicando en {data['colonia']}...")
                        coords = get_coordinates(data['colonia'])
                        
                        hora_parts = data["hora_aprox"].split(':')
                        hora = int(hora_parts[0]) if hora_parts[0].isdigit() else 12
                        nivel = 6 if (hora >= 22 or hora <= 6) else 5

                        event = {
                            "id": str(hash(url)),
                            "fecha": time.strftime("%Y-%m-%d"),
                            "hora": data["hora_aprox"],
                            "colonia": data["colonia"],
                            "coordenadas": coords,
                            "tipo_delito": data["delito"],
                            "nivel_inicial": nivel,
                            "nivel_actual": nivel,
                            "fuente": url,
                            "resumen": data["resumen"]
                        }
                        new_events.append(event)
                        time.sleep(1) # Respeto a Nominatim

        except Exception as e:
            print(f"❌ Error en fuente {source['name']}: {e}")

    if new_events:
        all_events = existing_events + new_events
        with open('data/events.json', 'w', encoding='utf-8') as f:
            json.dump(all_events, f, indent=4, ensure_ascii=False)
        print(f"✨ Éxito: {len(new_events)} nuevos eventos guardados.")
    else:
        print("ℹ️ No se encontraron nuevos eventos violentos hoy.")

if __name__ == "__main__":
    run_scraper()