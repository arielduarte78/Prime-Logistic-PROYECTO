import pandas as pd
from pathlib import Path

def generate_amba_dataset():
    # 1. Prepare output path
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    output_path = data_dir / "realistic_network_v135.xlsx"
    
    # 2. Setup Nodes data (Dense Urban Area - AMBA)
    nodes_data = [
        {
            "id": "BA_RETIRO", 
            "lat": -34.5913, 
            "lon": -58.3748, 
            "station_type": "factory", 
            "supply": 1000, 
            "demand": 0, 
            "proc_cost": 2.5
        },
        {
            "id": "BA_OBELISCO", 
            "lat": -34.6037, 
            "lon": -58.3816, 
            "station_type": "warehouse", 
            "supply": 500, 
            "demand": 500, 
            "proc_cost": 1.2
        },
        {
            "id": "BA_AVELLANEDA", 
            "lat": -34.6625, 
            "lon": -58.3653, 
            "station_type": "warehouse", 
            "supply": 200, 
            "demand": 800, 
            "proc_cost": 1.0
        },
        {
            "id": "BA_LANUS", 
            "lat": -34.7049, 
            "lon": -58.3900, 
            "station_type": "client", 
            "supply": 0, 
            "demand": 900, 
            "proc_cost": 0.0
        }
    ]
    df_nodes = pd.DataFrame(nodes_data)

    # 3. Setup Fleet data
    fleet_data = [
        {
            "mode": "truck", 
            "capacity": 500, 
            "cost_per_km": 1.5, 
            "max_range_km": 150.0, 
            "allowed_stations": "factory,warehouse,client"
        },
        {
            "mode": "car", 
            "capacity": 50, 
            "cost_per_km": 0.5, 
            "max_range_km": 300.0, 
            "allowed_stations": "factory,warehouse,client"
        }
    ]
    df_fleet = pd.DataFrame(fleet_data)

    # 4. Write to Excel
    print(f"Generating new AMBA dataset at {output_path}...")
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df_nodes.to_excel(writer, sheet_name='NODES', index=False)
        df_fleet.to_excel(writer, sheet_name='FLEET', index=False)
    
    print("[WAIT] Verifying generated sheet...")    
    # Quick sanity check
    df_verify = pd.read_excel(output_path, sheet_name='NODES')
    print(f"[OK] AMBA Dataset created successfully with {len(df_verify)} nodes and {len(df_fleet)} vehicles.")

if __name__ == "__main__":
    generate_amba_dataset()
