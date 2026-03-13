//prime-frontend/src/components/CostBreakdownPanel.jsx
import React from 'react';

const CostBreakdownPanel = ({ breakdown }) => {
  if (!breakdown) return null;

  const items = [
    { label: 'Combustible', value: breakdown.costo_combustible_ars, detail: `${breakdown.consumo_litros}L × $${breakdown.precio_gasoil_ars || 1865}`, icon: '⛽' },
    { label: 'Neumáticos', value: breakdown.costo_neumaticos_ars, detail: `${breakdown.distancia_km}km × $57`, icon: '🔧' },
    { label: 'Mantenimiento', value: breakdown.costo_mantenimiento_ars, detail: `${breakdown.distancia_km}km × $135.40`, icon: '🔩' },
    { label: 'Laboral (CCT 40/89)', value: breakdown.costo_laboral_hora * breakdown.duracion_horas, detail: `${breakdown.duracion_horas}hs × $${breakdown.costo_laboral_hora.toLocaleString()}`, icon: '👷' },
    { label: 'Amortización CAPEX', value: breakdown.costo_amort_hora * breakdown.duracion_horas, detail: `${breakdown.duracion_horas}hs × $${breakdown.costo_amort_hora.toLocaleString()}`, icon: '🏭' },
    { label: 'Seguros + Patentes', value: breakdown.costo_seguros_hora * breakdown.duracion_horas, detail: `${breakdown.duracion_horas}hs × $${breakdown.costo_seguros_hora.toLocaleString()}`, icon: '🛡️' },
    { label: 'Telemetría GPS/ADAS', value: breakdown.costo_telemetria_hora * breakdown.duracion_horas, detail: `${breakdown.duracion_horas}hs × $${breakdown.costo_telemetria_hora.toLocaleString()}`, icon: '📡' },
    { label: 'Peajes dinámicos', value: breakdown.costo_peajes_ars, detail: breakdown.peajes_cruzados?.length > 0 ? `${breakdown.peajes_cruzados.length} cruces` : 'Sin peajes', icon: '🛣️' },
    { label: 'Viático CCT', value: breakdown.viatico_ars, detail: 'Monto fijo diario', icon: '🍽️' },
  ];

  return (
    <div className="bg-slate-900/50 border border-slate-700/50 rounded-xl p-4 mt-4 text-sm backdrop-blur-sm shadow-2xl overflow-hidden relative group">
      <div className="absolute top-0 right-0 p-2 opacity-10 group-hover:opacity-20 transition-opacity">
        <span className="text-4xl">💰</span>
      </div>

      <h3 className="text-slate-200 font-bold mb-3 flex items-center gap-2">
        <span>Desglose Real AMBA</span>
        <span className="text-[10px] font-normal bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded uppercase tracking-wider">Investigación Primaria</span>
      </h3>

      <div className="space-y-2.5">
        {items.map((item, idx) => (
          <div key={idx} className="flex justify-between items-center group/item hover:bg-slate-800/40 p-1.5 rounded-lg transition-colors border border-transparent hover:border-slate-700/30">
            <div className="flex items-center gap-2.5">
              <span className="text-lg w-6 text-center">{item.icon}</span>
              <div className="flex flex-col">
                <span className="text-slate-300 font-medium">{item.label}</span>
                <span className="text-slate-500 text-[11px]">{item.detail}</span>
              </div>
            </div>
            <div className="text-right">
              <div className="text-slate-200 font-mono font-bold">
                ${item.value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-3 border-t border-slate-700/50 flex justify-between items-end">
        <div>
          <div className="text-slate-400 text-[11px] mb-1">Impacto total por vehículo</div>
          <div className="text-2xl font-black text-white flex items-baseline gap-2">
            ${breakdown.costo_total_ars.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
            <span className="text-sm font-normal text-slate-400 tracking-tight">ARS</span>
          </div>
        </div>
        <div className="text-right flex flex-col items-end">
          <div className="text-emerald-400 font-bold text-lg">U$S {breakdown.costo_total_usd}</div>
          <div className="text-[10px] text-slate-500 font-mono uppercase">MEP: ${breakdown.dolar_mep || '1.415'}</div>
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
