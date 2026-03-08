# src/block5/speed_profile_loader.py
"""
V1.4.10 — Speed Profile Loader
Reads config/speed_profiles.yaml and provides deterministic
traffic multipliers by time-of-day x H3 macro-zone x highway type.
"""
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger("SpeedProfileLoader")

_YAML_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "speed_profiles.yaml"


def load_speed_profiles() -> Dict[str, Any]:
    """
    Load the speed profiles YAML.  Returns the full dictionary.
    Safe: returns empty dict on any I/O error.
    """
    try:
        with open(_YAML_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        logger.info("speed_profiles loaded from %s", _YAML_PATH)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Could not load speed_profiles.yaml: %s — using empty profiles", exc)
        return {}


def get_h3_parent(h3_index: str) -> str:
    """
    Convert an H3 index (typically resolution 8) to resolution 4.
    Returns 'DEFAULT' on any error, empty, or null input.
    Never raises.
    """
    if not h3_index:
        return "DEFAULT"
    try:
        import h3 as h3lib
        parent = h3lib.h3_to_parent(h3_index, 4)
        return parent if parent else "DEFAULT"
    except Exception:
        return "DEFAULT"


def get_velocity_multiplier(
    profiles: Dict[str, Any],
    highway: str,
    h3_parent: str,
    departure_hour: int,
) -> float:
    """
    Determine the velocity multiplier given:
      - profiles:       full dict from load_speed_profiles()
      - highway:        OSM highway tag (e.g. 'motorway', 'residential')
      - h3_parent:      H3 res-4 hex string (or 'DEFAULT')
      - departure_hour: integer 0-23

    Fallback hierarchy:
      zone-specific highway -> zone 'default' -> DEFAULT zone highway
      -> DEFAULT zone 'default' -> band-level global -> 1.0

    Never raises.
    """
    try:
        franjas = profiles.get("franjas", {})

        # 1. Determine which band this hour falls into
        active_band_name: Optional[str] = None
        for band_name, band_data in franjas.items():
            if band_name == "libre":
                continue
            horas = band_data.get("horas", [])
            if departure_hour in horas:
                active_band_name = band_name
                break

        # If no specific band matched, use 'libre'
        if active_band_name is None:
            active_band_name = "libre"

        band = franjas.get(active_band_name, {})
        zonas = band.get("zonas", {})

        # 2. Lookup with hierarchical fallback
        #    Try: zone_specific[highway] -> zone_specific['default']
        #         -> DEFAULT[highway] -> DEFAULT['default'] -> 1.0
        zone_data = zonas.get(h3_parent, {})
        if zone_data:
            val = zone_data.get(highway)
            if val is not None:
                return float(val)
            val = zone_data.get("default")
            if val is not None:
                return float(val)

        # Fallback to DEFAULT zone
        default_zone = zonas.get("DEFAULT", {})
        if default_zone:
            val = default_zone.get(highway)
            if val is not None:
                return float(val)
            val = default_zone.get("default")
            if val is not None:
                return float(val)

        return 1.0

    except Exception:
        return 1.0
