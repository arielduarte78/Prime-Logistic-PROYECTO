import sys
from pathlib import Path
import time

# Incorporar src al PYTHONPATH temporalmente para garantizar que reconozca los módulos
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bloque1.models import NodeRecord
from bloque1.fleet_schema import FleetVehicle
from bloque1.discovery_engine import DiscoveryEngine
from bloque1.smart_ingestor import SmartLazyIngestor
from bloque1.cache_manager import SafeCacheManager
from bloque1.config import H3RouterConfig

def main():
    print("="*60)
    print(" SMOKE TEST: Prime-Logistic V1.3.5 Discovery Engine")
    print("="*60)
    
    # 1. Instanciación Manual de Nodos (Memoria puro, sin Excel)
    print("\n[+] Instanciando Nodos (Sin I/O)...")
    n1 = NodeRecord(id="N_OBELISCO", lat=-34.6037, lon=-58.3816, station_type="warehouse")
    n2 = NodeRecord(id="N_RETIRO",   lat=-34.5913, lon=-58.3748, station_type="factory")
    n3 = NodeRecord(id="N_MADERO",   lat=-34.6118, lon=-58.3646, station_type="factory")
    
    nodes = [n1, n2, n3]
    for n in nodes:
        print(f"  - {n.id:<12}: {n.station_type:<10} ({n.lat}, {n.lon})")
        
    # 2. Instanciación Manual de Flota
    print("\n[+] Instanciando Vehículo de Flota (Sin I/O)...")
    truck = FleetVehicle(
        mode="truck",
        capacity=20.0,
        cost_per_km=1.5,
        max_range_km=50.0,
        allowed_stations=["warehouse", "factory"]
    )
    fleet = [truck]
    print(f"  - 1 Vehículo: {truck.mode.upper()} (Rango: {truck.max_range_km}km, Costo: ${truck.cost_per_km}/km)")
    print(f"    Permitidos: {truck.allowed_stations}")

    # 3. Discovery Engine: Filtros 1 y 2
    print("\n[+] Instanciando DiscoveryEngine e iniciando Filtros 1 y 2...")
    engine = DiscoveryEngine(nodes, fleet)
    candidates, telemetry = engine.run_filters_1_2()
    
    print("\n[+] Matriz de Distancias Calculada (NumPy Broadcasting Estricto):")
    print(engine._dist_matrix)
    
    # 4. Ingestor: Filtro 3 (OSMnx con Protección Concurrent)
    print("\n[+] Instanciando SmartLazyIngestor y CacheManager...")
    cache_mgr = SafeCacheManager(cache_dir=Path(".prime_cache_smoke"))
    config = H3RouterConfig(resolution=8)  # Baja resolución para agilizar test
    ingestor = SmartLazyIngestor(config, cache_mgr)
    
    print("\n[+] Lanzando Filtro 3 (Validación Física OSMnx)...")
    final_survivors = engine.run_filter_3(
        candidates=candidates, 
        ingestor=ingestor, 
        telemetry=telemetry, 
        output_csv="smoke_discovery_audit.csv"
    )
    
    # 5. Reporte de Telemetría Final
    print("\n" + "="*60)
    print(" REPORTE FINAL DE TELEMETRÍA - SMOKE V1.3.5")
    print("="*60)
    print(f" Pares Iniciales Posibles (N×N×M) : {telemetry.total_input_pairs} pares")
    print(f" Sobrevivientes Filtro 1 (Semántica) : {telemetry.filter_1_survivors} pares")
    print(f" Sobrevivientes Filtro 2 (Haversine) : {telemetry.filter_2_survivors} pares")
    print(f" Validación Exitosa Filtro 3 (OSMnx) : {telemetry.filter_3_survivors} pares")
    
    print("\n[+] Resultados Finales: Trazado de Rutas y Costo Real Económico:")
    if not final_survivors:
        print("    [-] Ningún candidato pudo ser validado físicamente.")
    else:
        for c in final_survivors:
            costo_total = c.physical_distance_km * c.vehicle.cost_per_km
            print(f"  > {c.origin.id:<12} ---> {c.destination.id:<12} | "
                  f"Modo: {c.vehicle.mode.upper()} | "
                  f"Distancia Física: {c.physical_distance_km:>5.2f} km | "
                  f"Costo: ${costo_total:>6.2f}")
    
    print("\n✓ Smoke test completado.")

if __name__ == "__main__":
    main()
