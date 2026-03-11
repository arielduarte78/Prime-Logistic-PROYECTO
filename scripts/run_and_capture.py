import subprocess
import os

with open("c:/Users/Usuario/Prime-Logistic-PROYECTO/scripts/torture_log.txt", "w", encoding="utf-8") as f:
    subprocess.run(["c:/Users/Usuario/Prime-Logistic-PROYECTO/venv/Scripts/python.exe", "c:/Users/Usuario/Prime-Logistic-PROYECTO/scripts/torture_test.py"], stdout=f, stderr=subprocess.STDOUT)
