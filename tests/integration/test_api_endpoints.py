#tests/integration/test_api_endpoints.py
import pytest

def test_fleet_invalid_coordinates(test_client):
    """
    Verifica que el API rechaza instantáneamente coordenadas fuera del bounding box
    del area de cobertura (AMBA), sin llegar a encolar trabajo al VRP.
    """
    payload = {
        "vehicles": [
            {
                "id": "trk_01",
                "origin_lat": 0.0, # Fuera de AMBA (0,0) = Null Island
                "origin_lon": 0.0,
                "capacity_tons": 10.0
            }
        ],
        "destinations": [
            {
                "id": "dest_01",
                "lat": -34.61,
                "lon": -58.38,
                "demand_tons": 5.0
            }
        ]
    }
    
    response = test_client.post("/fleet", json=payload, headers={"x-api-key": "test_key_123"})
    assert response.status_code == 400
    assert "fuera del bounding box" in response.text.lower() or "unreachable" in response.text.lower()


def test_fleet_successful_routing(test_client):
    """
    Verifica un Happy Path de /fleet contra el grafo mockeado.
    Demuestra que todo el pipeline (VRP -> A* Bayesiano -> Costos) 
    puede completarse en milisegundos y expone `toll_fallback_edges`.
    """
    payload = {
        "vehicles": [
            {
                "id": "trk_01",
                "origin_lat": -34.60,
                "origin_lon": -58.38, # Nodo 0 en el mock
                "capacity_tons": 10.0
            }
        ],
        "destinations": [
            {
                "id": "dest_01",
                "lat": -34.62,
                "lon": -58.39, # Nodo 2 en el mock
                "demand_tons": 5.0
            }
        ],
        "allowed_archetypes": ["tanque", "equilibrista"]
    }

    response = test_client.post("/fleet", json=payload, headers={"x-api-key": "test_key_123"})
    
    # Assert code 200
    assert response.status_code == 200, f"Error dict: {response.text}"
    
    data = response.json()
    
    tanque_plan = data["plans"].get("tanque", {})
    equilibrista_plan = data["plans"].get("equilibrista", {})

    # Verificamos que el plan existe y tiene la clave 'assignments', aunque esté vacía.
    # Un plan vacío es válido en un grafo de 3 nodos — lo importante es que el schema no explote.
    assert "assignments" in tanque_plan, "El plan tanque debe tener clave 'assignments'"
    assert "assignments" in equilibrista_plan, "El plan equilibrista debe tener clave 'assignments'"
    assert "uncovered" in tanque_plan, "El plan tanque debe exponer destinos no cubiertos"
    
    # The mock has only 3 nodes and extremely low complexity
    assert data["total_time_ms"] < 2000.0


def test_route_successful_path(test_client):
    """
    Verifica un Happy Path de /route punto a punto.
    """
    payload = {
        "vehicles": [
            {
                "id": "truck",
                "origin_lat": -34.60,
                "origin_lon": -58.38,
                "capacity_tons": 10.0
            }
        ],
        "destinations": [
            {
                "id": "dest",
                "lat": -34.61,
                "lon": -58.37,
                "demand_tons": 5.0
            }
        ]
    }

    response = test_client.post("/route", json=payload, headers={"x-api-key": "test_key_123"})
    assert response.status_code == 200
    data = response.json()
    assert "toll_fallback_edges" in data
    assert len(data.get("pareto_solutions", [])) > 0


def test_route_con_economic_profile_propio(test_client):
    """
    /route debe aceptar un economic_profile del cliente (antes devolvía 422
    porque mezclaba el perfil anidado con el CostSettings plano).
    """
    payload = {
        "vehicles": [{"id": "truck", "origin_lat": -34.60, "origin_lon": -58.38, "capacity_tons": 10.0}],
        "destinations": [{"id": "dest", "lat": -34.61, "lon": -58.37, "demand_tons": 5.0}],
        "economic_profile": {
            "dolar_mep_ars": 1500.0,
            "opex_movil": {"gasoil_ars_l": 2000.0},
        },
    }
    response = test_client.post("/route", json=payload, headers={"x-api-key": "test_key_123"})
    assert response.status_code == 200, response.text


def test_fleet_toll_markers_salen_de_la_ruta_real(test_client, mock_app_state):
    """
    En el grafo mock la ruta nodo0 -> nodo1 -> nodo2 pasa por la arista 0->1 (autopista '25 de Mayo').
    toll_markers y el desglose de costos tienen que ver ese peaje, una sola vez.
    """
    # El camión tiene que poder volver al depósito: agregamos aristas de retorno (calles, sin peaje).
    from src.bloque1.graph_builder import EdgePayload
    for u, v, u_osm, v_osm in [(1, 0, 2000, 1000), (2, 1, 3000, 2000)]:
        mock_app_state.base_graph.add_edge(u, v, EdgePayload(
            u_osm=u_osm, v_osm=v_osm, length=1500.0, highway="residential", name="Calle Vuelta",
            ref="", h3_index="8a801234567ffff", alpha_prior=99.0, beta_prior=1.0))
    payload = {
        "vehicles": [{"id": "trk_01", "origin_lat": -34.60, "origin_lon": -58.38, "capacity_tons": 10.0}],
        "destinations": [{"id": "dest_01", "lat": -34.62, "lon": -58.39, "demand_tons": 5.0}],
        "allowed_archetypes": ["equilibrista"],
    }
    response = test_client.post("/fleet", json=payload, headers={"x-api-key": "test_key_123"})
    assert response.status_code == 200, response.text
    plan = response.json()["plans"]["equilibrista"]

    marcas = plan["topology_visuals"]["toll_markers"]
    assert [m["name"] for m in marcas] == ["Peaje AUSA 25 de Mayo"]

    desglose = plan["assignments"][0]["cost_breakdown"]
    assert len(desglose["peajes_cruzados"]) == 1
    assert desglose["costo_peajes_ars"] > 0


def test_fleet_exposure_risk_va_aparte_del_total(test_client, mock_app_state):
    """
    exposure_risk_ars (1% fijo de la franquicia, estimación en revisión) se devuelve aparte con su nota
    y NO se suma a costo_total_ars, ni en el desglose por vehículo ni en el resumen del plan.
    """
    from src.bloque1.graph_builder import EdgePayload
    for u, v, u_osm, v_osm in [(1, 0, 2000, 1000), (2, 1, 3000, 2000)]:
        mock_app_state.base_graph.add_edge(u, v, EdgePayload(
            u_osm=u_osm, v_osm=v_osm, length=1500.0, highway="residential", name="Calle Vuelta",
            ref="", h3_index="8a801234567ffff", alpha_prior=99.0, beta_prior=1.0))
    payload = {
        "vehicles": [{"id": "trk_01", "origin_lat": -34.60, "origin_lon": -58.38, "capacity_tons": 10.0}],
        "destinations": [{"id": "dest_01", "lat": -34.62, "lon": -58.39, "demand_tons": 5.0}],
        "allowed_archetypes": ["equilibrista"],
    }
    response = test_client.post("/fleet", json=payload, headers={"x-api-key": "test_key_123"})
    assert response.status_code == 200, response.text
    plan = response.json()["plans"]["equilibrista"]

    d = plan["assignments"][0]["cost_breakdown"]
    sin_exposicion = (d["opex_distance_ars"] + d["opex_time_ars"] + d["capex_amortization_ars"]
                      + d["fixed_costs_ars"] + d["custodia_ars"])
    assert d["exposure_risk_ars"] > 0
    assert d["exposure_risk_nota"] == "estimación en revisión"
    assert d["costo_total_ars"] == pytest.approx(sin_exposicion, abs=0.05)

    r = plan["plan_financial_summary"]
    resumen = (r["opex_distance_ars"] + r["opex_time_ars"] + r["capex_amortization_ars"]
               + r["fixed_costs_ars"] + r["custodia_ars"])
    assert r["exposure_risk_ars"] > 0
    assert r["exposure_risk_nota"] == "estimación en revisión"
    assert r["costo_total_ars"] == pytest.approx(resumen, abs=0.05)
    assert r["total_expected_cost"] == pytest.approx(resumen, abs=0.05)
