// Correr con: npm test   (usa el runner que trae Node, sin dependencias nuevas)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildCostLines } from './costLines.js';

// Desglose real devuelto por producción (/fleet, ejemplo del Excel de invitado, 10/11/2026)
const BREAKDOWN_REAL = {
  opex_distance_ars: 22012.33, opex_time_ars: 36016.15, capex_amortization_ars: 20738.57,
  fixed_costs_ars: 15671.16, custodia_ars: 14833.33, exposure_risk_ars: 1132416.0,
  exposure_risk_nota: 'estimación en revisión', costo_total_ars: 109271.55, costo_total_usd: 77.2, dolar_mep: 1415.52,
};

test('las líneas suman el costo total (con tolerancia de redondeo)', () => {
  const { items, total } = buildCostLines(BREAKDOWN_REAL);
  const suma = items.reduce((acc, it) => acc + it.value, 0);
  assert.equal(total, BREAKDOWN_REAL.costo_total_ars);
  assert.ok(Math.abs(suma - total) < 1, `suma ${suma} != total ${total}`);
});

test('exposure_risk_ars NO está en las líneas: se muestra aparte con su nota', () => {
  const { items, exposure } = buildCostLines(BREAKDOWN_REAL);
  assert.ok(items.every((it) => !it.value.toString().includes('1132416')));
  assert.equal(items.find((it) => it.label.includes('Custodia')).value, 14833.33);
  assert.deepEqual(exposure, { value: 1132416.0, nota: 'estimación en revisión' });
});

test('si falta algún campo cuenta como 0 y no rompe', () => {
  const { items, total, exposure } = buildCostLines({ costo_total_ars: 0 });
  assert.equal(items.reduce((a, it) => a + it.value, 0), 0);
  assert.equal(total, 0);
  assert.equal(exposure.value, 0);
  assert.equal(exposure.nota, 'estimación en revisión');
});
