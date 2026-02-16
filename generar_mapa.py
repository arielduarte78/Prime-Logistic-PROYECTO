import pandas as pd
import folium
import os

def generar_mapa_validacion():
    file_path = "data/red_realista_argentina.xlsx"
    if not os.path.exists(file_path):
        print("❌ No encuentro el Excel. Corré el generador primero.")
        return

    print("🗺️  Leyendo datos geográficos...")
    df_nodes = pd.read_excel(file_path, sheet_name="NODES")
    
    # Centro aproximado en Argentina
    m = folium.Map(location=[-38.0, -64.0], zoom_start=4, tiles='CartoDB positron')

    print(f"📍 Dibujando {len(df_nodes)} nodos...")
    
    # Dibujamos solo los Hubs (supply/demand > 0 o type airport) para no saturar
    for _, row in df_nodes.iterrows():
        color = 'blue'
        radius = 2
        
        # Destacar Inicio (Jujuy) y Fin (Ushuaia)
        if row['supply'] > 0:
            color = 'green'
            radius = 6
            folium.Marker([row['lat'], row['lon']], popup=f"INICIO: {row['id']}", icon=folium.Icon(color='green')).add_to(m)
        elif row['demand'] > 0:
            color = 'red'
            radius = 6
            folium.Marker([row['lat'], row['lon']], popup=f"FIN: {row['id']}", icon=folium.Icon(color='red')).add_to(m)
        elif row.get('station_type') == 'airport':
            color = 'orange'
            radius = 4
            folium.CircleMarker([row['lat'], row['lon']], radius=radius, color=color, fill=True).add_to(m)
        
    os.makedirs("output", exist_ok=True)
    out_path = "output/validacion_mapa.html"
    m.save(out_path)
    print(f"✅ Mapa guardado en: {out_path}")
    print("   -> Abrilo con tu navegador.")

if __name__ == "__main__":
    generar_mapa_validacion()