import unittest
import threading
import networkx as nx
from pathlib import Path
from src.bloque1.cache_manager import SafeCacheManager

class TestSafeCacheManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = "data/test_osm_cache"
        self.cache = SafeCacheManager(cache_dir=self.test_dir)
        self.dummy_graph = nx.MultiDiGraph()
        self.dummy_graph.add_node(1, x=0.0, y=0.0)
        self.dummy_graph.add_node(2, x=1.0, y=1.0)
        self.dummy_graph.add_edge(1, 2, length=100)

    def test_save_and_load_with_checksum(self):
        ok = self.cache.save_graph(self.dummy_graph, "A", "B", 6, 1, "drive")
        self.assertTrue(ok)
        loaded = self.cache.load_graph("A", "B", 6, 1, "drive")
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded.nodes), 2)

    def test_quarantine_on_corruption(self):
        self.cache.save_graph(self.dummy_graph, "A", "B", 6, 1, "drive")
        key = self.cache._generate_key("A", "B", 6, 1, "drive")
        graph_path = self.cache.cache_dir / f"{key}.graphml"
        
        # Simulamos corrupción inyectando bytes basura en el GraphML
        with open(graph_path, "a") as f:
            f.write("<<<CORRUPTED_XML_BYTES>>>")

        # Al intentar cargar, el checksum fallará y debe devolver None
        loaded = self.cache.load_graph("A", "B", 6, 1, "drive")
        self.assertIsNone(loaded)
        
        # Verificamos que se movió a cuarentena
        self.assertFalse(graph_path.exists())
        quarantine_files = list(self.cache.quarantine_dir.glob(f"{key}_*.corrupt.graphml"))
        self.assertGreater(len(quarantine_files), 0)

    def test_corrupted_meta_json_triggers_quarantine(self):
        """Simula un meta.json corrupto y valida que se genere el forensic.json."""
        self.cache.save_graph(self.dummy_graph, "C", "D", 6, 1, "drive")
        key = self.cache._generate_key("C", "D", 6, 1, "drive")
        meta_path = self.cache.cache_dir / f"{key}.meta.json"
        
        # Sobrescribimos el meta.json con JSON inválido
        with open(meta_path, "w") as f:
            f.write("{ invalid_json: missing_quotes ")

        # Intentamos cargar
        loaded = self.cache.load_graph("C", "D", 6, 1, "drive")
        
        # Validaciones
        self.assertIsNone(loaded, "Debería devolver None ante metadata corrupta")
        self.assertFalse(meta_path.exists(), "El archivo corrupto no fue movido")
        
        # Verificar artefactos forenses
        forensic_files = list(self.cache.quarantine_dir.glob(f"{key}_*.forensic.json"))
        self.assertEqual(len(forensic_files), 1, "No se generó el archivo forensic.json")
        
        import json
        with open(forensic_files[0], "r") as f:
            forensic_data = json.load(f)
            self.assertIn("error_reason", forensic_data)
            self.assertEqual(forensic_data["cache_key"], key)

    def test_concurrent_writes(self):
        """Simula 5 hilos intentando guardar el mismo caché al mismo tiempo."""
        threads = []
        errors = []

        def worker():
            try:
                self.cache.save_graph(self.dummy_graph, "X", "Y", 6, 1, "drive")
            except Exception as e:
                errors.append(e)

        for _ in range(5):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, "Hubo errores de concurrencia al guardar.")
        loaded = self.cache.load_graph("X", "Y", 6, 1, "drive")
        self.assertIsNotNone(loaded)

    def tearDown(self):
        import shutil
        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir)

if __name__ == '__main__':
    unittest.main()
