// prime-frontend/src/components/AdvancedConfig.jsx
import React, { useState, useEffect, useMemo } from 'react';
import {
  Settings,
  ChevronDown,
  RotateCcw,
  FileSpreadsheet
} from 'lucide-react';

const DEFAULTS = {
  dolar_mep: 1423.70,

  precio_camion_usd: 80000,
  vida_util_anios: 10,
  valor_recupero_pct: 0.20,
  km_vida_util: 800000,
  dias_habiles_mes: 22,
  horas_productivas_mes: 176,

  precio_gasoil: 1865.0,
  consumo_100km: 33,

  precio_cubierta: 600000,
  num_neumaticos: 6,
  vida_util_original_km: 60000,
  recapados_por_carcasa: 2,
  km_por_recapado: 30000,
  costo_recapado_pct: 0.45,

  sueldo_basico: 1007060,
  cargas_sociales_pct: 0.45,
  bono_mensual: 210000,
  viatico_diario: 15671.16,

  seguro_mensual: 265000,
  patente_mensual: 55000,

  gps_mensual: 85000,
  vigilancia_mensual: 50000,
  otros_gastos_mensual: 30000,

  mantenimiento_km_ars: 135.40,

  // Prioridad 1: Riesgo Patrimonial y Fricción
  velocidad_comercial_kmh: 40.0,
  peaje_promedio_ars: 1200.0,
  custodia_hora_ars: 0.0,
  franquicia_seguro_usd: 1500.0,

  departure_time: "08:00",
  stochastic_mode: false
};

const EditableRow = ({ label, value, onChange, format = "currency", unit = "" }) => {
  const [displayValue, setDisplayValue] = useState(() =>
    new Intl.NumberFormat('es-AR', { maximumFractionDigits: format === "currency" ? 2 : 4 }).format(value)
  );

  useEffect(() => {
    setDisplayValue(new Intl.NumberFormat('es-AR', { maximumFractionDigits: format === "currency" ? 2 : 4 }).format(value));
  }, [value, format]);

  const handleChange = (e) => {
    const inputValue = e.target.value.replace(/[^0-9.,-]/g, '');
    setDisplayValue(inputValue);

    let numericString = inputValue.replace(/\./g, '').replace(',', '.');
    if (numericString === '' || numericString === '-') return;

    const parsed = parseFloat(numericString);
    if (!isNaN(parsed)) onChange(parsed);
  };

  const handleBlur = () => {
    setDisplayValue(new Intl.NumberFormat('es-AR', { maximumFractionDigits: format === "currency" ? 2 : 4 }).format(value));
  };

  return (
    <div className="flex items-center justify-between py-2.5 border-b border-blue-50 hover:bg-blue-50/50 px-3 rounded-lg transition-all group">
      <span className="text-xs font-semibold text-slate-600 leading-tight pr-4 truncate flex-1" title={label}>{label}</span>
      <div className="flex items-center gap-2">
        <div className="relative w-[140px]">
          {format === "currency" && (
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-blue-400 font-bold text-xs">$</span>
          )}
          <input
            type="text"
            value={displayValue}
            onChange={handleChange}
            onBlur={handleBlur}
            className={`w-full bg-white border border-slate-200 text-slate-900 font-bold py-1.5 rounded-md text-right text-sm outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 tabular-nums transition-all shadow-sm ${format === "currency" ? 'pl-7 pr-3' : 'px-3'}`}
          />
        </div>
        <span className="text-[10px] text-slate-400 font-bold uppercase tracking-tighter w-[60px] text-left">{unit}</span>
      </div>
    </div>
  );
};

const CalculatedRow = ({ label, value, format = "currency", unit = "" }) => {
  const formatted = new Intl.NumberFormat('es-AR', { maximumFractionDigits: format === "currency" ? 2 : 4 }).format(value);
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-slate-50 bg-slate-50/30 px-3 rounded-lg my-1 shadow-[inset_0_1px_2px_rgba(0,0,0,0.02)]">
      <span className="text-xs font-medium text-slate-500 leading-tight pr-4 truncate flex-1" title={label}>{label}</span>
      <div className="flex items-center gap-2">
        <div className="relative w-[140px] text-right bg-transparent py-1.5">
          {format === "currency" && <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-300 font-bold text-xs">$</span>}
          <span className={`text-slate-700 font-black tabular-nums text-sm ${format === "currency" ? 'pl-7 pr-3' : 'px-3'}`}>{formatted}</span>
        </div>
        <span className="text-[10px] text-slate-300 font-bold uppercase tracking-tighter w-[60px] text-left">{unit}</span>
      </div>
    </div>
  );
};

const SectionHeader = ({ title, subtitle }) => (
  <div className="mt-10 mb-6 px-2">
    <h3 className="text-[11px] font-black text-slate-400 uppercase tracking-[0.3em] flex items-center gap-2">
      <div className="w-1.5 h-1.5 bg-blue-500 rounded-full shadow-[0_0_8px_rgba(59,130,246,0.5)]"></div>
      {title}
    </h3>
    {subtitle && <p className="text-xs text-slate-400 font-medium mt-1.5 italic">{subtitle}</p>}
  </div>
);

const ResultRow = ({ label, value, unit = "ARS" }) => {
  const formatted = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 2 }).format(value);
  return (
    <div className="flex justify-between items-center py-5 px-6 bg-slate-900 border border-slate-800 rounded-2xl shadow-xl transition-transform hover:scale-[1.01]">
      <span className="text-xs font-black text-slate-400 uppercase tracking-[0.2em]">{label}</span>
      <div className="flex items-baseline gap-1.5">
        <span className="text-emerald-500 font-black text-sm">$</span>
        <span className="text-3xl font-black text-white tabular-nums tracking-tighter">{formatted}</span>
        <span className="text-[10px] font-black text-emerald-400/60 ml-2 uppercase tracking-widest">{unit}</span>
      </div>
    </div>
  )
};

const TIME_SLOTS = [
  "00:00", "01:00", "02:00", "03:00", "04:00", "05:00", "06:00", "07:00",
  "08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00",
  "16:00", "17:00", "18:00", "19:00", "20:00", "21:00", "22:00", "23:00"
];

export default function AdvancedConfig({ onChange }) {
  const [config, setConfig] = useState(DEFAULTS);
  const [isOpen, setIsOpen] = useState(false);

  const update = (key, value) => setConfig(prev => ({ ...prev, [key]: value }));

  const calc = useMemo(() => {
    const c = config;

    const valor_unidad_ars = c.precio_camion_usd * c.dolar_mep;
    const valor_residual_ars = valor_unidad_ars * c.valor_recupero_pct;
    const base_amortizable_ars = valor_unidad_ars - valor_residual_ars;
    const amortizacion_mensual = base_amortizable_ars / (c.vida_util_anios * 12);
    const amortizacion_hora = amortizacion_mensual / c.horas_productivas_mes;

    const consumo_l_km = c.consumo_100km / 100;
    const costo_combustible_km = c.precio_gasoil * consumo_l_km;

    const vida_util_total_posicion = c.vida_util_original_km + (c.recapados_por_carcasa * c.km_por_recapado);
    const inversion_inicial_juego = c.precio_cubierta * c.num_neumaticos;
    const costo_total_recapados = c.precio_cubierta * c.costo_recapado_pct * c.recapados_por_carcasa * c.num_neumaticos;
    const costo_neumaticos_km = (inversion_inicial_juego + costo_total_recapados) / vida_util_total_posicion;

    const cargas_sociales_ars = c.sueldo_basico * c.cargas_sociales_pct;
    const viaticos_mensuales = c.viatico_diario * c.dias_habiles_mes;
    const provision_sac_vacaciones = (c.sueldo_basico + cargas_sociales_ars) / 12;
    const costo_laboral_mensual = c.sueldo_basico + cargas_sociales_ars + c.bono_mensual + viaticos_mensuales + provision_sac_vacaciones;
    const costo_laboral_hora = costo_laboral_mensual / c.horas_productivas_mes;

    const total_seguros_impuestos = c.seguro_mensual + c.patente_mensual;
    const costo_seguros_hora = total_seguros_impuestos / c.horas_productivas_mes;

    const total_telemetria_generales = c.gps_mensual + c.vigilancia_mensual + c.otros_gastos_mensual;
    const costo_telemetria_hora = total_telemetria_generales / c.horas_productivas_mes;

    const costo_mantenimiento_km = c.mantenimiento_km_ars;

    const ckm_total = costo_combustible_km + costo_neumaticos_km + costo_mantenimiento_km;
    const ch_total = costo_laboral_hora + amortizacion_hora + costo_seguros_hora + costo_telemetria_hora;

    const economic_profile = {
      opex_movil: {
        gasoil_ars_l: c.precio_gasoil,
        consumo_l_km: consumo_l_km,
        neumaticos_km_ars: costo_neumaticos_km,
        mantenimiento_km_ars: costo_mantenimiento_km
      },
      personal: {
        sueldo_basico_ars: c.sueldo_basico,
        cargas_sociales_factor: 1 + c.cargas_sociales_pct,
        bono_mensual_ars: c.bono_mensual,
        viatico_dia_ars: c.viatico_diario,
        jornada_mensual_hs: c.horas_productivas_mes,
        provision_sac_vacaciones_ars: provision_sac_vacaciones
      },
      capex: {
        valor_unidad_ars: valor_unidad_ars,
        vida_util_meses: c.vida_util_anios * 12,
        valor_recupero_pct: c.valor_recupero_pct,
        seguros_patentes_mes_ars: total_seguros_impuestos,
        telemetria_mes_ars: total_telemetria_generales
      },
      // Prioridad 1: Inyección en la raíz del objeto según directiva
      dolar_mep_ars: c.dolar_mep,
      velocidad_comercial_kmh: c.velocidad_comercial_kmh,
      peaje_promedio_ars: c.peaje_promedio_ars,
      custodia_hora_ars: c.custodia_hora_ars,
      franquicia_seguro_usd: c.franquicia_seguro_usd
    };

    return {
      valor_unidad_ars, valor_residual_ars, base_amortizable_ars, amortizacion_hora,
      consumo_l_km, costo_combustible_km,
      vida_util_total_posicion, inversion_inicial_juego, costo_total_recapados, costo_neumaticos_km,
      cargas_sociales_ars, viaticos_mensuales, provision_sac_vacaciones, costo_laboral_mensual, costo_laboral_hora,
      total_seguros_impuestos, costo_seguros_hora,
      total_telemetria_generales, costo_telemetria_hora,
      costo_mantenimiento_km,
      ckm_total, ch_total,
      economic_profile
    };
  }, [config]);

  useEffect(() => {
    if (onChange) {
      onChange({
        departure_time: config.departure_time,
        stochastic_mode: config.stochastic_mode,
        economic_profile: calc.economic_profile
      });
    }
  }, [calc, config.departure_time, config.stochastic_mode, onChange]);

  const formatCurr = (val) => new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', minimumFractionDigits: 2 }).format(val);

  return (
    <div className="w-full max-w-6xl mx-auto mt-8 mb-16">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full flex items-center justify-between p-6 bg-white border rounded-[2.5rem] transition-all duration-500 group relative overflow-hidden ${isOpen ? 'border-slate-300 shadow-2xl' : 'border-slate-200 shadow-lg hover:border-slate-900 group-hover:shadow-xl'}`}
      >
        <div className="flex items-center gap-6 relative z-10">
          <div className={`p-4 rounded-2xl text-white shadow-2xl transition-all duration-500 group-hover:scale-105 ${isOpen ? 'bg-slate-900 rotate-90' : 'bg-slate-900'}`}>
            <Settings size={22} />
          </div>
          <div className="text-left">
            <span className="block text-slate-900 font-black text-lg tracking-tight italic">Panel de Control CFO</span>
            <div className="flex items-center gap-2">
              <span className="block text-slate-400 text-[10px] uppercase tracking-[0.4em] font-bold">Auditoría y Costos Unitarios v1.5</span>
              <div className="h-0.5 w-8 bg-blue-500/30 rounded-full"></div>
            </div>
          </div>
        </div>

        {!isOpen && (
          <div className="flex gap-10 mr-6 z-10 py-1 px-4 rounded-full bg-slate-50 border border-slate-100 opacity-0 group-hover:opacity-100 transition-all transform translate-y-2 group-hover:translate-y-0 duration-500">
            <div className="text-right">
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter mb-1">Costo Operativo/KM</p>
              <p className="text-lg font-black text-slate-900 tabular-nums leading-none tracking-tight">{formatCurr(calc.ckm_total)}</p>
            </div>
            <div className="text-right border-l border-slate-200 pl-10">
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter mb-1">Costo Fijo/Hora</p>
              <p className="text-lg font-black text-slate-900 tabular-nums leading-none tracking-tight">{formatCurr(calc.ch_total)}</p>
            </div>
          </div>
        )}

        <div className={`transition-all duration-700 relative z-10 ${isOpen ? 'rotate-180 scale-125 text-slate-900' : 'text-slate-300 group-hover:text-slate-900'}`}>
          <ChevronDown size={24} strokeWidth={3} />
        </div>
      </button>

      {isOpen && (
        <div className="mt-6 p-10 bg-white border border-slate-200 rounded-[3.5rem] shadow-[0_32px_64px_-16px_rgba(0,0,0,0.1)] animate-in fade-in slide-in-from-top-4 duration-700 overflow-hidden ring-1 ring-black/5 text-left">

          <div className="flex justify-between items-end mb-12 pb-10 border-b border-slate-100">
            <div>
              <h2 className="text-2xl font-black text-slate-950 tracking-tight flex items-center gap-4 uppercase mb-2">
                Matriz de Auditoría y Costos
              </h2>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></div>
                <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Unidad de Negocio: Gestión Logística Prime</p>
              </div>
            </div>
            <button
              onClick={() => setConfig(DEFAULTS)}
              className="group flex items-center gap-3 px-6 py-3 bg-slate-50 hover:bg-rose-50 text-slate-500 hover:text-rose-600 rounded-2xl text-xs font-black transition-all border border-slate-100 hover:border-rose-100 shadow-sm"
            >
              <RotateCcw size={16} className="group-hover:rotate-[-120deg] transition-all duration-500" /> Restaurar Defaults
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-20 gap-y-6">

            {/* COLUMNA IZQUIERDA */}
            <div className="space-y-2">
              <SectionHeader title="SECCIÓN A — VEHÍCULO Y CAPEX" subtitle="Referencia: MB Atego 1721 · Camión Rígido + Acompañante" />
              <EditableRow label="Precio Camión (USD, a nuevo)" value={config.precio_camion_usd} onChange={(v) => update('precio_camion_usd', v)} unit="USD" />
              <EditableRow label="Cotización Dólar MEP" value={config.dolar_mep} onChange={(v) => update('dolar_mep', v)} unit="ARS/USD" />
              <CalculatedRow label="Valor a Nuevo camión" value={calc.valor_unidad_ars} />
              <EditableRow label="Vida Útil Contable" value={config.vida_util_anios} onChange={(v) => update('vida_util_anios', v)} format="number" unit="años" />
              <EditableRow label="Factor de Recupero" value={config.valor_recupero_pct} onChange={(v) => update('valor_recupero_pct', v)} format="number" unit="factor" />
              <CalculatedRow label="Valor Residual Estimado" value={calc.valor_residual_ars} />
              <CalculatedRow label="Base Amortizable Total" value={calc.base_amortizable_ars} />
              <EditableRow label="Km Vida Útil Total" value={config.km_vida_util} onChange={(v) => update('km_vida_util', v)} format="number" unit="km" />
              <EditableRow label="Días Hábiles por Mes" value={config.dias_habiles_mes} onChange={(v) => update('dias_habiles_mes', v)} format="number" unit="días/mes" />
              <EditableRow label="Horas Productivas por Mes" value={config.horas_productivas_mes} onChange={(v) => update('horas_productivas_mes', v)} format="number" unit="hs/mes" />

              <SectionHeader title="SECCIÓN B — COMBUSTIBLE (Costo/KM)" subtitle="Cálculo basado en Diesel 500 / Puma Grado 2" />
              <EditableRow label="Precio Combustible" value={config.precio_gasoil} onChange={(v) => update('precio_gasoil', v)} unit="ARS/L" />
              <EditableRow label="Consumo Combinado" value={config.consumo_100km} onChange={(v) => update('consumo_100km', v)} format="number" unit="L/100km" />
              <CalculatedRow label="Consumo Específico" value={calc.consumo_l_km} format="number" unit="L/km" />
              <CalculatedRow label="COSTO COMBUSTIBLE POR KM" value={calc.costo_combustible_km} unit="ARS/km" />

              <SectionHeader title="SECCIÓN C — NEUMÁTICOS" subtitle="Ciclo de Vida: Original + 2 Recapados" />
              <EditableRow label="Cubierta 295/80 R22.5" value={config.precio_cubierta} onChange={(v) => update('precio_cubierta', v)} unit="ARS/cub." />
              <EditableRow label="Dotación de Ejes" value={config.num_neumaticos} onChange={(v) => update('num_neumaticos', v)} format="number" unit="unidades" />
              <EditableRow label="Vida Útil Original" value={config.vida_util_original_km} onChange={(v) => update('vida_util_original_km', v)} format="number" unit="km" />
              <EditableRow label="Índice de Recapabilidad" value={config.recapados_por_carcasa} onChange={(v) => update('recapados_por_carcasa', v)} format="number" unit="recapados" />
              <CalculatedRow label="Vida Útil Total por Posición" value={calc.vida_util_total_posicion} format="number" unit="km" />
              <CalculatedRow label="COSTO NEUMÁTICOS POR KM" value={calc.costo_neumaticos_km} unit="ARS/km" />
            </div>

            {/* COLUMNA DERECHA */}
            <div className="space-y-2">
              <SectionHeader title="SECCIÓN D — STAFF LABORAL (Costo/Hora)" subtitle="Convenio Colectivo 40/89 · Base Mar 2026" />
              <EditableRow label="Sueldo Básico CCT" value={config.sueldo_basico} onChange={(v) => update('sueldo_basico', v)} unit="ARS/mes" />
              <EditableRow label="Aportes y ART (Factor)" value={config.cargas_sociales_pct} onChange={(v) => update('cargas_sociales_pct', v)} format="number" unit="factor" />
              <CalculatedRow label="Cargas Sociales ARS" value={calc.cargas_sociales_ars} unit="ARS/mes" />
              <EditableRow label="Bonos / Premios Fijos" value={config.bono_mensual} onChange={(v) => update('bono_mensual', v)} unit="ARS/mes" />
              <EditableRow label="Viático Comida Diario" value={config.viatico_diario} onChange={(v) => update('viatico_diario', v)} unit="ARS/día" />
              <CalculatedRow label="Provisión SAC/Vacaciones" value={calc.provision_sac_vacaciones} unit="ARS/mes" />
              <CalculatedRow label="COSTO LABORAL POR HORA" value={calc.costo_laboral_hora} unit="ARS/hora" />

              <SectionHeader title="SECCIÓN E — OPERATIVA FIJA" subtitle="Seguros, Patentes y Telemetría Mensual" />
              <EditableRow label="Seguro Todo Riesgo" value={config.seguro_mensual} onChange={(v) => update('seguro_mensual', v)} unit="ARS/mes" />
              <EditableRow label="Patentes y Tasas" value={config.patente_mensual} onChange={(v) => update('patente_mensual', v)} unit="ARS/mes" />
              <EditableRow label="GPS y Cámaras de Fatiga" value={config.gps_mensual} onChange={(v) => update('gps_mensual', v)} unit="ARS/mes" />
              <EditableRow label="Seguridad Perimetral Base" value={config.vigilancia_mensual} onChange={(v) => update('vigilancia_mensual', v)} unit="ARS/mes" />
              <CalculatedRow label="TOTAL OPERATIVA FIJA" value={calc.total_seguros_impuestos + calc.total_telemetria_generales} unit="ARS/mes" />
              <CalculatedRow label="COSTO FIJO POR HORA" value={calc.costo_seguros_hora + calc.costo_telemetria_hora} unit="ARS/hora" />

              <SectionHeader title="SECCIÓN G — MANTENIMIENTO" subtitle="Correctivo + Preventivo Programado" />
              <EditableRow label="Mantenimiento Integral x KM" value={config.mantenimiento_km_ars} onChange={(v) => update('mantenimiento_km_ars', v)} unit="ARS/km" />

              <SectionHeader title="SECCIÓN H — RIESGO PATRIMONIAL Y FRICCIÓN" subtitle="Auditoría de Exposición y Velocidad de Servicio" />
              <EditableRow label="Velocidad Comercial Promedio" value={config.velocidad_comercial_kmh} onChange={(v) => update('velocidad_comercial_kmh', v)} format="number" unit="km/h" />
              <EditableRow label="Costo Peaje Promedio" value={config.peaje_promedio_ars} onChange={(v) => update('peaje_promedio_ars', v)} unit="ARS/ruta" />
              <EditableRow label="Tarifa Custodia por Hora" value={config.custodia_hora_ars} onChange={(v) => update('custodia_hora_ars', v)} unit="ARS/h" />
              <EditableRow label="Franquicia de Seguro (Deducible)" value={config.franquicia_seguro_usd} onChange={(v) => update('franquicia_seguro_usd', v)} unit="USD" />
            </div>

          </div>

          <div className="mt-20 pt-12 border-t border-slate-100 relative">
            <div className="absolute top-0 left-1/2 transform -translate-x-1/2 -translate-y-1/2 bg-white px-8 py-2 border border-slate-100 rounded-full shadow-sm">
              <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.5em]">Resumen Ejecutivo</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
              <div className="space-y-4">
                <div className="p-1 px-3 bg-blue-50 text-blue-600 text-[10px] font-black uppercase tracking-widest rounded-md w-fit mb-2">Variables Distancia</div>
                <CalculatedRow label="Combustible por km" value={calc.costo_combustible_km} unit="ARS/km" />
                <CalculatedRow label="Neumáticos por km" value={calc.costo_neumaticos_km} unit="ARS/km" />
                <CalculatedRow label="Mantenimiento por km" value={calc.costo_mantenimiento_km} unit="ARS/km" />
                <div className="mt-4">
                  <ResultRow label="Costo Operativo por KM" value={calc.ckm_total} unit="ARS/km" />
                </div>
              </div>
              <div className="space-y-4">
                <div className="p-1 px-3 bg-slate-900 text-white text-[10px] font-black uppercase tracking-widest rounded-md w-fit mb-2">Variables Tiempo</div>
                <CalculatedRow label="Mano de Obra por hora" value={calc.costo_laboral_hora} unit="ARS/hora" />
                <CalculatedRow label="Amortización por hora" value={calc.amortizacion_hora} unit="ARS/hora" />
                <CalculatedRow label="Estructurales por hora" value={calc.costo_seguros_hora + calc.costo_telemetria_hora} unit="ARS/hora" />
                <div className="mt-4">
                  <ResultRow label="Costo Fijo por Hora" value={calc.ch_total} unit="ARS/hora" />
                </div>
              </div>
            </div>
          </div>

          <div className="mt-12 pt-10 border-t border-slate-100 flex flex-col md:flex-row items-center justify-between gap-8">
            <div className="flex-1 w-full max-w-sm">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.3em] mb-4 block">🕒 Horario de Salida Global</label>
              <select
                value={config.departure_time}
                onChange={(e) => update('departure_time', e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 text-slate-900 font-bold p-4 rounded-2xl focus:ring-4 focus:ring-blue-500/10 focus:border-blue-500 outline-none transition-all appearance-none cursor-pointer"
                style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2394a3b8' stroke-width='3'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' d='M19.5 8.25l-7.5 7.5-7.5-7.5' /%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 1.25rem center', backgroundSize: '1rem' }}
              >
                {TIME_SLOTS.map(t => <option key={t} value={t}>{t} HS</option>)}
              </select>
            </div>

            <div className="flex items-center gap-8 bg-slate-900 p-8 rounded-[2.5rem] shadow-2xl flex-1 w-full border border-slate-800">
              <div>
                <h4 className="text-white font-black text-sm uppercase tracking-widest mb-1 italic">Modo Estocástico</h4>
                <p className="text-slate-400 text-[10px] font-medium leading-relaxed max-w-[200px]">Simulación de riesgo dinámica para contingencias en ruta.</p>
              </div>
              <button
                onClick={() => update('stochastic_mode', !config.stochastic_mode)}
                className={`w-24 h-10 rounded-full transition-all relative p-1.5 flex items-center shadow-inner ${config.stochastic_mode ? 'bg-emerald-500 shadow-emerald-500/40' : 'bg-slate-700'}`}
              >
                <div className={`w-12 h-7 bg-white rounded-full transition-all duration-500 shadow-lg flex items-center justify-center font-black text-[10px] text-slate-900 ${config.stochastic_mode ? 'translate-x-9' : 'translate-x-0'}`}>
                  {config.stochastic_mode ? 'SÍ' : 'NO'}
                </div>
              </button>
            </div>
          </div>

          <div className="mt-12 text-center">
            <p className="text-[9px] font-black text-slate-300 uppercase tracking-[1em]">Motor Central de Logística Prime v1.5.0 • Cumplimiento de Auditoría</p>
          </div>

        </div>
      )}
    </div>
  );
}