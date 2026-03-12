//prime-frontend/src/components/PdfExportButton.jsx
import { exportPdfs } from '../services/pdfGenerator';

export default function PdfExportButton({ fleetResponse, selectedArchetype }) {
  const handleExport = () => {
    exportPdfs(fleetResponse, selectedArchetype);
  };

  return (
    <button
      id="pdf-export-button"
      onClick={handleExport}
      className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-300 hover:text-white transition-all text-sm font-medium"
    >
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M12 10v6m0 0l-3-3m3 3l3-3M3 17V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
      </svg>
      Descargar hoja de ruta (PDF)
    </button>
  );
}
