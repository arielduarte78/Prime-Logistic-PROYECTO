import requests
import json

BASE = "http://localhost:8000/fleet"
HEADERS = {"X-API-Key": "dev_key_123", "Content-Type": "application/json"}
PAYLOAD = {
    "vehicles": [
        {"id": "V1", "capacity_tons": 5.0, "origin_lat": -34.6037, "origin_lon": -58.3816}
    ],
    "destinations": [
        {"id": "D1", "demand_tons": 2.0, "lat": -34.4500, "lon": -58.5500}
    ],
}

summary = []

for hour_tag in ["03:00", "08:00"]:
    payload = {**PAYLOAD, "departure_time": hour_tag}
    r = requests.post(BASE, json=payload, headers=HEADERS, timeout=180)
    data = r.json()
    
    plans = data.get("plans", {})
    for arch, plan_data in plans.items():
        if "metrics" not in plan_data:
            continue
        p2 = plan_data["metrics"]["phase2_time_ms"]
        
        apostador_cost = None
        equilibrista_cost = None
        tanque_cost = None
        
        for seg in plan_data.get("segments_pareto", []):
            for sol in seg.get("pareto_solutions", []):
                if sol["archetype"] == "apostador":
                    apostador_cost = sol["w_expected_cost"]
                elif sol["archetype"] == "equilibrista":
                    equilibrista_cost = sol["w_expected_cost"]
                elif sol["archetype"] == "tanque":
                    tanque_cost = sol["w_expected_cost"]
        
        summary.append({
            "departure": hour_tag,
            "archetype": arch,
            "phase2_ms": p2,
            "apostador_cost": apostador_cost,
            "equilibrista_cost": equilibrista_cost,
            "tanque_cost": tanque_cost,
        })

# Write output
with open("spacetime_results.txt", "w") as f:
    f.write("=" * 60 + "\n")
    f.write("V1.4.10 SPACE-TIME TEST RESULTS\n")
    f.write("=" * 60 + "\n\n")
    
    for row in summary:
        f.write(f"departure_time={row['departure']}  archetype={row['archetype']}\n")
        f.write(f"  Phase 2 time:        {row['phase2_ms']:.1f} ms\n")
        f.write(f"  apostador cost:      {row['apostador_cost']}\n")
        f.write(f"  equilibrista cost:   {row['equilibrista_cost']}\n")
        f.write(f"  tanque cost:         {row['tanque_cost']}\n")
        f.write("\n")
    
    # Delta
    if len(summary) >= 2:
        c03 = summary[0].get("apostador_cost")
        c08 = summary[1].get("apostador_cost")
        if c03 and c08:
            delta_pct = ((c08 - c03) / c03) * 100
            f.write(f"APOSTADOR DELTA: {c08:.2f} vs {c03:.2f} = +{delta_pct:.1f}%\n")
    
    f.write("=" * 60 + "\n")

# Also print to stdout
with open("spacetime_results.txt") as f:
    print(f.read())
