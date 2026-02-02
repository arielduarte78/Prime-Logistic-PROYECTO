"""
Ejemplo Avanzado: Análisis de Escenarios de Riesgo
===================================================

Demuestra casos de uso realistas del motor estocástico para:
1. Análisis de sensibilidad a parámetros globales
2. Simulación de cascadas de eventos
3. Cálculo de impactos agregados
4. Generación de reportes de riesgo
"""

from incidents import ManifestLoader, Category
from typing import List, Dict
import random


class RiskAnalyzer:
    """Analizador de riesgo logístico basado en el manifiesto."""
    
    def __init__(self, manifest_path: str = "manifest.yaml"):
        """Inicializa el analizador cargando el manifiesto."""
        self.manifest = ManifestLoader.load(manifest_path)
        self.global_params = {
            'alpha': self.manifest.global_parameters.alpha,
            'beta': self.manifest.global_parameters.beta,
            'gamma': self.manifest.global_parameters.gamma
        }
    
    def simulate_single_day(self, seed: int = None) -> Dict:
        """
        Simula un día individual con eventos estocásticos.
        
        Args:
            seed: Semilla para reproducibilidad
            
        Returns:
            Diccionario con eventos ocurridos y sus efectos
        """
        if seed is not None:
            random.seed(seed)
        
        active_events = []
        effects = {
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
                p_eff = incident.effective_probability(
                    [evt['code'] for evt in active_events]
                )
                
                # Lanzar dado
                if random.random() < p_eff:
                    # Evento ocurre
                    event_data = {
                        'code': incident.code,
                        'level': incident.level.value,
                        'p_base': incident.p_base,
                        'p_effective': p_eff,
                        'amplification': p_eff / incident.p_base if incident.p_base > 0 else 1.0
                    }
                    active_events.append(event_data)
                    
                    # Aplicar efectos estructurales
                    effects['capacity_reduction'] *= incident.structural_effects.capacity.modifier
                    effects['demand_increase'] *= incident.structural_effects.demand.modifier
                    
                    if incident.structural_effects.adjacency.action.value == 'DISABLE':
                        effects['disabled_connections'] += 1
                    
                    # Registrar elementos afectados
                    if incident.target.type.value in ['NODE', 'ZONE']:
                        effects['affected_nodes'].append(incident.target.selector)
                    elif incident.target.type.value == 'ARC':
                        effects['affected_arcs'].append(incident.target.selector)
        
        return {
            'events': active_events,
            'effects': effects,
            'total_events': len(active_events)
        }
    
    def monte_carlo_analysis(self, n_scenarios: int = 1000, seed: int = 42) -> Dict:
        """
        Ejecuta análisis Monte Carlo de N escenarios.
        
        Args:
            n_scenarios: Número de escenarios a simular
            seed: Semilla inicial
            
        Returns:
            Estadísticas agregadas de los escenarios
        """
        random.seed(seed)
        
        results = {
            'event_frequencies': {},
            'cascade_activations': 0,
            'capacity_reductions': [],
            'demand_increases': [],
            'scenarios_with_events': 0
        }
        
        # Inicializar contadores de frecuencia
        for incident in self.manifest.incidents:
            results['event_frequencies'][incident.code] = 0
        
        # Ejecutar simulaciones
        for i in range(n_scenarios):
            scenario = self.simulate_single_day(seed=seed + i)
            
            if scenario['total_events'] > 0:
                results['scenarios_with_events'] += 1
            
            # Contar eventos
            for event in scenario['events']:
                results['event_frequencies'][event['code']] += 1
                
                # Detectar cascadas (amplificación > 1)
                if event['amplification'] > 1.1:
                    results['cascade_activations'] += 1
            
            # Acumular efectos
            results['capacity_reductions'].append(scenario['effects']['capacity_reduction'])
            results['demand_increases'].append(scenario['effects']['demand_increase'])
        
        # Calcular estadísticas
        results['event_probabilities'] = {
            code: freq / n_scenarios 
            for code, freq in results['event_frequencies'].items()
        }
        
        results['avg_capacity_reduction'] = sum(results['capacity_reductions']) / n_scenarios
        results['avg_demand_increase'] = sum(results['demand_increases']) / n_scenarios
        results['cascade_rate'] = results['cascade_activations'] / max(1, results['scenarios_with_events'])
        
        return results
    
    def sensitivity_analysis(self, parameter: str, values: List[float]) -> Dict:
        """
        Analiza sensibilidad de impactos a parámetros globales.
        
        Args:
            parameter: Nombre del parámetro (alpha, beta, gamma)
            values: Lista de valores a probar
            
        Returns:
            Resultados de sensibilidad
        """
        original_value = self.global_params[parameter]
        sensitivity = {}
        
        for val in values:
            # Modificar parámetro temporalmente
            self.global_params[parameter] = val
            
            # Calcular impactos promedio
            total_impact_c = 0
            total_impact_t = 0
            count = 0
            
            for incident in self.manifest.incidents:
                impact_c = incident.get_impact_multiplier('C', self.global_params)
                impact_t = incident.get_impact_multiplier('T', self.global_params)
                
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
        mc_results = self.monte_carlo_analysis(n_scenarios)
        
        report = []
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
            incident = self.manifest.get_incident(code)
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
        
        for incident in self.manifest.incidents:
            if incident.conditioners:
                report.append(f"\n{incident.code}:")
                for cond in incident.conditioners:
                    report.append(f"  → Amplifica {cond.multiplier:.1f}x cuando ocurre {cond.event}")
        
        report.append("\n" + "=" * 80)
        
        return "\n".join(report)


def example_1_basic_simulation():
    """Ejemplo 1: Simulación básica de un día."""
    print("\n" + "="*80)
    print("EJEMPLO 1: Simulación de un Día Individual")
    print("="*80)
    
    analyzer = RiskAnalyzer()
    
    # Simular 3 días diferentes
    for day in range(1, 4):
        print(f"\n--- Día {day} ---")
        scenario = analyzer.simulate_single_day(seed=day)
        
        if scenario['total_events'] == 0:
            print("Sin eventos disruptivos")
        else:
            print(f"Eventos ocurridos: {scenario['total_events']}")
            for event in scenario['events']:
                amp_str = f" (x{event['amplification']:.1f})" if event['amplification'] > 1.1 else ""
                print(f"  - {event['code']}: P_eff={event['p_effective']:.4f}{amp_str}")
            
            effects = scenario['effects']
            print("\nEfectos agregados:")
            print(f"  Capacidad residual: {effects['capacity_reduction'] * 100:.1f}%")
            print(f"  Demanda ajustada: {effects['demand_increase'] * 100:.1f}%")


def example_2_monte_carlo():
    """Ejemplo 2: Análisis Monte Carlo."""
    print("\n" + "="*80)
    print("EJEMPLO 2: Análisis Monte Carlo (1000 escenarios)")
    print("="*80)
    
    analyzer = RiskAnalyzer()
    results = analyzer.monte_carlo_analysis(n_scenarios=1000)
    
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
        print(f"  {code}: {prob:.4f} (esperado: {analyzer.manifest.get_incident(code).p_base:.4f})")


def example_3_sensitivity():
    """Ejemplo 3: Análisis de sensibilidad."""
    print("\n" + "="*80)
    print("EJEMPLO 3: Análisis de Sensibilidad a Parámetro γ (gamma)")
    print("="*80)
    
    analyzer = RiskAnalyzer()
    
    # Probar diferentes valores de gamma
    gamma_values = [0.1, 0.25, 0.5, 1.0]
    sensitivity = analyzer.sensitivity_analysis('gamma', gamma_values)
    
    print("\nImpacto de γ en multiplicadores de tiempo:")
    for gamma, impacts in sensitivity.items():
        print(f"  γ={gamma:.2f}: Impacto promedio en T = {impacts['avg_impact_t']:.3f}")


def example_4_risk_report():
    """Ejemplo 4: Reporte completo de riesgo."""
    print("\n" + "="*80)
    print("EJEMPLO 4: Reporte de Riesgo Completo")
    print("="*80)
    
    analyzer = RiskAnalyzer()
    report = analyzer.generate_risk_report(n_scenarios=1000)
    print(report)


def main():
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
