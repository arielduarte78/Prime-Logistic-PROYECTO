//prime-frontend/src/components/CfoReportModal.jsx
import React from 'react';
import { X, FileText, Download, TrendingUp, DollarSign, Clock, ShieldCheck } from 'lucide-react';
import { jsPDF } from 'jspdf';
import 'jspdf-autotable';

export default function CfoReportModal({ isOpen, onClose, breakdown, archetype, currentPlan }) {
  if (!isOpen || !breakdown) return null;

  // TAREA 2: Cálculo robusto desde currentPlan (Sincronía Total)
  const assignments = currentPlan?.assignments || [];
  
  const opex_dist = assignments.reduce((acc, curr) => acc + (curr.cost_breakdown?.opex_distance_ars || 0), 0);
  const opex_time = assignments.reduce((acc, curr) => acc + (curr.cost_breakdown?.opex_time_ars || 0), 0);
  const capex = assignments.reduce((acc, curr) => acc + (curr.cost_breakdown?.capex_amortization_ars || 0), 0);
  const fixed = assignments.reduce((acc, curr) => acc + (curr.cost_breakdown?.fixed_costs_ars || 0), 0);
  const risk = assignments.reduce((acc, curr) => acc + (curr.cost_breakdown?.exposure_risk_ars || 0), 0);
  const custody = assignments.reduce((acc, curr) => acc + (curr.cost_breakdown?.custodia_ars || 0), 0);
  const riskCustody = risk + custody;

  // Control de Integridad: Usamos el total directo del motor CFO
  const totalCost = breakdown.costo_total_ars || (opex_dist + opex_time + capex + fixed + riskCustody);
  const totalDist = assignments.reduce((acc, curr) => acc + (curr.cost_breakdown?.distancia_km || 0), 0);

  // Formula Corrección Ejecutiva: opex_distancia / total_km
  const costPerKm = totalDist > 0 ? (opex_dist / totalDist) : 0;

  const exportPDF = () => {
    const doc = new jsPDF();

    // Header
    doc.setFontSize(22);
    doc.setTextColor(15, 23, 42); // slate-900
    doc.text("Abbey - Estado de Resultados Logístico", 14, 22);

    doc.setFontSize(10);
    doc.setTextColor(100);
    doc.text(`Arquetipo: ${archetype?.toUpperCase()} | Fecha: ${new Date().toLocaleDateString()}`, 14, 30);
    doc.text("División: Finanzas & Operaciones Logísticas", 14, 35);

    // Executive Summary: Texto Exacto TAREA 2
    doc.setFontSize(14);
    doc.setTextColor(15, 23, 42);
    doc.text("Resumen Ejecutivo Estatutario", 14, 50);
    
    doc.setFontSize(10);
    doc.setTextColor(80);
    const summaryText = "Este Estado de Resultados desglosa el Costo Servido Total en cuatro dimensiones: 1) Gastos de Desplazamiento (Variables), 2) Personal y Estructura (Fijos por tiempo), 3) Gastos fijos de la operación y 4) Riesgo Patrimonial y Custodia. La varianza expone la pérdida de margen operativo traccionada por ineficiencias de tráfico y exposición al siniestro.";
    const splitSummary = doc.splitTextToSize(summaryText, 180);
    doc.text(splitSummary, 14, 58);

    // P&L Table (Corporate Terms)
    const tableBody = [
      ['Gastos de Desplazamiento (Variables)', `$ ${opex_dist.toLocaleString(undefined, { minimumFractionDigits: 2 })}`, `${((opex_dist / totalCost) * 100).toFixed(1)}%`],
      ['Personal y Estructura (Fijos por tiempo)', `$ ${(opex_time + capex).toLocaleString(undefined, { minimumFractionDigits: 2 })}`, `${(((opex_time + capex) / totalCost) * 100).toFixed(1)}%`],
      ['Costos Fijos por Ruta', `$ ${fixed.toLocaleString(undefined, { minimumFractionDigits: 2 })}`, `${((fixed / totalCost) * 100).toFixed(1)}%`],
      ['Riesgo Patrimonial y Custodia', `$ ${riskCustody.toLocaleString(undefined, { minimumFractionDigits: 2 })}`, `${((riskCustody / totalCost) * 100).toFixed(1)}%`],
      [{ content: 'COSTO SERVIDO TOTAL (CTS)', styles: { fontStyle: 'bold', fillColor: [15, 23, 42], textColor: [255, 255, 255] } }, { content: `$ ${totalCost.toLocaleString(undefined, { minimumFractionDigits: 2 })}`, styles: { fontStyle: 'bold', fillColor: [15, 23, 42], textColor: [255, 255, 255] } }, { content: '100.0%', styles: { fontStyle: 'bold', fillColor: [15, 23, 42], textColor: [255, 255, 255] } }]
    ];

    doc.autoTable({
      startY: 85,
      head: [['Concepto P&L (CFO)', 'Monto (ARS)', 'Impacto %']],
      body: tableBody,
      theme: 'striped',
      headStyles: { fillColor: [15, 23, 42], textColor: [255, 255, 255], fontStyle: 'bold' },
      styles: { fontSize: 10, cellPadding: 5 },
      columnStyles: { 
        1: { halign: 'right' },
        2: { halign: 'right' }
      }
    });

    // FOOTER
    const finalY = doc.lastAutoTable.finalY + 20;
    doc.setFontSize(8);
    doc.setTextColor(150);
    doc.text("Generado por Abbey Audit Engine v2.0 - Reporte de Confianza Senior CFO", 14, finalY);

    doc.save(`Abbey_CfoReport_${archetype}_${Date.now()}.pdf`);
  };

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-slate-900/80 backdrop-blur-md animate-in fade-in duration-300">
      <div className="bg-white w-full max-w-4xl rounded-[2.5rem] shadow-2xl overflow-hidden border border-slate-200 flex flex-col max-h-[90vh] ring-1 ring-white/20">
        {/* Header */}
        <div className="p-8 border-b border-slate-100 flex items-center justify-between bg-slate-900 text-white">
          <div className="flex items-center gap-6">
            <div className="p-4 bg-emerald-500/10 rounded-[1.25rem] ring-1 ring-emerald-500/20">
              <TrendingUp className="text-emerald-400" size={32} />
            </div>
            <div>
              <h2 className="text-2xl font-black tracking-tight leading-none mb-2">Financial Audit Report</h2>
              <p className="text-[10px] uppercase tracking-[0.3em] font-bold text-white/40">CFO Dashboard • Unit Economics • Cost-to-Serve (CTS)</p>
            </div>
          </div>
          <button onClick={onClose} className="p-3 hover:bg-white/10 rounded-2xl transition-all hover:rotate-90">
            <X size={24} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-10 space-y-10">
          {/* Executive Summary Section */}
          <div className="space-y-6">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
              <FileText size={14} className="text-emerald-600" /> Resumen Ejecutivo Estatutario
            </div>
            <div className="relative">
              <div className="absolute -left-4 top-0 bottom-0 w-1.5 bg-emerald-600 rounded-full" />
              <p className="text-base font-medium leading-relaxed text-slate-600 pl-6 pr-10 py-2">
                "Este Estado de Resultados desglosa el <span className="text-slate-900 font-bold">Costo Servido Total</span> en cuatro dimensiones: 
                1) <span className="text-slate-900 font-bold underline decoration-emerald-500/30 decoration-4">Gastos de Desplazamiento (Variables)</span>, 
                2) <span className="text-slate-900 font-bold underline decoration-emerald-500/30 decoration-4">Personal y Estructura (Fijos por tiempo)</span>, 
                3) <span className="text-slate-900 font-bold underline decoration-emerald-500/30 decoration-4">Gastos fijos de la operación</span> y 
                4) <span className="text-slate-900 font-bold underline decoration-emerald-500/30 decoration-4">Riesgo Patrimonial y Custodia</span>. 
                La varianza expone la pérdida de margen operativo traccionada por ineficiencias de tráfico y exposición al siniestro."
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
             {/* P&L Table */}
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-900">
                  <DollarSign size={14} className="text-emerald-600" /> Statement of Result
                </div>
                <span className="text-[10px] font-bold text-slate-300 tabular-nums uppercase">Audit Source: CFO Excel v2.0</span>
              </div>
              <div className="border border-slate-100 rounded-[2rem] overflow-hidden shadow-sm ring-1 ring-slate-100">
                <table className="w-full text-left border-collapse tabular-nums">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      <th className="p-5 text-[10px] font-black uppercase text-slate-400">Concepto P&L</th>
                      <th className="p-5 text-[10px] font-black uppercase text-slate-400 text-right">Monto (ARS)</th>
                      <th className="p-5 text-[10px] font-black uppercase text-slate-400 text-right">%</th>
                    </tr>
                  </thead>
                  <tbody className="text-xs font-bold text-slate-700">
                    <tr className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                      <td className="p-5 text-slate-900">Gastos Desplazamiento</td>
                      <td className="p-5 text-right font-black">$ {opex_dist.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                      <td className="p-5 text-right text-slate-400">{((opex_dist/totalCost)*100).toFixed(1)}%</td>
                    </tr>
                     <tr className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                      <td className="p-5 text-slate-900">Personal y Estructura (Fijos por tiempo)</td>
                      <td className="p-5 text-right font-black">$ {(opex_time + capex).toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                      <td className="p-5 text-right text-slate-400">{(((opex_time + capex)/totalCost)*100).toFixed(1)}%</td>
                    </tr>
                    <tr className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                      <td className="p-5 text-slate-900">Costos Fijos por Ruta</td>
                      <td className="p-5 text-right font-black">$ {fixed.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                      <td className="p-5 text-right text-slate-400">{((fixed/totalCost)*100).toFixed(1)}%</td>
                    </tr>
                    <tr className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                      <td className="p-5 text-slate-900">Riesgo Patrimonial y Custodia</td>
                      <td className="p-5 text-right font-black">$ {riskCustody.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                      <td className="p-5 text-right text-slate-400">{((riskCustody/totalCost)*100).toFixed(1)}%</td>
                    </tr>
                    <tr className="bg-slate-900 text-white leading-none">
                      <td className="p-6 font-black uppercase tracking-tighter text-sm">Costo Servido Total</td>
                      <td className="p-6 text-right font-black text-sm">$ {totalCost.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                      <td className="p-6 text-right font-black text-sm">100%</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Variance & KPIs */}
            <div className="space-y-6">
             <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
                <ShieldCheck size={14} className="text-emerald-600" /> Analítica de Varianza
              </div>
              
              <div className="grid grid-cols-1 gap-4">
                {(breakdown.executive_variance_analysis || []).map((rev, idx) => (
                  <div key={idx} className="p-5 bg-slate-50 border border-slate-200 rounded-3xl text-[11px] font-bold text-slate-700 flex items-start gap-4 transition-all hover:border-emerald-200 hover:bg-emerald-50/10 group">
                    <div className="w-8 h-8 rounded-full bg-white border border-slate-200 flex items-center justify-center text-slate-400 group-hover:text-emerald-600 group-hover:border-emerald-200 transition-colors shrink-0 tabular-nums">
                      {idx + 1}
                    </div>
                    <div className="leading-relaxed">
                      {rev}
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-6 p-6 bg-slate-900 rounded-[2rem] text-white space-y-4 shadow-xl shadow-slate-200">
                 <div className="flex items-center justify-between text-[10px] font-black uppercase tracking-widest text-white/30">
                    <span>Executive Metrics</span>
                    <TrendingUp size={12} />
                 </div>
                 <div className="flex items-end justify-between tabular-nums">
                    <div>
                      <span className="block text-[10px] font-bold text-emerald-500">Monto USD (MEP)</span>
                      <span className="text-2xl font-black">${(totalCost / (breakdown.dolar_mep || 1415.52)).toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                    </div>
                    <div className="text-right">
                      <span className="block text-[10px] font-bold text-white/30">Costo por KM</span>
                      <span className="text-lg font-black text-white/80">${costPerKm.toFixed(2)}</span>
                    </div>
                 </div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-8 bg-slate-50 border-t border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-3 text-[10px] font-black text-slate-300 uppercase tracking-[0.2em]">
            <Clock size={16} /> Verified by Abbey Logic Engine • Senior CFO Dashboard
          </div>
          <button 
            onClick={exportPDF}
            className="flex items-center gap-3 px-10 py-5 bg-slate-900 text-white rounded-[1.25rem] font-black text-xs uppercase tracking-[0.2em] hover:bg-black shadow-2xl transition-all hover:-translate-y-1 active:scale-95 group"
          >
            <Download size={18} className="text-emerald-600 group-hover:animate-bounce" /> Export Senior Office Report
          </button>
        </div>
      </div>
    </div>
  );
}
