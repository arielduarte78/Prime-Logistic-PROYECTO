/**
 * POST /fleet — envía los datos procesados del Excel al backend en Hugging Face.
 *
 * El backend atiende un /fleet a la vez (en el CPU gratis tarda ~30 s) y pone el resto en cola
 * hasta 90 s. Si aun así está ocupado responde 429 con Retry-After: acá esperamos ese tiempo,
 * avisamos al usuario y reintentamos. Si el cálculo tarda más de TIEMPO_MAX_MS, cortamos.
 */

// `import.meta.env` lo completa Vite al compilar; en los tests (Node) no existe.
const env = import.meta.env ?? {};
const API_URL = (env.VITE_API_URL || '').replace(/\/$/, '');
const API_KEY = env.VITE_API_KEY || 'messiycr7';

const TIEMPO_MAX_MS = 180_000;   // 90 s de cola + ~30 s de cálculo + margen
const REINTENTOS_SI_OCUPADO = 2;

const ERROR_MESSAGES = {
  400: 'Las coordenadas están fuera del área de cobertura (Buenos Aires y alrededores).',
  422: 'Los datos del Excel tienen formato incorrecto. Revisá los valores numéricos.',
  429: 'El motor sigue ocupado con otras solicitudes. Probá de nuevo en un minuto.',
};

const esperarMs = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function sendFleetRequest(payload, {
  onStatus = () => {},
  fetchFn = (...args) => fetch(...args),
  esperar = esperarMs,
  tiempoMaxMs = TIEMPO_MAX_MS,
} = {}) {
  const fullUrl = `${API_URL}/fleet`;

  for (let intento = 0; ; intento++) {
    const controller = new AbortController();
    const corte = setTimeout(() => controller.abort(), tiempoMaxMs);
    let response;
    try {
      response = await fetchFn(fullUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-api-key': API_KEY },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
    } catch (err) {
      if (err?.name === 'AbortError') {
        throw new Error('El cálculo tardó más de lo esperado (3 minutos). Probá con menos destinos o intentá de nuevo en un rato.');
      }
      console.error('Error de conexión:', err);
      throw new Error('No se puede conectar con el servidor de Hugging Face. Verificá que el backend esté en estado "Running".');
    } finally {
      clearTimeout(corte);
    }

    // Motor ocupado: esperar lo que pide el servidor y reintentar (pocas veces)
    if (response.status === 429 && intento < REINTENTOS_SI_OCUPADO) {
      const segundos = Number(response.headers.get('Retry-After')) || 20;
      onStatus(`El motor está ocupado con otra solicitud. Reintentamos en ${segundos} s…`);
      await esperar(segundos * 1000);
      onStatus('Tu solicitud volvió a la cola. Calculando…');
      continue;
    }

    if (!response.ok) {
      let deepError = '';
      try {
        const errorData = await response.json();
        deepError = errorData.detail || JSON.stringify(errorData);
        console.error('Deep backend error:', deepError);
      } catch {
        deepError = 'No se pudo parsear el error del backend.';
      }
      const msg = ERROR_MESSAGES[response.status]
        || (response.status >= 500
          ? 'Error en el servidor de logística. Intentá nuevamente.'
          : `Error inesperado (${response.status}): ${deepError}`);
      const finalError = new Error(msg);
      finalError.detail = deepError;
      throw finalError;
    }

    return response.json();
  }
}

// Keepalive: ping cada 4 minutos para evitar que HF duerma el Space (solo en el navegador)
if (typeof window !== 'undefined') {
  setInterval(() => {
    fetch(`${API_URL}/health`).catch(() => {});
  }, 4 * 60 * 1000);
}
