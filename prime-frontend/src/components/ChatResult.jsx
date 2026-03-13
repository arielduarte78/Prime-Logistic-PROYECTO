import { ARCHETYPES } from '../constants/archetypes';
import ArchetypeChip from './ArchetypeChip';
import TechnicalDetail from './TechnicalDetail';
import CostBreakdownPanel from './CostBreakdownPanel';
import React, { useState } from 'react';
import { Calculator, DollarSign, Shield, Zap } from 'lucide-react';

export default function ChatResult({ fleetResponse, parsedPayload, onSelectArchetype }) {
  const [localSelected, setLocalSelected] = useState('equilibrista');
  const plans = fleetResponse?.plans || {};
  const numVehicles = parsedPayload?.vehicles?.length || 0;
  const numDestinations = parsedPayload?.destinations?.length || 0;

  const availableArchetypes = Object.entries(ARCHETYPES).filter(([key]) => {
    const plan = plans[key];
    if (!plan || plan.error) return false;
    return true;
  });

  const currentPlan = plans[localSelected] || {};
  const assignments = currentPlan.assignments || [];

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
          const isSelected = localSelected === key;
          
          return (
            <div key={key} className="flex flex-col items-center gap-1">
              <ArchetypeChip 
                archetype={arch} 
                onClick={(id) => {
                  setLocalSelected(id);
                  onSelectArchetype(id);
                }} 
                isSelected={isSelected} 
              />
              {summary && (
                <div className={`flex items-center gap-2 text-xs font-mono font-bold ${isSelected ? 'text-emerald-500' : 'text-gray-400 opacity-60'}`}>
                  <span>${summary.total_expected_cost?.toLocaleString()} ARS</span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Per-Assignment Cost Breakdown */}
      {assignments.length > 0 && (
        <div className="w-full space-y-4">
          <h4 className="text-gray-900 font-bold text-sm px-1 border-l-4 border-blue-500 ml-1">
            Impacto Operativo Detallado
          </h4>
          {assignments.map((asn, idx) => (
            <div key={idx} className="space-y-2">
              <div className="flex items-center gap-2 px-1 text-xs text-gray-500 font-medium">
                <span className="bg-slate-100 px-2 py-0.5 rounded text-slate-600">Vehículo {asn.vehicle?.id || idx + 1}</span>
                <span>·</span>
                <span>{asn.route_destinations?.length || 0} entregas</span>
              </div>
              <CostBreakdownPanel breakdown={asn.cost_breakdown} />
            </div>
          ))}
        </div>
      )}

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
