"""Gestor de Caché Seguro para Prime Logistics v1.2."""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import socket
import tempfile
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from time import sleep

import networkx as nx
from filelock import FileLock, Timeout

logger = logging.getLogger(__name__)


class SafeCacheManager:
    def __init__(self, cache_dir: str = "data/osm_cache", file_mode: int = 0o600):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir = self.cache_dir / "quarantine"
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self.lock_dir = self.cache_dir / "locks"
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self.file_mode = file_mode  # Permisos para archivos guardados

    # ----------------------------------------------------------------------
    # Métricas (hooks para integración con Prometheus/StatsD)
    # ----------------------------------------------------------------------

    def _emit_metric(self, name: str, value: float = 1.0, labels: dict | None = None):
        """Hook para emitir métricas. Sobrescribir en producción."""
        # Ejemplo: if metrics: metrics.counter(name).inc()
        pass

    # ----------------------------------------------------------------------
    # Utilidades internas
    # ----------------------------------------------------------------------

    def _generate_key(self, origin: str, dest: str, zoom: int, profile: int, mode: str) -> str:
        key_raw = f"{origin}|{dest}|{zoom}|{profile}|{mode}"
        return hashlib.sha256(key_raw.encode("utf-8")).hexdigest()

    def _file_checksum(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _prepare_graph_for_write(self, graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
        """
        Devuelve una copia ligera del grafo con atributos convertidos a str
        cuando son tipos no serializables (list, dict, tuple, set).
        El grafo original no se modifica.
        """
        G = nx.MultiDiGraph()

        # Copiar nodos
        for n, data in graph.nodes(data=True):
            attrs = {
                k: (str(v) if isinstance(v, (list, dict, tuple, set)) else v)
                for k, v in data.items()
            }
            G.add_node(n, **attrs)

        # Copiar aristas preservando keys y atributos
        if graph.is_multigraph():
            for u, v, key, data in graph.edges(keys=True, data=True):
                attrs = {
                    k: (str(vv) if isinstance(vv, (list, dict, tuple, set)) else vv)
                    for k, vv in data.items()
                }
                G.add_edge(u, v, key=key, **attrs)
        else:
            for u, v, data in graph.edges(data=True):
                attrs = {
                    k: (str(vv) if isinstance(vv, (list, dict, tuple, set)) else vv)
                    for k, vv in data.items()
                }
                G.add_edge(u, v, **attrs)

        return G

    # ----------------------------------------------------------------------
    # Cuarentena robusta con metadatos forenses
    # ----------------------------------------------------------------------

    def _quarantine_file(
        self,
        path: Path,
        key: str,
        suffix: str = "",
        reason: str = "",
        exc: Exception = None,
    ) -> None:
        try:
            if not path.exists():
                logger.error("Intento de cuarentena de archivo inexistente: %s", path)
                ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
                forensic_path = self.quarantine_dir / f"{key}_{ts}.forensic.json"
                forensic = {
                    "cache_key": key,
                    "original_path": str(path),
                    "quarantine_path": None,
                    "error_reason": "missing_file",
                    "exception": repr(exc) if exc else None,
                    "timestamp": datetime.utcnow().isoformat(),
                    "host": socket.gethostname(),
                }
                with open(forensic_path, "w", encoding="utf-8") as f:
                    json.dump(forensic, f)
                self._emit_metric("cache.quarantine.count", labels={"reason": "missing_file"})
                return

            ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            dest = self.quarantine_dir / f"{key}_{ts}{suffix}"
            shutil.move(str(path), str(dest))

            stat = dest.stat()
            sha = self._file_checksum(dest)

            excerpt = None
            try:
                with open(dest, "rb") as fh:
                    excerpt = fh.read(512).decode("utf-8", errors="replace")
            except Exception:
                pass

            forensic = {
                "cache_key": key,
                "original_path": str(path),
                "quarantine_path": str(dest),
                "error_reason": reason,
                "exception": repr(exc) if exc else None,
                "timestamp": datetime.utcnow().isoformat(),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "sha256": sha,
                "excerpt": excerpt,
                "host": socket.gethostname(),
            }
            forensic_path = self.quarantine_dir / f"{key}_{ts}.forensic.json"
            with open(forensic_path, "w", encoding="utf-8") as f:
                json.dump(forensic, f)

            logger.error("Archivo movido a cuarentena: %s (sha256=%s, size=%d)", dest.name, sha, stat.st_size)
            self._emit_metric("cache.quarantine.count", labels={"reason": reason or "unknown"})
            self._emit_metric("cache.quarantine.size_bytes", value=stat.st_size, labels={"reason": reason or "unknown"})

            # Alerta si la cuarentena crece demasiado
            self._alert_if_quarantine_large()

        except Exception:
            logger.exception("Fallo catastrófico al intentar mover a cuarentena el archivo %s", path)

    def _alert_if_quarantine_large(self, threshold: int = 1000):
        """Emite una métrica de alerta si hay demasiados archivos en cuarentena."""
        try:
            count = sum(1 for _ in self.quarantine_dir.iterdir())
            # Emitir métrica de conteo para dashboards
            self._emit_metric("cache.quarantine.count_total", value=count)
            if count > threshold:
                self._emit_metric("cache.quarantine.size_alert", value=1, labels={"threshold": str(threshold)})
        except Exception:
            pass

    # ----------------------------------------------------------------------
    # Política de retención de cuarentena
    # ----------------------------------------------------------------------

    def prune_quarantine(self, retention_days: int = 30, auto: bool = False):
        """
        Elimina archivos de cuarentena más antiguos que retention_days.
        Si auto=True, el log es a nivel debug (sin alarmas); si False, se loggea resumen informativo.
        Llamar desde tareas de mantenimiento (cron, systemd timers).
        """
        cutoff = datetime.utcnow().timestamp() - retention_days * 86400
        removed = 0
        for p in self.quarantine_dir.iterdir():
            try:
                if p.is_file() and p.stat().st_mtime < cutoff:
                    p.unlink()
                    removed += 1
            except Exception as e:
                logger.debug("No se pudo eliminar %s: %s", p, e)
        if removed:
            log_func = logger.debug if auto else logger.info
            log_func("Prune: eliminados %d archivos de cuarentena con más de %d días", removed, retention_days)
            self._emit_metric("cache.prune.removed", value=removed)

    # ----------------------------------------------------------------------
    # Guardado atómico con fsync, fallback y permisos
    # ----------------------------------------------------------------------

    def save_graph(
        self,
        graph: nx.MultiDiGraph,
        origin: str,
        dest: str,
        zoom: int,
        profile: int,
        mode: str,
        lock_retries: int = 3,
    ) -> bool:
        """
        Guarda el grafo y su metadata de forma atómica y segura.
        lock_retries: número de reintentos en caso de Timeout.
        """
        key = self._generate_key(origin, dest, zoom, profile, mode)
        graph_path = self.cache_dir / f"{key}.graphml"
        meta_path = self.cache_dir / f"{key}.meta.json"
        lock_path = self.lock_dir / f"{key}.lock"

        lock = FileLock(str(lock_path), timeout=10)
        start_time = datetime.utcnow()

        for attempt in range(lock_retries):
            try:
                with lock:
                    # 1. Preparar copia sanitizada (sin mutar original)
                    safe_graph = self._prepare_graph_for_write(graph)

                    # 2. Escribir grafo a archivo temporal con fsync
                    fd, tmp_graph_name = tempfile.mkstemp(
                        dir=self.cache_dir, prefix=f"{key}.graph.tmp."
                    )
                    os.close(fd)
                    tmp_graph_path = Path(tmp_graph_name)

                    tmp_meta_path = None  # para centralizar limpieza

                    try:
                        nx.write_graphml(safe_graph, str(tmp_graph_path))

                        with open(tmp_graph_path, "rb") as fh:
                            fh.flush()
                            os.fsync(fh.fileno())

                        checksum = self._file_checksum(tmp_graph_path)

                        # 3. Preparar metadatos
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

                        # 4. Escribir metadatos a archivo temporal
                        fd2, tmp_meta_name = tempfile.mkstemp(
                            dir=self.cache_dir, prefix=f"{key}.meta.tmp."
                        )
                        os.close(fd2)
                        tmp_meta_path = Path(tmp_meta_name)

                        with open(tmp_meta_path, "w", encoding="utf-8") as f:
                            json.dump(meta, f)
                            f.flush()
                            os.fsync(f.fileno())

                        # 5. Movimientos atómicos con fallback y permisos
                        try:
                            # Mover grafo
                            try:
                                os.replace(str(tmp_graph_path), str(graph_path))
                            except OSError as e:
                                logger.warning(
                                    "os.replace falló, usando shutil.move para %s -> %s: %s",
                                    tmp_graph_path, graph_path, e
                                )
                                self._emit_metric("cache.replace.fallback", labels={"file": "graph"})
                                shutil.move(str(tmp_graph_path), str(graph_path))

                            # Mover metadatos
                            try:
                                os.replace(str(tmp_meta_path), str(meta_path))
                            except OSError as e:
                                logger.warning(
                                    "os.replace falló, usando shutil.move para %s -> %s: %s",
                                    tmp_meta_path, meta_path, e
                                )
                                self._emit_metric("cache.replace.fallback", labels={"file": "meta"})
                                shutil.move(str(tmp_meta_path), str(meta_path))

                            # Fijar permisos según file_mode (configurable)
                            try:
                                os.chmod(str(graph_path), self.file_mode)
                                os.chmod(str(meta_path), self.file_mode)
                            except Exception as e:
                                logger.debug(
                                    "No se pudieron fijar permisos en archivos de cache; "
                                    "puede ser sistema Windows o restricciones de contenedor: %s",
                                    e, exc_info=True
                                )

                        except Exception as move_error:  # noqa: F841
                            # Registrar checksum del temporal para diagnóstico
                            try:
                                tmp_checksum = self._file_checksum(tmp_graph_path)
                                logger.error("Tmp graph checksum before failure: %s", tmp_checksum)
                                self._emit_metric("cache.tmp.checksum_logged")
                            except Exception:
                                pass
                            logger.exception("Error moviendo archivos a destino final para %s", key)
                            raise

                        elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000
                        logger.info("Caché guardado exitosamente: %s (%.2f ms)", key, elapsed)
                        self._emit_metric("cache.save.duration_ms", elapsed)
                        return True

                    finally:
                        # Limpiar temporales (centralizado)
                        temp_paths = [tmp_graph_path]
                        if tmp_meta_path is not None:
                            temp_paths.append(tmp_meta_path)
                        for p in temp_paths:
                            try:
                                if p.exists():
                                    p.unlink()
                            except Exception as e:
                                logger.debug("Error limpiando temporal %s: %s", p, e)

            except Timeout:
                if attempt < lock_retries - 1:
                    sleep(0.1 * (2**attempt))  # backoff exponencial
                    continue
                logger.error("Timeout al adquirir lock para %s tras %d intentos.", key, lock_retries)
                self._emit_metric("cache.lock.timeout", labels={"operation": "save"})
                return False

            except Exception as e:
                logger.exception("Error guardando el grafo en cache: %s", e)
                self._emit_metric("cache.save.error", labels={"error": type(e).__name__})
                return False

        return False  # nunca se alcanza

    # ----------------------------------------------------------------------
    # Carga con validación y cuarentena
    # ----------------------------------------------------------------------

    def load_graph(
        self,
        origin: str,
        dest: str,
        zoom: int,
        profile: int,
        mode: str,
        lock_retries: int = 2,
    ) -> Optional[nx.MultiDiGraph]:
        """Carga el grafo validando checksum y metadata."""
        key = self._generate_key(origin, dest, zoom, profile, mode)
        graph_path = self.cache_dir / f"{key}.graphml"
        meta_path = self.cache_dir / f"{key}.meta.json"
        lock_path = self.lock_dir / f"{key}.lock"

        if not graph_path.exists() or not meta_path.exists():
            self._emit_metric("cache.load.miss")
            return None

        lock = FileLock(str(lock_path), timeout=5)
        start_time = datetime.utcnow()

        for attempt in range(lock_retries):
            try:
                with lock:
                    # Leer metadata
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        expected_checksum = meta.get("checksum")
                    except Exception as e:
                        self._quarantine_file(
                            meta_path, key, suffix=".corrupt.meta", reason="meta_corrupt", exc=e
                        )
                        self._emit_metric("cache.load.corrupt", labels={"reason": "meta_corrupt"})
                        return None

                    # Verificar checksum
                    actual_checksum = self._file_checksum(graph_path)
                    if actual_checksum != expected_checksum:
                        self._quarantine_file(
                            graph_path,
                            key,
                            suffix=".corrupt.graphml",
                            reason="checksum_mismatch",
                        )
                        self._emit_metric("cache.load.corrupt", labels={"reason": "checksum_mismatch"})
                        return None

                    # Cargar grafo
                    try:
                        G = nx.read_graphml(str(graph_path))
                    except Exception as e:
                        # Mover ambos archivos a cuarentena para análisis completo
                        self._quarantine_file(
                            graph_path,
                            key,
                            suffix=".corrupt.graphml",
                            reason="load_error",
                            exc=e,
                        )
                        self._quarantine_file(
                            meta_path,
                            key,
                            suffix=".corrupt.meta",
                            reason="load_error_meta",
                            exc=None,
                        )
                        self._emit_metric("cache.load.corrupt", labels={"reason": "load_error"})
                        return None

                    # Asegurar que sea MultiDiGraph preservando keys
                    if not isinstance(G, nx.MultiDiGraph):
                        H = nx.MultiDiGraph()
                        for n, data in G.nodes(data=True):
                            H.add_node(n, **data)
                        try:
                            for u, v, key_edge, data in G.edges(keys=True, data=True):
                                H.add_edge(u, v, key=key_edge, **data)
                        except TypeError:
                            for u, v, data in G.edges(data=True):
                                H.add_edge(u, v, **data)
                        G = H

                    elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000
                    logger.info("Caché %s recuperado y validado (%.2f ms).", key, elapsed)
                    self._emit_metric("cache.load.hit")
                    self._emit_metric("cache.load.duration_ms", elapsed)
                    return G

            except Timeout:
                if attempt < lock_retries - 1:
                    sleep(0.1 * (2**attempt))
                    continue
                logger.warning("Timeout al leer lock para %s. Ignorando caché.", key)
                self._emit_metric("cache.lock.timeout", labels={"operation": "load"})
                return None

            except Exception as e:
                logger.exception("Error inesperado en load_graph para %s: %s", key, e)
                self._emit_metric("cache.load.error", labels={"error": type(e).__name__})
                return None

        return None