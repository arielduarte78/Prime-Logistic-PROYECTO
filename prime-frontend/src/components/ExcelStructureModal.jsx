//prime-frontend/src/components/ExcelStructureModal.jsx
import { useState } from 'react';
import ExcelTemplateButton from './ExcelTemplateButton';
import { VEHICULOS_REQUIRED, VEHICULOS_COLS, DESTINOS_REQUIRED, DESTINOS_COLS } from '../constants/excelColumns';

function ColumnTable({ title, columns, required }) {
  return (
    <div className="mb-6">
      <h4 className="text-sm font-semibold text-white mb-3">Hoja: {title}</h4>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-700">
              <th className="text-left py-2 px-3 text-zinc-400 font-medium">Columna</th>
              <th className="text-left py-2 px-3 text-zinc-400 font-medium">Requerida</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((col) => (
              <tr key={col} className="border-b border-zinc-800/50">
                <td className="py-2 px-3 text-zinc-300 font-mono text-xs">{col}</td>
                <td className="py-2 px-3">
                  {required.includes(col) ? (
                    <span className="text-red-400 text-xs font-medium">Obligatoria</span>
                  ) : (
                    <span className="text-zinc-500 text-xs">Opcional (tiene default)</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function ExcelStructureModal({ isOpen, onClose }) {
  if (!isOpen) return null;

  return (
    <div
      id="excel-structure-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-zinc-900 border border-zinc-700/50 rounded-2xl shadow-2xl w-full max-w-lg mx-4 p-6 max-h-[85vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold text-white">Estructura del Excel</h3>
          <button
            id="close-modal-button"
            onClick={onClose}
            className="text-zinc-400 hover:text-white transition-colors p-1"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <p className="text-sm text-zinc-400 mb-6">
          El archivo Excel debe tener exactamente dos hojas: <span className="text-white font-medium">Vehiculos</span> y <span className="text-white font-medium">Destinos</span>.
        </p>

        <ColumnTable title="Vehiculos" columns={[...VEHICULOS_COLS, 'referencia']} required={VEHICULOS_REQUIRED} />
        <ColumnTable title="Destinos" columns={[...DESTINOS_COLS, 'referencia']} required={DESTINOS_REQUIRED} />

        <div className="mt-4 pt-4 border-t border-zinc-800 flex justify-center">
          <ExcelTemplateButton />
        </div>
      </div>
    </div>
  );
}
