/**prime-frontend/src/services/pdfGenerator.js */
import { jsPDF } from 'jspdf';

/**
 * Generate a PDF route sheet for a single vehicle assignment.
 * Returns a jsPDF instance.
 */
function generateVehiclePdf(vehiclePlan, archetype, fleetResponse, generationDate) {
  const doc = new jsPDF({ unit: 'mm', format: 'a4' });
  const pageWidth = doc.internal.pageSize.getWidth();
  let y = 20;

  // --- Header ---
  doc.setFontSize(18);
  doc.setFont('helvetica', 'bold');
  doc.text('[NOMBRE] — Hoja de Ruta', pageWidth / 2, y, { align: 'center' });
  y += 8;

  doc.setFontSize(10);
  doc.setFont('helvetica', 'normal');
  doc.text(`Generado: ${generationDate}  |  Arquetipo: ${archetype}`, pageWidth / 2, y, { align: 'center' });
  y += 12;

  // --- Vehicle Info ---
  const vehicle = vehiclePlan.vehicle;
  doc.setFontSize(12);
  doc.setFont('helvetica', 'bold');
  doc.text('Vehículo', 15, y);
  y += 6;
  doc.setFontSize(10);
  doc.setFont('helvetica', 'normal');
  doc.text(`ID: ${vehicle.id}`, 15, y); y += 5;
  doc.text(`Origen: (${vehicle.origin_lat}, ${vehicle.origin_lon})`, 15, y); y += 5;
  doc.text(`Capacidad: ${vehicle.capacity_tons} tn`, 15, y); y += 10;

  // --- Schedule Table ---
  doc.setFontSize(12);
  doc.setFont('helvetica', 'bold');
  doc.text('Cronograma de Entregas', 15, y);
  y += 8;

  // Table header
  doc.setFontSize(9);
  doc.setFont('helvetica', 'bold');
  const colX = [15, 40, 90, 140];
  doc.text('#', colX[0], y);
  doc.text('Destino', colX[1], y);
  doc.text('Hora llegada', colX[2], y);
  doc.text('Servicio (min)', colX[3], y);
  y += 2;
  doc.setLineWidth(0.3);
  doc.line(15, y, pageWidth - 15, y);
  y += 5;

  doc.setFont('helvetica', 'normal');
  const destinations = vehiclePlan.route_destinations || [];
  const schedule = vehiclePlan.schedule || [];

  destinations.forEach((dest, idx) => {
    if (y > 270) {
      doc.addPage();
      y = 20;
    }
    const sched = schedule[idx] || {};
    doc.text(String(idx + 1), colX[0], y);
    doc.text(dest.id || '-', colX[1], y);
    doc.text(sched.suggested_arrival_hhmm || '--:--', colX[2], y);
    doc.text(String(dest.service_time_min ?? 0), colX[3], y);
    y += 6;
  });

  y += 8;

  // --- Summary ---
  doc.setFont('helvetica', 'bold');
  doc.text('Resumen', 15, y); y += 6;
  doc.setFont('helvetica', 'normal');
  doc.text(`Destinos asignados: ${destinations.length}`, 15, y); y += 5;
  doc.text(`Arquetipo: ${archetype}`, 15, y); y += 5;

  // --- Footer ---
  const footerY = doc.internal.pageSize.getHeight() - 10;
  doc.setFontSize(8);
  doc.setTextColor(120);
  doc.text('Generado por [NOMBRE] — Este documento es una hoja de ruta operativa.', pageWidth / 2, footerY, { align: 'center' });

  return doc;
}

/**
 * Export PDFs for all vehicles in a fleet plan.
 * If single vehicle: downloads one PDF.
 * If multiple: downloads a ZIP via dynamic import of JSZip (optional).
 */
export async function exportPdfs(fleetResponse, selectedArchetype) {
  const plan = fleetResponse.plans?.[selectedArchetype];
  if (!plan || !plan.assignments) return;

  const now = new Date().toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' });
  const assignments = plan.assignments;

  if (assignments.length === 1) {
    const doc = generateVehiclePdf(assignments[0], selectedArchetype, fleetResponse, now);
    doc.save(`hoja_ruta_${assignments[0].vehicle.id}.pdf`);
    return;
  }

  // Multiple vehicles — download individual PDFs
  for (const assignment of assignments) {
    const doc = generateVehiclePdf(assignment, selectedArchetype, fleetResponse, now);
    doc.save(`hoja_ruta_${assignment.vehicle.id}.pdf`);
  }
}
