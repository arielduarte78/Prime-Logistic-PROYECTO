//prime-frontend/src/components/ChatResult.jsx
import { ARCHETYPES } from '../constants/archetypes';
import ArchetypeChip from './ArchetypeChip';
import TechnicalDetail from './TechnicalDetail';
import PdfExportButton from './PdfExportButton';

export default function ChatResult({
  fleetResponse,
  parsedPayload,
  onSelectArchetype,
}) {
  const plans = fleetResponse?.plans || {};
  const numVehicles = parsedPayload?.vehicles?.length || 0;
  const numDestinations = parsedPayload?.destinations?.length || 0;

  // Available archetypes: filter to only those present in the response with valid assignments
  const availableArchetypes = Object.entries(ARCHETYPES).filter(([key]) => {
    const plan = plans[key];
    if (!plan || plan.error) return false;
    // unicornio: only show if has non-empty assignments
    if (key === 'unicornio') {
      return plan.assignments?.some(a => a.route_destinations?.length > 0);
    }
    return true;
  });

  const numStrategies = availableArchetypes.length;

  return (
    <div id="chat-result" className="flex flex-col items-center w-full max-w-2xl mx-auto gap-6 py-8 px-4">
      {/* Chat bubble */}
      <div className="w-full p-6 rounded-2xl bg-zinc-900/80 border border-zinc-800 backdrop-blur">
        <p className="text-zinc-200 leading-relaxed whitespace-pre-line">
          {`Analicé ${numVehicles} vehículo${numVehicles !== 1 ? 's' : ''} y ${numDestinations} destino${numDestinations !== 1 ? 's' : ''}.
Encontré ${numStrategies} estrategia${numStrategies !== 1 ? 's' : ''} de ruteo disponible${numStrategies !== 1 ? 's' : ''}.

El motor evaluó las rutas considerando seguridad vial, costos operativos y ventanas horarias de entrega.

Elegí una estrategia para ver el mapa de rutas:`}
        </p>
      </div>

      {/* Archetype chips */}
      <div className="flex flex-wrap justify-center gap-3">
        {availableArchetypes.map(([key, arch]) => (
          <ArchetypeChip
            key={key}
            archetype={arch}
            onClick={onSelectArchetype}
            isSelected={false}
          />
        ))}
      </div>

      {/* Actions */}
      <div className="flex flex-wrap items-center justify-center gap-4">
        <TechnicalDetail fleetResponse={fleetResponse} />
      </div>
    </div>
  );
}
