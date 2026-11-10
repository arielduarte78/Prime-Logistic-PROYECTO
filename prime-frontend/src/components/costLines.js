// Líneas del panel de costos. Tienen que sumar costo_total_ars (lo calcula el backend).
// exposure_risk_ars NO entra en el total: es una estimación en revisión (1% fijo de la
// franquicia, todavía no usa el modelo de riesgo) y se muestra aparte.
const n = (x) => Number(x) || 0;

export function buildCostLines(b = {}) {
  const items = [
    { label: 'Gastos de Desplazamiento', value: n(b.opex_distance_ars), detail: 'Combustible, Neumáticos, Mantenimiento', icon: '⛽' },
    { label: 'Personal y Estructura', value: n(b.opex_time_ars) + n(b.capex_amortization_ars), detail: 'CCT 40/89, CAPEX, Seguros, Telemetría', icon: '👷' },
    { label: 'Gastos Fijos de la Operación', value: n(b.fixed_costs_ars), detail: 'Peajes, Viáticos', icon: '🛣️' },
    { label: 'Custodia', value: n(b.custodia_ars), detail: 'Custodia por tiempo en ruta', icon: '🛡️' },
  ];
  return {
    items,
    total: n(b.costo_total_ars),
    exposure: { value: n(b.exposure_risk_ars), nota: b.exposure_risk_nota || 'estimación en revisión' },
  };
}
