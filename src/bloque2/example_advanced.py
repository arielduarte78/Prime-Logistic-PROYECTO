"""
Ejemplo Avanzado: Análisis de Escenarios de Riesgo
===================================================

Demuestra casos de uso realistas del motor estocástico para:
1. Análisis de sensibilidad a parámetros globales
2. Simulación de cascadas de eventos
3. Cálculo de impactos agregados
4. Generación de reportes de riesgo
"""

from bloque2.incidents import ManifestLoader, Category, IncidentDefinition
from typing import List, Dict, Any, Optional
import random


class RiskAnalyzer:
    """Analizador de riesgo logístico basado en el manifiesto."""
    
    def __init__(self, manifest_path: str = "manifest.yaml") -> None:
        """Inicializa el analizador cargando el manifiesto."""
        self.manifest = ManifestLoader.load(manifest_path)
        self.global_params: Dict[str, float] = {
            'alpha': self.manifest.global_parameters.alpha,
            'beta': self.manifest.global_parameters.beta,
            'gamma': self.manifest.global_parameters.gamma
        }
    
    def simulate_single_day(self, seed: Optional[int] = None) -> Dict[str, Any]:
        """
        Simula un día individual con eventos estocásticos.
        
        Args:
            seed: Semilla para reproducibilidad
            
        Returns:
            Diccionario con eventos ocurridos y sus efectos
        """
        if seed is not None:
            random.seed(seed)
        
        active_events: List[Dict[str, Any]] = []
        effects: Dict[str, Any] = {
            'capacity_reduction': 1.0,
            'demand_increase': 1.0,
            'disabled_connections': 0,
            'affected_nodes': [],
            'affected_arcs': []
        }
        
        # Procesar eventos en orden topológico (SYSTEMIC → TACTICAL → MICRO)
        for level in [Category.SYSTEMIC, Category.TACTICAL, Category.MICRO]:
            incidents = self.manifest.get_incidents_by_level(level)
            
            for incident in incidents:
                # Calcular probabilidad efectiva con cascada
                p_eff: float = incident.effective_probability(
                    [evt['code'] for evt in active_events]
                )
                
                # Lanzar dado
                if random.random() < p_eff:
                    # Evento ocurre
                    event_data: Dict[str, Any] = {
                        'code': incident.code,
                        'level': incident.level.value,
                        'p_base': incident.p_base,
                        'p_effective': p_eff,
                        'amplification': p_eff / incident.p_base if incident.p_base > 0 else 1.0
                    }
                    active_events.append(event_data)
                    
                    # Aplicar efectos estructurales
                    cap_val: float = effects['capacity_reduction']
                    effects['capacity_reduction'] = cap_val * incident.structural_effects.capacity.modifier
                    
                    dem_val: float = effects['demand_increase']
                    effects['demand_increase'] = dem_val * incident.structural_effects.demand.modifier
                    
                    if incident.structural_effects.adjacency.action.value == 'DISABLE':
                        dis_val: int = effects['disabled_connections']
                        effects['disabled_connections'] = dis_val + 1
                    
                    # Registrar elementos afectados
                    if incident.target.type.value in ['NODE', 'ZONE']:
                        node_list: List[str] = effects['affected_nodes']
                        node_list.append(incident.target.selector)
                    elif incident.target.type.value == 'ARC':
                        arc_list: List[str] = effects['affected_arcs']
                        arc_list.append(incident.target.selector)
        
        return {
            'events': active_events,
            'effects': effects,
            'total_events': len(active_events)
        }
    
    def monte_carlo_analysis(self, n_scenarios: int = 1000, seed: int = 42) -> Dict[str, Any]:
        """
        Ejecuta análisis Monte Carlo de N escenarios.
        
        Args:
            n_scenarios: Número de escenarios a simular
            seed: Semilla inicial
            
        Returns:
            Estadísticas agregadas de los escenarios
        """
        random.seed(seed)
        
        event_frequencies: Dict[str, int] = {}
        cascade_activations: int = 0
        capacity_reductions: List[float] = []
        demand_increases: List[float] = []
        scenarios_with_events: int = 0
        
        # Inicializar contadores de frecuencia
        for incident in self.manifest.incidents:
            event_frequencies[incident.code] = 0
        
        # Ejecutar simulaciones
        for i in range(n_scenarios):
            scenario: Dict[str, Any] = self.simulate_single_day(seed=seed + i)
            
            if scenario['total_events'] > 0:
                scenarios_with_events += 1
            
            # Contar eventos
            for event in scenario['events']:
                event_frequencies[event['code']] += 1
                
                # Detectar cascadas (amplificación > 1)
                if event['amplification'] > 1.1:
                    cascade_activations += 1
            
            # Acumular efectos
            capacity_reductions.append(scenario['effects']['capacity_reduction'])
            demand_increases.append(scenario['effects']['demand_increase'])
        
        # Calcular estadísticas
        event_probabilities: Dict[str, float] = {
            code: freq / n_scenarios 
            for code, freq in event_frequencies.items()
        }
        
        avg_capacity_reduction: float = sum(capacity_reductions) / n_scenarios
        avg_demand_increase: float = sum(demand_increases) / n_scenarios
        cascade_rate: float = cascade_activations / max(1, scenarios_with_events)
        
        results: Dict[str, Any] = {
            'event_frequencies': event_frequencies,
            'cascade_activations': cascade_activations,
            'capacity_reductions': capacity_reductions,
            'demand_increases': demand_increases,
            'scenarios_with_events': scenarios_with_events,
            'event_probabilities': event_probabilities,
            'avg_capacity_reduction': avg_capacity_reduction,
            'avg_demand_increase': avg_demand_increase,
            'cascade_rate': cascade_rate,
        }
        
        return results
    
    def sensitivity_analysis(self, parameter: str, values: List[float]) -> Dict[float, Dict[str, float]]:
        """
        Analiza sensibilidad de impactos a parámetros globales.
        
        Args:
            parameter: Nombre del parámetro (alpha, beta, gamma)
            values: Lista de valores a probar
            
        Returns:
            Resultados de sensibilidad
        """
        original_value: float = self.global_params[parameter]
        sensitivity: Dict[float, Dict[str, float]] = {}
        
        for val in values:
            # Modificar parámetro temporalmente
            self.global_params[parameter] = val
            
            # Calcular impactos promedio
            total_impact_c: float = 0.0
            total_impact_t: float = 0.0
            count: int = 0
            
            for incident in self.manifest.incidents:
                impact_c: float = incident.get_impact_multiplier('C', 0.5, self.global_params)
                impact_t: float = incident.get_impact_multiplier('T', 0.5, self.global_params)
                
                if impact_c > 1.0:
                    total_impact_c += impact_c
                    count += 1
                if impact_t > 1.0:
                    total_impact_t += impact_t
            
            sensitivity[val] = {
                'avg_impact_c': total_impact_c / count if count > 0 else 1.0,
                'avg_impact_t': total_impact_t / len(self.manifest.incidents)
            }
        
        # Restaurar valor original
        self.global_params[parameter] = original_value
        
        return sensitivity
    
    def generate_risk_report(self, n_scenarios: int = 1000) -> str:
        """
        Genera reporte de riesgo legible.
        
        Args:
            n_scenarios: Número de escenarios para Monte Carlo
            
        Returns:
            Reporte en formato texto
        """
        mc_results: Dict[str, Any] = self.monte_carlo_analysis(n_scenarios)
        
        report: List[str] = []
        report.append("=" * 80)
        report.append("REPORTE DE ANÁLISIS DE RIESGO LOGÍSTICO")
        report.append("=" * 80)
        report.append(f"\nSimulación Monte Carlo: {n_scenarios:,} escenarios")
        report.append(f"Escenarios con al menos un evento: {mc_results['scenarios_with_events']:,} "
                     f"({mc_results['scenarios_with_events']/n_scenarios*100:.1f}%)")
        
        # Top 5 eventos más frecuentes
        report.append("\n" + "-" * 80)
        report.append("TOP 5 EVENTOS MÁS FRECUENTES")
        report.append("-" * 80)
        
        sorted_events = sorted(
            mc_results['event_probabilities'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        for i, (code, prob) in enumerate(sorted_events, 1):
            incident: Optional[IncidentDefinition] = self.manifest.get_incident(code)
            if incident is None:
                continue
            report.append(f"{i}. {code}")
            report.append(f"   Nivel: {incident.level.value}")
            report.append(f"   P_base: {incident.p_base:.4f}")
            report.append(f"   P_observada: {prob:.4f}")
            report.append(f"   Frecuencia: {mc_results['event_frequencies'][code]} ocurrencias")
            report.append("")
        
        # Impacto promedio
        report.append("-" * 80)
        report.append("IMPACTOS PROMEDIO EN LA RED")
        report.append("-" * 80)
        report.append(f"Reducción de capacidad: {(1 - mc_results['avg_capacity_reduction']) * 100:.2f}%")
        report.append(f"Aumento de demanda: {(mc_results['avg_demand_increase'] - 1) * 100:.2f}%")
        report.append(f"Tasa de cascadas: {mc_results['cascade_rate']:.2f} cascadas/escenario con eventos")
        
        # Eventos con condicionadores activos
        report.append("\n" + "-" * 80)
        report.append("DEPENDENCIAS DE CASCADA")
        report.append("-" * 80)
        
        for incident_item in self.manifest.incidents:
            if incident_item.conditioners:
                report.append(f"\n{incident_item.code}:")
                for cond in incident_item.conditioners:
                    report.append(f"  → Amplifica {cond.multiplier:.1f}x cuando ocurre {cond.event}")
        
        report.append("\n" + "=" * 80)
        
        return "\n".join(report)


def example_1_basic_simulation() -> None:
    """Ejemplo 1: Simulación básica de un día."""
    print("\n" + "="*80)
    print("EJEMPLO 1: Simulación de un Día Individual")
    print("="*80)
    
    analyzer = RiskAnalyzer()
    
    # Simular 3 días diferentes
    for day in range(1, 4):
        print(f"\n--- Día {day} ---")
        scenario: Dict[str, Any] = analyzer.simulate_single_day(seed=day)
        
        if scenario['total_events'] == 0:
            print("Sin eventos disruptivos")
        else:
            print(f"Eventos ocurridos: {scenario['total_events']}")
            for event in scenario['events']:
                amp_str = f" (x{event['amplification']:.1f})" if event['amplification'] > 1.1 else ""
                print(f"  - {event['code']}: P_eff={event['p_effective']:.4f}{amp_str}")
            
            effects: Dict[str, Any] = scenario['effects']
            print("\nEfectos agregados:")
            print(f"  Capacidad residual: {effects['capacity_reduction'] * 100:.1f}%")
            print(f"  Demanda ajustada: {effects['demand_increase'] * 100:.1f}%")


def example_2_monte_carlo() -> None:
    """Ejemplo 2: Análisis Monte Carlo."""
    print("\n" + "="*80)
    print("EJEMPLO 2: Análisis Monte Carlo (1000 escenarios)")
    print("="*80)
    
    analyzer = RiskAnalyzer()
    results: Dict[str, Any] = analyzer.monte_carlo_analysis(n_scenarios=1000)
    
    print(f"\nEscenarios con eventos: {results['scenarios_with_events']}/1000")
    print(f"Tasa de cascadas: {results['cascade_rate']:.2f}")
    
    # Top 3 eventos
    print("\nTop 3 eventos más frecuentes:")
    sorted_events = sorted(
        results['event_probabilities'].items(),
        key=lambda x: x[1],
        reverse=True
    )[:3]
    
    for code, prob in sorted_events:
        inc: Optional[IncidentDefinition] = analyzer.manifest.get_incident(code)
        if inc is not None:
            print(f"  {code}: {prob:.4f} (esperado: {inc.p_base:.4f})")


def example_3_sensitivity() -> None:
    """Ejemplo 3: Análisis de sensibilidad."""
    print("\n" + "="*80)
    print("EJEMPLO 3: Análisis de Sensibilidad a Parámetro γ (gamma)")
    print("="*80)
    
    analyzer = RiskAnalyzer()
    
    # Probar diferentes valores de gamma
    gamma_values: List[float] = [0.1, 0.25, 0.5, 1.0]
    sensitivity: Dict[float, Dict[str, float]] = analyzer.sensitivity_analysis('gamma', gamma_values)
    
    print("\nImpacto de γ en multiplicadores de tiempo:")
    for gamma, impacts in sensitivity.items():
        print(f"  γ={gamma:.2f}: Impacto promedio en T = {impacts['avg_impact_t']:.3f}")


def example_4_risk_report() -> None:
    """Ejemplo 4: Reporte completo de riesgo."""
    print("\n" + "="*80)
    print("EJEMPLO 4: Reporte de Riesgo Completo")
    print("="*80)
    
    analyzer = RiskAnalyzer()
    report: str = analyzer.generate_risk_report(n_scenarios=1000)
    print(report)


def main() -> None:
    """Ejecuta todos los ejemplos."""
    print("="*80)
    print("EJEMPLOS AVANZADOS: MOTOR ESTOCÁSTICO")
    print("="*80)
    
    example_1_basic_simulation()
    example_2_monte_carlo()
    example_3_sensitivity()
    example_4_risk_report()
    
    print("\n" + "="*80)
    print("✓ EJEMPLOS COMPLETADOS")
    print("="*80)


if __name__ == "__main__":
    main()
