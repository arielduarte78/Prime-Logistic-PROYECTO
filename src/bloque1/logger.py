# src/bloque1/logger.py
"""
Configuracion centralizada de logging para Prime Logistics V1.3.5.

Formato estandar: [Timestamp] [Level] [Module] - Message

Uso:
    from bloque1.logger import setup_logging
    setup_logging()          # INFO por defecto
    setup_logging("DEBUG")   # para desarrollo
"""
from __future__ import annotations

import logging
import sys
from typing import Optional

# Formato profesional: Timestamp + Level + Module + Message
LOG_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_initialized = False


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Configura el logging centralizado para todo el proyecto.

    Parameters
    ----------
    level : str
        Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    log_file : str, optional
        Ruta a archivo de log. Si se provee, se agrega un FileHandler.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Handler para consola (stdout, encoding-safe para Windows cp1252)
    import io
    safe_stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    console_handler = logging.StreamHandler(stream=safe_stream)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    root.addHandler(console_handler)

    # Handler opcional para archivo
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
        root.addHandler(file_handler)

    # Silenciar loggers ruidosos de terceros
    for noisy in ("urllib3", "requests", "filelock", "osmnx", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
