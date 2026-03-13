//prime-frontend/src/components/AdvancedConfig.jsx
import React, { useState, useEffect } from 'react';
import { Settings, Sliders, DollarSign, Clock, Zap, RotateCcw } from 'lucide-react';

const DEFAULTS = {
  departure_time: "08:00",
  stochastic_mode: false,
  precio_gasoil_ars: 1865,
  tarifa_hora_ars: 12140,
  consumo_l_por_km: 0.33,
  dolar_mep: 1415.52,
  factor_friccion: 1.0
};

export default function AdvancedConfig({ onChange }) {
  const [config, setConfig] = useState(DEFAULTS);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    onChange(config);
  }, [config]);

  const handleReset = () => setConfig(DEFAULTS);

  // Totales calculados (Black, non-editable)
  const ckm_calc = (config.consumo_l_por_km * config.precio_gasoil_ars) + 192.4; // +57 neuma + 135.4 mant
  const ch_calc = config.tarifa_hora_ars + 4234.84 + 1818.18 + 937.50; // +amort + seguros + tele

  return (
    <div className="w-full max-w-xl mx-auto mt-4 transition-all duration-500">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 bg-white border border-gray-200 rounded-2xl shadow-sm hover:border-blue-400 transition-colors group"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-50 rounded-xl text-blue-600 group-hover:bg-blue-600 group-hover:text-white transition-all">
            <Settings size={20} />
          </div>
          <div className="text-left">
            <span className="block text-gray-900 font-bold text-sm">Configuración Avanzada</span>
            <span className="block text-gray-400 text-[10px] uppercase tracking-widest font-bold">Perfil Económico & Modo AMBA</span>
          </div>
        </div>
        <div className={`transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`}>
          <Sliders size={18} className="text-gray-400" />
        </div>
      </button>

      {isOpen && (
        <div className="mt-2 p-6 bg-white border border-gray-200 rounded-2xl shadow-xl animate-in fade-in slide-in-from-top-4 duration-300">
          <div className="grid grid-cols-2 gap-8">
            {/* Sección A: Operativa */}
            <div className="space-y-4">
              <h3 className="text-[10px] font-black text-gray-400 uppercase tracking-[0.2em] border-b pb-2 flex items-center gap-2">
                <Clock size={12} /> Operación
              </h3>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-gray-600">Horario de Salida</label>
                <input
                  type="time"
                  value={config.departure_time}
                  onChange={(e) => setConfig({ ...config, departure_time: e.target.value })}
                  className="bg-blue-50/50 border border-blue-200 text-blue-700 font-bold p-2.5 rounded-xl focus:ring-2 focus:ring-blue-400 outline-none transition-all"
                />
              </div>

              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-xl border border-slate-200">
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-gray-700 flex items-center gap-1.5">
                    Modo Estocástico <Zap size={10} className={config.stochastic_mode ? 'text-yellow-500 fill-yellow-500' : 'text-gray-300'} />
                  </span>
                  <span className="text-[10px] text-gray-400">Modelado de riesgo premium</span>
                </div>
                <button
                  onClick={() => setConfig({ ...config, stochastic_mode: !config.stochastic_mode })}
                  className={`w-10 h-5 rounded-full transition-colors relative ${config.stochastic_mode ? 'bg-blue-600' : 'bg-gray-300'}`}
                >
                  <div className={`absolute top-1 left-1 w-3 h-3 bg-white rounded-full transition-transform ${config.stochastic_mode ? 'translate-x-5' : ''}`}></div>
                </button>
              </div>
            </div>

            {/* Sección B: Unit Economics */}
            <div className="space-y-4">
              <h3 className="text-[10px] font-black text-gray-400 uppercase tracking-[0.2em] border-b pb-2 flex items-center gap-2">
                <DollarSign size={12} /> Unit Economics (CFO Grade)
              </h3>

              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] font-bold text-gray-500">Gasoil (ARS/L)</label>
                  <input
                    type="number"
                    value={config.precio_gasoil_ars}
                    onChange={(e) => setConfig({ ...config, precio_gasoil_ars: parseFloat(e.target.value) })}
                    className="bg-blue-50/50 border border-blue-100 text-blue-600 font-bold p-2 rounded-lg text-sm"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] font-bold text-gray-500">Laboral (ARS/hr)</label>
                  <input
                    type="number"
                    value={config.tarifa_hora_ars}
                    onChange={(e) => setConfig({ ...config, tarifa_hora_ars: parseFloat(e.target.value) })}
                    className="bg-blue-50/50 border border-blue-100 text-blue-600 font-bold p-2 rounded-lg text-sm"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] font-bold text-gray-500">Consumo (L/km)</label>
                  <input
                    type="number" step="0.01"
                    value={config.consumo_l_por_km}
                    onChange={(e) => setConfig({ ...config, consumo_l_por_km: parseFloat(e.target.value) })}
                    className="bg-blue-50/50 border border-blue-100 text-blue-600 font-bold p-2 rounded-lg text-sm"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] font-bold text-gray-500">Dólar MEP</label>
                  <input
                    type="number"
                    value={config.dolar_mep}
                    onChange={(e) => setConfig({ ...config, dolar_mep: parseFloat(e.target.value) })}
                    className="bg-blue-50/50 border border-blue-100 text-blue-600 font-bold p-2 rounded-lg text-sm"
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="mt-8 pt-6 border-t border-gray-100 grid grid-cols-2 gap-8 items-center">
            <div className="flex gap-6">
              <div className="flex flex-col">
                <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">CKM Resultante</span>
                <span className="text-xl font-black text-black">${ckm_calc.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">CH Resultante</span>
                <span className="text-xl font-black text-black">${ch_calc.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
              </div>
            </div>

            <div className="flex justify-end gap-3">
              <button
                onClick={handleReset}
                className="flex items-center gap-2 px-4 py-2 text-xs font-bold text-gray-400 hover:text-gray-600 transition-colors uppercase tracking-widest"
              >
                <RotateCcw size={14} /> Restaurar Defaults
              </button>
            </div>
          </div>

          <div className="mt-4 p-3 bg-blue-50/50 rounded-xl border border-blue-100">
            <p className="text-[10px] text-blue-500 leading-snug">
              <span className="font-bold">Nota de Transparencia:</span> Los resultados de CKM y CH incluyen amortización, neumáticos, mantenimiento preventivo y cargas sociales (FADEEAC/CCT 40-89).
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
