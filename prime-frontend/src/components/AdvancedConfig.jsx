//prime-frontend/src/components/AdvancedConfig.jsx
import React, { useState, useEffect } from 'react';
import { Settings, Sliders, DollarSign, Clock, Zap, RotateCcw, Upload } from 'lucide-react';
import * as XLSX from 'xlsx';

const DEFAULTS = {
  departure_time: "08:00",
  stochastic_mode: false,
  precio_gasoil_ars: 1865,
  tarifa_hora_ars: 12140,
  consumo_l_por_km: 0.33,
  dolar_mep: 1415.52,
  factor_friccion: 1.0,
  // CFO Deep Parameters
  valor_unidad_ars: 85000000,
  alicuota_art: 0.045,
  sueldo_base_ars: 850000,
  factor_amortizacion: 0.20
};

export default function AdvancedConfig({ onChange }) {
  const [config, setConfig] = useState(DEFAULTS);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    onChange(config);
  }, [config]);

  const handleReset = () => setConfig(DEFAULTS);

  const handleExcelImport = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      const bstr = evt.target.result;
      const wb = XLSX.read(bstr, { type: 'binary' });
      const wsname = wb.SheetNames[0];
      const ws = wb.Sheets[wsname];
      const data = XLSX.utils.sheet_to_json(ws, { header: 1 });
      
      // Simple mapping logic (exemplary, should be refined based on actual Excel structure)
      // Here we look for keywords in the first column
      const newConfig = { ...config };
      data.forEach(row => {
        if (!row[0]) return;
        const key = row[0].toString().toUpperCase();
        if (key.includes('GASOIL')) newConfig.precio_gasoil_ars = parseFloat(row[1]);
        if (key.includes('SUELDO')) newConfig.sueldo_base_ars = parseFloat(row[1]);
        if (key.includes('VALOR') && key.includes('UNIDAD')) newConfig.valor_unidad_ars = parseFloat(row[1]);
        if (key.includes('DOLAR')) newConfig.dolar_mep = parseFloat(row[1]);
      });
      setConfig(newConfig);
      alert("Parámetros CFO actualizados desde Excel.");
    };
    reader.readAsBinaryString(file);
  };

  // Totales calculados (Black, non-editable)
  const ckm_calc = (config.consumo_l_por_km * config.precio_gasoil_ars) + 57 + 135.40;
  const ch_calc = config.tarifa_hora_ars + 4234.84 + 1818.18 + 937.50;

  return (
    <div className="w-full max-w-xl mx-auto mt-4 transition-all duration-500">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 bg-white border border-gray-200 rounded-2xl shadow-sm hover:border-slate-950 transition-colors group ring-1 ring-black/5"
      >
        <div className="flex items-center gap-4">
          <div className="p-3 bg-slate-900 rounded-xl text-white shadow-lg shadow-slate-200 transition-all group-hover:scale-105">
            <Settings size={18} />
          </div>
          <div className="text-left">
            <span className="block text-slate-900 font-black text-sm tracking-tight">Audit & Economics Control</span>
            <span className="block text-slate-400 text-[10px] uppercase tracking-[0.2em] font-bold">CFO-Grade v2.0 • OPEX/CAPEX</span>
          </div>
        </div>
        <div className={`transition-transform duration-500 ${isOpen ? 'rotate-180' : ''}`}>
          <Sliders size={16} className="text-slate-300" />
        </div>
      </button>

      {isOpen && (
        <div className="mt-3 p-8 bg-white border border-slate-100 rounded-[2rem] shadow-2xl animate-in fade-in slide-in-from-top-4 duration-500 ring-1 ring-black/5">
          <div className="flex justify-between items-center mb-8 border-b border-slate-50 pb-6">
             <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.3em]">Financial Modeling</h3>
             </div>
             <label className="flex items-center gap-2 px-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-[10px] font-bold text-slate-600 cursor-pointer hover:bg-slate-100 transition-all active:scale-95">
                <Upload size={12} /> Import from Excel
                <input type="file" className="hidden" accept=".xlsx,.xls" onChange={handleExcelImport} />
             </label>
          </div>

          <div className="grid grid-cols-2 gap-10">
            {/* Sección A: Operativa */}
            <div className="space-y-6">
              <div className="flex flex-col gap-2">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest flex items-center gap-2">
                  <Clock size={12} className="text-slate-300" /> Horario de Salida
                </label>
                <input
                  type="time"
                  value={config.departure_time}
                  onChange={(e) => setConfig({ ...config, departure_time: e.target.value })}
                  className="bg-slate-50 border border-slate-100 text-slate-900 font-bold p-3 rounded-2xl focus:ring-2 focus:ring-slate-900 outline-none transition-all tabular-nums text-sm"
                />
              </div>

              <div className="flex items-center justify-between p-4 bg-slate-900 rounded-[1.25rem] shadow-xl shadow-slate-200">
                <div className="flex flex-col">
                  <span className="text-[10px] font-black text-white/40 uppercase tracking-widest flex items-center gap-2">
                    Stochastic Mode <Zap size={10} className={config.stochastic_mode ? 'text-yellow-400 fill-yellow-400' : 'text-white/20'} />
                  </span>
                  <span className="text-[10px] text-white/60 font-medium">Risk Modeling Engine</span>
                </div>
                <button
                  onClick={() => setConfig({ ...config, stochastic_mode: !config.stochastic_mode })}
                  className={`w-11 h-6 rounded-full transition-all relative p-1 ${config.stochastic_mode ? 'bg-emerald-500' : 'bg-white/10'}`}
                >
                  <div className={`w-4 h-4 bg-white rounded-full transition-transform shadow-sm ${config.stochastic_mode ? 'translate-x-5' : ''}`}></div>
                </button>
              </div>
            </div>

            {/* Sección B: Unit Economics */}
            <div className="space-y-6">
              <div className="flex items-center gap-2 text-[10px] font-black text-slate-400 uppercase tracking-widest">
                <DollarSign size={12} className="text-slate-300" /> Cost Drivers
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-[9px] font-bold text-slate-400 uppercase tracking-tight">Gasoil ARS/L</label>
                  <input
                    type="number"
                    value={config.precio_gasoil_ars}
                    onChange={(e) => setConfig({ ...config, precio_gasoil_ars: parseFloat(e.target.value) })}
                    className="bg-slate-50 border border-slate-100 text-slate-900 font-bold p-2.5 rounded-xl text-xs tabular-nums"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-[9px] font-bold text-slate-400 uppercase tracking-tight">Sueldo Base</label>
                  <input
                    type="number"
                    value={config.sueldo_base_ars}
                    onChange={(e) => setConfig({ ...config, sueldo_base_ars: parseFloat(e.target.value) })}
                    className="bg-slate-50 border border-slate-100 text-slate-900 font-bold p-2.5 rounded-xl text-xs tabular-nums"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-[9px] font-bold text-slate-400 uppercase tracking-tight">Valor Unidad</label>
                  <input
                    type="number"
                    value={config.valor_unidad_ars}
                    onChange={(e) => setConfig({ ...config, valor_unidad_ars: parseFloat(e.target.value) })}
                    className="bg-slate-50 border border-slate-100 text-slate-900 font-bold p-2.5 rounded-xl text-xs tabular-nums"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-[9px] font-bold text-slate-400 uppercase tracking-tight">Dólar MEP</label>
                  <input
                    type="number"
                    value={config.dolar_mep}
                    onChange={(e) => setConfig({ ...config, dolar_mep: parseFloat(e.target.value) })}
                    className="bg-slate-50 border border-slate-100 text-slate-900 font-bold p-2.5 rounded-xl text-xs tabular-nums"
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="mt-10 pt-8 border-t border-slate-50 flex items-center justify-between">
            <div className="flex gap-10">
              <div className="flex flex-col">
                <span className="text-[9px] font-black text-slate-400 uppercase tracking-[0.2em] mb-1">CKM Resultante</span>
                <span className="text-2xl font-black text-slate-900 tabular-nums">${ckm_calc.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[9px] font-black text-slate-400 uppercase tracking-[0.2em] mb-1">CH Resultante</span>
                <span className="text-2xl font-black text-slate-900 tabular-nums">${ch_calc.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
              </div>
            </div>

            <button
              onClick={handleReset}
              className="group flex items-center gap-2 px-5 py-2.5 text-[10px] font-black text-slate-400 hover:text-slate-900 transition-all uppercase tracking-widest border border-slate-100 rounded-xl hover:border-slate-200"
            >
              <RotateCcw size={12} className="group-hover:rotate-[-120deg] transition-transform" /> Restaurar Defaults
            </button>
          </div>

          <div className="mt-6 p-4 bg-slate-50/50 rounded-2xl border border-slate-100">
            <p className="text-[10px] text-slate-400 leading-relaxed font-medium">
              <span className="font-black text-slate-500">ENGINE DIRECTIVE:</span> Los resultados incluyen amortización lineal (20% anual), mantenimiento preventivo (FADEEAC) y cargas sociales laborales (CCT 40-89) proyectadas a Mar 2026.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
