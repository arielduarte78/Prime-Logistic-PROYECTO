#report.py
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from typing import List, Tuple, Set, Dict, Optional, Any

from .schema import StrategicOption, StrategicTag, OptimizerConfig, RouteProfile, RawSolution
from .pareto import ParetoFrontResult, ParetoSolution

LOGGER = logging.getLogger(__name__)

@dataclass
class RenderProfile:
    """
    Configuración visual agnóstica para la salida del reporte.
    """
    use_emojis: bool = True
    border_top: str = "┌─────────────────────────────────────────────────────────────┐"
    border_bottom: str = "└─────────────────────────────────────────────────────────────┘"
    bullet_point: str = "•"
    section_sep: str = "============================================================="
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
        "SECURITY": "🛡️",
        "RIGIDITY": "🏗️",
        "ENTROPY": "🌌"
    })

class PrimeStrategicReporter:
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
        self.currency_symbol = currency_symbol
        self.decimal_sep = decimal_sep
        self.thousands_sep = thousands_sep

        self._archetype_rules: List[Tuple[Set[StrategicTag], str]] = [
            ({StrategicTag.SUBOPTIMAL}, "THE_DOMINATED"),
            ({StrategicTag.LOW_COST, StrategicTag.HIGH_RESILIENCE}, "THE_UNICORN"),
            ({StrategicTag.HIGH_RESILIENCE}, "THE_TANK"),
            ({StrategicTag.LOW_COST}, "THE_GAMBLER"),
            (set(), "THE_BALANCER")
        ]

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
        if not options:
            LOGGER.error("Intento de reporte con lista de opciones vacía.")
            return f"{self._icon('THE_DOMINATED')} SISTEMA: No hay soluciones viables en la Frontera de Pareto."

        self._perform_forensic_audit(options)

        ranked = sorted(options, key=lambda x: x.recommendation_strength, reverse=True)

        market_mood = self._analyze_market_mood(ranked)

        blocks: List[str] = []
        for i, opt in enumerate(ranked):
            try:
                blocks.append(self._render_deep_dive(i + 1, opt))
            except Exception as e:
                LOGGER.exception("Error renderizando opción %s: %s", i + 1, e)
                blocks.append(f"[ERROR] No se pudo renderizar la opción #{i+1}")

        header_sep = self.style.section_sep
        closing = self._generate_closing(ranked[0]) if ranked else ""

        return f"{header_sep}\n{market_mood}\n{header_sep}\n\n" + "\n\n".join(blocks) + f"\n\n{closing}"

    def _render_deep_dive(self, rank: int, opt: StrategicOption) -> str:
        archetype_key = self._classify_archetype(opt)
        template = self._narrative_templates.get(archetype_key, self._narrative_templates["THE_BALANCER"])

        premium = self._calculate_risk_premium(opt)
        entropy_insight = self._analyze_entropy_context(getattr(opt.profile, "entropy", 0.0))
        fmt_cost = self._format_currency(getattr(opt.solution, "total_cost", 0.0))

        header_block = self._render_block_header(
            rank,
            self._icon(archetype_key),
            template['headline'],
            float(getattr(opt, "recommendation_strength", 0.0))
        )

        return f"""
{header_block}
  
  [EL DIAGNÓSTICO]
  "{template['body']}"

  [MÉTRICAS DE DECISIÓN]
  {self.style.bullet_point} {self._icon('MONEY')} Inversión Total:      {fmt_cost}
  {self.style.bullet_point} {self._icon('SECURITY')} Costo de Seguridad:   {premium}
  {self.style.bullet_point} {self._icon('RIGIDITY')} Índice de Rigidez:    {getattr(opt.profile, 'rigidity', 0.0):.4f}
  {self.style.bullet_point} {self._icon('ENTROPY')} Entropía Relativa:    {getattr(opt.profile, 'entropy', 0.0):.2f} ({entropy_insight})

  [VERDICTO TÁCTICO]
  ➜ {template['action']}
"""

    def _render_block_header(self, rank: int, icon: str, headline: str, strength: float) -> str:
        return f"""{self.style.border_top}
│ OPCIÓN #{rank} | {icon} {headline}
│ Confianza del Sistema: {strength:.2%}
{self.style.border_bottom}"""

    def _analyze_market_mood(self, ranked_options: List[StrategicOption]) -> str:
        slice_idx = min(len(ranked_options), self.top_n)
        top_slice = ranked_options[:slice_idx]

        has_unicorn = any(self._classify_archetype(o) == "THE_UNICORN" for o in top_slice)
        all_gamblers = all(self._classify_archetype(o) == "THE_GAMBLER" for o in top_slice)

        base = "🚛 PRIME LOGISTICS INTELLIGENCE | REPORTE DE ESTRATEGIA\n"
        base += f"   Configuración: κ={getattr(self.config, 'kappa', 'N/A')} | Top-{self.top_n} Análisis\n"

        if has_unicorn:
            base += f"   {self._icon('THE_UNICORN')} ESCENARIO: EXCEPCIONAL. Anomalías de eficiencia detectadas."
        elif all_gamblers:
            base += f"   {self._icon('WARN')} ESCENARIO: VOLÁTIL. Mercado polarizado hacia alto riesgo."
        else:
            base += f"   {self._icon('OK')} ESCENARIO: ESTABLE. Opciones estándar disponibles."

        return base

    def _classify_archetype(self, opt: StrategicOption) -> str:
        tags = opt.strategic_tags or set()
        for required_tags, archetype in self._archetype_rules:
            if required_tags.issubset(tags):
                return archetype
        return "THE_BALANCER"

    def _icon(self, key: str) -> str:
        return self.style.icons.get(key, "") if self.style.use_emojis else ""

    def _format_currency(self, amount: float) -> str:
        try:
            s = f"{float(amount):,.2f}"
        except Exception:
            s = "0.00"
        if self.thousands_sep == "." and self.decimal_sep == ",":
            s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{self.currency_symbol}{s}"

    def _calculate_risk_premium(self, opt: StrategicOption) -> str:
        cost = float(getattr(opt.solution, "total_cost", 0.0))
        optimized = getattr(opt.solution, "optimized_cost", None)

        if cost < 1e-6:
            return "N/A"

        if optimized is None:
            # If optimized_cost missing, attempt to use total_cost as fallback
            return "Incluido"

        try:
            diff = float(optimized) - cost
            percent = diff / cost
        except Exception:
            return "N/A"

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
        costs = [float(getattr(o.solution, "total_cost", 0.0)) for o in options]
        audit_summary = {
            "n_options": len(options),
            "cost_min": min(costs) if costs else 0.0,
            "cost_max": max(costs) if costs else 0.0,
            "cost_avg": statistics.mean(costs) if costs else 0.0
        }
        LOGGER.info("REPORT_AUDIT_SUMMARY: %s", audit_summary)

        for i, opt in enumerate(options):
            LOGGER.debug(
                "OPTION_TRACE | ID=%d | Str=%.4f | Cost=%.2f | Rig=%.4f | Ent=%.4f",
                i,
                float(getattr(opt, "recommendation_strength", 0.0)),
                float(getattr(opt.solution, "total_cost", 0.0)),
                float(getattr(opt.profile, "rigidity", 0.0)),
                float(getattr(opt.profile, "entropy", 0.0))
            )

    def _generate_closing(self, best_opt: StrategicOption) -> str:
        archetype = self._classify_archetype(best_opt)
        strength = float(getattr(best_opt, "recommendation_strength", 0.0))
        return f"""
{self.style.section_sep}
🏁 CONCLUSIÓN FINAL:
El sistema sugiere la OPCIÓN #1 ({archetype}) 
con una certeza del {strength:.2%}.
{self.style.section_sep}
"""

# ==============================================================================

def _build_profile_from_solution(sol: ParetoSolution) -> RouteProfile:
    entropy = float(min(1.0, (float(sol.w_survival) + float(sol.w_expected_cost)) / (1.0 + float(sol.w_expected_cost))))
    rigidity = float(max(0.0, 1.0 - entropy))
    redundancy_index = float(max(0.0, 1.0 - (float(sol.total_risk or 0.0))))
    sensitivity_vector = {"w_survival": float(sol.w_survival), "w_expected_cost": float(sol.w_expected_cost)}
    return RouteProfile(
        risk_scale=float(sol.total_risk or 0.0),
        entropy=entropy,
        rigidity=rigidity,
        redundancy_index=redundancy_index,
        sensitivity_vector=sensitivity_vector
    )

def _derive_tags(profile: RouteProfile, sol: ParetoSolution) -> Set[StrategicTag]:
    tags: Set[StrategicTag] = set()
    try:
        if float(sol.w_expected_cost) <= 1.0 * float(getattr(sol, "total_cost", sol.w_expected_cost)):
            tags.add(StrategicTag.LOW_COST)
    except Exception:
        pass

    try:
        if float(sol.w_survival) <= 0.1 or profile.redundancy_index > 0.9:
            tags.add(StrategicTag.HIGH_RESILIENCE)
    except Exception:
        pass

    if profile.entropy > 0.6:
        tags.add(StrategicTag.DISTRIBUTED_RISK)

    if not tags:
        tags.add(StrategicTag.BALANCED)
    return tags

def _score_recommendation(sol: ParetoSolution, profile: RouteProfile) -> float:
    try:
        c = 1.0 / (1.0 + float(sol.w_expected_cost))
        r = 1.0 / (1.0 + float(sol.w_survival))
        e = float(profile.entropy)
        raw = 0.5 * c + 0.3 * r + 0.2 * (1.0 - abs(0.5 - e))
        return float(max(0.0, min(1.0, raw)))
    except Exception:
        return 0.0

def build_strategic_options_from_frontier(labels: List[Any], engine: Any, config: OptimizerConfig) -> List[StrategicOption]:
    pf = ParetoFrontResult.from_labels(labels, engine)
    options: List[StrategicOption] = []
    for sol in pf.solutions:
        profile = _build_profile_from_solution(sol)
        tags = _derive_tags(profile, sol)
        strength = _score_recommendation(sol, profile)
        raw = RawSolution(
            path=list(getattr(sol, "path", [])),
            edges=list(getattr(sol, "edges", [])),
            total_cost=float(getattr(sol, "total_cost", 0.0)),
            optimized_cost=float(getattr(sol, "optimized_cost", getattr(sol, "w_expected_cost", 0.0))),
            total_time=float(getattr(sol, "total_time", 0.0)),
            total_risk=float(getattr(sol, "total_risk", 0.0))
        )
        opt = StrategicOption(
            solution=raw,
            profile=profile,
            strategic_tags=tags,
            recommendation_strength=float(strength)
        )
        options.append(opt)
    return options
