//prime-frontend/src/services/osrmService.js
const OSRM_BASE = 'https://router.project-osrm.org/route/v1/driving';

/**
 * Given an array of waypoints [{lat, lon}], calls OSRM to get the real
 * road geometry and returns an array of [lat, lon][] for Leaflet.
 */
export async function buildRouteFromWaypoints(waypoints) {
  if (!waypoints || waypoints.length < 2) return [];
  try {
    const coordStr = waypoints.map(w => `${w.lon},${w.lat}`).join(';');
    const url = `${OSRM_BASE}/${coordStr}?overview=full&geometries=geojson`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`OSRM ${res.status}`);
    const data = await res.json();
    const geometry = data.routes?.[0]?.geometry?.coordinates;
    if (!geometry) return waypoints.map(w => [w.lat, w.lon]);
    return geometry.map(([lon, lat]) => [lat, lon]);
  } catch (err) {
    console.warn('OSRM fallback:', err.message);
    return waypoints.map(w => [w.lat, w.lon]);
  }
}
