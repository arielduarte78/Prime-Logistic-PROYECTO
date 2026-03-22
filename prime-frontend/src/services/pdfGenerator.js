//prime-frontend/src/services/pdfGenerator.js
import jsPDF from 'jspdf';
import 'jspdf-autotable';

function generateVehiclePdf(assignment, archetype, parsedPayload, generationDate) {
  const doc = new jsPDF({ unit: 'mm', format: 'a4' });
  const pageWidth = doc.internal.pageSize.getWidth();
  const margin = 15;
  let y = 0;

  // ── ENCABEZADO ──
  doc.setFillColor(15, 23, 42); // #0F172A
  doc.rect(0, 0, pageWidth, 28, 'F');
  doc.setFontSize(22);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(255, 255, 255);
  doc.text('Abbey', margin, 14);
  
  doc.setFontSize(14);
  doc.setFont('helvetica', 'bold');
  doc.text('HOJA DE RUTA', margin, 22);

  doc.setFontSize(10);
  doc.setFont('helvetica', 'normal');
  doc.text(`${generationDate}`, pageWidth - margin, 22, { align: 'right' });

  y = 35;

  // ── BLOQUE 1: DATOS DEL SERVICIO ──
  const vehicle = assignment.vehicle;
  const vehicleData = parsedPayload?.vehicles?.find(v => v.id === vehicle?.id);
  const vId = vehicle?.id || vehicleData?.id || '?';
  
  // Strategy name translation
  const getStrategyName = (key) => {
    const map = {
      tanque: 'Ruta más segura 🛡️',
      apostador: 'Menor costo 💰',
      equilibrista: 'Equilibrio Óptimo ⚖️',
      unicornio: 'Solución excepcional 🦄'
    };
    return map[key] || key;
  };

  const originLabel = vehicleData?.referencia ? vehicleData.referencia : (vehicle?.origin_lat && vehicle?.origin_lon ? "Base operativa" : "No especificado");

  doc.setDrawColor(200, 200, 200);
  doc.roundedRect(margin, y, pageWidth - margin * 2, 28, 2, 2, 'S');
  
  doc.setFontSize(12);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(0, 0, 0);
  doc.text('DATOS DEL SERVICIO', margin + 4, y + 6);
  
  doc.setFontSize(10);
  doc.setFont('helvetica', 'normal');
  doc.text(`Estrategia: ${getStrategyName(archetype)}`, margin + 4, y + 13);
  doc.text(`Vehículo: Unidad ${vId}  |  Capacidad: ${vehicle?.capacity_tons || 0} toneladas`, margin + 4, y + 19);
  doc.text(`Origen: ${originLabel}  |  Salida estimada: ${parsedPayload?.departure_time || '08:00'} hs`, margin + 4, y + 25);
  
  y += 35;

  // ── BLOQUE 2: CRONOGRAMA DE ENTREGAS ──
  const destinations = assignment.route_destinations || [];
  const schedule = assignment.schedule || [];
  const destLookup = {};
  (parsedPayload?.destinations || []).forEach(d => { destLookup[d.id] = d; });

  const tableBody = destinations.map((dest, idx) => {
    const sched = schedule[idx] || {};
    const ref = destLookup[dest.id]?.referencia || '-';
    return [
      idx + 1,
      dest.id || '-',
      ref,
      `${sched.suggested_arrival_hhmm || '--:--'} hs`,
      `${dest.service_time_min ?? 0} min`,
      ''
    ];
  });

  doc.autoTable({
    startY: y,
    head: [['N°', 'Destino', 'Dirección/Ref', 'Hora estimada', 'Tiempo de servicio', 'Observaciones']],
    body: tableBody,
    theme: 'striped',
    headStyles: { fillColor: [240, 240, 240], textColor: [0, 0, 0], fontStyle: 'bold', lineWidth: 0.1, lineColor: [200, 200, 200] },
    bodyStyles: { textColor: [0, 0, 0] },
    alternateRowStyles: { fillColor: [250, 250, 250] },
    styles: { font: 'helvetica', fontSize: 9, cellPadding: 3, lineColor: [200, 200, 200], lineWidth: 0.1 },
    columnStyles: {
      0: { cellWidth: 10, halign: 'center' },
      1: { cellWidth: 30 },
      2: { cellWidth: 50 },
      3: { cellWidth: 25 },
      4: { cellWidth: 30, halign: 'center' },
      5: { cellWidth: 'auto' }
    }
  });

  y = doc.lastAutoTable.finalY + 8;

  // Retorno a base
  doc.setFontSize(10);
  doc.setFont('helvetica', 'normal');
  const returnEntry = schedule.find(s => s.is_return || s.destination_id === "__RETURN_BASE__");
  doc.text(`Retorno a base estimado: ${returnEntry?.suggested_arrival_hhmm ? returnEntry.suggested_arrival_hhmm + ' hs' : 'Horario a confirmar'}`, margin, y);
  y += 12;

  // ── BLOQUE 3: RESUMEN OPERATIVO ──
  if (y > 220) { doc.addPage(); y = 20; }
  
  doc.setFillColor(245, 245, 245);
  doc.rect(margin, y, pageWidth - margin * 2, 22, 'F');
  
  const totalTonnage = destinations.reduce((sum, d) => sum + (d.demand_tons || 0), 0);
  const totalKm = assignment.cost_breakdown?.distancia_km || 0;
  const cost = assignment.cost_breakdown?.costo_total_ars || 0;

  doc.setFontSize(10);
  doc.setFont('helvetica', 'bold');
  doc.text('RESUMEN OPERATIVO', margin + 4, y + 6);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.text(`Cantidad de entregas: ${destinations.length}  |  Carga total asignada: ${totalTonnage} toneladas`, margin + 4, y + 13);
  doc.text(`Distancia estimada: ${totalKm > 0 ? totalKm.toFixed(1) + ' km' : 'N/A'}  |  Costo operativo de la ruta: $${Math.round(cost).toLocaleString('es-AR')} ARS`, margin + 4, y + 19);
  
  y += 35;

  // ── BLOQUE 4: FIRMA Y CONFORMIDAD ──
  if (y > 230) { doc.addPage(); y = 20; }
  
  doc.setFontSize(11);
  doc.setFont('helvetica', 'bold');
  doc.text('FIRMA Y CONFORMIDAD', margin, y);
  
  y += 10;
  doc.setFontSize(10);
  doc.setFont('helvetica', 'normal');
  
  const lineGap = 12;
  doc.text('Firma del conductor: _________________________________', margin, y);
  doc.text('DNI: _______________________________', margin + 100, y);
  y += lineGap;
  doc.text('Hora de salida real: __________________', margin, y);
  doc.text('Kilometraje al salir: __________________', margin + 100, y);
  y += lineGap;
  doc.text('Observaciones: __________________________________________________________________________', margin, y);
  y += lineGap;
  doc.text('_______________________________________________________________________________________', margin + 25, y);

  // ── PIE DE PÁGINA ──
  const footerY = doc.internal.pageSize.getHeight() - 10;
  doc.setFontSize(8);
  doc.setTextColor(150, 150, 150);
  doc.text(`Generado por Abbey — Motor Logístico Aphira — ${generationDate}`, pageWidth / 2, footerY, { align: 'center' });

  return doc;
}

export async function exportPdfs(fleetResponse, selectedArchetype, parsedPayload) {
  const plan = fleetResponse?.plans?.[selectedArchetype];
  if (!plan?.assignments) return;

  const now = new Date().toLocaleDateString('es-AR', {
    weekday: 'long',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric'
  });

  const assignments = plan.assignments.filter(a => (a.route_destinations || []).length > 0);
  if (assignments.length === 0) return;

  if (assignments.length === 1) {
    const doc = generateVehiclePdf(assignments[0], selectedArchetype, parsedPayload, now);
    doc.save(`abbey_hoja_de_ruta_${assignments[0].vehicle?.id || 'V1'}.pdf`);
    return;
  }

  // Múltiples vehículos → ZIP
  const JSZip = (await import('jszip')).default;
  const zip = new JSZip();
  for (const assignment of assignments) {
    const doc = generateVehiclePdf(assignment, selectedArchetype, parsedPayload, now);
    const pdfBytes = doc.output('arraybuffer');
    zip.file(`abbey_hoja_de_ruta_${assignment.vehicle?.id || 'V'}.pdf`, pdfBytes);
  }
  const blob = await zip.generateAsync({ type: 'blob' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `abbey_hojas_de_ruta_${selectedArchetype}_${new Date().toISOString().slice(0, 10)}.zip`;
  a.click();
  URL.revokeObjectURL(url);
}
