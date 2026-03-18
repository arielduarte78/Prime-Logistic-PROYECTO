//prime-frontend/src/components/ExcelUploader.jsx
import { useState, useRef } from 'react';
import ExcelTemplateButton from './ExcelTemplateButton';
import ExcelStructureModal from './ExcelStructureModal';
import { parseExcelToFleetPayload } from '../services/excelParser';

export default function ExcelUploader({ onParsed }) {
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState('');
  const [warnings, setWarnings] = useState([]);
  const [modalOpen, setModalOpen] = useState(false);
  const fileInputRef = useRef(null);

  const handleFile = async (file) => {
    setError('');
    setWarnings([]);
    const ext = file.name.split('.').pop().toLowerCase();
    if (ext !== 'xlsx' && ext !== 'xls') {
      setError('Solo se aceptan archivos .xlsx o .xls');
      return;
    }
    try {
      const buffer = await file.arrayBuffer();
      const { payload, warnings: w } = parseExcelToFleetPayload(buffer);
      setWarnings(w);
      onParsed(payload);
    } catch (err) {
      setError(err.message);
    }
  };

  const onDrop = (e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files?.[0]; if (f) handleFile(f); };
  const onDragOver = (e) => { e.preventDefault(); setDragOver(true); };
  const onDragLeave = () => setDragOver(false);
  const onClickZone = () => fileInputRef.current?.click();
  const onFileChange = (e) => { const f = e.target.files?.[0]; if (f) handleFile(f); };

  return (
    <div id="excel-uploader" className="flex flex-col items-center justify-center min-h-[70vh] gap-6 px-4 bg-gray-50">
      {/* Drop zone */}
      <div
        id="drop-zone"
        onClick={onClickZone}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        className={`
          w-full max-w-xl aspect-[16/9] rounded-2xl border-2 border-dashed
          flex flex-col items-center justify-center gap-4 cursor-pointer
          transition-all duration-300 shadow-sm
          ${dragOver
            ? 'border-[#1F9D6A] bg-green-50 scale-[1.02]'
            : 'border-gray-300 bg-white hover:border-[#1F9D6A] hover:bg-green-50/30'
          }
        `}
      >
        <div className="w-16 h-16 rounded-2xl bg-green-100 flex items-center justify-center">
          <svg className="w-8 h-8 text-[#1F9D6A]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>
        <div className="text-center">
          <p className="text-gray-700 font-medium">Arrastrá tus datos acá o hacé click para seleccionar</p>
          <p className="text-gray-400 text-sm mt-1">Formatos aceptados: .xlsx, .xls</p>
        </div>
        <input ref={fileInputRef} type="file" accept=".xlsx,.xls" onChange={onFileChange} className="hidden" />
      </div>

      {error && (
        <div className="w-full max-w-xl px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-600 text-sm">{error}</div>
      )}
      {warnings.length > 0 && (
        <div className="w-full max-w-xl px-4 py-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-700 text-sm">
          {warnings.map((w, i) => <p key={i}>{w}</p>)}
        </div>
      )}

      <div className="flex flex-col items-center gap-3">
        <button id="show-structure-button" onClick={() => setModalOpen(true)}
          className="text-sm text-gray-500 hover:text-[#1F9D6A] underline underline-offset-4 transition-colors">
          ¿Cómo deben ser los datos?
        </button>
        <ExcelTemplateButton />
      </div>

      <ExcelStructureModal isOpen={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  );
}
