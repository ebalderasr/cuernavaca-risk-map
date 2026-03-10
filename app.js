// Inicializar el mapa centrado en Cuernavaca
const map = L.map('map').setView([18.9218, -99.2347], 13);

// Añadir capa de mapa (CartoDB Positron es más limpio para datos de riesgo)
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO'
}).addTo(map);

// Función para determinar el color según el nivel
function getColor(nivel) {
    return nivel >= 7 ? '#8B0000' :
           nivel >= 4 ? '#FF8C00' :
                        '#FFD700';
}

// Cargar los datos desde el archivo GeoJSON generado por Python
fetch('data/map_layers.json')
    .then(response => response.json())
    .then(data => {
        L.geoJSON(data, {
            style: function(feature) {
                return {
                    fillColor: getColor(feature.properties.nivel),
                    weight: 1,
                    opacity: 1,
                    color: 'white',
                    fillOpacity: 0.6
                };
            },
            onEachFeature: function(feature, layer) {
                const popupContent = `
                    <strong>Nivel de Riesgo: ${feature.properties.nivel}</strong><br>
                    ${feature.properties.info}
                `;
                layer.bindPopup(popupContent);
            }
        }).addTo(map);
    })
    .catch(error => console.error('Error cargando el mapa:', error));