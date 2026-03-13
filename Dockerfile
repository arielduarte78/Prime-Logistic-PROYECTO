FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ENV HOME=/root PATH="/root/.local/bin:$PATH"

RUN apt-get update && apt-get install -y software-properties-common curl git build-essential \
    && add-apt-repository ppa:deadsnakes/ppa -y && apt-get update \
    && apt-get install -y python3.14 python3.14-dev python3.14-venv \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --python 3.14

COPY . .

EXPOSE 7860
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
