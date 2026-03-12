//prime-frontend/src/components/TechnicalDetail.jsx
import { useState } from 'react';
import { ARCHETYPES } from '../constants/archetypes';

export default function TechnicalDetail({ fleetResponse }) {
  const [isOpen, setIsOpen] = useState(false);

  if (!fleetResponse) return null;

  return (
    <div className="w-full max-w-2xl mt-4">
      <button
        id="toggle-technical-detail"
        onClick={() => setIsOpen(!isOpen)}
        className="text-sm text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-1"
      >
        <svg
          className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-90' : ''}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        Ver detalle técnico
      </button>

      {isOpen && (
        <div className="mt-3 p-4 rounded-xl bg-zinc-900/80 border border-zinc-800 text-sm space-y-4 animate-in">
          {/* General metrics */}
          <div className="grid grid-cols-3 gap-4">
            <MetricCard label="Tiempo total" value={`${fleetResponse.total_time_ms?.toFixed(0)} ms`} />
            <MetricCard label="Tramos Pareto" value={fleetResponse.phase4_total_legs} />
            <MetricCard label="Peajes estimados" value={fleetResponse.toll_fallback_edges} />
          </div>

          {/* Per-archetype */}
          {Object.entries(fleetResponse.plans || {}).map(([arch, plan]) => {
            if (!plan?.segments_pareto) return null;
            const archDef = ARCHETYPES[arch];
            if (!archDef) return null;

            // Get pareto solutions across segments
            const solutions = plan.segments_pareto.flatMap(
              s => s.pareto_solutions || []
            ).filter(s => s.archetype === arch);

            const avgConfidence = solutions.length > 0
              ? (solutions.reduce((a, s) => a + s.confidence, 0) / solutions.length).toFixed(1)
              : '—';

            // Schedule from assignments
            const scheduleRows = (plan.assignments || []).flatMap(
              (a) => (a.schedule || [])
            );

            return (
              <div key={arch} className="border-t border-zinc-800 pt-3">
                <p className="font-medium text-zinc-200 mb-2">
                  {archDef.emoji} {archDef.label}
                </p>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <span className="text-zinc-500">Confianza promedio</span>
                  <span className="text-zinc-300">{avgConfidence}%</span>
                </div>

                {scheduleRows.length > 0 && (
                  <div className="mt-3 overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-zinc-800">
                          <th className="text-left py-1 text-zinc-500">Destino</th>
                          <th className="text-left py-1 text-zinc-500">Llegada</th>
                        </tr>
                      </thead>
                      <tbody>
                        {scheduleRows.map((s, i) => (
                          <tr key={i} className="border-b border-zinc-900">
                            <td className="py-1 text-zinc-300">{s.destination_id}</td>
                            <td className="py-1 text-zinc-300">{s.suggested_arrival_hhmm || '--:--'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="text-center p-3 rounded-lg bg-zinc-800/50">
      <p className="text-zinc-500 text-xs mb-1">{label}</p>
      <p className="text-zinc-200 font-semibold">{value ?? '—'}</p>
    </div>
  );
}
