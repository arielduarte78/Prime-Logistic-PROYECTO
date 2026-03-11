import sys

def view():
    with open('c:/Users/Usuario/Prime-Logistic-PROYECTO/src/api/main.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for i in range(290, 320):
        print(f"{i}: {repr(lines[i])}")
        
view()
