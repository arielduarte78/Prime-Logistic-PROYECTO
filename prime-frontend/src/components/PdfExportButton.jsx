//prime-frontend/src/components/PdfExportButton.jsx
import { exportPdfs } from '../services/pdfGenerator';

export default function PdfExportButton({ fleetResponse, selectedArchetype, parsedPayload, dark = false }) {
  const handleExport = () => {
    exportPdfs(fleetResponse, selectedArchetype, parsedPayload);
  };

  return (
    <button id="pdf-export-button" onClick={handleExport}
      className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-lg border text-sm font-medium transition-all ${dark
        ? 'bg-white/10 hover:bg-white/20 text-white border-white/20'
        : 'bg-white hover:bg-gray-50 border-gray-200 text-gray-700 hover:text-gray-900'
        }`}>
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M12 10v6m0 0l-3-3m3 3l3-3M3 17V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
      </svg>
      Descargar hoja de ruta (PDF)
    </button>
  );
}
