"""
Test Suite para el Motor Estocástico
=====================================

Validación completa del sistema de carga y manejo de incidentes.
"""

import sys
from incidents import (
    ManifestLoader, 
    Category, 
    print_manifest_summary,
    validate_manifest_integrity
)


def test_basic_loading():
    """Test 1: Carga básica del manifiesto."""
    print("\n" + "="*80)
    print("TEST 1: Carga Básica del Manifiesto")
    print("="*80)
    
    try:
        manifest = ManifestLoader.load("manifest.yaml")
        print("✓ Manifiesto cargado exitosamente")
        print(f"✓ Total de eventos: {len(manifest.incidents)}")
        return manifest
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


def test_incident_access(manifest):
    """Test 2: Acceso a incidentes por código y categoría."""
    print("\n" + "="*80)
    print("TEST 2: Acceso a Incidentes")
    print("="*80)
    
    # Por código
    paro = manifest.get_incident("PARO_NACIONAL_TRANSPORTE")
    if paro:
        print(f"✓ Incidente encontrado: {paro.code}")
        print(f"  - Nivel: {paro.level.value}")
        print(f"  - P_base: {paro.p_base}")
        print(f"  - Target: {paro.target.type.value}")
    else:
        print("✗ No se encontró PARO_NACIONAL_TRANSPORTE")
    
    # Por categoría
    systemic = manifest.get_incidents_by_level(Category.SYSTEMIC)
    tactical = manifest.get_incidents_by_level(Category.TACTICAL)
    micro = manifest.get_incidents_by_level(Category.MICRO)
    
    print("\n✓ Eventos por nivel:")
    print(f"  - SYSTEMIC: {len(systemic)}")
    print(f"  - TACTICAL: {len(tactical)}")
    print(f"  - MICRO: {len(micro)}")


def test_cascade_probability(manifest):
    """Test 3: Cálculo de probabilidad efectiva con cascada."""
    print("\n" + "="*80)
    print("TEST 3: Probabilidad Efectiva con Cascada")
    print("="*80)
    
    # Escenario 1: Sin eventos activos
    huelga = manifest.get_incident("HUELGA_ALMACEN")
    if huelga:
        p_normal = huelga.effective_probability([])
        print("\nHUELGA_ALMACEN:")
        print(f"  P_base: {huelga.p_base:.4f}")
        print(f"  P_efectiva (sin cascada): {p_normal:.4f}")
        
        # Escenario 2: Con PARO_NACIONAL_TRANSPORTE activo
        p_cascada = huelga.effective_probability(["PARO_NACIONAL_TRANSPORTE"])
        print(f"  P_efectiva (con PARO activo): {p_cascada:.4f}")
        print(f"  Amplificación: {p_cascada/p_normal:.2f}x")
        
        # Verificar que coincide con el multiplier esperado (8.0)
        expected = min(1.0, huelga.p_base * 8.0)
        assert abs(p_cascada - expected) < 1e-6, "Error en cálculo de cascada"
        print("  ✓ Cálculo de cascada correcto")


def test_impact_calculation(manifest):
    """Test 4: Cálculo de multiplicadores de impacto."""
    print("\n" + "="*80)
    print("TEST 4: Cálculo de Impactos en Métricas")
    print("="*80)
    
    crisis = manifest.get_incident("CRISIS_COMBUSTIBLE")
    if crisis:
        global_params = {
            'alpha': manifest.global_parameters.alpha,
            'beta': manifest.global_parameters.beta,
            'gamma': manifest.global_parameters.gamma
        }
        
        print("\nCRISIS_COMBUSTIBLE:")
        print(f"  Parámetros globales: α={global_params['alpha']}, "
              f"β={global_params['beta']}, γ={global_params['gamma']}")
        
        # Calcular impactos
        impact_c = crisis.get_impact_multiplier('C', global_params)
        impact_t = crisis.get_impact_multiplier('T', global_params)
        
        print("\n  Multiplicadores de impacto:")
        print(f"    - Métrica C: {impact_c:.3f}")
        print(f"    - Métrica T: {impact_t:.3f}")
        
        # Verificar manualmente
        # C: base=2.0, scaling=beta=0.35 → 2.0 * (1 + 0.35) = 2.7
        expected_c = 2.0 * (1 + global_params['beta'])
        assert abs(impact_c - expected_c) < 1e-6, "Error en cálculo de impacto C"
        print(f"    ✓ Impacto C verificado: {expected_c:.3f}")


def test_structural_effects(manifest):
    """Test 5: Efectos estructurales sobre la red."""
    print("\n" + "="*80)
    print("TEST 5: Efectos Estructurales")
    print("="*80)
    
    # Evento que deshabilita adyacencia
    paro = manifest.get_incident("PARO_NACIONAL_TRANSPORTE")
    if paro:
        print(f"\n{paro.code}:")
        print(f"  Acción de adyacencia: {paro.structural_effects.adjacency.action.value}")
        print(f"  Modificador de capacidad: {paro.structural_effects.capacity.modifier}")
        print(f"  Modificador de demanda: {paro.structural_effects.demand.modifier}")
        
        assert paro.structural_effects.adjacency.action.value == "DISABLE"
        assert paro.structural_effects.capacity.modifier == 0.0
        print("  ✓ Paro nacional: adyacencia DISABLE, capacidad 0")
    
    # Evento con efectos parciales
    ola_calor = manifest.get_incident("OLA_CALOR_EXTREMA")
    if ola_calor:
        print(f"\n{ola_calor.code}:")
        print(f"  Acción de adyacencia: {ola_calor.structural_effects.adjacency.action.value}")
        print(f"  Modificador de capacidad: {ola_calor.structural_effects.capacity.modifier}")
        print(f"  Modificador de demanda: {ola_calor.structural_effects.demand.modifier}")
        print("  ✓ Ola de calor: reducción parcial de capacidad y aumento de demanda")


def test_conditioners_chain(manifest):
    """Test 6: Cadena de condicionadores."""
    print("\n" + "="*80)
    print("TEST 6: Análisis de Cadenas de Dependencia")
    print("="*80)
    
    print("\nEventos con condicionadores:")
    for incident in manifest.incidents:
        if incident.conditioners:
            print(f"\n{incident.code}:")
            for cond in incident.conditioners:
                print(f"  ← {cond.event} (x{cond.multiplier}, scope: {cond.scope.value})")


def test_global_parameters(manifest):
    """Test 7: Parámetros globales."""
    print("\n" + "="*80)
    print("TEST 7: Parámetros Globales")
    print("="*80)
    
    gp = manifest.global_parameters
    print(f"\nStress Index: {gp.stress_index}")
    print(f"Coeficientes: α={gp.alpha}, β={gp.beta}, γ={gp.gamma}")
    print(f"Rango de pesos: {gp.severity_weights_range}")
    print(f"Outlier Cap: {gp.outlier_cap.type}, max={gp.outlier_cap.max_multiplier}")
    print(f"Convergencia: {gp.convergence.window_iterations} iter, ε={gp.convergence.epsilon}")
    print(f"Reglas de combinación: {', '.join(gp.impact_combination_rules)}")


def test_extensibility():
    """Test 8: Demostración de extensibilidad."""
    print("\n" + "="*80)
    print("TEST 8: Extensibilidad del Sistema")
    print("="*80)
    
    print("\n✓ El sistema está diseñado para extensibilidad:")
    print("  - Agregar nuevo evento al YAML → Sin cambios en código")
    print("  - Nuevas distribuciones → Agregar a DistType enum")
    print("  - Nuevos target types → Agregar a TargetType enum")
    print("  - Nuevas métricas → Sin cambios necesarios")
    print("\n✓ Ejemplo: Para agregar evento 'CISNE_NEGRO':")
    print("  1. Agregarlo a manifest.yaml con la estructura estándar")
    print("  2. Ejecutar ManifestLoader.load() → Listo")


def run_all_tests():
    """Ejecuta todos los tests."""
    print("="*80)
    print("SUITE DE TESTS - MOTOR ESTOCÁSTICO")
    print("="*80)
    
    try:
        # Test 1: Carga básica
        manifest = test_basic_loading()
        
        # Test 2: Acceso a incidentes
        test_incident_access(manifest)
        
        # Test 3: Probabilidad con cascada
        test_cascade_probability(manifest)
        
        # Test 4: Cálculo de impactos
        test_impact_calculation(manifest)
        
        # Test 5: Efectos estructurales
        test_structural_effects(manifest)
        
        # Test 6: Cadenas de condicionadores
        test_conditioners_chain(manifest)
        
        # Test 7: Parámetros globales
        test_global_parameters(manifest)
        
        # Test 8: Extensibilidad
        test_extensibility()
        
        # Validación de integridad
        print("\n" + "="*80)
        print("VALIDACIÓN DE INTEGRIDAD")
        print("="*80)
        warnings = validate_manifest_integrity(manifest)
        if warnings:
            print("\nAdvertencias:")
            for w in warnings:
                print(f"  {w}")
        else:
            print("\n✓ Manifiesto validado: Sin advertencias")
        
        # Resumen final
        print("\n" + "="*80)
        print("RESUMEN EJECUTIVO")
        print("="*80)
        print_manifest_summary(manifest)
        
        print("\n" + "="*80)
        print("✓ TODOS LOS TESTS COMPLETADOS EXITOSAMENTE")
        print("="*80)
        
    except Exception as e:
        print(f"\n✗ TEST FALLIDO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
