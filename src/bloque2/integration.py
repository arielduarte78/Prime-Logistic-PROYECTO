"""
Integration Module - Bloque 1 ↔ Bloque 2
=========================================

Este módulo proporciona la interfaz de alto nivel para conectar:
    - Bloque 1: Topología estática (NetworkIndexer, TopologyBuilder)
    - Bloque 2: Motor estocástico (MonteCarloGenerator)

Flujo completo:
    1. Cargar datos → Bloque 1
    2. Construir topología → Bloque 1
    3. Exportar matrices base → Bloque 1
    4. Cargar manifiesto de incidentes → Bloque 2
    5. Generar escenarios estocásticos → Bloque 2
    6. Exportar paquete para Bloque 3/4 (Optimizador)

Uso típico:
    >>> pipeline = StochasticNetworkPipeline()
    >>> pipeline.load_topology_from_bloque1(indexer)
    >>> pipeline.load_incident_manifest("manifest.yaml")
    >>> scenarios = pipeline.generate_stochastic_scenarios(n=1000)
    >>> pipeline.export_for_optimizer("output/scenarios.pkl")
"""

import numpy as np
from typing import List, Dict, Any, Optional
from pathlib import Path
import pickle
import json
from datetime import datetime

from bloque2.incidents import ManifestLoader, Manifest
from bloque2.generator import (
    MonteCarloGenerator,
    NetworkSnapshot,
    Scenario,
    ScenarioAnalyzer,
    load_base_network_from_bloque1
)


# ============================================================================
# PIPELINE DE INTEGRACIÓN
# ============================================================================

class StochasticNetworkPipeline:
    """
    Pipeline de alto nivel para generar redes estocásticas.
    
    Integra Bloque 1 (topología) con Bloque 2 (incidentes) para
    producir un conjunto de escenarios listos para el optimizador.
    
    Flujo de trabajo:
        1. load_topology_from_bloque1()
        2. load_incident_manifest()
        3. generate_stochastic_scenarios()
        4. export_for_optimizer()
    """
    
    def __init__(self, seed: Optional[int] = None):
        """
        Inicializa el pipeline.
        
        Args:
            seed: Semilla para reproducibilidad
        """
        self.seed = seed
        self.base_network: Optional[NetworkSnapshot] = None
        self.manifest: Optional[Manifest] = None
        self.scenarios: Optional[List[Scenario]] = None
        self.generator: Optional[MonteCarloGenerator] = None
    
    def load_topology_from_bloque1(
        self, 
        topology_package: Dict[str, Any]
    ):
        """
        Carga la topología exportada por Bloque 1.
        
        Args:
            topology_package: Resultado de TopologyBuilder.export_matrices()
        
        Ejemplo:
            >>> from src.bloque1.network import NetworkIndexer
            >>> from src.bloque1.topology import TopologyBuilder
            >>> idx = NetworkIndexer()
            >>> # ... registrar nodos y arcos ...
            >>> tb = TopologyBuilder(idx)
            >>> tb.build_topology()
            >>> package = tb.export_matrices()
            >>> pipeline.load_topology_from_bloque1(package)
        """
        self.base_network = load_base_network_from_bloque1(topology_package)
        print(f"✓ Topología cargada: {self.base_network.n_nodes} nodos")
    
    def load_incident_manifest(self, manifest_path: str):
        """
        Carga el manifiesto de incidentes.
        
        Args:
            manifest_path: Ruta al archivo manifest.yaml
        """
        self.manifest = ManifestLoader.load(manifest_path)
        print(f"✓ Manifiesto cargado: {len(self.manifest.incidents)} eventos")
    
    def generate_stochastic_scenarios(
        self, 
        n_scenarios: int,
        verbose: bool = True
    ) -> List[Scenario]:
        """
        Genera N escenarios estocásticos.
        
        Args:
            n_scenarios: Número de escenarios a generar
            verbose: Si True, muestra progreso
            
        Returns:
            Lista de escenarios generados
            
        Raises:
            RuntimeError: Si no se ha cargado topología o manifiesto
        """
        if self.base_network is None:
            raise RuntimeError("Debe cargar topología primero (load_topology_from_bloque1)")
        
        if self.manifest is None:
            raise RuntimeError("Debe cargar manifiesto primero (load_incident_manifest)")
        
        # Crear generador
        self.generator = MonteCarloGenerator(
            self.base_network,
            self.manifest,
            seed=self.seed
        )
        
        # Generar escenarios
        if verbose:
            def progress(i, n):
                if i % max(1, n // 20) == 0 or i == n:
                    print(f"  Progreso: {i}/{n} ({i/n*100:.1f}%)", end='\r')
            
            print(f"\nGenerando {n_scenarios} escenarios...")
            self.scenarios = self.generator.generate_scenarios(
                n_scenarios, 
                progress_callback=progress
            )
            print()  # Nueva línea después del progreso
        else:
            self.scenarios = self.generator.generate_scenarios(n_scenarios)
        
        if verbose:
            print(f"✓ {len(self.scenarios)} escenarios generados")
        
        return self.scenarios
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Retorna estadísticas de los escenarios generados.
        
        Returns:
            Diccionario con estadísticas agregadas
        """
        if self.scenarios is None:
            raise RuntimeError("Debe generar escenarios primero")
        
        return ScenarioAnalyzer.compute_statistics(self.scenarios)
    
    def export_for_optimizer(
        self, 
        output_path: str,
        format: str = "pickle"
    ):
        """
        Exporta los escenarios en formato listo para el optimizador.
        
        Args:
            output_path: Ruta del archivo de salida
            format: Formato de exportación ("pickle" o "json")
        """
        if self.scenarios is None:
            raise RuntimeError("Debe generar escenarios primero")
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if format == "pickle":
            self._export_pickle(output_path)
        elif format == "json":
            self._export_json(output_path)
        else:
            raise ValueError(f"Formato no soportado: {format}")
        
        print(f"✓ Escenarios exportados a: {output_path}")
    
    def _export_pickle(self, path: Path):
        """Exporta en formato pickle (binario)."""
        package = {
            'base_network': self.base_network,
            'scenarios': self.scenarios,
            'manifest_meta': self.manifest.meta,
            'global_parameters': {
                'alpha': self.manifest.global_parameters.alpha,
                'beta': self.manifest.global_parameters.beta,
                'gamma': self.manifest.global_parameters.gamma
            },
            'statistics': self.get_statistics(),
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'n_scenarios': len(self.scenarios),
                'seed': self.seed
            }
        }
        
        with open(path, 'wb') as f:
            pickle.dump(package, f, protocol=pickle.HIGHEST_PROTOCOL)
    
    def _export_json(self, path: Path):
        """Exporta en formato JSON (legible)."""
        # JSON no puede serializar numpy arrays directamente,
        # así que exportamos solo metadatos
        package = {
            'statistics': self.get_statistics(),
            'scenarios': [
                {
                    'scenario_id': s.scenario_id,
                    'n_events': s.total_events,
                    'has_cascades': s.has_cascades,
                    'events': [
                        {
                            'code': e.code,
                            'level': e.level,
                            'amplification': e.amplification
                        }
                        for e in s.events
                    ]
                }
                for s in self.scenarios
            ],
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'n_scenarios': len(self.scenarios),
                'seed': self.seed,
                'n_nodes': self.base_network.n_nodes
            }
        }
        
        with open(path, 'w') as f:
            json.dump(package, f, indent=2)
    
    def generate_report(self, output_path: Optional[str] = None) -> str:
        """
        Genera un reporte legible de los escenarios.
        
        Args:
            output_path: Ruta opcional para guardar el reporte
            
        Returns:
            Texto del reporte
        """
        if self.scenarios is None:
            raise RuntimeError("Debe generar escenarios primero")
        
        stats = self.get_statistics()
        
        report = []
        report.append("="*80)
        report.append("REPORTE DE ESCENARIOS ESTOCÁSTICOS")
        report.append("="*80)
        report.append(f"\nGenerado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Semilla: {self.seed}")
        report.append("\nRed Base:")
        report.append(f"  - Nodos: {self.base_network.n_nodes}")
        report.append(f"  - Arcos activos: {np.sum(self.base_network.A)}")
        
        report.append(f"\nEscenarios Generados: {stats['n_scenarios']}")
        report.append(f"  - Con eventos: {stats['scenarios_with_events']} "
                     f"({stats['scenarios_with_events']/stats['n_scenarios']*100:.1f}%)")
        report.append(f"  - Con cascadas: {stats['cascade_count']} "
                     f"({stats['cascade_count']/stats['n_scenarios']*100:.1f}%)")
        
        report.append("\nImpacto Promedio:")
        report.append(f"  - Pérdida de capacidad: {stats['avg_capacity_loss']*100:.2f}%")
        report.append(f"  - Retención de capacidad: {stats['avg_capacity_retention']*100:.2f}%")
        
        report.append("\nTop 5 Eventos Más Frecuentes:")
        sorted_events = sorted(
            stats['event_frequencies'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        for i, (code, freq) in enumerate(sorted_events, 1):
            incident = self.manifest.get_incident(code)
            prob_observed = freq / stats['n_scenarios']
            report.append(f"  {i}. {code}")
            report.append(f"     Nivel: {incident.level.value}")
            report.append(f"     P_base: {incident.p_base:.4f}")
            report.append(f"     P_observada: {prob_observed:.4f}")
            report.append(f"     Ocurrencias: {freq}")
        
        # Análisis de cascadas
        if stats['cascade_count'] > 0:
            report.append("\nAnálisis de Cascadas:")
            cascade_scenarios = [s for s in self.scenarios if s.has_cascades]
            
            # Encontrar la cascada más grande
            max_amp = 0
            max_event = None
            for s in cascade_scenarios:
                for e in s.events:
                    if e.amplification > max_amp:
                        max_amp = e.amplification
                        max_event = e
            
            if max_event:
                report.append(f"  - Amplificación máxima observada: {max_amp:.2f}x")
                report.append(f"    Evento: {max_event.code}")
        
        # Casos extremos
        worst = ScenarioAnalyzer.get_worst_case_scenario(self.scenarios)
        best = ScenarioAnalyzer.get_best_case_scenario(self.scenarios)
        
        report.append("\nCasos Extremos:")
        report.append(f"  Peor caso (Escenario #{worst.scenario_id}):")
        report.append(f"    - Eventos: {worst.total_events}")
        report.append(f"    - Capacidad retenida: {worst.get_capacity_reduction()*100:.1f}%")
        
        report.append(f"  Mejor caso (Escenario #{best.scenario_id}):")
        report.append(f"    - Eventos: {best.total_events}")
        report.append(f"    - Capacidad retenida: {best.get_capacity_reduction()*100:.1f}%")
        
        report.append("\n" + "="*80)
        
        report_text = "\n".join(report)
        
        if output_path:
            Path(output_path).write_text(report_text)
            print(f"✓ Reporte guardado en: {output_path}")
        
        return report_text


# ============================================================================
# UTILIDADES DE ANÁLISIS
# ============================================================================

def compare_scenarios(
    scenario_a: Scenario,
    scenario_b: Scenario,
    metric: str = "capacity"
) -> Dict[str, Any]:
    """
    Compara dos escenarios según una métrica.
    
    Args:
        scenario_a, scenario_b: Escenarios a comparar
        metric: Métrica de comparación ("capacity", "cost", "time")
        
    Returns:
        Diccionario con resultados de comparación
    """
    if metric == "capacity":
        cap_a = scenario_a.get_capacity_reduction()
        cap_b = scenario_b.get_capacity_reduction()
        
        return {
            'metric': 'capacity_retention',
            'scenario_a': cap_a,
            'scenario_b': cap_b,
            'difference': cap_a - cap_b,
            'better': 'A' if cap_a > cap_b else 'B' if cap_b > cap_a else 'Equal'
        }
    
    elif metric == "cost":
        cost_a = np.sum(scenario_a.network.C[np.isfinite(scenario_a.network.C)])
        cost_b = np.sum(scenario_b.network.C[np.isfinite(scenario_b.network.C)])
        
        return {
            'metric': 'total_cost',
            'scenario_a': cost_a,
            'scenario_b': cost_b,
            'difference': cost_a - cost_b,
            'better': 'A' if cost_a < cost_b else 'B' if cost_b < cost_a else 'Equal'
        }
    
    else:
        raise ValueError(f"Métrica no soportada: {metric}")


def find_critical_events(
    scenarios: List[Scenario],
    threshold: float = 0.8
) -> Dict[str, float]:
    """
    Identifica eventos críticos que causan más del threshold% de pérdida.
    
    Args:
        scenarios: Lista de escenarios
        threshold: Umbral de capacidad retenida
        
    Returns:
        Diccionario {evento: frecuencia_en_casos_críticos}
    """
    critical_scenarios = [
        s for s in scenarios 
        if s.get_capacity_reduction() < threshold
    ]
    
    critical_events = {}
    for scenario in critical_scenarios:
        for event in scenario.events:
            critical_events[event.code] = critical_events.get(event.code, 0) + 1
    
    # Normalizar por total de escenarios críticos
    total_critical = len(critical_scenarios)
    if total_critical > 0:
        critical_events = {
            k: v / total_critical 
            for k, v in critical_events.items()
        }
    
    return critical_events


# ============================================================================
# EJEMPLO DE USO COMPLETO (INTEGRACIÓN)
# ============================================================================

if __name__ == "__main__":
    print("="*80)
    print("INTEGRACIÓN COMPLETA: BLOQUE 1 ↔ BLOQUE 2")
    print("="*80)
    
    # ========================================================================
    # SIMULACIÓN DE BLOQUE 1 (normalmente vendría de tu código real)
    # ========================================================================
    
    print("\n[BLOQUE 1] Construyendo topología base...")
    
    # Crear red sintética (esto vendría de tu NetworkIndexer real)
    n_nodes = 10
    nodes = [f"NODE_{i:03d}" for i in range(n_nodes)]
    
    # Topología de grafo conectado
    A = np.zeros((n_nodes, n_nodes), dtype=bool)
    for i in range(n_nodes - 1):
        A[i, i+1] = True
        A[i+1, i] = True
    # Agregar algunos arcos adicionales
    A[0, 5] = A[5, 0] = True
    A[2, 7] = A[7, 2] = True
    
    # Costos proporcionales a distancia
    C = np.full((n_nodes, n_nodes), np.inf)
    C[A] = np.random.uniform(100, 300, np.sum(A))
    
    # Tiempos
    T = np.full((n_nodes, n_nodes), np.inf)
    T[A] = C[A] / 80  # Asumiendo velocidad promedio de 80 $/h
    
    # Capacidades
    K = np.zeros((n_nodes, n_nodes))
    K[A] = np.random.uniform(500, 2000, np.sum(A))
    
    # Balance de nodos (demanda - supply)
    D = np.random.uniform(-100, 100, n_nodes)
    
    # Paquete simulado del Bloque 1
    topology_package = {
        'A': A,
        'C': C,
        'T': T,
        'K': K,
        'D': D,
        'nodes': nodes,
        'meta': {
            'source': 'synthetic_test',
            'generated': datetime.now().isoformat()
        }
    }
    
    print(f"  ✓ Red con {n_nodes} nodos y {np.sum(A)} arcos")
    
    # ========================================================================
    # BLOQUE 2: GENERAR ESCENARIOS ESTOCÁSTICOS
    # ========================================================================
    
    print("\n[BLOQUE 2] Generando escenarios estocásticos...")
    
    # Crear pipeline
    pipeline = StochasticNetworkPipeline(seed=42)
    
    # Cargar topología del Bloque 1
    pipeline.load_topology_from_bloque1(topology_package)
    
    # Cargar manifiesto de incidentes
    pipeline.load_incident_manifest("manifest.yaml")
    
    # Generar 500 escenarios
    scenarios = pipeline.generate_stochastic_scenarios(n_scenarios=500, verbose=True)
    
    # ========================================================================
    # ANÁLISIS
    # ========================================================================
    
    print("\n[ANÁLISIS] Procesando resultados...")
    
    # Estadísticas generales
    stats = pipeline.get_statistics()
    print(f"\n  Escenarios con eventos: {stats['scenarios_with_events']}")
    print(f"  Pérdida promedio de capacidad: {stats['avg_capacity_loss']*100:.2f}%")
    
    # Eventos críticos
    critical = find_critical_events(scenarios, threshold=0.7)
    if critical:
        print("\n  Eventos más frecuentes en casos críticos (>30% pérdida):")
        for event, freq in sorted(critical.items(), key=lambda x: x[1], reverse=True)[:3]:
            print(f"    - {event}: {freq*100:.1f}%")
    
    # ========================================================================
    # EXPORTACIÓN
    # ========================================================================
    
    print("\n[EXPORTACIÓN] Guardando resultados...")
    
    # Generar reporte
    report = pipeline.generate_report("stochastic_report.txt")
    
    # Exportar escenarios para optimizador
    pipeline.export_for_optimizer("scenarios.pkl", format="pickle")
    pipeline.export_for_optimizer("scenarios_meta.json", format="json")
    
    print("\n" + "="*80)
    print("✓ INTEGRACIÓN COMPLETADA")
    print("="*80)
    print("\nArchivos generados:")
    print("  - stochastic_report.txt : Reporte legible")
    print("  - scenarios.pkl         : Escenarios completos (binario)")
    print("  - scenarios_meta.json   : Metadatos (JSON)")
