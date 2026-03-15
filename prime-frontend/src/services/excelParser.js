//prime-frontend/src/services/excelParser.js
import * as XLSX from 'xlsx';
import {
  VEHICULOS_REQUIRED,
  DESTINOS_REQUIRED,
  VEHICULOS_DEFAULTS,
  DESTINOS_DEFAULTS,
} from '../constants/excelColumns';

/**
 * Parse an Excel file buffer into a fleet request JSON payload.
 * Throws descriptive Error on validation failures.
 */
export function parseExcelToFleetPayload(buffer) {
  const workbook = XLSX.read(buffer, { type: 'array' });

  // --- Validate sheets exist ---
  if (!workbook.SheetNames.includes('Vehiculos')) {
    throw new Error("El archivo no tiene la hoja 'Vehiculos'.");
  }
  if (!workbook.SheetNames.includes('Destinos')) {
    throw new Error("El archivo no tiene la hoja 'Destinos'.");
  }

  // --- Parse sheets ---
  const vehiculosRaw = XLSX.utils.sheet_to_json(workbook.Sheets['Vehiculos']);
  const destinosRaw = XLSX.utils.sheet_to_json(workbook.Sheets['Destinos']);

  if (vehiculosRaw.length === 0) {
    throw new Error("La hoja 'Vehiculos' no tiene filas de datos.");
  }
  if (destinosRaw.length === 0) {
    throw new Error("La hoja 'Destinos' no tiene filas de datos.");
  }

  // --- Validate required columns ---
  const vCols = Object.keys(vehiculosRaw[0]);
  for (const col of VEHICULOS_REQUIRED) {
    if (!vCols.includes(col)) {
      throw new Error(`Falta la columna '${col}' en la hoja 'Vehiculos'.`);
    }
  }

  const dCols = Object.keys(destinosRaw[0]);
  for (const col of DESTINOS_REQUIRED) {
    if (!dCols.includes(col)) {
      throw new Error(`Falta la columna '${col}' en la hoja 'Destinos'.`);
    }
  }

  // --- Build vehicles array with defaults and sanitization ---
  const vehicles = vehiculosRaw.map((row) => {
    // Prioridad 3: Sanitización de IDs
    const sanitizedId = String(row.id).replace(/[^a-zA-Z0-9_-]/g, '_');
    
    return {
      id: sanitizedId,
      origin_lat: Number(row.origin_lat),
      origin_lon: Number(row.origin_lon),
      capacity_tons: Number(row.capacity_tons),
      max_shift_minutes: row.max_shift_minutes != null
        ? Number(row.max_shift_minutes)
        : VEHICULOS_DEFAULTS.max_shift_minutes,
      // Prioridad 2: Extracción Per-Vehicle
      departure_time: row.horario_salida ? String(row.horario_salida) : null,
      overtime_cost_hr: row.costo_hora_extra != null ? Number(row.costo_hora_extra) : null,
    };
  });

  // --- Build destinations array with defaults and validation ---
  const destinations = destinosRaw.map((row) => {
    // Prioridad 3: Sanitización de IDs
    const sanitizedId = String(row.id).replace(/[^a-zA-Z0-9_-]/g, '_');
    
    let tw_start = row.tw_start_min != null ? Number(row.tw_start_min) : DESTINOS_DEFAULTS.tw_start_min;
    let tw_end = row.tw_end_min != null ? Number(row.tw_end_min) : DESTINOS_DEFAULTS.tw_end_min;
    
    // Prioridad 3b: Validación de contrato de ventanas
    if (tw_end <= tw_start) {
      tw_end = tw_start + 60;
    }

    return {
      id: sanitizedId,
      lat: Number(row.lat),
      lon: Number(row.lon),
      demand_tons: Number(row.demand_tons),
      service_time_min: row.service_time_min != null
        ? Number(row.service_time_min)
        : DESTINOS_DEFAULTS.service_time_min,
      tw_start_min: tw_start,
      tw_end_min: tw_end,
    };
  });

  // --- AMBA bounding-box warnings (non-blocking) ---
  const warnings = [];
  const AMBA = { latMin: -35.5, latMax: -33.5, lonMin: -59.5, lonMax: -57.5 };
  vehicles.forEach((v) => {
    if (v.origin_lat < AMBA.latMin || v.origin_lat > AMBA.latMax ||
      v.origin_lon < AMBA.lonMin || v.origin_lon > AMBA.lonMax) {
      warnings.push(`Vehículo ${v.id}: coordenadas fuera del AMBA.`);
    }
  });
  destinations.forEach((d) => {
    if (d.lat < AMBA.latMin || d.lat > AMBA.latMax ||
      d.lon < AMBA.lonMin || d.lon > AMBA.lonMax) {
      warnings.push(`Destino ${d.id}: coordenadas fuera del AMBA.`);
    }
  });

  return {
    payload: {
      vehicles,
      destinations,
      allowed_archetypes: ['tanque', 'apostador', 'equilibrista', 'unicornio'], // Prioridad Auditoría: Habilitamos Unicornio
      time_limit_seconds: 15, // Aumentamos margen para flotas complejas
    },
    warnings,
  };
}
