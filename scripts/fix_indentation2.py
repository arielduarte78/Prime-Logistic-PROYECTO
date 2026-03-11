import sys

def fix_indentation():
    with open('c:/Users/Usuario/Prime-Logistic-PROYECTO/src/api/main.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for i in range(298, len(lines)):
        if lines[i].startswith('            '):
            if "except HTTPException:" not in lines[i] and "except Exception as e:" not in lines[i] and "logger.error" not in lines[i] and "raise HTTPException" not in lines[i] and "finally:" not in lines[i] and "del legacy_graph" not in lines[i] and "gc.collect()" not in lines[i] and "pass" not in lines[i] and "except NameError:" not in lines[i] and "try:" not in lines[i] and "finally:" not in lines[i]:
                lines[i] = lines[i][4:]
                
        # Hardcode the specific lines matching what we want to unindent:
        if i >= 298 and i <= 340 and lines[i].startswith('            '):
            lines[i] = lines[i][4:]
            
    with open('c:/Users/Usuario/Prime-Logistic-PROYECTO/src/api/main.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
        
fix_indentation()
