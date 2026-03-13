//prime-frontend/src/components/ChatResult.jsx
import { ARCHETYPES } from '../constants/archetypes';
import ArchetypeChip from './ArchetypeChip';
import TechnicalDetail from './TechnicalDetail';

export default function ChatResult({ fleetResponse, parsedPayload, onSelectArchetype }) {
  const plans = fleetResponse?.plans || {};
  const numVehicles = parsedPayload?.vehicles?.length || 0;
  const numDestinations = parsedPayload?.destinations?.length || 0;

  const availableArchetypes = Object.entries(ARCHETYPES).filter(([key]) => {
    const plan = plans[key];
    if (!plan || plan.error) return false;
    if (key === 'unicornio') return plan.assignments?.some(a => a.route_destinations?.length > 0);
    return true;
  });

  return (
    <div id="chat-result" className="flex flex-col items-center w-full max-w-2xl mx-auto gap-6 py-10 px-4">
      {/* Chat bubble */}
      <div className="w-full p-6 rounded-2xl bg-white border border-gray-200 shadow-sm">
        <p className="text-gray-800 leading-relaxed whitespace-pre-line">
          {`Analicé ${numVehicles} vehículo${numVehicles !== 1 ? 's' : ''} y ${numDestinations} destino${numDestinations !== 1 ? 's' : ''}.
Encontré ${availableArchetypes.length} estrategia${availableArchetypes.length !== 1 ? 's' : ''} de ruteo disponible${availableArchetypes.length !== 1 ? 's' : ''}.

Elegí una estrategia para ver el mapa de rutas:`}
        </p>
      </div>

      {/* Archetype chips with cost summary */}
      <div className="flex flex-wrap justify-center gap-3">
        {availableArchetypes.map(([key, arch]) => {
          const plan = plans[key];
          const summary = plan?.plan_financial_summary;
          return (
            <div key={key} className="flex flex-col items-center gap-1">
              <ArchetypeChip archetype={arch} onClick={onSelectArchetype} isSelected={false} />
              {summary && (
                <div className="flex items-center gap-2 text-xs text-gray-400">
                  <span>${summary.total_expected_cost?.toFixed(0)} ARS</span>
                  <span>·</span>
                  <span>{summary.avg_confidence}% conf.</span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Reasoning logs */}
      {availableArchetypes.some(([key]) => plans[key]?.reasoning_log) && (
        <div className="w-full space-y-2">
          {availableArchetypes.map(([key, arch]) => {
            const plan = plans[key];
            if (!plan?.reasoning_log) return null;
            return (
              <div key={`reason-${key}`}
                className="w-full px-4 py-3 rounded-xl bg-gray-50 border border-gray-100 text-xs text-gray-500 leading-relaxed">
                <span className="font-medium text-gray-700">{arch.emoji} {arch.label}:</span>{' '}
                {plan.reasoning_log}
              </div>
            );
          })}
        </div>
      )}

      {/* Technical detail */}
      <TechnicalDetail fleetResponse={fleetResponse} />
    </div>
  );
}
