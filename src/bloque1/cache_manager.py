from __future__ import annotations


import hashlib
import json
import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import networkx as nx
from filelock import FileLock


class SafeCacheManager:
    def __init__(self, cache_dir: str = "data/osm_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir = self.cache_dir / "quarantine"
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self.lock_dir = self.cache_dir / "locks"
        self.lock_dir.mkdir(parents=True, exist_ok=True)

    def _generate_key(self, origin: str, dest: str, zoom: int, profile: int, mode: str) -> str:
        key_raw = f"{origin}|{dest}|{zoom}|{profile}|{mode}"
        return hashlib.sha256(key_raw.encode("utf-8")).hexdigest()

    def save_graph(
        self,
        graph: "nx.MultiDiGraph",
        origin: str,
        dest: str,
        zoom: int,
        profile: int,
        mode: str,
    ) -> bool:
        """
        Guarda el grafo y su metadata de forma atómica.
        Usa networkx.write_graphml para serializar y evitar dependencia en osmnx.
        """
        key = self._generate_key(origin, dest, zoom, profile, mode)
        graph_path = self.cache_dir / f"{key}.graphml"
        meta_path = self.cache_dir / f"{key}.meta.json"
        lock_path = self.lock_dir / f"{key}.lock"

        lock = FileLock(str(lock_path))
        with lock:
            # Guardado atómico: escribir en temp y mover
            with tempfile.NamedTemporaryFile(delete=False, dir=self.cache_dir) as tmp:
                tmp_path = Path(tmp.name)
            try:
                # usar networkx para serializar
                nx.write_graphml(graph, str(tmp_path))
                checksum = self._file_checksum(tmp_path)
                meta = {
                    "cache_key": key,
                    "origin": origin,
                    "dest": dest,
                    "zoom": zoom,
                    "profile": profile,
                    "mode": mode,
                    "checksum": checksum,
                    "saved_at": datetime.utcnow().isoformat(),
                }
                shutil.move(str(tmp_path), str(graph_path))
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f)
                return True
            except Exception as e:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass
                logging.exception("Error saving graph to cache: %s", e)
                return False

    def load_graph(
        self, origin: str, dest: str, zoom: int, profile: int, mode: str
    ) -> Optional["nx.MultiDiGraph"]:
        """
        Carga el grafo validando checksum y metadata.
        Usa networkx.read_graphml para deserializar y evitar dependencia en osmnx.
        """
        key = self._generate_key(origin, dest, zoom, profile, mode)
        graph_path = self.cache_dir / f"{key}.graphml"
        meta_path = self.cache_dir / f"{key}.meta.json"
        lock_path = self.lock_dir / f"{key}.lock"

        if not graph_path.exists() or not meta_path.exists():
            return None

        lock = FileLock(str(lock_path))
        with lock:
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                expected_checksum = meta.get("checksum")
            except Exception as e:
                self._quarantine_file(meta_path, key, reason="meta_corrupt", exc=e)
                return None

            actual_checksum = self._file_checksum(graph_path)
            if actual_checksum != expected_checksum:
                self._quarantine_file(
                    graph_path, key, suffix=".corrupt.graphml", reason="checksum_mismatch"
                )
                return None

            try:
                # usar networkx para cargar
                G = nx.read_graphml(str(graph_path))
                # networkx.read_graphml puede devolver Graph; convertir a MultiDiGraph si es necesario
                if not isinstance(G, nx.MultiDiGraph):
                    H = nx.MultiDiGraph()
                    H.add_nodes_from(G.nodes(data=True))
                    H.add_edges_from(G.edges(data=True))
                    G = H
                return G
            except Exception as e:
                self._quarantine_file(
                    graph_path, key, suffix=".corrupt.graphml", reason="load_error", exc=e
                )
                return None

    # Métodos auxiliares
    def _file_checksum(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _quarantine_file(
        self, path: Path, key: str, suffix: str = "", reason: str = "", exc: Exception = None
    ):
        try:
            ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            dest_name = f"{key}_{ts}{suffix}"
            dest = self.quarantine_dir / dest_name
            shutil.move(str(path), str(dest))
            forensic = {
                "cache_key": key,
                "original_path": str(path),
                "quarantine_path": str(dest),
                "error_reason": reason,
                "exception": repr(exc),
                "timestamp": datetime.utcnow().isoformat(),
            }
            forensic_path = self.quarantine_dir / f"{key}_{ts}.forensic.json"
            with open(forensic_path, "w", encoding="utf-8") as f:
                json.dump(forensic, f)
        except Exception:
            logging.exception("Failed to quarantine file %s", path)
