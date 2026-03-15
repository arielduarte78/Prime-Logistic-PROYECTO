// prime-frontend/src/components/AdvancedConfig.jsx
import React, { useState, useEffect, useMemo } from 'react';
import {
  Settings,
  ChevronDown,
  RotateCcw,
  FileSpreadsheet
} from 'lucide-react';

const DEFAULTS = {
  // Global
  dolar_mep: 1423.70, // Actualizado según tu directiva

  // A. CAPEX
  precio_camion_usd: 80000,
  vida_util_anios: 10,
  valor_recupero_pct: 0.20,
  km_vida_util: 800000,
  dias_habiles_mes: 22,
  horas_productivas_mes: 176,

  // B. Combustible
  precio_gasoil: 1865.0,
  consumo_100km: 33,

  // C. Neumáticos
  precio_cubierta: 600000,
  num_neumaticos: 6,
  vida_util_original_km: 60000,
  recapados_por_carcasa: 2,
  km_por_recapado: 30000,
  costo_recapado_pct: 0.45,

  // D. Laboral
  sueldo_basico: 1007060,
  cargas_sociales_pct: 0.45,
  bono_mensual: 210000,
  viatico_diario: 15671.16,

  // E. Seguros y Patentes
  seguro_mensual: 265000,
  patente_mensual: 55000,

  // F. Telemetría y Generales
  gps_mensual: 85000,
  vigilancia_mensual: 50000,
  otros_gastos_mensual: 30000,

  // G. Mantenimiento
  mantenimiento_km_ars: 135.40,

  // Global Configs
  departure_time: "08:00",
  stochastic_mode: false
};

const EditableRow = ({ label, value, onChange, format = "currency", unit = "" }) => {
  // Magia de formateo para que se vean los puntos de miles en tiempo real
  const [displayValue, setDisplayValue] = useState(() =>
    new Intl.NumberFormat('es-AR', { maximumFractionDigits: format === "currency" ? 2 : 4 }).format(value)
  );

  useEffect(() => {
    setDisplayValue(new Intl.NumberFormat('es-AR', { maximumFractionDigits: format === "currency" ? 2 : 4 }).format(value));
  }, [value, format]);

  const handleChange = (e) => {
    const inputValue = e.target.value;
    setDisplayValue(inputValue);

    // Traduce el texto humano a número de máquina (remueve puntos, cambia coma por punto)
    let numericString = inputValue.replace(/\./g, '').replace(',', '.');
    if (numericString === '' || numericString === '-') return;

    const parsed = parseFloat(numericString);
    if (!isNaN(parsed)) onChange(parsed);
  };

  const handleBlur = () => {
    setDisplayValue(new Intl.NumberFormat('es-AR', { maximumFractionDigits: format === "currency" ? 2 : 4 }).format(value));
  };

  return (
    <div className="flex justify-between items-center py-2 border-b border-blue-100 hover:bg-blue-50/30 px-2 rounded transition-colors group">
      <span className="text-xs font-bold text-blue-900 w-1/2 leading-tight pr-2">{label}</span>
      <div className="flex items-center justify-end w-1/2 gap-2">
        {format === "currency" && <span className="text-blue-500/50 font-black">$</span>}
        <input
          type="text"
          value={displayValue}
          onChange={handleChange}
          onBlur={handleBlur}
          className="bg-blue-50 border border-blue-200 text-blue-900 font-bold p-1.5 px-3 rounded-lg text-right w-28 outline-none focus:ring-2 focus:ring-blue-500 tabular-nums transition-all shadow-inner"
        />
        <span className="text-[10px] text-slate-500 font-bold w-16 text-left">{unit}</span>
      </div>
    </div>
  );
};

const CalculatedRow = ({ label, value, format = "currency", unit = "" }) => {
  const formatted = new Intl.NumberFormat('es-AR', { maximumFractionDigits: format === "currency" ? 2 : 4 }).format(value);
  return (
    <div className="flex justify-between items-center py-2 border-b border-slate-100 bg-slate-50/50 px-2 rounded my-0.5">
      <span className="text-xs font-semibold text-slate-700 w-1/2 leading-tight pr-2">{label}</span>
      <div className="flex items-center justify-end w-1/2 gap-2">
        {format === "currency" && <span className="text-slate-400 font-bold">$</span>}
        <span className="text-slate-900 font-black text-right w-28 tabular-nums">{formatted}</span>
        <span className="text-[10px] text-slate-400 font-bold w-16 text-left">{unit}</span>
      </div>
    </div>
  );
};

const SectionHeader = ({ title, subtitle }) => (
  <div className="mt-8 mb-4">
    <h3 className="text-sm font-black text-slate-900 uppercase tracking-widest flex items-center gap-2">
      {title}
    </h3>
    {subtitle && <p className="text-xs text-slate-500 font-medium mt-1">{subtitle}</p>}
  </div>
);

const ResultRow = ({ label, value, unit = "ARS" }) => {
  const formatted = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 2 }).format(value);
  return (
    <div className="flex justify-between items-center py-4 px-5 bg-emerald-50 border border-emerald-200 rounded-2xl shadow-sm">
      <span className="text-sm font-black text-emerald-900 uppercase tracking-tight">{label}</span>
      <div className="flex items-end gap-1">
        <span className="text-emerald-500 font-black mb-1">$</span>
        <span className="text-2xl font-black text-emerald-900 tabular-nums">{formatted}</span>
        <span className="text-xs font-black text-emerald-600 mb-1 ml-1">{unit}</span>
      </div>
    </div>
  )
};

export default function AdvancedConfig({ onChange }) {
  const [config, setConfig] = useState(DEFAULTS);
  const [isOpen, setIsOpen] = useState(false);

  const update = (key, value) => setConfig(prev => ({ ...prev, [key]: value }));

  // --- MOTOR MATEMÁTICO CFO ---
  const calc = useMemo(() => {
    const c = config;

    // A. CAPEX
    const valor_unidad_ars = c.precio_camion_usd * c.dolar_mep;
    const valor_residual_ars = valor_unidad_ars * c.valor_recupero_pct;
    const base_amortizable_ars = valor_unidad_ars - valor_residual_ars;
    const amortizacion_mensual = base_amortizable_ars / (c.vida_util_anios * 12);
    const amortizacion_hora = amortizacion_mensual / c.horas_productivas_mes;

    // B. Combustible
    const consumo_l_km = c.consumo_100km / 100;
    const costo_combustible_km = c.precio_gasoil * consumo_l_km;

    // C. Neumáticos
    const vida_util_total_posicion = c.vida_util_original_km + (c.recapados_por_carcasa * c.km_por_recapado);
    const inversion_inicial_juego = c.precio_cubierta * c.num_neumaticos;
    const costo_total_recapados = c.precio_cubierta * c.costo_recapado_pct * c.recapados_por_carcasa * c.num_neumaticos;
    const costo_neumaticos_km = (inversion_inicial_juego + costo_total_recapados) / vida_util_total_posicion;

    // D. Laboral
    const cargas_sociales_ars = c.sueldo_basico * c.cargas_sociales_pct;
    const viaticos_mensuales = c.viatico_diario * c.dias_habiles_mes;
    const provision_sac_vacaciones = (c.sueldo_basico + cargas_sociales_ars) / 12;
    const costo_laboral_mensual = c.sueldo_basico + cargas_sociales_ars + c.bono_mensual + viaticos_mensuales + provision_sac_vacaciones;
    const costo_laboral_hora = costo_laboral_mensual / c.horas_productivas_mes;

    // E. Seguros y Patentes
    const total_seguros_impuestos = c.seguro_mensual + c.patente_mensual;
    const costo_seguros_hora = total_seguros_impuestos / c.horas_productivas_mes;

    // F. Telemetría y Generales
    const total_telemetria_generales = c.gps_mensual + c.vigilancia_mensual + c.otros_gastos_mensual;
    const costo_telemetria_hora = total_telemetria_generales / c.horas_productivas_mes;

    // G. Mantenimiento
    const costo_mantenimiento_km = c.mantenimiento_km_ars;

    // Totales de OR-Tools
    const ckm_total = costo_combustible_km + costo_neumaticos_km + costo_mantenimiento_km;
    const ch_total = costo_laboral_hora + amortizacion_hora + costo_seguros_hora + costo_telemetria_hora;

    // Payload de envío al Backend
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
      dolar_mep_ars: c.dolar_mep
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

  // Sincronización continua con la app padre
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
    <div className="w-full max-w-5xl mx-auto mt-6 mb-12">
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

        {!isOpen && (
          <div className="flex gap-6 mr-4 opacity-0 group-hover:opacity-100 transition-opacity">
            <div className="text-right">
              <p className="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">Costo Operativo/KM</p>
              <p className="text-sm font-black text-slate-900 leading-none">{formatCurr(calc.ckm_total)}</p>
            </div>
            <div className="text-right border-l border-slate-100 pl-6">
              <p className="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">Costo Fijo/Hora</p>
              <p className="text-sm font-black text-slate-900 leading-none">{formatCurr(calc.ch_total)}</p>
            </div>
          </div>
        )}

        <div className={`transition-transform duration-500 ${isOpen ? 'rotate-180' : ''}`}>
          <ChevronDown size={20} className="text-slate-300" />
        </div>
      </button>

      {isOpen && (
        <div className="mt-4 p-8 bg-white border border-slate-200 rounded-[2.5rem] shadow-2xl animate-in fade-in duration-500 overflow-hidden ring-1 ring-black/5 text-left">

          <div className="flex justify-between items-center mb-6 pb-6 border-b border-slate-100">
            <h2 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-3 uppercase">
              <FileSpreadsheet className="text-emerald-600" /> ⚙️ CONFIGURACIÓN DE COSTOS — TU FLOTA
            </h2>
            <button onClick={() => setConfig(DEFAULTS)} className="flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-xl text-xs font-bold transition-colors">
              <RotateCcw size={14} /> Restaurar Defaults
            </button>
          </div>

          <div className="bg-blue-50/50 border border-blue-100 rounded-xl p-4 mb-8">
            <p className="text-xs font-bold text-blue-900 flex items-center gap-8">
              <span className="flex items-center gap-2"><div className="w-3 h-3 bg-blue-100 ring-1 ring-blue-300 rounded-sm"></div> Celdas AZULES = podés modificarlas.</span>
              <span className="flex items-center gap-2"><div className="w-3 h-3 bg-slate-100 ring-1 ring-slate-200 rounded-sm"></div> Celdas GRISES = calculadas automáticamente.</span>
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-12 gap-y-4">

            {/* COLUMNA IZQUIERDA */}
            <div>
              <SectionHeader title="🚛 SECCIÓN A — VEHÍCULO DE REFERENCIA (CAPEX)" subtitle="Camión rígido 10-15t · MB Atego 1721 o equivalente" />
              <EditableRow label="Precio del camión (USD, a nuevo)" value={config.precio_camion_usd} onChange={(v) => update('precio_camion_usd', v)} unit="USD" />
              <EditableRow label="Cotización dólar (ARS por USD)" value={config.dolar_mep} onChange={(v) => update('dolar_mep', v)} unit="ARS/USD" />
              <CalculatedRow label="Valor a Nuevo del camión [FÓRMULA]" value={calc.valor_unidad_ars} />
              <EditableRow label="Vida útil contable del camión" value={config.vida_util_anios} onChange={(v) => update('vida_util_anios', v)} format="number" unit="años" />
              <EditableRow label="Valor de recupero residual" value={config.valor_recupero_pct} onChange={(v) => update('valor_recupero_pct', v)} format="number" unit="factor" />
              <CalculatedRow label="Valor residual en ARS [FÓRMULA]" value={calc.valor_residual_ars} />
              <CalculatedRow label="Base amortizable (VN − Residual) [FÓRMULA]" value={calc.base_amortizable_ars} />
              <EditableRow label="Kilómetros de vida útil total" value={config.km_vida_util} onChange={(v) => update('km_vida_util', v)} format="number" unit="km" />
              <EditableRow label="Días hábiles por mes" value={config.dias_habiles_mes} onChange={(v) => update('dias_habiles_mes', v)} format="number" unit="días/mes" />
              <EditableRow label="Horas productivas por mes" value={config.horas_productivas_mes} onChange={(v) => update('horas_productivas_mes', v)} format="number" unit="hs/mes" />

              <SectionHeader title="⛽ SECCIÓN B — COMBUSTIBLE" subtitle="El costo más pesado: 76% del costo por kilómetro" />
              <EditableRow label="Precio del gasoil en surtidor" value={config.precio_gasoil} onChange={(v) => update('precio_gasoil', v)} unit="ARS/L" />
              <EditableRow label="Consumo real de tu flota" value={config.consumo_100km} onChange={(v) => update('consumo_100km', v)} format="number" unit="L/100km" />
              <CalculatedRow label="Consumo en L/km [FÓRMULA]" value={calc.consumo_l_km} format="number" unit="L/km" />
              <CalculatedRow label="COSTO COMBUSTIBLE POR KM [FÓRMULA]" value={calc.costo_combustible_km} unit="ARS/km" />

              <SectionHeader title="🔧 SECCIÓN C — NEUMÁTICOS" subtitle="7% del costo por kilómetro — activo consumible" />
              <EditableRow label="Precio unitario de cada cubierta" value={config.precio_cubierta} onChange={(v) => update('precio_cubierta', v)} unit="ARS/cub." />
              <EditableRow label="Número de neumáticos del camión" value={config.num_neumaticos} onChange={(v) => update('num_neumaticos', v)} format="number" unit="unidades" />
              <EditableRow label="Kilómetros de vida útil por cubierta" value={config.vida_util_original_km} onChange={(v) => update('vida_util_original_km', v)} format="number" unit="km" />
              <EditableRow label="Recapados por carcasa" value={config.recapados_por_carcasa} onChange={(v) => update('recapados_por_carcasa', v)} format="number" unit="recapados" />
              <EditableRow label="Kilómetros adicionales por recapado" value={config.km_por_recapado} onChange={(v) => update('km_por_recapado', v)} format="number" unit="km/recap" />
              <EditableRow label="Costo por recapado (% del precio nuevo)" value={config.costo_recapado_pct} onChange={(v) => update('costo_recapado_pct', v)} format="number" unit="factor" />
              <CalculatedRow label="Vida útil total por posición [FÓRMULA]" value={calc.vida_util_total_posicion} format="number" unit="km" />
              <CalculatedRow label="Inversión inicial juego completo [FÓRMULA]" value={calc.inversion_inicial_juego} />
              <CalculatedRow label="Costo total de recapados en el ciclo [FÓRMULA]" value={calc.costo_total_recapados} />
              <CalculatedRow label="COSTO NEUMÁTICOS POR KM [FÓRMULA]" value={calc.costo_neumaticos_km} unit="ARS/km" />
            </div>

            {/* COLUMNA DERECHA */}
            <div>
              <SectionHeader title="👷 SECCIÓN D — COSTO LABORAL" subtitle="CCT 40/89 · 63% del costo por hora — el más grande" />
              <EditableRow label="Salario básico mensual remunerativo" value={config.sueldo_basico} onChange={(v) => update('sueldo_basico', v)} unit="ARS/mes" />
              <EditableRow label="Cargas sociales y aportes patronales" value={config.cargas_sociales_pct} onChange={(v) => update('cargas_sociales_pct', v)} format="number" unit="factor" />
              <CalculatedRow label="Cargas sociales en ARS/mes [FÓRMULA]" value={calc.cargas_sociales_ars} unit="ARS/mes" />
              <EditableRow label="Bono extraordinario anual (cuota mensual)" value={config.bono_mensual} onChange={(v) => update('bono_mensual', v)} unit="ARS/mes" />
              <EditableRow label="Viático diario por comida (ítem 5.3.11 CCT)" value={config.viatico_diario} onChange={(v) => update('viatico_diario', v)} unit="ARS/día" />
              <CalculatedRow label="Viáticos mensuales totales [FÓRMULA]" value={calc.viaticos_mensuales} unit="ARS/mes" />
              <CalculatedRow label="Provisión SAC + Vacaciones (1/12) [FÓRMULA]" value={calc.provision_sac_vacaciones} unit="ARS/mes" />
              <CalculatedRow label="COSTO LABORAL TOTAL (CLMT) [FÓRMULA]" value={calc.costo_laboral_mensual} unit="ARS/mes" />
              <CalculatedRow label="COSTO LABORAL POR HORA [FÓRMULA]" value={calc.costo_laboral_hora} unit="ARS/hora" />

              <SectionHeader title="🛡️ SECCIÓN E — SEGUROS, PATENTES Y FISCALIZACIÓN" subtitle="9.5% del costo por hora" />
              <EditableRow label="Prima mensual seguro Todo Riesgo + RC" value={config.seguro_mensual} onChange={(v) => update('seguro_mensual', v)} unit="ARS/mes" />
              <EditableRow label="Patente + RTO + CNRT (mensual)" value={config.patente_mensual} onChange={(v) => update('patente_mensual', v)} unit="ARS/mes" />
              <CalculatedRow label="Total seguros + impuestos mensuales [FÓRMULA]" value={calc.total_seguros_impuestos} unit="ARS/mes" />
              <CalculatedRow label="COSTO SEGUROS+IMP. POR HORA [FÓRMULA]" value={calc.costo_seguros_hora} unit="ARS/hora" />

              <SectionHeader title="📡 SECCIÓN F — TELEMETRÍA Y GASTOS GENERALES" subtitle="4.9% del costo por hora" />
              <EditableRow label="GPS + ADAS (cámaras de fatiga) mensual" value={config.gps_mensual} onChange={(v) => update('gps_mensual', v)} unit="ARS/mes" />
              <EditableRow label="Vigilancia y guarda nocturna base" value={config.vigilancia_mensual} onChange={(v) => update('vigilancia_mensual', v)} unit="ARS/mes" />
              <EditableRow label="Otros gastos generales (admin, etc.)" value={config.otros_gastos_mensual} onChange={(v) => update('otros_gastos_mensual', v)} unit="ARS/mes" />
              <CalculatedRow label="Total telemetría + generales [FÓRMULA]" value={calc.total_telemetria_generales} unit="ARS/mes" />
              <CalculatedRow label="COSTO TELEMETRÍA POR HORA [FÓRMULA]" value={calc.costo_telemetria_hora} unit="ARS/hora" />

              <SectionHeader title="🔩 SECCIÓN G — MANTENIMIENTO" subtitle="16.76% del costo por kilómetro" />
              <EditableRow label="Costo mantenimiento integral" value={config.mantenimiento_km_ars} onChange={(v) => update('mantenimiento_km_ars', v)} unit="ARS/km" />
            </div>

          </div>

          <div className="mt-12 pt-8 border-t border-slate-200">
            <SectionHeader title="🎯 RESUMEN FINAL — LOS DOS ESCALARES QUE USA ABBEY" subtitle="Estos son los valores que OR-Tools procesa para optimizar tus rutas" />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              <div>
                <CalculatedRow label="⛽ Costo combustible/km" value={calc.costo_combustible_km} unit="ARS/km" />
                <CalculatedRow label="🔧 Costo neumáticos/km" value={calc.costo_neumaticos_km} unit="ARS/km" />
                <CalculatedRow label="🔩 Costo mantenimiento/km" value={calc.costo_mantenimiento_km} unit="ARS/km" />
                <div className="mt-3">
                  <ResultRow label="COSTO POR KM (CKM)" value={calc.ckm_total} unit="ARS/km" />
                </div>
              </div>
              <div>
                <CalculatedRow label="👷 Costo laboral/hora (CCT 40/89)" value={calc.costo_laboral_hora} unit="ARS/hora" />
                <CalculatedRow label="🏭 Amortización CAPEX/hora" value={calc.amortizacion_hora} unit="ARS/hora" />
                <CalculatedRow label="🛡️ Seguros + patentes/hora" value={calc.costo_seguros_hora} unit="ARS/hora" />
                <CalculatedRow label="📡 Telemetría + generales/hora" value={calc.costo_telemetria_hora} unit="ARS/hora" />
                <div className="mt-3">
                  <ResultRow label="COSTO POR HORA (CH)" value={calc.ch_total} unit="ARS/hora" />
                </div>
              </div>
            </div>
          </div>

          <div className="mt-8 pt-8 border-t border-slate-200 grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="bg-slate-50 p-6 rounded-2xl border border-slate-200">
              <label className="text-sm font-black text-slate-900 uppercase tracking-widest mb-3 block">🕒 Horario de Salida Global</label>
              <p className="text-xs text-slate-500 mb-4 font-medium">Aplica a toda la flota a menos que el vehículo tenga su propio horario en el Excel.</p>
              <input
                type="time"
                value={config.departure_time}
                onChange={(e) => update('departure_time', e.target.value)}
                className="bg-white border border-slate-300 text-slate-900 font-bold p-3 rounded-xl focus:ring-2 focus:ring-emerald-500 outline-none transition-all w-32"
              />
            </div>
            <div className="bg-slate-50 p-6 rounded-2xl border border-slate-200">
              <label className="text-sm font-black text-slate-900 uppercase tracking-widest mb-3 block">🎲 Simulación Dinámica de Tráfico</label>
              <p className="text-xs text-slate-500 mb-4 font-medium">Activar para análisis estocástico de riesgo (piquetes, cortes, atascos).</p>
              <button
                onClick={() => update('stochastic_mode', !config.stochastic_mode)}
                className={`w-16 h-8 rounded-full transition-all relative p-1 ${config.stochastic_mode ? 'bg-emerald-500' : 'bg-slate-300'}`}
              >
                <div className={`w-6 h-6 bg-white rounded-full transition-transform shadow-sm ${config.stochastic_mode ? 'translate-x-8' : ''}`}></div>
              </button>
            </div>
          </div>

        </div>
      )}
    </div>
  );
}