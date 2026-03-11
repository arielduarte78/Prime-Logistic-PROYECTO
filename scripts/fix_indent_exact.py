import sys

def fix_indentation():
    with open('c:/Users/Usuario/Prime-Logistic-PROYECTO/src/api/main.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for i in range(298, len(lines)):
        line = lines[i]
        
        # Line 299: archetipos = {
        if line.startswith('        archetipos = {'):
            lines[i] = '            ' + line[8:]
        elif line.startswith('        "tanque":'):
            lines[i] = '                ' + line[8:]
        elif line.startswith('        "apostador":'):
            lines[i] = '                ' + line[8:]
        elif line.startswith('        "equilibrista":'):
            lines[i] = '                ' + line[8:]
        elif line.startswith('        "unicornio":'):
            lines[i] = '                ' + line[8:]
        elif line.startswith('        }'):
            lines[i] = '            ' + line[8:]

        elif line.startswith('        # 9. Construir respuesta'):
            lines[i] = '            ' + line[8:]
        elif line.startswith('        pareto_solutions = []'):
            lines[i] = '            ' + line[8:]
        elif line.startswith('        soluciones_validas ='):
            lines[i] = '            ' + line[8:]
        elif line.startswith('        if soluciones_validas:'):
            lines[i] = '            ' + line[8:]
        elif line.startswith('        w_min ='):
            lines[i] = '                ' + line[8:]
        elif line.startswith('        w_max ='):
            lines[i] = '                ' + line[8:]
        elif line.startswith('        def normalize_confidence'):
            lines[i] = '                ' + line[8:]
        elif line.startswith('            if w_max == w_min:'):
            lines[i] = '                    ' + line[12:]
        elif line.startswith('                return 100.0'):
            lines[i] = '                        ' + line[16:]
        elif line.startswith('            return round'):
            lines[i] = '                    ' + line[12:]
        elif line.startswith('        else:'):
            lines[i] = '            ' + line[8:]
        elif line.startswith('        normalize_confidence ='):
            lines[i] = '                ' + line[8:]
        elif line.startswith('        for archetype_name,'):
            lines[i] = '            ' + line[8:]
        elif line.startswith('        if sol is None:'):
            lines[i] = '                ' + line[8:]
        elif line.startswith('            continue'):
            lines[i] = '                    ' + line[12:]
        elif line.startswith('        confidence ='):
            lines[i] = '                ' + line[8:]
        elif line.startswith('        pareto_solutions.append'):
            lines[i] = '                ' + line[8:]
        elif line.startswith('            archetype='):
            lines[i] = '                    ' + line[12:]
        elif line.startswith('            w_survival='):
            lines[i] = '                    ' + line[12:]
        elif line.startswith('            w_expected_cost='):
            lines[i] = '                    ' + line[12:]
        elif line.startswith('            route_nodes='):
            lines[i] = '                    ' + line[12:]
        elif line.startswith('            confidence='):
            lines[i] = '                    ' + line[12:]
        elif line.startswith('        ))'):
            lines[i] = '                ' + line[8:]
            
        elif line.startswith('        proc_time_ms ='):
            lines[i] = '            ' + line[8:]
        elif line.startswith('        return RouteResponse('):
            lines[i] = '            ' + line[8:]
        elif line.startswith('            processing_time_ms='):
            lines[i] = '                ' + line[12:]
        elif line.startswith('            total_edges='):
            lines[i] = '                ' + line[12:]
        elif line.startswith('            pareto_solutions='):
            lines[i] = '                ' + line[12:]
        elif line.startswith('        )'):
            if lines[i] == '        )\n' or lines[i] == '        )\r\n':
                lines[i] = '            ' + line[8:]
                
        elif line.startswith('    except HTTPException:'):
            lines[i] = '        ' + line[4:]
        elif line.startswith('    except Exception as e:'):
            lines[i] = '        ' + line[4:]
        elif line.startswith('        logger.error'):
            lines[i] = '            ' + line[8:]
        elif line.startswith('        raise HTTPException'):
            # Only unindent the general exception raise
            if i > 330:
                lines[i] = '            ' + line[8:]
        elif line.startswith('    finally:'):
            # Only unindent the try-finally
            if i > 330:
                lines[i] = '        ' + line[4:]
        elif line.startswith('        try:'):
            if i > 330:
                lines[i] = '            ' + line[8:]
        elif line.startswith('            del legacy_graph,'):
            if i > 330:
                lines[i] = '                ' + line[12:]
        elif line.startswith('            gc.collect()'):
            if i > 330:
                lines[i] = '                ' + line[12:]
        elif line.startswith('        except NameError:'):
            if i > 330:
                lines[i] = '            ' + line[8:]
        elif line.startswith('            pass'):
            if i > 330:
                lines[i] = '                ' + line[12:]
                
        # Semaphore release
        elif line.startswith('finally:'):
            lines[i] = '    ' + line
        elif line.startswith('    semaphore.release()'):
            lines[i] = '        ' + line[4:]

    with open('c:/Users/Usuario/Prime-Logistic-PROYECTO/src/api/main.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
        
fix_indentation()
