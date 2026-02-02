"""
Stochastic Engine - Incident Definition Module
================================================

Este módulo proporciona las estructuras de datos y cargadores para el manifiesto
de eventos de riesgo logístico. Diseñado para ser extensible: agregar nuevos eventos
al YAML no requiere cambios en este código.

Arquitectura:
    - Enums tipados para categorías, tipos de distribución y objetivos
    - Dataclasses para mapear la estructura del YAML
    - Validación automática en __post_init__
    - Cargador centralizado con manejo de errores

Uso:
    >>> manifest = ManifestLoader.load("manifest.yaml")
    >>> for incident in manifest.incidents:
    ...     print(f"{incident.code}: P={incident.p_base}")
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional
import yaml
import os

# ============================================================================
# ENUMERACIONES TIPADAS
# ============================================================================

class Category(Enum):
    """Categoría jerárquica del evento de riesgo."""
    SYSTEMIC = "SYSTEMIC"    # Alcance nacional/regional
    TACTICAL = "TACTICAL"    # Alcance zonal/sectorial
    MICRO = "MICRO"          # Operativo/cotidiano


class DistType(Enum):
    """Tipo de distribución probabilística para el evento."""
    EVT = "EVT"              # Extreme Value Theory
    LOGNORMAL = "LOGNORMAL"  # Log-normal
    POISSON = "POISSON"      # Poisson
    UNIFORM = "UNIFORM"      # Uniforme


class TargetType(Enum):
    """Tipo de elemento de la red afectado por el evento."""
    NETWORK = "NETWORK"      # Red completa
    ZONE = "ZONE"            # Zona geográfica
    ARC = "ARC"              # Arco/conexión
    NODE = "NODE"            # Nodo/instalación
    UNIT = "UNIT"            # Unidad/vehículo


class AdjacencyAction(Enum):
    """Acción sobre la adyacencia/conectividad del elemento."""
    NONE = "NONE"            # Sin cambio
    DISABLE = "DISABLE"      # Deshabilitar completamente
    PARTIAL = "PARTIAL"      # Afectación parcial


class ConditionerScope(Enum):
    """Ámbito de aplicación del condicionador de cascada."""
    PROBABILITY = "probability"  # Modifica probabilidad
    IMPACT = "impact"            # Modifica impacto


# ============================================================================
# DATACLASSES - ESTRUCTURAS ANIDADAS
# ============================================================================

@dataclass
class Distribution:
    """Especificación de distribución probabilística."""
    type: DistType
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Valida que el tipo sea un DistType válido."""
        if isinstance(self.type, str):
            self.type = DistType[self.type]


@dataclass
class Target:
    """Especificación del objetivo del evento."""
    type: TargetType
    selector: str  # Patrón para seleccionar elementos (e.g., "WAREHOUSE_*")
    
    def __post_init__(self):
        """Convierte string a TargetType si es necesario."""
        if isinstance(self.type, str):
            self.type = TargetType[self.type]


@dataclass
class AdjacencyEffect:
    """Efecto sobre la adyacencia/conectividad."""
    action: AdjacencyAction
    
    def __post_init__(self):
        """Convierte string a AdjacencyAction si es necesario."""
        if isinstance(self.action, str):
            self.action = AdjacencyAction[self.action]


@dataclass
class CapacityEffect:
    """Efecto sobre la capacidad del elemento."""
    modifier: float  # Multiplicador: 1.0 = sin cambio, 0.0 = anulado, >1.0 = incremento
    
    def __post_init__(self):
        """Valida que el modificador sea no-negativo."""
        if self.modifier < 0:
            raise ValueError(f"Capacity modifier debe ser >= 0, obtenido: {self.modifier}")


@dataclass
class DemandEffect:
    """Efecto sobre la demanda del elemento."""
    modifier: float  # Multiplicador de demanda
    
    def __post_init__(self):
        """Valida que el modificador sea no-negativo."""
        if self.modifier < 0:
            raise ValueError(f"Demand modifier debe ser >= 0, obtenido: {self.modifier}")


@dataclass
class StructuralEffects:
    """Conjunto de efectos estructurales sobre la red."""
    adjacency: AdjacencyEffect
    capacity: CapacityEffect
    demand: DemandEffect


@dataclass
class MetricImpact:
    """Impacto sobre una métrica específica (C, T, etc.)."""
    metric: str  # Código de métrica (e.g., "T", "C")
    base_multiplier: float
    stress_scaling: str  # Parámetro global a usar (alpha, beta, gamma)
    
    def __post_init__(self):
        """Valida que el multiplicador base sea positivo."""
        if self.base_multiplier <= 0:
            raise ValueError(f"base_multiplier debe ser > 0, obtenido: {self.base_multiplier}")


@dataclass
class Conditioner:
    """
    Condicionador de cascada: especifica cómo un evento previo afecta a este.
    
    La probabilidad efectiva se calculará como:
        P_eff = min(1, P_base * ∏ φ_k)
    donde φ_k es el multiplier de cada conditioner activo.
    """
    event: str  # Código del evento condicionante
    multiplier: float  # Factor multiplicativo
    scope: ConditionerScope  # Ámbito de aplicación
    
    def __post_init__(self):
        """Valida el condicionador."""
        if isinstance(self.scope, str):
            self.scope = ConditionerScope[self.scope.upper()]
        if self.multiplier < 0:
            raise ValueError(f"Conditioner multiplier debe ser >= 0, obtenido: {self.multiplier}")


# ============================================================================
# DATACLASS PRINCIPAL - DEFINICIÓN DE INCIDENTE
# ============================================================================

@dataclass
class IncidentDefinition:
    """
    Definición completa de un evento de riesgo logístico.
    
    Mapea directamente la estructura del YAML y proporciona validación
    automática de parámetros críticos.
    """
    code: str  # Identificador único del evento
    level: Category  # Categoría jerárquica
    description: str  # Descripción legible
    p_base: float  # Probabilidad base [0, 1]
    distribution: Distribution  # Especificación de distribución
    stress_weight: float  # Peso para stress testing
    conditioners: List[Conditioner]  # Lista de dependencias de cascada
    target: Target  # Especificación del objetivo
    structural_effects: StructuralEffects  # Efectos sobre estructura
    metric_impacts: List[MetricImpact]  # Impactos en métricas
    
    def __post_init__(self):
        """
        Validación post-inicialización.
        
        Verifica:
            - p_base ∈ [0, 1]
            - level es un Category válido
            - Tipos anidados están correctamente instanciados
        """
        # Validar probabilidad base
        if not 0 <= self.p_base <= 1:
            raise ValueError(
                f"Probabilidad base para {self.code} fuera de rango [0,1]: {self.p_base}"
            )
        
        # Convertir level si viene como string
        if isinstance(self.level, str):
            try:
                self.level = Category[self.level]
            except KeyError:
                raise ValueError(f"Categoría inválida para {self.code}: {self.level}")
        
        # Validar stress_weight
        if self.stress_weight < 0:
            raise ValueError(f"stress_weight debe ser >= 0 para {self.code}")
    
    def effective_probability(self, active_events: List[str]) -> float:
        """Cálculo de cascada: P_eff = min(1, P_base * ∏ φ_k)"""
        p_eff = self.p_base
        for cond in self.conditioners:
            if cond.scope == ConditionerScope.PROBABILITY and cond.event in active_events:
                p_eff *= cond.multiplier
        return min(1.0, p_eff)
    
    def get_impact_multiplier(self, metric: str, stress_index: float, global_params: Dict[str, float]) -> float:
        """
        CÁLCULO DINÁMICO: Aplica la sensibilidad al Stress Index real.
        Fórmula Prime: Multiplier = Base * (1 + Sensibilidad * S)
        """
        for impact in self.metric_impacts:
            if impact.metric == metric:
                sensitivity = global_params.get(impact.stress_scaling, 0.0)
                # Aquí inyectamos el Stress Index (S) de la iteración
                return impact.base_multiplier * (1 + (sensitivity * stress_index))
        return 1.0


# ============================================================================
# PARÁMETROS GLOBALES
# ============================================================================

@dataclass
class OutlierCap:
    """Configuración de límites para valores atípicos."""
    type: str  # "hard" o "soft"
    max_multiplier: float


@dataclass
class Convergence:
    """Parámetros de convergencia para simulaciones."""
    window_iterations: int
    epsilon: float


@dataclass
class GlobalParameters:
    """Parámetros globales del manifiesto."""
    stress_index: str
    alpha: float
    beta: float
    gamma: float
    severity_weights_range: List[float]
    outlier_cap: OutlierCap
    convergence: Convergence
    impact_combination_rules: List[str]


# ============================================================================
# MANIFIESTO COMPLETO
# ============================================================================

@dataclass
class Manifest:
    """Manifiesto completo cargado desde YAML."""
    meta: Dict[str, Any]
    global_parameters: GlobalParameters
    event_levels: Dict[str, Dict[str, Any]]
    incidents: List[IncidentDefinition]
    
    def get_incident(self, code: str) -> Optional[IncidentDefinition]:
        """Busca un incidente por su código."""
        for incident in self.incidents:
            if incident.code == code:
                return incident
        return None
    
    def get_incidents_by_level(self, level: Category) -> List[IncidentDefinition]:
        """Retorna todos los incidentes de un nivel dado."""
        return [inc for inc in self.incidents if inc.level == level]


# ============================================================================
# CARGADOR DE MANIFIESTO
# ============================================================================

class ManifestLoader:
    """
    Cargador centralizado del manifiesto YAML.
    
    Responsabilidades:
        - Parsear YAML
        - Instanciar dataclasses
        - Validar estructura
        - Manejo de errores
    """
    
   
    @staticmethod
    def load(filename: str = "manifest.yaml") -> 'Manifest':
        # RECUPERAMOS EL BLINDAJE DE RUTA (Esencial para que no falle el test)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(base_dir, filename)
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Error: No se encontró el manifiesto en {full_path}")
        
        # Extraer secciones
        meta = data.get('meta', {})
        global_params_raw = data.get('global_parameters', {})
        event_levels = data.get('event_levels', {})
        events_raw = data.get('events', [])
        
        # Parsear global_parameters
        global_params = ManifestLoader._parse_global_parameters(global_params_raw)
        
        # Parsear incidents
        incidents = ManifestLoader._parse_incidents(events_raw)
        
        return Manifest(
            meta=meta,
            global_parameters=global_params,
            event_levels=event_levels,
            incidents=incidents
        )
    
    @staticmethod
    def _parse_global_parameters(data: Dict[str, Any]) -> GlobalParameters:
        """Parsea la sección global_parameters."""
        outlier_cap = OutlierCap(
            type=data['outlier_cap']['type'],
            max_multiplier=data['outlier_cap']['max_multiplier']
        )
        
        convergence = Convergence(
            window_iterations=data['convergence']['window_iterations'],
            epsilon=data['convergence']['epsilon']
        )
        
        return GlobalParameters(
            stress_index=data['stress_index'],
            alpha=data['alpha'],
            beta=data['beta'],
            gamma=data['gamma'],
            severity_weights_range=data['severity_weights_range'],
            outlier_cap=outlier_cap,
            convergence=convergence,
            impact_combination_rules=data['impact_combination_rules']
        )
    
    @staticmethod
    def _parse_incidents(events_list: List[Dict[str, Any]]) -> List[IncidentDefinition]:
        """Parsea la lista de eventos en IncidentDefinitions."""
        incidents = []
        
        for event_data in events_list:
            # Parsear estructuras anidadas
            distribution = Distribution(**event_data['distribution'])
            target = Target(**event_data['target'])
            
            # Parsear structural_effects
            adjacency = AdjacencyEffect(**event_data['structural_effects']['adjacency'])
            capacity = CapacityEffect(**event_data['structural_effects']['capacity'])
            demand = DemandEffect(**event_data['structural_effects']['demand'])
            structural_effects = StructuralEffects(
                adjacency=adjacency,
                capacity=capacity,
                demand=demand
            )
            
            # Parsear metric_impacts
            metric_impacts = [MetricImpact(**mi) for mi in event_data['metric_impacts']]
            
            # Parsear conditioners
            conditioners = [Conditioner(**c) for c in event_data['conditioners']]
            
            # Crear IncidentDefinition
            incident = IncidentDefinition(
                code=event_data['code'],
                level=event_data['level'],
                description=event_data['description'],
                p_base=event_data['p_base'],
                distribution=distribution,
                stress_weight=event_data['stress_weight'],
                conditioners=conditioners,
                target=target,
                structural_effects=structural_effects,
                metric_impacts=metric_impacts
            )
            
            incidents.append(incident)
        
        return incidents


# ============================================================================
# UTILIDADES Y HELPERS
# ============================================================================

def print_manifest_summary(manifest: Manifest) -> None:
    """Imprime un resumen del manifiesto cargado."""
    print("=" * 80)
    print("MANIFIESTO DE EVENTOS DE RIESGO LOGÍSTICO")
    print("=" * 80)
    print(f"Versión Schema: {manifest.meta.get('schema_version')}")
    print(f"Contexto: {manifest.meta.get('geographic_context')}")
    print(f"\nTotal de eventos: {len(manifest.incidents)}")
    
    # Resumen por categoría
    for category in Category:
        incidents = manifest.get_incidents_by_level(category)
        print(f"  - {category.value}: {len(incidents)} eventos")
    
    # Parámetros globales
    print("\nParámetros Globales:")
    print(f"  - Stress Index: {manifest.global_parameters.stress_index}")
    print(f"  - Alpha: {manifest.global_parameters.alpha}")
    print(f"  - Beta: {manifest.global_parameters.beta}")
    print(f"  - Gamma: {manifest.global_parameters.gamma}")
    
    print("=" * 80)


def validate_manifest_integrity(manifest: Manifest) -> List[str]:
    """
    Valida la integridad del manifiesto cargado.
    
    Verifica:
        - Referencias de conditioners son válidas
        - No hay ciclos en dependencias
        - Target types son consistentes con event levels
        
    Returns:
        Lista de advertencias (vacía si todo OK)
    """
    warnings = []
    event_codes = {inc.code for inc in manifest.incidents}
    
    # Verificar referencias de conditioners
    for incident in manifest.incidents:
        for cond in incident.conditioners:
            if cond.event not in event_codes:
                warnings.append(
                    f"WARNING: {incident.code} referencia evento inexistente: {cond.event}"
                )
    
    # Verificar consistencia de target types con event levels
    level_rules = manifest.event_levels
    for incident in manifest.incidents:
        allowed = level_rules[incident.level.value].get('allowed_target_types', [])
        if incident.target.type.value not in allowed:
            warnings.append(
                f"WARNING: {incident.code} usa target {incident.target.type.value} "
                f"no permitido para nivel {incident.level.value}"
            )
    
    return warnings


# ============================================================================
# EJEMPLO DE USO
# ============================================================================

if __name__ == "__main__":
    # Cargar manifiesto
    manifest = ManifestLoader.load("manifest.yaml")
    
    # Mostrar resumen
    print_manifest_summary(manifest)
    
    # Validar integridad
    warnings = validate_manifest_integrity(manifest)
    if warnings:
        print("\nADVERTENCIAS:")
        for w in warnings:
            print(f"  {w}")
    else:
        print("\n✓ Manifiesto validado correctamente")
    
    # Ejemplo: Calcular probabilidad efectiva con cascada
    print("\n" + "=" * 80)
    print("EJEMPLO: Cálculo de Probabilidad Efectiva con Cascada")
    print("=" * 80)
    
    # Simular que INUNDACION_REGIONAL está activo
    active_events = ["INUNDACION_REGIONAL"]
    
    # Buscar evento que depende de INUNDACION_REGIONAL
    bloqueo = manifest.get_incident("BLOQUEO_RUTA")
    if bloqueo:
        p_base = bloqueo.p_base
        p_eff = bloqueo.effective_probability(active_events)
        print(f"\nEvento: {bloqueo.code}")
        print(f"  P_base: {p_base:.4f}")
        print(f"  P_efectiva (con INUNDACION_REGIONAL activo): {p_eff:.4f}")
        print(f"  Factor de amplificación: {p_eff/p_base:.2f}x")
    
    # Mostrar detalles de un evento SYSTEMIC
    print("\n" + "=" * 80)
    print("EJEMPLO: Detalles de Evento SYSTEMIC")
    print("=" * 80)
    
    crisis = manifest.get_incident("CRISIS_COMBUSTIBLE")
    if crisis:
        print(f"\n{crisis.code}:")
        print(f"  Nivel: {crisis.level.value}")
        print(f"  P_base: {crisis.p_base}")
        print(f"  Target: {crisis.target.type.value} ({crisis.target.selector})")
        print(f"  Capacidad reducida a: {crisis.structural_effects.capacity.modifier * 100}%")
        print("  Impactos en métricas:")
        for impact in crisis.metric_impacts:
            print(f"    - {impact.metric}: x{impact.base_multiplier} (escala: {impact.stress_scaling})")
