import json
import logging
from pathlib import Path
from typing import Dict

import h3

logger = logging.getLogger("ThreatLoader")

THREAT_INDEX_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "threat_index.json"

def load_h3_threat_matrix(resolution: int = 8) -> Dict[str, float]: 
    """ 
    Convert red zone bounding boxes into a dictionary 
    h3_index -> very_risk (0.1 to 1.0). 
    Severity 1-10 is normalized by dividing by 10. 
    """ 
    if not THREAT_INDEX_PATH.exists(): 
        logger.warning("threat_index.json not found. Threat matrix empty.") 
        return {} 

    with open(THREAT_INDEX_PATH, "r", encoding="utf-8") as f: 
        data = json.load(f) 

    threat_matrix: Dict[str, float] = {} 

    for zone in data["zones"]: 
        mu = zone["severity"] / 10.0 
        bbox = zone["bbox"] 
        lat_step = 0.005 
        lon_step = 0.005 
        lat = bbox["min_lat"] 
        while lat <= bbox["max_lat"]: 
            lon = bbox["min_lon"] 
            while lon <= bbox["max_lon"]: 
                try: 
                    try: 
                        h3_idx = h3.latlng_to_cell(lat, lon, resolution) 
                    except AttributeError: 
                        h3_idx = h3.geo_to_h3(lat, lon, resolution) 
                    threat_matrix[h3_idx] = max(threat_matrix.get(h3_idx, 0.0), mu) 
                except Exception: 
                    pass 
                lon += lon_step 
            lat += lat_step 

    logger.info(f"H3 Threat Matrix loaded: {len(threat_matrix)} hexes in red zones.") 
    return threat_matrix
