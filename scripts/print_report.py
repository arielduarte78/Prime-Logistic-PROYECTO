import sys
with open('batch_zone_out.txt', 'r', encoding='utf-16le') as f:
    text = f.read()
    if 'REPORTE STOCHASTIC BATCH' in text:
        idx = text.find('REPORTE STOCHASTIC BATCH')
        with open('final_extract.txt', 'w', encoding='utf-8') as out:
            out.write(text[max(0, idx-500):].strip())
