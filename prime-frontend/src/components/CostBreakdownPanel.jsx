//prime-frontend/src/components/CostBreakdownPanel.jsx
import React from 'react';

const CostBreakdownPanel = ({ breakdown }) => {
  if (!breakdown) return null;

  const items = [
    { label: 'Gastos de Desplazamiento', value: breakdown.costo_combustible_ars + breakdown.costo_neumaticos_ars + breakdown.costo_mantenimiento_ars, detail: 'Combustible, Neumáticos, Mantenimiento', icon: '⛽' },
    { label: 'Personal y Estructura', value: (breakdown.costo_laboral_hora + breakdown.costo_amort_hora + breakdown.costo_seguros_hora + breakdown.costo_telemetria_hora) * breakdown.duracion_horas, detail: 'CCT 40/89, CAPEX, Seguros, Telemetría', icon: '👷' },
    { label: 'Gastos Fijos de la Operación', value: breakdown.fixed_costs_ars, detail: 'Peajes, Viáticos, Varios', icon: '🛣️' },
  ];

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 mt-4 text-sm shadow-2xl overflow-hidden relative group">
      <div className="absolute top-0 right-0 p-2 opacity-10 group-hover:opacity-20 transition-opacity">
        <span className="text-4xl">💰</span>
      </div>

      <h3 className="text-slate-100 font-bold mb-3 flex items-center gap-2 uppercase tracking-tighter">
        <span>Análisis de Desvíos de Margen</span>
        <span className="text-[10px] font-black bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded uppercase tracking-widest border border-emerald-500/20 tabular-nums">CCT 40/89 AUDIT</span>
      </h3>

      <div className="space-y-2.5">
        {items.map((item, idx) => (
          <div key={idx} className="flex justify-between items-center group/item hover:bg-slate-800/40 p-1.5 rounded-lg transition-colors border border-transparent hover:border-slate-800/50">
            <div className="flex items-center gap-2.5">
              <span className="text-lg w-6 text-center">{item.icon}</span>
              <div className="flex flex-col">
                <span className="text-slate-200 font-bold">{item.label}</span>
                <span className="text-slate-500 text-[10px] uppercase font-bold tracking-tight">{item.detail}</span>
              </div>
            </div>
            <div className="text-right">
              <div className="text-slate-100 font-mono font-bold tabular-nums">
                ${item.value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-3 border-t border-slate-800 flex justify-between items-end">
        <div>
          <div className="text-slate-500 text-[10px] mb-1 font-bold uppercase tracking-widest">Costo Servido Total</div>
          <div className="text-2xl font-black text-white flex items-baseline gap-2 tabular-nums">
            ${breakdown.costo_total_ars.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
            <span className="text-xs font-bold text-slate-500 tracking-widest uppercase">ARS</span>
          </div>
        </div>
        <div className="text-right flex flex-col items-end">
          <div className="text-emerald-500 font-black text-lg tabular-nums">U$D {breakdown.costo_total_usd}</div>
          <div className="text-[9px] text-slate-600 font-black uppercase tracking-widest">MEP REF: ${breakdown.dolar_mep || '1.415'}</div>
        </div>
      </div>

      <div className="mt-4 text-[10px] text-slate-500 italic flex items-center gap-1.5">
        <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></div>
        Fuente: FADEEAC / AUSA / CCT 40/89 · Actualizado 13/03/2026
      </div>
    </div>
  );
};

export default CostBreakdownPanel;
