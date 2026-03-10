const map = L.map('map').setView([18.9218, -99.2347], 13);

L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; OpenStreetMap &copy; CARTO'
}).addTo(map);

function getColor(nivel) {
  return nivel >= 7 ? '#8B0000' :
         nivel >= 4 ? '#FF8C00' :
                      '#FFD700';
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function joinList(items, fallback = 'No disponible') {
  if (!Array.isArray(items) || items.length === 0) return fallback;
  return items.map(x => escapeHtml(x)).join(', ');
}

const infoPanel = document.getElementById('info-panel');

const statusEl = document.createElement('p');
statusEl.id = 'status-text';
statusEl.style.fontSize = '0.85rem';
statusEl.style.color = '#bbb';
statusEl.style.marginTop = '12px';
statusEl.textContent = 'Cargando datos…';
infoPanel.appendChild(statusEl);

const statsEl = document.createElement('p');
statsEl.id = 'stats-text';
statsEl.style.fontSize = '0.8rem';
statsEl.style.color = '#9ad';
statsEl.style.marginTop = '8px';
statsEl.textContent = '';
infoPanel.appendChild(statsEl);

function buildPopup(props) {
  const fuentes = Array.isArray(props.fuentes) ? props.fuentes : [];

  const fuentesHtml = fuentes.length
    ? `<ul style="padding-left: 18px; margin: 8px 0 0;">
        ${fuentes.map((f) => {
          const title = escapeHtml((f && f.title) || 'Fuente');
          const url = (f && f.url) || '#';
          return `<li><a href="${url}" target="_blank" rel="noopener noreferrer">${title}</a></li>`;
        }).join('')}
      </ul>`
    : '<div>Sin fuentes enlazadas.</div>';

  return `
    <div style="min-width: 240px; line-height: 1.45;">
      <div style="font-size: 1rem; font-weight: 700; margin-bottom: 8px;">
        Nivel ${escapeHtml(props.nivel)}
      </div>

      <div><strong>Eventos activos:</strong> ${escapeHtml(props.n_eventos)}</div>
      <div><strong>Eventos ≥ 5:</strong> ${escapeHtml(props.n_eventos_ge5)}</div>
      <div><strong>Colonias:</strong> ${joinList(props.colonias)}</div>
      <div><strong>Delitos:</strong> ${joinList(props.delitos)}</div>

      <div style="margin-top: 8px; color: #555;">
        ${escapeHtml(props.info || '')}
      </div>

      <div style="margin-top: 10px;">
        <strong>Fuentes:</strong>
        ${fuentesHtml}
      </div>
    </div>
  `;
}

fetch(`data/map_layers.json?v=${Date.now()}`, { cache: 'no-store' })
  .then((response) => {
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
  })
  .then((data) => {
    const features = Array.isArray(data.features) ? data.features : [];

    if (features.length === 0) {
      statusEl.textContent = 'No hay celdas activas en este momento.';
      statsEl.textContent = '0 zonas visibles';
      return;
    }

    let maxNivel = 0;

    const layer = L.geoJSON(data, {
      style: function(feature) {
        const nivel = feature.properties.nivel || 0;
        maxNivel = Math.max(maxNivel, nivel);

        return {
          fillColor: getColor(nivel),
          weight: 0.8,
          opacity: 1,
          color: '#ffffff',
          fillOpacity: 0.55
        };
      },
      onEachFeature: function(feature, layer) {
        const popupContent = buildPopup(feature.properties || {});
        layer.bindPopup(popupContent, { maxWidth: 320 });
      }
    }).addTo(map);

    const bounds = layer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [20, 20] });
    }

    statusEl.textContent = 'Datos cargados correctamente.';
    statsEl.textContent = `${features.length} zonas visibles · nivel máximo ${maxNivel}`;
  })
  .catch((error) => {
    console.error('Error cargando el mapa:', error);
    statusEl.textContent = 'No se pudieron cargar los datos del mapa.';
    statsEl.textContent = 'Revisa data/map_layers.json';
  });