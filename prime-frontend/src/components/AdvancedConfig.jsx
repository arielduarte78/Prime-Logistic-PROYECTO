// prime-frontend/src/components/AdvancedConfig.jsx
import React, { useState, useEffect, useMemo } from 'react';
import {
  Settings,
  ChevronDown,
  DollarSign,
  Truck,
  Users,
  TrendingUp,
  Clock,
  Calendar,
  ShieldCheck,
  Cpu,
  RotateCcw
} from 'lucide-react';

/**
 * DEFAULTS UNIT ECONOMICS - MARZO 2026
 * Fuente: Informe Financiero Oficial Abbey 1.5
 */
const DEFAULTS = {
  // Operativa Global
  departure_time: "08:00",
  stochastic_mode: false,
  dolar_mep: 1423.70,

  // OPEX Móvil (Target: $807,85 / km)
  opex_movil: {
    gasoil_ars_l: 1865.0,
    consumo_l_km: 0.33,
    neumaticos_km_ars: 57.0,
    mantenimiento_km_ars: 135.4
  },

  // Personal (Target: $19.130,79 / hora - Parte A)
  personal: {
    sueldo_basico_ars: 1007060,
    cargas_sociales_factor: 1.45,
    bono_mensual_ars: 210000,
    viatico_dia_ars: 15671.16,
    jornada_mensual_hs: 176,
    provision_sac_vacaciones_ars: 121686
  },

  // CAPEX & Seguros (Target: $19.130,79 / hora - Parte B)
  capex: {
    valor_unidad_ars: 111800000,
    vida_util_meses: 120,
    valor_recupero_pct: 0.20,
    seguros_patentes_mes_ars: 320000,
    telemetria_mes_ars: 165000
  }
};

export default function AdvancedConfig({ onChange }) {
  const [config, setConfig] = useState(DEFAULTS);
  const [isOpen, setIsOpen] = useState(false);

  // --- MOTOR MATEMÁTICO EN TIEMPO REAL ---
  const results = useMemo(() => {
    // 1. Cálculo Costo Operativo por KM
    const movil = config.opex_movil;
    const costoKM = (movil.gasoil_ars_l * movil.consumo_l_km) +
      movil.neumaticos_km_ars +
      movil.mantenimiento_km_ars;

    // 2. Cálculo Costo Fijo por Hora
    const p = config.personal;
    const c = config.capex;

    // Parte Personal: ((Básico * Factor) + Bono + (Viáticos * 22 días)) / Horas Mensuales
    const costoLaboralHora = ((p.sueldo_basico_ars * p.cargas_sociales_factor) +
      p.bono_mensual_ars +
      (p.viatico_dia_ars * 22) +
      p.provision_sac_vacaciones_ars) / p.jornada_mensual_hs;

    // Parte CAPEX: (Amortización Mensual + Seguros + Telemetría) / Horas Mensuales
    const amortizacionMensual = (c.valor_unidad_ars * (1 - c.valor_recupero_pct)) / c.vida_util_meses;
    const costoEstructuralHora = (amortizacionMensual +
      c.seguros_patentes_mes_ars +
      c.telemetria_mes_ars) / p.jornada_mensual_hs;

    const costoHora = costoLaboralHora + costoEstructuralHora;

    return {
      costoKM,
      costoHora,
      costoUSD: costoKM / config.dolar_mep
    };
  }, [config]);

  // Notificar al padre cuando el estado cambie
  useEffect(() => {
    if (onChange) onChange(config);
  }, [config, onChange]);

  const handleReset = () => setConfig(DEFAULTS);

  const formatCurr = (val) => val.toLocaleString('es-AR', {
    style: 'currency',
    currency: 'ARS',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });

  const InputField = ({ label, value, onChange, icon: Icon, step = "0.01" }) => (
    <div className="flex flex-col gap-1.5 mb-4">
      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest flex items-center gap-2">
        {Icon && <Icon size={12} className="text-slate-300" />} {label}
      </label>
      <input
        type="number"
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        className="bg-slate-50 border border-slate-100 text-slate-900 font-bold p-3 rounded-xl focus:ring-2 focus:ring-emerald-500 outline-none transition-all tabular-nums text-sm w-full"
      />
    </div>
  );

  return (
    <div className="w-full max-w-2xl mx-auto mt-6">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-5 bg-white border border-slate-200 rounded-[2rem] shadow-sm hover:border-slate-950 transition-all group ring-1 ring-black/5"
      >
        <div className="flex items-center gap-5">
          <div className="p-4 bg-slate-900 rounded-2xl text-white shadow-xl shadow-slate-200 transition-all group-hover:scale-105">
            <Settings size={20} className={isOpen ? 'rotate-90 transition-transform' : ''} />
          </div>
          <div className="text-left">
            <span className="block text-slate-900 font-black text-base tracking-tight italic">CFO Command Center</span>
            <span className="block text-slate-400 text-[10px] uppercase tracking-[0.3em] font-bold">Audit & Unit Economics v1.5</span>
          </div>
        </div>

        {/* Real-time Indicator Headlines */}
        {!isOpen && (
          <div className="flex gap-6 mr-4 opacity-0 group-hover:opacity-100 transition-opacity">
            <div className="text-right">
              <p className="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">$/KM</p>
              <p className="text-sm font-black text-slate-900 leading-none">{formatCurr(results.costoKM)}</p>
            </div>
            <div className="text-right border-l border-slate-100 pl-6">
              <p className="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">$/HORA</p>
              <p className="text-sm font-black text-slate-900 leading-none">{formatCurr(results.costoHora)}</p>
            </div>
          </div>
        )}

        <div className={`transition-transform duration-500 ${isOpen ? 'rotate-180' : ''}`}>
          <ChevronDown size={20} className="text-slate-300" />
        </div>
      </button>

      {isOpen && (
        <div className="mt-4 p-8 bg-white border border-slate-200 rounded-[2.5rem] shadow-2xl animate-in fade-in slide-in-from-top-4 duration-500 overflow-hidden ring-1 ring-black/5">

          {/* FADEEAC / AUDIT HEADER */}
          <div className="flex justify-between items-end mb-10 pb-8 border-b border-slate-50">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.4em]">Live Matrix Recalculation</h3>
              </div>
              <div className="flex gap-12">
                <div>
                  <p className="text-[10px] font-bold text-slate-400 uppercase mb-1">Costo Operativo por KM</p>
                  <p className="text-3xl font-black text-slate-900 tabular-nums tracking-tighter">
                    {formatCurr(results.costoKM)}
                  </p>
                </div>
                <div className="border-l border-slate-100 pl-12">
                  <p className="text-[10px] font-bold text-slate-400 uppercase mb-1">Costo Fijo por Hora</p>
                  <p className="text-3xl font-black text-slate-900 tabular-nums tracking-tighter">
                    {formatCurr(results.costoHora)}
                  </p>
                </div>
              </div>
            </div>

            <button
              onClick={handleReset}
              className="group flex items-center gap-2 px-4 py-2 text-[10px] font-black text-slate-400 hover:text-rose-500 transition-all uppercase tracking-widest border border-slate-100 rounded-xl hover:bg-rose-50"
            >
              <RotateCcw size={12} className="group-hover:rotate-[-120deg] transition-all" /> Restaurar Defaults
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-10">

            {/* 1. OPEX MÓVIL */}
            <details open className="group/section">
              <summary className="list-none cursor-pointer mb-6">
                <div className="flex items-center gap-2 text-slate-900">
                  <Truck size={16} className="text-emerald-500" />
                  <span className="text-xs font-black uppercase tracking-widest">1. OPEX Móvil</span>
                  <ChevronDown size={14} className="ml-auto text-slate-300 group-open/section:rotate-180 transition-transform" />
                </div>
              </summary>
              <div className="space-y-1">
                <InputField
                  label="Gasoil ($/Litro)"
                  value={config.opex_movil.gasoil_ars_l}
                  onChange={(v) => setConfig({
                    ...config,
                    opex_movil: { ...config.opex_movil, gasoil_ars_l: v }
                  })}
                  icon={DollarSign}
                />
                <InputField
                  label="Consumo (L/KM)"
                  value={config.opex_movil.consumo_l_km}
                  onChange={(v) => setConfig({
                    ...config,
                    opex_movil: { ...config.opex_movil, consumo_l_km: v }
                  })}
                  icon={TrendingUp}
                />
                <InputField
                  label="Neumáticos ($/KM)"
                  value={config.opex_movil.neumaticos_km_ars}
                  onChange={(v) => setConfig({
                    ...config,
                    opex_movil: { ...config.opex_movil, neumaticos_km_ars: v }
                  })}
                  icon={Cpu}
                />
                <InputField
                  label="Mantenimiento ($/KM)"
                  value={config.opex_movil.mantenimiento_km_ars}
                  onChange={(v) => setConfig({
                    ...config,
                    opex_movil: { ...config.opex_movil, mantenimiento_km_ars: v }
                  })}
                  icon={Settings}
                />
              </div>
            </details>

            {/* 2. PERSONAL Y ESTRUCTURA */}
            <details open className="group/section border-l border-slate-50 pl-10">
              <summary className="list-none cursor-pointer mb-6">
                <div className="flex items-center gap-2 text-slate-900">
                  <Users size={16} className="text-emerald-500" />
                  <span className="text-xs font-black uppercase tracking-widest">2. Personal</span>
                  <ChevronDown size={14} className="ml-auto text-slate-300 group-open/section:rotate-180 transition-transform" />
                </div>
              </summary>
              <div className="space-y-1">
                <InputField
                  label="Sueldo Básico ($)"
                  value={config.personal.sueldo_basico_ars}
                  onChange={(v) => setConfig({
                    ...config,
                    personal: { ...config.personal, sueldo_basico_ars: v }
                  })}
                // icon={DollarSign}
                />
                <InputField
                  label="Cargas Soc. (Factor)"
                  value={config.personal.cargas_sociales_factor}
                  onChange={(v) => setConfig({
                    ...config,
                    personal: { ...config.personal, cargas_sociales_factor: v }
                  })}
                // icon={TrendingUp}
                />
                <InputField
                  label="Viáticos ($/Día)"
                  value={config.personal.viatico_dia_ars}
                  onChange={(v) => setConfig({
                    ...config,
                    personal: { ...config.personal, viatico_dia_ars: v }
                  })}
                  icon={Calendar}
                />
                <InputField
                  label="Hs Productivas / Mes"
                  value={config.personal.jornada_mensual_hs}
                  onChange={(v) => setConfig({
                    ...config,
                    personal: { ...config.personal, jornada_mensual_hs: v }
                  })}
                  icon={Clock}
                />
              </div>
            </details>

            {/* 3. CAPEX & SEGUROS */}
            <details open className="group/section border-l border-slate-50 pl-10">
              <summary className="list-none cursor-pointer mb-6">
                <div className="flex items-center gap-2 text-slate-900">
                  <ShieldCheck size={16} className="text-emerald-500" />
                  <span className="text-xs font-black uppercase tracking-widest">3. CAPEX & Seguros</span>
                  <ChevronDown size={14} className="ml-auto text-slate-300 group-open/section:rotate-180 transition-transform" />
                </div>
              </summary>
              <div className="space-y-1">
                <InputField
                  label="Valor Unidad VN ($)"
                  value={config.capex.valor_unidad_ars}
                  onChange={(v) => setConfig({
                    ...config,
                    capex: { ...config.capex, valor_unidad_ars: v }
                  })}
                />
                <InputField
                  label="Rescate Camión (%)"
                  value={config.capex.valor_recupero_pct}
                  step="0.05"
                  onChange={(v) => setConfig({
                    ...config,
                    capex: { ...config.capex, valor_recupero_pct: v }
                  })}
                />
                <InputField
                  label="Seguros/Pat. ($/Mes)"
                  value={config.capex.seguros_patentes_mes_ars}
                  onChange={(v) => setConfig({
                    ...config,
                    capex: { ...config.capex, seguros_patentes_mes_ars: v }
                  })}
                />
                <InputField
                  label="Dólar MEP (Referencia)"
                  value={config.dolar_mep}
                  onChange={(v) => setConfig({
                    ...config,
                    dolar_mep: v
                  })}
                  icon={TrendingUp}
                />
              </div>
            </details>

          </div>

          <div className="mt-10 p-6 bg-slate-900 rounded-[2rem] border border-slate-800">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center">
                  <TrendingUp className="text-emerald-500" size={20} />
                </div>
                <div>
                  <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Economic Engine Status</p>
                  <p className="text-sm font-bold text-white">Todas las variables auditadas por CFO</p>
                </div>
              </div>
              <div className="flex items-center gap-6">
                <div className="text-right">
                  <p className="text-[10px] text-slate-500 font-bold uppercase">USD/KM (MEP)</p>
                  <p className="text-xl font-black text-white italic">U$S {results.costoUSD.toFixed(2)}</p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex flex-col gap-1 items-end">
                    <span className="text-[10px] font-black text-white/40 uppercase tracking-widest">Simulación Dinámica</span>
                    <span className="text-[10px] text-white/20 font-medium">Análisis de Riesgo</span>
                  </div>
                  <button
                    onClick={() => setConfig({ ...config, stochastic_mode: !config.stochastic_mode })}
                    className={`w-12 h-6 rounded-full transition-all relative p-1 ${config.stochastic_mode ? 'bg-emerald-500' : 'bg-white/10'}`}
                  >
                    <div className={`w-4 h-4 bg-white rounded-full transition-transform shadow-sm ${config.stochastic_mode ? 'translate-x-6' : ''}`}></div>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-8 flex items-center gap-2 text-slate-400">
            <div className="h-px bg-slate-50 flex-1" />
            <p className="text-[9px] uppercase font-black tracking-[0.4em] px-4">Engine Logic: CCT 40/89 + FADEEAC Audit Mode</p>
            <div className="h-px bg-slate-50 flex-1" />
          </div>
        </div>
      )}
    </div>
  );
}
