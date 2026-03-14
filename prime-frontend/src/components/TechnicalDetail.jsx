//prime-frontend/src/components/TechnicalDetail.jsx
import { useState } from 'react';
import { ARCHETYPES } from '../constants/archetypes';

export default function TechnicalDetail({ fleetResponse, selectedArchetype, departureTime }) {
  const [isOpen, setIsOpen] = useState(false);
  if (!fleetResponse || !selectedArchetype || !fleetResponse.plans) return null;
  
  const plan = fleetResponse.plans[selectedArchetype];
  if (!plan) return null;

  return (
    <div className="w-full max-w-2xl mt-4">
      <button id="toggle-technical-detail" onClick={() => setIsOpen(!isOpen)}
        className="text-sm text-gray-500 hover:text-gray-800 transition-colors flex items-center gap-1">
        <svg className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-90' : ''}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        Ver detalle técnico
      </button>

      {isOpen && (
        <div className="mt-3 p-5 rounded-xl bg-white border border-gray-200 shadow-sm text-sm space-y-5">
          {/* General metrics */}
          <div className="grid grid-cols-3 gap-4">
            <MetricCard label="Tiempo total" value={`${fleetResponse.total_time_ms?.toFixed(0)} ms`} />
            <MetricCard label="Tramos Pareto" value={fleetResponse.phase4_total_legs} />
            <MetricCard label="Peajes estimados" value={fleetResponse.toll_fallback_edges} />
          </div>

          {/* Per-archetype hierarchical schedule */}
          {(() => {
            if (!plan?.assignments) return null;
            const archDef = ARCHETYPES[selectedArchetype];
            if (!archDef) return null;

            return (
              <div key={selectedArchetype} className="border-t border-gray-200 pt-4">
                <p className="font-medium text-gray-900 mb-3">{archDef.emoji} {archDef.label}</p>

                <div className="space-y-3">
                  {plan.assignments.map((assignment, aIdx) => {
                    const vehicle = assignment.vehicle;
                    const destinations = assignment.route_destinations || [];
                    const schedule = assignment.schedule || [];

                    return (
                      <div key={aIdx} className="rounded-lg border border-gray-100 overflow-hidden">
                        {/* Vehicle header */}
                        <div className="px-4 py-2 bg-gray-50 flex items-center justify-between">
                          <span className="font-semibold text-gray-700 text-xs">🚛 {vehicle?.id || `V${aIdx + 1}`}</span>
                          <span className="text-gray-400 text-xs">{vehicle?.capacity_tons} tn</span>
                        </div>
                        <div className="divide-y divide-gray-50 text-xs">
                          {/* Departure */}
                          <div className="px-4 py-2 flex items-center justify-between">
                            <span className="text-gray-500 flex items-center gap-2">
                              <span className="text-green-500">🟢</span> Salida desde base
                            </span>
                            <span className="font-mono text-gray-400">{departureTime || "08:00"}</span>
                          </div>
                          {/* Stops */}
                          {destinations.length === 0 ? (
                            <div className="px-4 py-2 text-gray-400">Sin asignaciones</div>
                          ) : destinations.map((dest, dIdx) => (
                            <div key={dIdx} className="px-4 py-2 flex items-center justify-between">
                              <span className="text-gray-700 flex items-center gap-2">📍 {dest.id}</span>
                              <span className="font-mono text-gray-600">{schedule[dIdx]?.suggested_arrival_hhmm || '--:--'}</span>
                            </div>
                          ))}
                          {/* Return */}
                          <div className="px-4 py-2 flex items-center justify-between">
                            <span className="text-gray-400 flex items-center gap-2">
                              <span className="text-blue-400">🔵</span> Retorno a base
                            </span>
                            <span className="font-mono text-gray-400">—</span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="text-center p-3 rounded-lg bg-gray-50">
      <p className="text-gray-400 text-xs mb-1">{label}</p>
      <p className="text-gray-900 font-semibold">{value ?? '—'}</p>
    </div>
  );
}
