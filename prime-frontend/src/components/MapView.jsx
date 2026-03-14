//prime-frontend/src/components/MapView.jsx
import React, { useMemo, useState, useRef, useEffect } from 'react';
import { MapContainer, TileLayer, Polyline, Marker, Popup, Polygon } from 'react-leaflet';
import L from 'leaflet';
import { MAP_CONFIG } from '../constants/mapConfig';
import { ARCHETYPES } from '../constants/archetypes';
import { buildRouteFromWaypoints } from '../services/osrmService';
import ArchetypeChip from './ArchetypeChip';
import PdfExportButton from './PdfExportButton';

// Fix default marker icons
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

// ─── Vehicle color palette ───
const VEHICLE_COLORS = [
  '#0F172A', '#1F9D6A', '#D97706', '#7C3AED', '#DC2626', '#0891B2',
];

// ─── Custom icons ───
const truckIcon = (vehicleId) => L.divIcon({
  className: '',
  html: `<div style="background:#0F172A;color:white;padding:5px 10px;border-radius:10px;font-size:11px;font-weight:700;font-family:Inter,sans-serif;white-space:nowrap;box-shadow:0 3px 10px rgba(0,0,0,0.4);display:flex;align-items:center;gap:5px;">🚛 ${vehicleId}</div>`,
  iconAnchor: [0, 32],
});

const destIcon = (index, color = '#1F9D6A') => L.divIcon({
  className: '',
  html: `<div style="background:${color};color:white;width:30px;height:30px;border-radius:50%;font-size:12px;font-weight:800;font-family:Inter,sans-serif;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px ${color}80;border:2.5px solid white;">${index}</div>`,
  iconAnchor: [15, 15],
});

const animatingTruckIcon = (vehicleId, color) => L.divIcon({
  className: '',
  html: `<div style="background:${color};color:white;padding:5px 10px;border-radius:10px;font-size:11px;font-weight:800;font-family:Inter,sans-serif;box-shadow:0 4px 15px ${color}80;border:2px solid white;white-space:nowrap;">🚛 ${vehicleId}</div>`,
  iconAnchor: [40, 16],
});

const tollIcon = L.divIcon({
  className: '',
  html: `<div style="background:#0F172A;color:white;width:24px;height:24px;border-radius:6px;font-size:14px;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,0.3);border:2px solid #3B82F6;">🛣️</div>`,
  iconAnchor: [12, 12],
});

export default function MapView({ fleetResponse, selectedArchetype, parsedPayload, onChangeArchetype, onBack }) {
  const plans = fleetResponse?.plans || {};
  const destinations = parsedPayload?.destinations || [];

  // ─── OSRM state ───
  const [snappedCoords, setSnappedCoords] = useState({});
  const [isSnapping, setIsSnapping] = useState(false);

  // ─── Simulation state ───
  const [isSimulating, setIsSimulating] = useState(false);
  const [simTime, setSimTime] = useState('08:00');
  const [simPositions, setSimPositions] = useState({});
  const animFrameRef = useRef(null);

  // ─── Vehicle filter state ───
  const [visibleVehicles, setVisibleVehicles] = useState(null);

  useEffect(() => { setVisibleVehicles(null); }, [selectedArchetype]);
  useEffect(() => { return () => { if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current); }; }, []);

  // ─── Available archetypes ───
  const availableArchetypes = Object.entries(ARCHETYPES).filter(([key]) => {
    const plan = plans[key];
    if (!plan || plan.error) return false;
    if (key === 'unicornio') return plan.assignments?.some(a => a.route_destinations?.length > 0);
    return true;
  });

  // ─── Dest lookup ───
  const destLookup = useMemo(() => {
    const map = {};
    (parsedPayload?.destinations || []).forEach(d => { map[d.id] = d; });
    return map;
  }, [parsedPayload]);

  // ─── Bloque 7: Build waypoints from assignments ───
  const vehicleWaypoints = useMemo(() => {
    const plan = plans[selectedArchetype];
    if (!plan?.assignments) return [];
    return plan.assignments.map((assignment, vIdx) => {
      const vehicle = assignment.vehicle;
      const routeDests = assignment.route_destinations || [];
      const vehicleData = parsedPayload?.vehicles?.find(v => v.id === vehicle?.id);
      const origin = vehicleData ? { lat: vehicleData.origin_lat, lon: vehicleData.origin_lon } : null;
      const destWaypoints = routeDests.map(d => ({ lat: d.lat, lon: d.lon, id: d.id }));
      const waypoints = origin ? [origin, ...destWaypoints] : destWaypoints;
      return {
        vehicleId: vehicle?.id || `V${vIdx + 1}`,
        color: VEHICLE_COLORS[vIdx % VEHICLE_COLORS.length],
        waypoints,
        assignment,
        hasRoute: waypoints.length >= 2,
      };
    });
  }, [plans, selectedArchetype, parsedPayload]);

  // ─── Dest-vehicle color map ───
  const destVehicleMap = useMemo(() => {
    const plan = plans[selectedArchetype];
    if (!plan?.assignments) return {};
    const map = {};
    plan.assignments.forEach((assignment, vIdx) => {
      const color = VEHICLE_COLORS[vIdx % VEHICLE_COLORS.length];
      (assignment.route_destinations || []).forEach((dest, dIdx) => {
        map[dest.id] = { color, order: dIdx + 1, vehicleId: assignment.vehicle?.id };
      });
    });
    return map;
  }, [plans, selectedArchetype]);

  // ─── OSRM snap on demand per vehicle ───
  useEffect(() => {
    if (!selectedArchetype || !vehicleWaypoints.length) return;
    vehicleWaypoints.forEach(vw => {
      const key = `${selectedArchetype}-${vw.vehicleId}`;
      if (key in snappedCoords) return;
      if (!vw.hasRoute) return;
      setSnappedCoords(prev => ({ ...prev, [key]: null }));
      setIsSnapping(true);
      buildRouteFromWaypoints(vw.waypoints)
        .then(coords => setSnappedCoords(prev => ({ ...prev, [key]: coords })))
        .finally(() => setIsSnapping(false));
    });
  }, [selectedArchetype, vehicleWaypoints]);

  // ─── Vehicle filter logic ───
  const toggleVehicle = (vehicleId) => {
    setVisibleVehicles(prev => {
      if (prev === null) return new Set([vehicleId]);
      const next = new Set(prev);
      if (next.has(vehicleId)) { next.delete(vehicleId); if (next.size === 0) return null; }
      else { next.add(vehicleId); }
      return next;
    });
  };
  const isVehicleVisible = (vehicleId) => visibleVehicles === null || visibleVehicles.has(vehicleId);

  // ─── Simulation times ───
  const simulationTimes = useMemo(() => {
    const plan = plans[selectedArchetype];
    if (!plan?.assignments) return { startMinutes: 8 * 60, endMinutes: 17 * 60 };
    const allTimes = plan.assignments
      .flatMap(a => a.schedule || [])
      .map(s => s.suggested_arrival_hhmm).filter(Boolean)
      .map(t => { const [h, m] = t.split(':').map(Number); return h * 60 + m; })
      .filter(t => !isNaN(t));
    if (allTimes.length === 0) return { startMinutes: 8 * 60, endMinutes: 17 * 60 };
    return { startMinutes: Math.max(0, Math.min(...allTimes) - 30), endMinutes: Math.max(...allTimes) + 15 };
  }, [plans, selectedArchetype]);

  const startHH = String(Math.floor(simulationTimes.startMinutes / 60)).padStart(2, '0');
  const startMM = String(simulationTimes.startMinutes % 60).padStart(2, '0');

  // ─── Simulation ───
  const startSimulation = () => {
    const visibleRoutes = vehicleWaypoints.filter(vw => isVehicleVisible(vw.vehicleId));
    const hasAny = visibleRoutes.some(vw => {
      const key = `${selectedArchetype}-${vw.vehicleId}`;
      const coords = snappedCoords[key];
      return coords && coords.length >= 2;
    });
    if (!hasAny) return;
    setIsSimulating(true);
    setSimPositions({});
    const totalDurationMs = 10000;
    const startMs = Date.now();
    const { startMinutes, endMinutes } = simulationTimes;
    const totalSimMinutes = Math.max(endMinutes - startMinutes, 60);

    const animate = () => {
      const elapsed = Date.now() - startMs;
      const progress = Math.min(elapsed / totalDurationMs, 1);
      const currentMinutes = startMinutes + Math.floor(progress * totalSimMinutes);
      setSimTime(`${String(Math.floor(currentMinutes / 60)).padStart(2, '0')}:${String(currentMinutes % 60).padStart(2, '0')}`);
      const newPositions = {};
      visibleRoutes.forEach(vw => {
        const key = `${selectedArchetype}-${vw.vehicleId}`;
        const coords = snappedCoords[key];
        if (!coords || coords.length < 2) return;
        const idx = Math.min(Math.floor(progress * (coords.length - 1)), coords.length - 1);
        newPositions[vw.vehicleId] = { pos: coords[idx], color: vw.color };
      });
      setSimPositions(newPositions);
      if (progress < 1) { animFrameRef.current = requestAnimationFrame(animate); }
      else { setIsSimulating(false); setSimPositions({}); }
    };
    animFrameRef.current = requestAnimationFrame(animate);
  };

  const stopSimulation = () => {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    setIsSimulating(false);
    setSimPositions({});
  };

  return (
    <div id="map-view" className="flex flex-col h-screen">
      {/* ─── Top bar ─── */}
      <div className="flex items-center justify-between px-4 py-3 bg-[#0F172A] flex-shrink-0">
        <button id="back-to-results" onClick={onBack}
          className="text-sm text-gray-300 hover:text-white transition-colors flex items-center gap-1">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Volver
        </button>
        <div className="flex gap-2 overflow-x-auto">
          {availableArchetypes.map(([key, arch]) => (
            <ArchetypeChip key={key} archetype={arch} onClick={onChangeArchetype} isSelected={key === selectedArchetype} />
          ))}
        </div>
        <div className="flex items-center gap-3">
          {isSnapping && (
            <span className="text-xs text-gray-400 flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-[#1F9D6A] animate-pulse" /> Trazando calles reales...
            </span>
          )}
          <button onClick={isSimulating ? stopSimulation : startSimulation}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all"
            style={{ background: isSimulating ? '#DC2626' : '#1F9D6A', color: 'white' }}>
            {isSimulating ? '⏹ Detener' : `▶ Simular desde ${startHH}:${startMM}`}
          </button>
          <PdfExportButton fleetResponse={fleetResponse} selectedArchetype={selectedArchetype} parsedPayload={parsedPayload} dark />
        </div>
      </div>

      {/* ─── Vehicle filter bar ─── */}
      <div className="flex items-center gap-2 px-4 py-2 bg-[#0F172A]/50 border-b border-white/10 flex-shrink-0">
        <span className="text-xs text-gray-400 mr-1">Filtrar:</span>
        <button onClick={() => setVisibleVehicles(null)}
          className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
            visibleVehicles === null ? 'bg-white text-[#0F172A]' : 'bg-white/10 text-gray-300 hover:bg-white/20'
          }`}>Todos</button>
        {vehicleWaypoints.map((vw) => (
          <button key={vw.vehicleId} onClick={() => toggleVehicle(vw.vehicleId)}
            className="px-3 py-1 rounded-full text-xs font-medium transition-all border-2"
            style={{
              borderColor: vw.color,
              background: isVehicleVisible(vw.vehicleId) ? vw.color : 'transparent',
              color: isVehicleVisible(vw.vehicleId) ? 'white' : vw.color,
            }}>🚛 {vw.vehicleId}</button>
        ))}
      </div>

      {/* ─── Main: map + panel ─── */}
      <div className="flex flex-1 min-h-0">
        {/* Map */}
        <div className="flex-[7] relative">
          <MapContainer center={MAP_CONFIG.center} zoom={MAP_CONFIG.zoom}
            style={{ height: '100%', width: '100%' }} className="z-0">
            <TileLayer url={MAP_CONFIG.tileUrl} attribution={MAP_CONFIG.attribution} />

            {/* Per-vehicle polylines */}
            {vehicleWaypoints
              .filter(vw => isVehicleVisible(vw.vehicleId))
              .map((vw) => {
                const key = `${selectedArchetype}-${vw.vehicleId}`;
                const coords = snappedCoords[key] && snappedCoords[key].length > 0
                  ? snappedCoords[key]
                  : vw.waypoints.map(w => [w.lat, w.lon]);
                if (coords.length < 2) return null;
                return (
                  <React.Fragment key={vw.vehicleId}>
                    <Polyline positions={coords}
                      pathOptions={{ color: '#000', weight: 9, opacity: 0.12, lineCap: 'round', lineJoin: 'round' }}
                      smoothFactor={0.5} />
                    <Polyline positions={coords}
                      pathOptions={{ color: vw.color, weight: 5, opacity: 0.95, lineCap: 'round', lineJoin: 'round' }}
                      smoothFactor={0.5} />
                  </React.Fragment>
                );
              })
            }
            {/* Pareto segments (Bug 1 Fix - Redraw on selectedArchetype change) */}
            {(fleetResponse?.segments_pareto || []).map((segment, sIdx) => {
              return (segment.pareto_solutions || [])
                .filter(sol => sol.archetype === selectedArchetype)
                .map((sol, solIdx) => {
                  if (!sol.route_coordinates || sol.route_coordinates.length < 2) return null;
                  return (
                    <Polyline
                      key={`pareto-${sIdx}-${solIdx}`}
                      positions={sol.route_coordinates}
                      pathOptions={{
                        color: ARCHETYPES[selectedArchetype]?.color || '#6366F1',
                        weight: 4,
                        opacity: 0.4,
                        dashArray: '5, 8'
                      }}
                      smoothFactor={1}
                    />
                  );
                });
            })}

            {/* Vehicle origins */}
            {(parsedPayload?.vehicles || []).map((v) => (
              <Marker key={`origin-${v.id}`} position={[v.origin_lat, v.origin_lon]} icon={truckIcon(v.id)}>
                <Popup><strong>🚛 {v.id}</strong><br />Punto de partida<br />Capacidad: {v.capacity_tons} tn</Popup>
              </Marker>
            ))}

            {/* Destination markers with vehicle color */}
            {destinations.map((d) => {
              const info = destVehicleMap[d.id];
              const color = info?.color || '#6B7280';
              const order = info?.order || '?';
              return (
                <Marker key={`dest-${d.id}`} position={[d.lat, d.lon]} icon={destIcon(order, color)}>
                  <Popup>
                    <strong>{order}. {d.id}</strong>
                    {d.referencia && <><br /><span style={{ color: '#6B7280' }}>{d.referencia}</span></>}
                    <br />Demanda: {d.demand_tons} tn
                    <br />Vehículo: {info?.vehicleId || 'Sin asignar'}
                  </Popup>
                </Marker>
              );
            })}

            {/* Toll markers */}
            {(plans[selectedArchetype]?.topology_visuals?.toll_markers || []).map((toll, idx) => (
              <Marker key={`toll-${idx}`} position={[toll.lat, toll.lon]} icon={tollIcon}>
                <Popup>
                  <div className="text-xs font-bold text-slate-800">{toll.name}</div>
                  <div className="text-[10px] text-slate-500 uppercase font-mono mt-1">Detectado para {toll.vehicle_id}</div>
                </Popup>
              </Marker>
            ))}

            {/* H3 Risk Polygons */}
            {(plans[selectedArchetype]?.topology_visuals?.risk_polygons || []).map((poly, idx) => (
              <Polygon 
                key={`h3-${idx}`} 
                positions={poly.boundary}
                pathOptions={{
                  fillColor: '#EF4444',
                  fillOpacity: Math.min((poly.intensity - 1.0) * 0.8, 0.6),
                  color: '#B91C1C',
                  weight: 1,
                  dashArray: '3, 5'
                }}
              >
                <Popup>
                   <div className="text-xs font-bold text-red-700">Zona de Riesgo (H3)</div>
                   <div className="text-[10px] text-slate-600 mt-1 italic leading-tight">
                     Índice: {poly.h3_index}<br/>
                     Intensidad de Amenaza: {poly.intensity.toFixed(2)}x
                   </div>
                </Popup>
              </Polygon>
            ))}

            {/* Animated trucks */}
            {Object.entries(simPositions).map(([vehicleId, { pos, color }]) => (
              <Marker key={`sim-${vehicleId}`} position={pos}
                icon={animatingTruckIcon(vehicleId, color)} zIndexOffset={1000} />
            ))}
          </MapContainer>

          {/* Floating clock */}
          {isSimulating && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[1000] bg-[#0F172A]/95 text-white px-6 py-3 rounded-2xl shadow-2xl backdrop-blur-sm flex items-center gap-3">
              <span className="text-green-400 animate-pulse">●</span>
              <span className="font-mono text-2xl font-bold tracking-widest">{simTime}</span>
              <span className="text-gray-400 text-sm">simulación en curso</span>
            </div>
          )}
        </div>

        {/* ─── Schedule panel ─── */}
        <div className="flex-[3] bg-white border-l border-gray-200 overflow-y-auto p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">
            Cronograma — {ARCHETYPES[selectedArchetype]?.emoji} {ARCHETYPES[selectedArchetype]?.label}
          </h3>
          <div className="space-y-4">
            {(plans[selectedArchetype]?.assignments || []).map((assignment, aIdx) => {
              const vehicle = assignment.vehicle;
              const dests = assignment.route_destinations || [];
              const sched = assignment.schedule || [];
              const vehicleData = parsedPayload?.vehicles?.find(v => v.id === vehicle?.id);
              const originRef = vehicleData?.referencia || `${vehicleData?.origin_lat}, ${vehicleData?.origin_lon}`;

              return (
                <div key={aIdx} className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
                  {/* Vehicle header */}
                  <div className="px-4 py-3 flex items-center justify-between"
                    style={{ background: VEHICLE_COLORS[aIdx % VEHICLE_COLORS.length] }}>
                    <span className="text-white font-bold text-sm">🚛 {vehicle?.id || `V${aIdx + 1}`}</span>
                    <span className="text-white/70 text-xs">{vehicle?.capacity_tons} tn</span>
                  </div>
                  {/* Origin */}
                  <div className="px-4 py-2 bg-gray-50 text-xs text-gray-500 border-b border-gray-100">
                    📍 Origen: {originRef}
                  </div>
                  <div className="divide-y divide-gray-100">
                    <div className="px-4 py-2.5 flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-900 uppercase tracking-tighter flex items-center gap-2">
                        <span className="text-emerald-500">🟢</span> Salida desde base
                      </span>
                      <span className="text-sm font-black text-slate-900 tabular-nums">{parsedPayload?.departure_time || "08:00"}</span>
                    </div>
                    {dests.length === 0 ? (
                      <div className="px-4 py-3 text-sm text-gray-400">Sin asignaciones</div>
                    ) : dests.map((dest, dIdx) => {
                      const destInfo = destLookup[dest.id];
                      return (
                        <div key={dIdx} className="px-4 py-2.5 flex items-center justify-between">
                          <span className="text-sm text-gray-700 flex items-center gap-2">
                            <span className="w-5 h-5 rounded-full text-white text-xs flex items-center justify-center font-bold flex-shrink-0"
                              style={{ background: VEHICLE_COLORS[aIdx % VEHICLE_COLORS.length] }}>
                              {dIdx + 1}
                            </span>
                            <span>
                              <span className="font-medium">{dest.id}</span>
                              {destInfo?.referencia && (
                                <span className="block text-xs text-gray-400">{destInfo.referencia}</span>
                              )}
                            </span>
                          </span>
                          <span className="text-sm font-mono text-gray-600">
                            {sched[dIdx]?.suggested_arrival_hhmm || '--:--'}
                          </span>
                        </div>
                      );
                    })}
                    {(() => {
                      const returnEntry = sched.find(s => s.is_return);
                      return (
                        <div className="px-4 py-2.5 flex items-center justify-between">
                          <span className="text-sm text-gray-500 flex items-center gap-2">
                            <span className="text-blue-400">🔵</span> Retorno a base
                          </span>
                          <span className="text-sm font-mono text-gray-400">
                            {returnEntry?.suggested_arrival_hhmm || '—'}
                          </span>
                        </div>
                      );
                    })()}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
