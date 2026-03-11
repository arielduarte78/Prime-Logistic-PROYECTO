.PHONY: help install run test clean

help:
	@echo "Prime Logistics - Comandos Disponibles:"
	@echo "  make install    - Sincroniza las dependencias en el entorno usando uv sync"
	@echo "  make run        - Inicia el motor FastAPI (uv run uvicorn src.api.main:app)"
	@echo "  make test       - Ejecuta la suite de pruebas (uv run pytest)"
	@echo "  make clean      - Limpia los caches de Python (__pycache__, pytest) y borra los audit logs"

install:
	uv sync

run:
	uv run uvicorn src.api.main:app --port 8000 --reload

test:
	uv run pytest tests/

clean:
	@echo "Limpiando caches y datos temporales..."
	-rm -rf .pytest_cache
	-rm -rf tests/.pytest_cache
	-rm -rf data/audit_logs/*.jsonl
	-find . -type d -name "__pycache__" -exec rm -rf {} +
	@echo "Limpieza completada."
