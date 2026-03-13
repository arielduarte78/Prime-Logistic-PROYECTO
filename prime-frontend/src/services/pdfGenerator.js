//prime-frontend/src/services/pdfGenerator.js
import { jsPDF } from 'jspdf';

function generateVehiclePdf(assignment, archetype, parsedPayload, generationDate) {
  const doc = new jsPDF({ unit: 'mm', format: 'a4' });
  const pageWidth = doc.internal.pageSize.getWidth();
  const margin = 15;
  let y = 0;

  // ── Header band ──
  doc.setFillColor(15, 23, 42);
  doc.rect(0, 0, pageWidth, 28, 'F');
  doc.setFontSize(16);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(255, 255, 255);
  doc.text('Abbey — Hoja de Ruta', margin, 12);
  doc.setFontSize(8);
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(180, 180, 200);
  doc.text(`Generado: ${generationDate}  |  Estrategia: ${archetype.toUpperCase()}`, margin, 20);
  y = 38;

  // ── Vehicle info ──
  const vehicle = assignment.vehicle;
  const vehicleData = parsedPayload?.vehicles?.find(v => v.id === vehicle?.id);
  const originLabel = vehicleData?.referencia || `${vehicle?.origin_lat}, ${vehicle?.origin_lon}`;

  doc.setFillColor(249, 250, 251);
  doc.roundedRect(margin, y, pageWidth - margin * 2, 22, 3, 3, 'F');
  doc.setTextColor(17, 24, 39);
  doc.setFontSize(11);
  doc.setFont('helvetica', 'bold');
  doc.text(`Vehiculo: ${vehicle?.id}`, margin + 5, y + 8);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(107, 114, 128);
  doc.text(`Origen: ${originLabel}  |  Capacidad: ${vehicle?.capacity_tons} tn`, margin + 5, y + 16);
  y += 30;

  // ── Schedule table ──
  doc.setFontSize(11);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(17, 24, 39);
  doc.text('Cronograma de Entregas', margin, y);
  y += 6;

  doc.setFillColor(15, 23, 42);
  doc.rect(margin, y, pageWidth - margin * 2, 8, 'F');
  doc.setFontSize(8);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(255, 255, 255);
  const cols = [margin + 3, margin + 18, margin + 70, margin + 110, margin + 145];
  doc.text('#', cols[0], y + 5.5);
  doc.text('Destino', cols[1], y + 5.5);
  doc.text('Referencia', cols[2], y + 5.5);
  doc.text('Llegada', cols[3], y + 5.5);
  doc.text('Servicio (min)', cols[4], y + 5.5);
  y += 10;

  const destinations = assignment.route_destinations || [];
  const schedule = assignment.schedule || [];
  const destLookup = {};
  (parsedPayload?.destinations || []).forEach(d => { destLookup[d.id] = d; });

  destinations.forEach((dest, idx) => {
    if (y > 265) { doc.addPage(); y = 20; }
    if (idx % 2 === 0) {
      doc.setFillColor(249, 250, 251);
      doc.rect(margin, y - 1, pageWidth - margin * 2, 8, 'F');
    }
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    doc.setTextColor(17, 24, 39);
    const sched = schedule[idx] || {};
    const ref = destLookup[dest.id]?.referencia || '-';
    doc.text(String(idx + 1), cols[0], y + 5);
    doc.text(dest.id || '-', cols[1], y + 5);
    doc.text(ref.substring(0, 28), cols[2], y + 5);
    doc.text(sched.suggested_arrival_hhmm || '--:--', cols[3], y + 5);
    doc.text(String(dest.service_time_min ?? 0), cols[4], y + 5);
    y += 8;
  });

  y += 8;

  // ── Summary ──
  doc.setFillColor(220, 252, 231);
  doc.roundedRect(margin, y, pageWidth - margin * 2, 18, 3, 3, 'F');
  doc.setFontSize(9);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(22, 101, 52);
  doc.text(`Destinos asignados: ${destinations.length}  |  Estrategia: ${archetype}`, margin + 5, y + 8);
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(107, 114, 128);
  doc.text('Documento generado por Abbey — Motor logístico para flotas en Buenos Aires', margin + 5, y + 14);

  // ── Footer ──
  const footerY = doc.internal.pageSize.getHeight() - 8;
  doc.setFontSize(7);
  doc.setTextColor(180, 180, 180);
  doc.text('© 2026 Aphira — Este documento es una hoja de ruta operativa. No compartir fuera de la operación.', pageWidth / 2, footerY, { align: 'center' });

  return doc;
}

export async function exportPdfs(fleetResponse, selectedArchetype, parsedPayload) {
  const plan = fleetResponse?.plans?.[selectedArchetype];
  if (!plan?.assignments) return;

  const now = new Date().toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' });
  const assignments = plan.assignments.filter(a => (a.route_destinations || []).length > 0);
  if (assignments.length === 0) return;

  if (assignments.length === 1) {
    const doc = generateVehiclePdf(assignments[0], selectedArchetype, parsedPayload, now);
    doc.save(`abbey_ruta_${assignments[0].vehicle?.id || 'V1'}.pdf`);
    return;
  }

  // Múltiples vehículos → ZIP
  const JSZip = (await import('jszip')).default;
  const zip = new JSZip();
  for (const assignment of assignments) {
    const doc = generateVehiclePdf(assignment, selectedArchetype, parsedPayload, now);
    const pdfBytes = doc.output('arraybuffer');
    zip.file(`abbey_ruta_${assignment.vehicle?.id || 'V'}.pdf`, pdfBytes);
  }
  const blob = await zip.generateAsync({ type: 'blob' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `abbey_rutas_${selectedArchetype}_${new Date().toISOString().slice(0, 10)}.zip`;
  a.click();
  URL.revokeObjectURL(url);
}
