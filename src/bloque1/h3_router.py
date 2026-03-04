#H3_router.py
import h3
import math

def build_h3_corridor(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float, resolution: int = 8) -> list[str]:
    # 1. Obtener hexágonos de origen y destino
    try:
        origin_hex = h3.latlng_to_cell(origin_lat, origin_lon, resolution)
        dest_hex = h3.latlng_to_cell(dest_lat, dest_lon, resolution)
    except AttributeError:
        origin_hex = h3.geo_to_h3(origin_lat, origin_lon, resolution)
        dest_hex = h3.geo_to_h3(dest_lat, dest_lon, resolution)
        
    # 2. Trazar la línea recta base (corredor estricto)
    if origin_hex == dest_hex:
        base_line = [origin_hex]
    else:
        try:
            base_line = h3.grid_path_cells(origin_hex, dest_hex)
        except AttributeError:
            base_line = h3.h3_line(origin_hex, dest_hex)
            
    # 3. DILATACIÓN GEOMÉTRICA (El parche para cruzar puentes)
    expanded_corridor = set()
    
    dist_grados = math.sqrt((origin_lat - dest_lat)**2 + (origin_lon - dest_lon)**2)
    buffer_radius = max(1, min(5, int(1 + (dist_grados * 25))))
    
    for hex_id in base_line:
        try:
            # grid_disk (o k_ring en versiones viejas de h3) obtiene los vecinos a radio k
            vecinos = h3.grid_disk(hex_id, buffer_radius)
        except AttributeError:
            vecinos = h3.k_ring(hex_id, buffer_radius)
            
        expanded_corridor.update(vecinos)
        
    return list(expanded_corridor)
