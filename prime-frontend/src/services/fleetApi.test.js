// Correr con: npm test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { sendFleetRequest } from './fleetApi.js';

const resp = (status, body, headers = {}) => ({
  status, ok: status >= 200 && status < 300,
  json: async () => body,
  headers: { get: (k) => headers[k.toLowerCase()] ?? null },
});
const sinEspera = async () => {};

test('si el motor está ocupado (429) espera lo que dice Retry-After, avisa y reintenta', async () => {
  const respuestas = [resp(429, { detail: 'ocupado' }, { 'retry-after': '30' }), resp(200, { plans: {} })];
  const esperas = []; const avisos = [];
  const r = await sendFleetRequest({}, {
    fetchFn: async () => respuestas.shift(),
    esperar: async (ms) => { esperas.push(ms); },
    onStatus: (m) => avisos.push(m),
  });
  assert.deepEqual(r, { plans: {} });
  assert.deepEqual(esperas, [30000]);
  assert.match(avisos[0], /ocupado/i);
});

test('si sigue ocupado después de reintentar, el error es claro', async () => {
  await assert.rejects(
    sendFleetRequest({}, { fetchFn: async () => resp(429, { detail: 'x' }, { 'retry-after': '1' }), esperar: sinEspera }),
    /ocupado.*minuto/i,
  );
});

test('si el cálculo tarda más que el máximo, corta con un mensaje claro', async () => {
  const fetchColgado = (_url, { signal }) => new Promise((_, rej) =>
    signal.addEventListener('abort', () => rej(Object.assign(new Error('aborted'), { name: 'AbortError' }))));
  await assert.rejects(
    sendFleetRequest({}, { fetchFn: fetchColgado, tiempoMaxMs: 20, esperar: sinEspera }),
    /tardó más de lo esperado/i,
  );
});

test('manda la clave en x-api-key y el body como JSON', async () => {
  let visto;
  await sendFleetRequest({ a: 1 }, { fetchFn: async (url, opts) => { visto = { url, opts }; return resp(200, {}); } });
  assert.ok(visto.url.endsWith('/fleet'));
  assert.equal(visto.opts.method, 'POST');
  assert.ok(visto.opts.headers['x-api-key']);
  assert.equal(visto.opts.body, '{"a":1}');
});
