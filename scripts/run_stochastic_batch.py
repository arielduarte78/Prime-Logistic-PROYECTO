#scripts/run_stochastic_batch.py
"""
run_stochastic_batch.py
========================
Standalone batch script — NO FastAPI imports.
Runs Monte Carlo simulation from Bloque 2 and compiles degraded Bayesian
priors into data/parquet_db/stochastic_priors.parquet.

Usage:
    python scripts/run_stochastic_batch.py
"""
import sys
import os
import shutil
import time
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import scipy.sparse as sp

# ---------------------------------------------------------------------------
# Path Setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "parquet_db"
EDGES_PATH = DATA_DIR / "edges.parquet"
PRIORS_PATH = DATA_DIR / "stochastic_priors.parquet"
BACKUP_PATH = DATA_DIR / "stochastic_priors_backup.parquet"
MANIFEST_PATH = PROJECT_ROOT / "src" / "bloque2" / "manifest.yaml"

# Allow imports from project root
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bloque2.incidents import ManifestLoader
from bloque2.generator import (
    MonteCarloGenerator,
    MonteCarloEngine,
    NetworkSnapshot,
    ScenarioAnalyzer,
    load_base_network_from_bloque1,
)
from bloque2.integration import StochasticNetworkPipeline


def main() -> None:
    from src.block5.lambda_scalarizer import clear_cost_cache
    clear_cost_cache()

    from src.block5.cost_matrix_builder import clear_time_weight_cache
    clear_time_weight_cache()

    t0 = time.time()
    print("=" * 70)
    print("PRIME LOGISTICS — Stochastic Batch Compiler")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 1. Backup obligatorio
    # ------------------------------------------------------------------
    if PRIORS_PATH.exists():
        try:
            shutil.copy2(str(PRIORS_PATH), str(BACKUP_PATH))
            print(f"[OK] Backup guardado: {BACKUP_PATH.name}")
        except Exception as exc:
            print(f"[ERROR] Error al crear backup: {exc}")
            sys.exit(1)
    else:
        print("· stochastic_priors.parquet no existía previamente — sin backup.")

    # ------------------------------------------------------------------
    # 2. Cargar edges.parquet y construir matrices sparse
    # ------------------------------------------------------------------
    print("\n[1/5] Cargando edges.parquet...")
    df_edges = pd.read_parquet(str(EDGES_PATH))
    print(f"  → {len(df_edges):,} aristas leídas.")

    # Mapeo OSM → índice entero consecutivo
    all_osm_ids = pd.unique(df_edges[["u", "v"]].values.ravel())
    osm_to_idx = {int(osm_id): idx for idx, osm_id in enumerate(all_osm_ids)}
    n_nodes = len(osm_to_idx)
    nodes_list = [str(osm_id) for osm_id in all_osm_ids]

    rows = df_edges["u"].map(osm_to_idx).values
    cols = df_edges["v"].map(osm_to_idx).values

    # A — Adyacencia binaria
    A = sp.coo_matrix(
        (np.ones(len(df_edges), dtype=np.float64), (rows, cols)),
        shape=(n_nodes, n_nodes),
    ).tocsr()

    # C — Costos (length como proxy)
    lengths = df_edges["length"].fillna(100.0).values.astype(np.float64)
    C = sp.coo_matrix((lengths, (rows, cols)), shape=(n_nodes, n_nodes)).tocsr()

    # T — Tiempos (length / 60 km/h → horas, escalado a minutos)
    T = sp.coo_matrix(
        (lengths / 1000.0 / 60.0 * 60.0, (rows, cols)),
        shape=(n_nodes, n_nodes),
    ).tocsr()

    # K — Capacidad (constante 1000 por arista activa)
    K = sp.coo_matrix(
        (np.full(len(df_edges), 1000.0), (rows, cols)),
        shape=(n_nodes, n_nodes),
    ).tocsr()

    # D — Vector de demanda (cero para escenario de stress)
    D = np.zeros(n_nodes)

    topology_package = {
        "A": A,
        "C": C,
        "T": T,
        "K": K,
        "D": D,
        "nodes": nodes_list,
        "meta": {"source": "edges.parquet", "n_edges": len(df_edges)},
    }
    print(f"  → Matrices sparse construidas: {n_nodes:,} nodos.")

    # ------------------------------------------------------------------
    # 3. Cargar manifiesto
    # ------------------------------------------------------------------
    print("[2/5] Cargando manifiesto de incidentes...")
    manifest = ManifestLoader.load(str(MANIFEST_PATH))
    print(f"  → {len(manifest.incidents)} eventos cargados.")

    # ------------------------------------------------------------------
    # 4. Definir afinidades zonales y mapeo de eventos
    # ------------------------------------------------------------------
    import h3
    print("[3/5] Calculando zonas H3 res-4 y mapeo de eventos...")
    h3_func = getattr(h3, 'cell_to_parent', getattr(h3, 'h3_to_parent', None))
    df_edges['h3_res4'] = df_edges['h3_index_origin'].apply(
        lambda x: h3_func(x, 4) if pd.notna(x) else None
    )
    
    pipeline = StochasticNetworkPipeline(seed=42)
    pipeline.load_topology_from_bloque1(topology_package)
    pipeline.manifest = manifest
    pipeline.generator = MonteCarloGenerator(pipeline.base_network, manifest, seed=42)
    engine = MonteCarloEngine(pipeline.generator)
    
    systemic_codes = [e.code for e in manifest.incidents if e.level.name == 'SYSTEMIC']
    micro_codes = [e.code for e in manifest.incidents if e.level.name == 'MICRO']
    
    tactical_map = {
        'CORTE_ACCESO_NORTE': ['84c2e3bffffffff'],
        'CORTE_ACCESO_OESTE': ['84c2e3bffffffff', '84c2e31ffffffff'],
        'CORTE_ACCESO_SUR': ['84c2e3dffffffff', '84c2e33ffffffff'],
        'HUELGA_TRANSPORTE_ZONA': list(df_edges['h3_res4'].dropna().unique())
    }
    
    zone_event_map = {}
    for z in df_edges['h3_res4'].dropna().unique():
        valid = systemic_codes + micro_codes
        for tac_code, tac_zones in tactical_map.items():
            if z in tac_zones or tac_code == 'HUELGA_TRANSPORTE_ZONA':
                valid.append(tac_code)
        zone_event_map[z] = list(set(valid))

    # ------------------------------------------------------------------
    # 5. Ejecutar Monte Carlo Zonal (Escalar)
    # ------------------------------------------------------------------
    print("[4/5] Ejecutando simulación Monte Carlo por Zonas H3...")
    zone_stress = engine.run_by_zone(zone_event_map, e_limit=0.001, window=100, max_iter=5000)
    
    avg_stress = float(np.mean(list(zone_stress.values())))
    print("  → stress por zona:")
    for z, z_stress in sorted(zone_stress.items(), key=lambda x: str(x[0])):
        print(f"    {z}: ~{z_stress:.4f}")
    print(f"  → avg_stress global = {avg_stress:.6f}")

    # ------------------------------------------------------------------
    # 6. Compilar stochastic_priors.parquet
    # ------------------------------------------------------------------
    print("[5/5] Compilando stochastic_priors.parquet...")

    u_osm_col = df_edges["u"].values.astype(np.int64)
    v_osm_col = df_edges["v"].values.astype(np.int64)
    alpha_col = df_edges["alpha_prior"].values.astype(np.float32)
    beta_col = df_edges["beta_prior"].values.astype(np.float32)

    stress_col = df_edges['h3_res4'].map(zone_stress).fillna(avg_stress).values.astype(np.float32)

    alpha_degraded = alpha_col * (1.0 - stress_col * 0.5)
    beta_degraded = beta_col * (1.0 + stress_col * 0.5)

    df_priors = pd.DataFrame(
        {
            "u_osm": u_osm_col,
            "v_osm": v_osm_col,
            "alpha_degraded": alpha_degraded.astype(np.float32),
            "beta_degraded": beta_degraded.astype(np.float32),
        }
    )
    df_priors.to_parquet(str(PRIORS_PATH), index=False)

    elapsed = time.time() - t0

    # ------------------------------------------------------------------
    # Reporte final
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("REPORTE STOCHASTIC BATCH")
    print("=" * 70)
    print(f"  Total aristas procesadas : {len(df_priors):,}")
    print(f"  avg_stress               : {avg_stress:.6f}")
    print(f"  Escenarios simulados     : {len(scenarios)}")
    print(f"  Archivo generado         : {PRIORS_PATH}")
    print(f"  Timestamp                : {datetime.now().isoformat()}")
    print(f"  Tiempo total             : {elapsed:.2f}s")
    print("=" * 70)


if __name__ == "__main__":
    main()
