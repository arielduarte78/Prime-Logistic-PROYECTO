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

    // Validate extension
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

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const onDragOver = (e) => { e.preventDefault(); setDragOver(true); };
  const onDragLeave = () => setDragOver(false);
  const onClickZone = () => fileInputRef.current?.click();
  const onFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div id="excel-uploader" className="flex flex-col items-center justify-center min-h-[60vh] gap-6 px-4">
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
          transition-all duration-300
          ${dragOver
            ? 'border-blue-500 bg-blue-500/10 scale-[1.02]'
            : 'border-zinc-700 bg-zinc-900/50 hover:border-zinc-500 hover:bg-zinc-900'
          }
        `}
      >
        {/* Excel icon */}
        <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 flex items-center justify-center">
          <svg className="w-8 h-8 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>

        <div className="text-center">
          <p className="text-zinc-300 font-medium">
            Arrastrá tu Excel acá o hacé click para seleccionar
          </p>
          <p className="text-zinc-500 text-sm mt-1">
            Formatos aceptados: .xlsx, .xls
          </p>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx,.xls"
          onChange={onFileChange}
          className="hidden"
        />
      </div>

      {/* Error */}
      {error && (
        <div className="w-full max-w-xl px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="w-full max-w-xl px-4 py-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 text-sm">
          {warnings.map((w, i) => <p key={i}>{w}</p>)}
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-col items-center gap-3">
        <button
          id="show-structure-button"
          onClick={() => setModalOpen(true)}
          className="text-sm text-zinc-400 hover:text-blue-400 underline underline-offset-4 transition-colors"
        >
          ¿Cómo debe ser el Excel?
        </button>
        <ExcelTemplateButton />
      </div>

      <ExcelStructureModal isOpen={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  );
}
