# tests/stochopti/conftest.py — Isolated conftest for stochopti tests.
# This file exists to prevent pytest from walking up to the root conftest.py,
# which imports fastapi and other Abbey domain dependencies.
