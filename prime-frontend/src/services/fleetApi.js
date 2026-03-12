/**prime-frontend/src/services/fleetApi.js */
/**
 * POST /fleet — sends parsed Excel data to the Prime Logistics Engine backend.
 */

const ERROR_MESSAGES = {
  400: 'Las coordenadas están fuera del área de cobertura (Buenos Aires y alrededores).',
  422: 'Los datos del Excel tienen formato incorrecto. Revisá los valores numéricos.',
  429: 'El motor está procesando otra solicitud. Intentá en unos segundos.',
};

export async function sendFleetRequest(payload) {
  let response;
  try {
    response = await fetch('/fleet', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': import.meta.env.VITE_API_KEY || 'dev_key_123',
      },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    throw new Error('No se puede conectar con el servidor. Verificá que el backend esté corriendo.');
  }

  if (!response.ok) {
    const msg = ERROR_MESSAGES[response.status]
      || (response.status >= 500
        ? 'Error en el servidor. Intentá nuevamente.'
        : `Error inesperado (${response.status}).`);
    throw new Error(msg);
  }

  return response.json();
}
