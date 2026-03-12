//prime-frontend/src/components/mapview.jsx
import { useMemo } from 'react';
import { MapContainer, TileLayer, Polyline, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import { MAP_CONFIG } from '../constants/mapConfig';
import { ARCHETYPES } from '../constants/archetypes';
import ArchetypeChip from './ArchetypeChip';
import PdfExportButton from './PdfExportButton';

// Fix for default marker icons in Leaflet + bundlers
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

export default function MapView({
  fleetResponse,
  selectedArchetype,
  parsedPayload,
  onChangeArchetype,
  onBack,
}) {
  const plans = fleetResponse?.plans || {};

  // Available archetype keys
  const availableArchetypes = Object.entries(ARCHETYPES).filter(([key]) => {
    const plan = plans[key];
    if (!plan || plan.error) return false;
    if (key === 'unicornio') {
      return plan.assignments?.some(a => a.route_destinations?.length > 0);
    }
    return true;
  });

  // Extract route coordinates for the selected archetype
  const routeCoords = useMemo(() => {
    const plan = plans[selectedArchetype];
    if (!plan?.segments_pareto) return [];

    const coords = [];
    for (const segment of plan.segments_pareto) {
      const match = segment.pareto_solutions?.find(s => s.archetype === selectedArchetype);
      if (match?.route_coordinates) {
        coords.push(...match.route_coordinates);
      }
    }
    return coords;
  }, [plans, selectedArchetype]);

  // Schedule for panel
  const schedule = useMemo(() => {
    const plan = plans[selectedArchetype];
    if (!plan?.assignments) return [];
    return plan.assignments.flatMap((a, vIdx) =>
      (a.schedule || []).map(s => ({
        ...s,
        vehicleId: a.vehicle?.id || `V${vIdx + 1}`,
      }))
    );
  }, [plans, selectedArchetype]);

  const destinations = parsedPayload?.destinations || [];
  const archetypeColor = ARCHETYPES[selectedArchetype]?.color || '#2563EB';

  return (
    <div id="map-view" className="flex flex-col h-[calc(100vh-4rem)]">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-3 bg-zinc-900/90 border-b border-zinc-800 flex-shrink-0">
        <button
          id="back-to-results"
          onClick={onBack}
          className="text-sm text-zinc-400 hover:text-white transition-colors flex items-center gap-1"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Volver a resultados
        </button>

        <div className="flex gap-2 overflow-x-auto">
          {availableArchetypes.map(([key, arch]) => (
            <ArchetypeChip
              key={key}
              archetype={arch}
              onClick={onChangeArchetype}
              isSelected={key === selectedArchetype}
            />
          ))}
        </div>

        <PdfExportButton fleetResponse={fleetResponse} selectedArchetype={selectedArchetype} />
      </div>

      {/* Main content: map + panel */}
      <div className="flex flex-1 min-h-0">
        {/* Map */}
        <div className="flex-[7] relative">
          <MapContainer
            center={MAP_CONFIG.center}
            zoom={MAP_CONFIG.zoom}
            style={{ height: '100%', width: '100%' }}
            className="z-0"
          >
            <TileLayer url={MAP_CONFIG.tileUrl} attribution={MAP_CONFIG.attribution} />

            {routeCoords.length > 0 && (
              <Polyline
                positions={routeCoords}
                color={archetypeColor}
                weight={4}
                opacity={0.85}
              />
            )}

            {destinations.map(d => (
              <Marker key={d.id} position={[d.lat, d.lon]}>
                <Popup>
                  <strong>{d.id}</strong><br />
                  {d.demand_tons} tn
                </Popup>
              </Marker>
            ))}
          </MapContainer>
        </div>

        {/* Schedule panel */}
        <div className="flex-[3] bg-zinc-900 border-l border-zinc-800 overflow-y-auto p-4">
          <h3 className="text-sm font-semibold text-zinc-300 mb-4">
            Cronograma — {ARCHETYPES[selectedArchetype]?.emoji} {ARCHETYPES[selectedArchetype]?.label}
          </h3>

          {schedule.length === 0 ? (
            <p className="text-zinc-500 text-sm">Sin paradas asignadas.</p>
          ) : (
            <div className="space-y-2">
              {schedule.map((s, i) => (
                <div
                  key={i}
                  className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/30"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-zinc-200">{s.destination_id}</span>
                    <span className="text-sm font-mono text-zinc-400">
                      {s.suggested_arrival_hhmm || '--:--'}
                    </span>
                  </div>
                  <span className="text-xs text-zinc-500">
                    Vehículo {s.vehicleId}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
