import os

# Configuración del empaquetador
PROJECT_ROOT = "."
OUTPUT_FILE = "contexto_proyecto.txt"
EXCLUDE_DIRS = {'.git', 'venv', '__pycache__', '.ipynb_checkpoints', 'output'}
EXCLUDE_FILES = {OUTPUT_FILE, '.DS_Store'}

def get_project_context():
    context = []
    
    # 1. Generar el árbol de directorios para que el AI vea la jerarquía
    context.append("### ESTRUCTURA DEL PROYECTO ###\n")
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        level = root.replace(PROJECT_ROOT, '').count(os.sep)
        indent = ' ' * 4 * level
        context.append(f"{indent}{os.path.basename(root)}/")
        sub_indent = ' ' * 4 * (level + 1)
        for f in files:
            if f not in EXCLUDE_FILES:
                context.append(f"{sub_indent}{f}")
    
    context.append("\n" + "="*80 + "\n")
    context.append("### CONTENIDO DE LOS ARCHIVOS ###\n")

    # 2. Leer y formatear cada archivo
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if f.endswith(('.py', '.yaml', '.yml', '.txt')) and f not in EXCLUDE_FILES:
                full_path = os.path.join(root, f)
                context.append(f"\n--- FILE: {full_path} ---")
                context.append("```" + (f.split('.')[-1] if '.' in f else ''))
                try:
                    with open(full_path, 'r', encoding='utf-8') as file:
                        context.append(file.read())
                except Exception as e:
                    context.append(f"ERROR LEYENDO ARCHIVO: {e}")
                context.append("```\n")

    return "\n".join(context)

# Ejecución y guardado
with open(OUTPUT_FILE, "w", encoding='utf-8') as out:
    out.write(get_project_context())

print(f"✓ Contexto empaquetado con éxito en: {OUTPUT_FILE}")