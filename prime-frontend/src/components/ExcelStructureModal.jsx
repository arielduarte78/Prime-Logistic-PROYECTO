//prime-frontend/src/components/ExcelStructureModal.jsx
import ExcelTemplateButton from './ExcelTemplateButton';

function ColumnTable({ title, columns }) {
  return (
    <div className="mb-6">
      <h4 className="text-sm font-semibold text-gray-900 mb-3">Hoja: {title}</h4>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="text-left py-2 px-3 text-gray-500 font-medium">Columna</th>
              <th className="text-left py-2 px-3 text-gray-500 font-medium">Requerida</th>
              <th className="text-left py-2 px-3 text-gray-500 font-medium">Descripción</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((col) => (
              <tr key={col.name} className="border-b border-gray-100">
                <td className="py-2 px-3 text-gray-700 font-mono text-xs">{col.name}</td>
                <td className="py-2 px-3">
                  {col.required ? (
                    <span className="text-red-600 text-xs font-medium">Obligatoria</span>
                  ) : (
                    <span className="text-gray-400 text-xs">Opcional</span>
                  )}
                </td>
                <td className="py-2 px-3 text-gray-500 text-xs">{col.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const VEHICULOS_COLUMNS = [
  { name: 'id', required: true, description: 'Identificador único del camión (ej: CAM-01)' },
  { name: 'origin_lat', required: true, description: 'Latitud del punto de partida (ej: -34.6037)' },
  { name: 'origin_lon', required: true, description: 'Longitud del punto de partida (ej: -58.3816)' },
  { name: 'capacity_tons', required: true, description: 'Capacidad máxima de carga en toneladas' },
  { name: 'max_shift_minutes', required: false, description: 'Duración máxima del turno en minutos (default: 480 = 8hs)' },
  { name: 'referencia', required: false, description: 'Nombre legible del punto de partida (ej: Depósito Flores)' },
];

const DESTINOS_COLUMNS = [
  { name: 'id', required: true, description: 'Identificador único del destino (ej: CLI-042)' },
  { name: 'lat', required: true, description: 'Latitud del destino (ej: -34.5200)' },
  { name: 'lon', required: true, description: 'Longitud del destino (ej: -58.4500)' },
  { name: 'demand_tons', required: true, description: 'Toneladas a entregar en este destino' },
  { name: 'service_time_min', required: false, description: 'Minutos que tarda la descarga (default: 0)' },
  { name: 'tw_start_min', required: false, description: 'Minuto del día desde el que se puede entregar (default: 0 = medianoche)' },
  { name: 'tw_end_min', required: false, description: 'Minuto del día hasta el que se puede entregar (default: 1440 = medianoche)' },
  { name: 'referencia', required: false, description: 'Nombre legible del destino (ej: Supermercado Caballito)' },
];

export default function ExcelStructureModal({ isOpen, onClose }) {
  if (!isOpen) return null;

  return (
    <div
      id="excel-structure-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white border border-gray-200 rounded-2xl shadow-2xl w-full max-w-2xl mx-4 max-h-[85vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h3 className="text-lg font-semibold text-gray-900">Estructura del Excel</h3>
          <button id="close-modal-button" onClick={onClose} className="text-gray-400 hover:text-gray-700 transition-colors p-1">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-6 py-4 flex-1">
          <p className="text-sm text-gray-500 mb-6">
            El archivo Excel debe tener exactamente dos hojas: <span className="text-gray-900 font-medium">Vehiculos</span> y <span className="text-gray-900 font-medium">Destinos</span>.
          </p>

          <ColumnTable title="Vehiculos" columns={VEHICULOS_COLUMNS} />
          <ColumnTable title="Destinos" columns={DESTINOS_COLUMNS} />

          <p className="text-xs text-gray-400 mt-2 mb-4">
            <span className="font-medium">Nota:</span> tw_start_min y tw_end_min son minutos desde las 00:00. Ejemplo: 480 = 08:00, 1020 = 17:00.
          </p>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100 flex justify-center">
          <ExcelTemplateButton />
        </div>
      </div>
    </div>
  );
}
