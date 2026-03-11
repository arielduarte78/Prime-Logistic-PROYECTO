import sys

def fix_indentation():
    with open('c:/Users/Usuario/Prime-Logistic-PROYECTO/src/api/main.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    in_try_block = False
    for i in range(205, 297):
        if lines[i].startswith('            '):
            lines[i] = lines[i][4:]
            
    with open('c:/Users/Usuario/Prime-Logistic-PROYECTO/src/api/main.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
        
fix_indentation()
