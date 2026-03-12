//prime-frontend/src/constants/excelColumns.js
export const VEHICULOS_COLS = ['id', 'origin_lat', 'origin_lon', 'capacity_tons', 'max_shift_minutes'];
export const VEHICULOS_REQUIRED = ['id', 'origin_lat', 'origin_lon', 'capacity_tons'];
export const DESTINOS_COLS = ['id', 'lat', 'lon', 'demand_tons', 'service_time_min', 'tw_start_min', 'tw_end_min'];
export const DESTINOS_REQUIRED = ['id', 'lat', 'lon', 'demand_tons'];
export const VEHICULOS_DEFAULTS = { max_shift_minutes: 480 };
export const DESTINOS_DEFAULTS = { service_time_min: 0, tw_start_min: 0, tw_end_min: 1440 };
