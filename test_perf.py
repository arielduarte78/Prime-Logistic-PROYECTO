import time
import json
import logging
from fastapi.testclient import TestClient
from main import app, lifespan

logging.basicConfig(level=logging.ERROR)

payload = {
  "vehicles": [
    {
      "id": "truck-01",
      "origin_lat": -34.582,
      "origin_lon": -58.417,
      "capacity_tons": 10.0,
      "max_shift_minutes": 480
    }
  ],
  "destinations": [
    {
      "id": "dest-01",
      "lat": -34.615,
      "lon": -58.435,
      "demand_tons": 2.0
    },
    {
      "id": "dest-02",
      "lat": -34.630,
      "lon": -58.390,
      "demand_tons": 1.5
    }
  ],
  "allowed_archetypes": ["equilibrista"],
  "stochastic_mode": True
}

headers = {"Authorization": "Bearer bypass-for-testing"}

import asyncio

async def run_benchmark():
    async with lifespan(app):
        client = TestClient(app)
        from src.api.identity import get_current_identity, TokenPayload
        app.dependency_overrides[get_current_identity] = lambda: TokenPayload(sub="test", client_id="test", client_name="test", role="admin", jti="test-jti", exp=9999999999, iat=1)
        
        times = []
        print("Starting Warmup...")
        res = client.post("/fleet", json=payload, headers=headers)
        if res.status_code != 200:
              print(res.text)
              return
              
        print("Running Benchmark iterations...")
        for i in range(5):
            t0 = time.time()
            res = client.post("/fleet", json=payload, headers=headers)
            dt = (time.time() - t0) * 1000
            
            if res.status_code != 200:
                print("Error:", res.text)
            else:
                times.append(dt)
                print(f"Run {i+1}: {dt:.2f} ms")
        
        if times:
            print(f"Average latency (stochastic engine hot-path): {sum(times)/len(times):.2f} ms")

asyncio.run(run_benchmark())
