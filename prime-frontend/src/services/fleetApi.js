/**
 * POST /fleet — envía los datos procesados del Excel al backend en Hugging Face.
 */

// 1. Capturamos la URL del backend desde las variables de entorno de Vercel
const API_URL = import.meta.env.VITE_API_URL || '';

const ERROR_MESSAGES = {
  400: 'Las coordenadas están fuera del área de cobertura (Buenos Aires y alrededores).',
  422: 'Los datos del Excel tienen formato incorrecto. Revisá los valores numéricos.',
  429: 'El motor está procesando otra solicitud. Intentá en unos segundos.',
};

export async function sendFleetRequest(payload) {
  let response;

  // 2. Construimos la URL completa (ej: https://aphira-abbey.hf.space/fleet)
  const fullUrl = `${API_URL}/fleet/`;

  try {
    response = await fetch(fullUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        // Usamos la API Key configurada en Vercel o la de desarrollo
        'x-api-key': import.meta.env.VITE_API_KEY || 'messiycr7',
      },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    console.error("Error de conexión:", err);
    throw new Error('No se puede conectar con el servidor de Hugging Face. Verificá que el backend esté en estado "Running".');
  }

  if (!response.ok) {
    const msg = ERROR_MESSAGES[response.status]
      || (response.status >= 500
        ? 'Error en el servidor de logística. Intentá nuevamente.'
        : `Error inesperado (${response.status}).`);
    throw new Error(msg);
  }

  return response.json();
}