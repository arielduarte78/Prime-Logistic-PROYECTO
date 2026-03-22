//prime-frontend/src/components/ChatResult.jsx
import { ARCHETYPES } from '../constants/archetypes';
import ArchetypeChip from './ArchetypeChip';
import TechnicalDetail from './TechnicalDetail';
import CostBreakdownPanel from './CostBreakdownPanel';
import CfoReportModal from './CfoReportModal';
import React, { useState } from 'react';
import { Calculator, DollarSign, Shield, Zap, TrendingUp, FileText } from 'lucide-react';

export default function ChatResult({ fleetResponse, parsedPayload, onSelectArchetype }) {
  const [localSelected, setLocalSelected] = useState('equilibrista');
  const [isCfoModalOpen, setIsCfoModalOpen] = useState(false);
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
      {/* Reporte de Auditoría Trigger */}
      <div className="w-full flex justify-end">
        <button
          onClick={() => setIsCfoModalOpen(true)}
          className="flex items-center gap-2 px-6 py-3 bg-slate-900 text-white rounded-[1.25rem] text-[10px] font-black uppercase tracking-[0.2em] hover:bg-black transition-all shadow-xl shadow-slate-200 ring-1 ring-white/10 hover:-translate-y-0.5 group"
        >
          <TrendingUp size={14} className="text-emerald-400 group-hover:scale-110 transition-transform" />
          Auditoria de Costo Servido
        </button>
      </div>

      {/* Chat bubble */}
      <div className="w-full p-6 rounded-[2rem] bg-white border border-gray-100 shadow-sm ring-1 ring-black/5">
        <p className="text-gray-800 leading-relaxed whitespace-pre-line">
          {`Se auditó una flota de ${numVehicles} vehículo${numVehicles !== 1 ? 's' : ''} para ${numDestinations} destino${numDestinations !== 1 ? 's' : ''}.
Se identificaron ${availableArchetypes.length} estrategia${availableArchetypes.length !== 1 ? 's' : ''} de optimización con desvíos de margen controlados.

Seleccione Estrategia de Auditoría:`}
        </p>
      </div>

      {/* Archetype chips with financial summary */}
      <div className="flex flex-wrap justify-center gap-3">
        {availableArchetypes.map(([key, arch]) => {
          // REFERENCIA DIRECTA AL PLAN DE LA ESTRATEGIA EN LA VUELTA DEL MAP
          const planData = plans[key];
          const totalArchetypeCost = planData?.plan_financial_summary?.total_expected_cost || 0;

          const isSelected = localSelected === key;

          return (
            <div key={key} className="flex flex-col items-center gap-1">
              <ArchetypeChip
                archetype={arch}
                onClick={(id) => {
                  setLocalSelected(id);
                }}
                isSelected={isSelected}
              />
              {totalArchetypeCost > 0 && (
                <div className={`flex items-center gap-2 text-[10px] font-mono font-bold tabular-nums ${isSelected ? 'text-emerald-600' : 'text-slate-400 opacity-60'}`}>
                  <span>$ {totalArchetypeCost.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* BOTÓN AGREGADO DESPUÉS DEL CONTENEDOR DE LOS CHIPS */}
      <button
        onClick={() => onSelectArchetype(localSelected)}
        className="w-full py-3 bg-slate-900 text-white rounded-2xl text-xs font-black uppercase tracking-widest hover:bg-emerald-600 transition-all shadow-lg mt-2"
      >
        Ver rutas en mapa →
      </button>

      {/* Per-Assignment Cost Breakdown (Impacto Operativo) */}
      {assignments.length > 0 && (
        <div className="w-full space-y-4">
          <h4 className="text-gray-900 font-bold text-sm px-1 border-l-4 border-slate-900 ml-1 uppercase tracking-tight">
            Impacto Operativo y Análisis de Desvíos
          </h4>
          {assignments.map((asn, idx) => (
            <div key={idx} className="space-y-2">
              <div className="flex items-center gap-2 px-1 text-[10px] text-slate-400 font-bold uppercase tracking-widest">
                <span className="bg-slate-100 px-2 py-0.5 rounded text-slate-600">Unidad {asn.vehicle?.id || idx + 1}</span>
                <span>·</span>
                <span>{asn.route_destinations?.length || 0} Entregas Servidas</span>
              </div>
              <CostBreakdownPanel breakdown={asn.cost_breakdown} />
            </div>
          ))}
        </div>
      )}

      {/* Reasoning logs (Criterio de Optimización) */}
      {availableArchetypes.some(([key]) => plans[key]?.reasoning_log) && (
        <div className="w-full space-y-2">
          {availableArchetypes.map(([key, arch]) => {
            const plan = plans[key];
            if (!plan?.reasoning_log) return null;
            
            const log = plan.reasoning_log;
            const tramosMatch = log.match(/(\d+) tramos reales/);
            const opexMatch = log.match(/OPEX Distancia auditado: \$ ([\d,.]+) ARS/);
            const tramos = tramosMatch?.[1];
            const opex = opexMatch ? parseFloat(opexMatch[1].replace(',', '')) : null;
            
            const labels = {
              tanque: '🛡️ Ruta más segura',
              apostador: '💰 Menor costo',
              equilibrista: '⚖️ Equilibrio óptimo',
              unicornio: '🦄 Solución excepcional'
            };

            return (
              <div key={`reason-${key}`}
                className="w-full px-4 py-3 rounded-xl bg-slate-50 border border-slate-100 text-[11px] text-slate-600 leading-relaxed font-medium">
                <span className="font-black text-slate-900 uppercase tracking-tighter">{labels[key] || arch.label}:</span>{' '}
                {tramos && <span>{tramos} tramos analizados · </span>}
                {opex && <span>Costo de desplazamiento: <span className="font-bold text-slate-800">${opex.toLocaleString('es-AR', {minimumFractionDigits: 0, maximumFractionDigits: 0})} ARS</span></span>}
              </div>
            );
          })}
        </div>
      )}

      {/* Technical detail (Cronograma de Salidas) */}
      <TechnicalDetail
        fleetResponse={fleetResponse}
        selectedArchetype={localSelected}
        departureTime={parsedPayload?.departure_time || "08:00"}
      />

      {/* Auditoría Modal */}
      <CfoReportModal
        isOpen={isCfoModalOpen}
        onClose={() => setIsCfoModalOpen(false)}
        breakdown={currentPlan.plan_financial_summary}
        archetype={localSelected}
        currentPlan={currentPlan}
      />
    </div>
  );
}
