#H3_router.py
import h3

def build_h3_corridor(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float, resolution: int = 8, k_buffer: int = 2) -> list[str]:
    """
    Calculates an H3 spatial corridor between an origin and a destination,
    incorporating a buffer zone to guarantee edge coverage.
    """
    # 1. Convert origin and destination coordinates to H3 cells
    try:
        # Standard API for h3-py >= 4.0
        origin_hex = h3.latlng_to_cell(origin_lat, origin_lon, resolution)
        dest_hex = h3.latlng_to_cell(dest_lat, dest_lon, resolution)
    except AttributeError:
        # Fallback API for h3-py <= 3.7.x
        origin_hex = h3.geo_to_h3(origin_lat, origin_lon, resolution)
        dest_hex = h3.geo_to_h3(dest_lat, dest_lon, resolution)
        
    # 2. Draw line between hexes
    if origin_hex == dest_hex:
        # Edge case: Origin and destination are inside the exact same Hexagon
        line_hexes = [origin_hex]
    else:
        try:
            # Standard API for h3-py >= 4.0
            line_hexes = h3.grid_path_cells(origin_hex, dest_hex)
        except AttributeError:
            # Fallback API for h3-py <= 3.7.x
            line_hexes = h3.h3_line(origin_hex, dest_hex)
            
    # 3. Expand each cell to create the corridor buffer (k rings)
    corridor_cells = set()
    for hex_cell in line_hexes:
        try:
            # Standard API for h3-py >= 4.0
            buffer_cells = h3.grid_disk(hex_cell, k_buffer)
        except AttributeError:
            # Fallback API for h3-py <= 3.7.x
            buffer_cells = h3.k_ring(hex_cell, k_buffer)
            
        corridor_cells.update(buffer_cells)
        
    # Return a unique list of hexagons (as strings)
    return list(corridor_cells)
