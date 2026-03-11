import httpx
import asyncio

async def test():
    payload = {
        "vehicles": [{"id": "v1", "origin_lat": -34.6037, "origin_lon": -58.3816, "capacity_tons": 10}],
        "destinations": [{"id": "d1", "lat": -34.5200, "lon": -58.4500, "demand_tons": 2}]
    }
    
    async with httpx.AsyncClient() as client:
        r = await client.post("http://localhost:8000/route", json=payload, headers={"X-API-Key": "dev_key_123"}, timeout=30.0)
        print("Status code:", r.status_code)
        if r.status_code == 200:
            data = r.json()
            for obj in data["pareto_solutions"]:
                if obj["archetype"] == "equilibrista":
                    print("Equilibrista first 3 coords:", obj["route_coordinates"][:3])
        else:
            print("Response:", r.text)

if __name__ == '__main__':
    asyncio.run(test())
