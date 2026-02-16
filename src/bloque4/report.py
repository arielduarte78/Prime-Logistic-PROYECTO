#report.py
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from typing import List, Tuple, Set, Dict, Optional
from .schema import StrategicOption, StrategicTag, OptimizerConfig

# Configuración de Logging
LOGGER = logging.getLogger(__name__)

@dataclass
class RenderProfile:
    """
    Configuración visual agnóstica para la salida del reporte.
    
    Example:
        >>> profile = RenderProfile(use_emojis=False, border_top="---")
    """
    use_emojis: bool = True
    border_top: str = "┌─────────────────────────────────────────────────────────────┐"
    border_bottom: str = "└─────────────────────────────────────────────────────────────┘"
    bullet_point: str = "•"
    section_sep: str = "============================================================="
    
    # Mapeo semántico de íconos (Separación de concerns visuales)
    icons: Dict[str, str] = field(default_factory=lambda: {
        "THE_UNICORN": "🦄",
        "THE_TANK": "🛡️",
        "THE_GAMBLER": "🎲",
        "THE_BALANCER": "⚖️",
        "THE_DOMINATED": "🚫",
        "WARN": "⚠️",
        "OK": "✅",
        "INFO": "ℹ️",
        "MONEY": "💰",
        "SECURITY": "🛡️",  # Para Costo de Seguridad (Risk Premium)
        "RIGIDITY": "🏗️",  # Para Rigidez Estructural (Structure)
        "ENTROPY": "🌌"    # Para Entropía (Incertidumbre/Neblina)
    })

class PrimeStrategicReporter:
    """
    Motor de Inteligencia Narrativa (Masterpiece Edition).
    
    Capacidades:
    - Renderizado modular (Header/Body/Footer desacoplados).
    - Distinción semántica estricta (Security vs Rigidity).
    - Tipado exhaustivo para validación estática (MyPy strict).
    - Documentación con ejemplos de uso.
    """

    def __init__(
        self, 
        config: OptimizerConfig, 
        render_profile: Optional[RenderProfile] = None,
        top_n_analysis: int = 3,
        currency_symbol: str = "$",
        decimal_sep: str = ".",
        thousands_sep: str = ","
    ) -> None:
        self.config = config
        self.style = render_profile or RenderProfile()
        self.top_n = top_n_analysis
        
        # Configuración I18N
        self.currency_symbol = currency_symbol
        self.decimal_sep = decimal_sep
        self.thousands_sep = thousands_sep

        # Motor de Reglas
        self._archetype_rules: List[Tuple[Set[StrategicTag], str]] = [
            ({StrategicTag.SUBOPTIMAL}, "THE_DOMINATED"),
            ({StrategicTag.LOW_COST, StrategicTag.HIGH_RESILIENCE}, "THE_UNICORN"),
            ({StrategicTag.HIGH_RESILIENCE}, "THE_TANK"),
            ({StrategicTag.LOW_COST}, "THE_GAMBLER"),
            (set(), "THE_BALANCER")
        ]

        # Plantillas Narrativas
        self._narrative_templates: Dict[str, Dict[str, str]] = {
            "THE_UNICORN": {
                "headline": "EL UNICORNIO OPERATIVO (Dominancia Total)",
                "body": "Anomalía positiva detectada. Minimiza costo financiero SIN sacrificar integridad.",
                "action": "ACCIÓN: Ejecutar de inmediato. Oportunidad de mercado."
            },
            "THE_TANK": {
                "headline": "LA FORTALEZA (Máxima Resiliencia)",
                "body": "Opción 'Zero-Trust'. Paga una prima alta, pero atomiza el riesgo.",
                "action": "ACCIÓN: Mandatorio para cargas críticas."
            },
            "THE_GAMBLER": {
                "headline": "LA APUESTA TÁCTICA (Riesgo Concentrado)",
                "body": "Máxima eficiencia de capital, pero fragilidad estructural (Puente de Cristal).",
                "action": "ACCIÓN: Requiere monitoreo en tiempo real."
            },
            "THE_BALANCER": {
                "headline": "EL EQUILIBRIO PRIME",
                "body": "Maximiza la utilidad marginal por unidad monetaria invertida en seguridad.",
                "action": "ACCIÓN: Estándar para operaciones recurrentes."
            },
            "THE_DOMINATED": {
                "headline": "OPCIÓN SUBÓPTIMA",
                "body": "Ineficiente. Existen opciones que cuestan menos y protegen más.",
                "action": "ACCIÓN: Descartar."
            }
        }

    def generate_full_report(self, options: List[StrategicOption]) -> str:
        """
        Orquesta la generación del reporte estratégico completo.

        Example:
            >>> reporter = PrimeStrategicReporter(config)
            >>> print(reporter.generate_full_report(my_options))

        Args:
            options: Lista de opciones estratégicas calculadas por el Selector.

        Returns:
            str: El reporte completo formateado.
        """
        if not options:
            LOGGER.error("Intento de reporte con lista de opciones vacía.")
            return f"{self._icon('THE_DOMINATED')} SISTEMA: No hay soluciones viables en la Frontera de Pareto."

        # 1. Auditoría Forense
        self._perform_forensic_audit(options)

        # 2. Ranking
        ranked = sorted(options, key=lambda x: x.recommendation_strength, reverse=True)
        
        # 3. Construcción del Reporte
        market_mood = self._analyze_market_mood(ranked)
        
        blocks: List[str] = []
        for i, opt in enumerate(ranked):
            blocks.append(self._render_deep_dive(i + 1, opt))

        header_sep = self.style.section_sep
        closing = self._generate_closing(ranked[0])
        
        return f"{header_sep}\n{market_mood}\n{header_sep}\n\n" + "\n\n".join(blocks) + f"\n\n{closing}"

    def _render_deep_dive(self, rank: int, opt: StrategicOption) -> str:
        """Renderiza el bloque detallado de una opción usando componentes modulares."""
        archetype_key = self._classify_archetype(opt)
        template = self._narrative_templates.get(archetype_key, self._narrative_templates["THE_BALANCER"])
        
        # Métricas calculadas
        premium = self._calculate_risk_premium(opt)
        entropy_insight = self._analyze_entropy_context(opt.profile.entropy)
        fmt_cost = self._format_currency(opt.solution.total_cost)
        
        # 1. Renderizado del Header (Modular)
        header_block = self._render_block_header(
            rank, 
            self._icon(archetype_key), 
            template['headline'], 
            opt.recommendation_strength
        )
        
        # 2. Renderizado del Cuerpo (Semántica Estricta)
        return f"""
{header_block}
  
  [EL DIAGNÓSTICO]
  "{template['body']}"

  [MÉTRICAS DE DECISIÓN]
  {self.style.bullet_point} {self._icon('MONEY')} Inversión Total:      {fmt_cost}
  {self.style.bullet_point} {self._icon('SECURITY')} Costo de Seguridad:   {premium}
  {self.style.bullet_point} {self._icon('RIGIDITY')} Índice de Rigidez:    {opt.profile.rigidity:.4f}
  {self.style.bullet_point} {self._icon('ENTROPY')} Entropía Relativa:    {opt.profile.entropy:.2f} ({entropy_insight})

  [VERDICTO TÁCTICO]
  ➜ {template['action']}
"""

    def _render_block_header(self, rank: int, icon: str, headline: str, strength: float) -> str:
        """
        Genera el encabezado visual de un bloque de opción.
        Abstrae la lógica de bordes para facilitar futuros cambios de formato (ej. HTML).
        """
        return f"""{self.style.border_top}
│ OPCIÓN #{rank} | {icon} {headline}
│ Confianza del Sistema: {strength:.2%}
{self.style.border_bottom}"""

    def _analyze_market_mood(self, ranked_options: List[StrategicOption]) -> str:
        """Genera el texto de situación de mercado analizando el Top-N."""
        slice_idx = min(len(ranked_options), self.top_n)
        top_slice = ranked_options[:slice_idx]
        
        has_unicorn = any(self._classify_archetype(o) == "THE_UNICORN" for o in top_slice)
        all_gamblers = all(self._classify_archetype(o) == "THE_GAMBLER" for o in top_slice)
        
        base = "🚛 PRIME LOGISTICS INTELLIGENCE | REPORTE DE ESTRATEGIA\n"
        base += f"   Configuración: κ={self.config.kappa} | Top-{self.top_n} Análisis\n"
        
        if has_unicorn:
            base += f"   {self._icon('THE_UNICORN')} ESCENARIO: EXCEPCIONAL. Anomalías de eficiencia detectadas."
        elif all_gamblers:
            base += f"   {self._icon('WARN')} ESCENARIO: VOLÁTIL. Mercado polarizado hacia alto riesgo."
        else:
            base += f"   {self._icon('OK')} ESCENARIO: ESTABLE. Opciones estándar disponibles."
            
        return base

    def _classify_archetype(self, opt: StrategicOption) -> str:
        tags = opt.strategic_tags
        for required_tags, archetype in self._archetype_rules:
            if required_tags.issubset(tags):
                return archetype
        return "THE_BALANCER"

    def _icon(self, key: str) -> str:
        return self.style.icons.get(key, "") if self.style.use_emojis else ""

    def _format_currency(self, amount: float) -> str:
        s = f"{amount:,.2f}"
        if self.thousands_sep == "." and self.decimal_sep == ",":
            s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{self.currency_symbol}{s}"

    def _calculate_risk_premium(self, opt: StrategicOption) -> str:
        cost = opt.solution.total_cost
        optimized = opt.solution.optimized_cost
        
        if cost < 1e-6: 
            return "N/A"
            
        diff = optimized - cost
        percent = diff / cost
        
        if percent < 0.001:
            return "Incluido"
        
        return f"+{percent:.1%} (Prima)"

    def _analyze_entropy_context(self, entropy: float) -> str:
        if entropy < 0.3: 
            return "Riesgo Concentrado"
        if entropy > 0.7: 
            return "Riesgo Distribuido"
        return "Riesgo Estándar"

    def _perform_forensic_audit(self, options: List[StrategicOption]) -> None:
        costs = [o.solution.total_cost for o in options]
        audit_summary = {
            "n_options": len(options),
            "cost_min": min(costs),
            "cost_max": max(costs),
            "cost_avg": statistics.mean(costs) if costs else 0.0
        }
        LOGGER.info(f"REPORT_AUDIT_SUMMARY: {audit_summary}")
        
        for i, opt in enumerate(options):
            LOGGER.debug(
                "OPTION_TRACE | ID=%d | Str=%.4f | Cost=%.2f | Rig=%.4f | Ent=%.4f",
                i, opt.recommendation_strength, opt.solution.total_cost, 
                opt.profile.rigidity, opt.profile.entropy
            )

    def _generate_closing(self, best_opt: StrategicOption) -> str:
        archetype = self._classify_archetype(best_opt)
        return f"""
{self.style.section_sep}
🏁 CONCLUSIÓN FINAL:
El sistema sugiere la OPCIÓN #1 ({archetype}) 
con una certeza del {best_opt.recommendation_strength:.2%}.
{self.style.section_sep}
"""