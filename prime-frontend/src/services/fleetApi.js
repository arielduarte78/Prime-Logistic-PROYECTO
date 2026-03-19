/**
 * POST /fleet — envía los datos procesados del Excel al backend en Hugging Face.
 */

// 1. Capturamos y sanitizamos la URL del backend
const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
const API_KEY = import.meta.env.VITE_API_KEY || 'messiycr7';

const ERROR_MESSAGES = {
  400: 'Las coordenadas están fuera del área de cobertura (Buenos Aires y alrededores).',
  422: 'Los datos del Excel tienen formato incorrecto. Revisá los valores numéricos.',
  429: 'El motor está procesando otra solicitud. Intentá en unos segundos.',
};

export async function sendFleetRequest(payload) {
  let response;
  const fullUrl = `${API_URL}/fleet`;

  try {
    response = await fetch(fullUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': API_KEY,
      },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    console.error("Error de conexión:", err);
    throw new Error('No se puede conectar con el servidor de Hugging Face. Verificá que el backend esté en estado "Running".');
  }

  if (!response.ok) {
    let deepError = '';
    try {
      const errorData = await response.json();
      deepError = errorData.detail || JSON.stringify(errorData);
      console.error("Deep backend error:", deepError);
    } catch (e) {
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

// Keepalive: ping cada 4 minutos para evitar que HF duerma el Space
setInterval(() => {
  fetch(`${API_URL}/health`).catch(() => {});
}, 4 * 60 * 1000);
