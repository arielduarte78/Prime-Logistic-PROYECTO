import pandas as pd
import openpyxl

path = 'prime-frontend/public/ejemplo_rutas.xlsx'
print(f"Reading {path}...")
sheets = pd.read_excel(path, sheet_name=None)

if 'Destinos' in sheets:
    print("Updating 'Destinos' sheet...")
    df = sheets['Destinos']
    df['tw_start_min'] = 0
    df['tw_end_min'] = 1440
    
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        for sheet_name, sheet_df in sheets.items():
            if sheet_name == 'Destinos':
                df.to_excel(writer, sheet_name=sheet_name, index=False)
            else:
                sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
    print("Excel file updated successfully.")
else:
    print("Sheet 'Destinos' not found.")
