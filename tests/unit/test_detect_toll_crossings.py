import rustworkx as rx
from src.api.schemas import EconomicProfile
from src.bloque1.graph_builder import EdgePayload, NodePayload
from src.block5.vrp_orchestrator import _detect_toll_crossings


def _grafo_lineal(nombres):
    """Grafo 0 -> 1 -> 2 ... con una arista por nombre."""
    g = rx.PyDiGraph()
    for i in range(len(nombres) + 1):
        g.add_node(NodePayload(osm_id=i, lat=-34.6 - i * 0.001, lon=-58.4))
    for i, nombre in enumerate(nombres):
        g.add_edge(i, i + 1, EdgePayload(u_osm=i, v_osm=i + 1, length=300.0, highway="motorway",
                                         name=nombre, ref="", h3_index="", alpha_prior=99.0, beta_prior=1.0))
    return g


def test_aristas_seguidas_de_la_misma_autopista_son_un_solo_cruce():
    g = _grafo_lineal(["Autopista 25 de Mayo"] * 5)
    marcas = _detect_toll_crossings(list(range(6)), None, g, EconomicProfile(), "08:00")
    assert len(marcas) == 1


def test_dos_autopistas_distintas_son_dos_cruces():
    g = _grafo_lineal(["Autopista 25 de Mayo"] * 3 + ["Acceso Norte"] * 3)
    marcas = _detect_toll_crossings(list(range(7)), None, g, EconomicProfile(), "08:00")
    assert [m["name"] for m in marcas] == ["Peaje AUSA 25 de Mayo", "Peaje Acceso Norte"]
