# Deployment Guide - Abbey Engine

## Architecture
- **Monorepo**: Multi-platform codebase.
- **Frontend**: React + Vite (deployed on **Vercel**). Root: `prime-frontend/`.
- **Backend**: Python 3.14 + FastAPI + OR-Tools + rustworkx (deployed on **Hugging Face Spaces**).
- **Database**: Parquet files (`edges.parquet`, `nodes.parquet`) + DuckDB for lazy loading.

## Endpoints
- **Hugging Face**: [https://aphira-abbey.hf.space](https://aphira-abbey.hf.space)
- **Vercel**: [https://abbey-frontend.vercel.app](https://abbey-frontend.vercel.app) (Update with final alias).

## Environment Variables

### Frontend (Vercel)
| Variable | Value | Description |
| :--- | :--- | :--- |
| `VITE_API_URL` | `https://aphira-abbey.hf.space` | Backend URL (NO trailing slash). |
| `VITE_API_KEY` | `abbey2024` | Client-side API Key for headers. |

### Backend (Hugging Face)
| Variable | Value | Description |
| :--- | :--- | :--- |
| `PRIME_API_KEYS` | `abbey:abbey2024` | Authorized keys (`user:key` format). |

## Known Errors & Solutions
- **slowapi version**: Version 0.1.9+ is required for FastAPI 0.115 compatibility.
- **edges.parquet missing**: The Hugging Face Space fails if `data/parquet_db/edges.parquet` is missing during lifespan. Use `git lfs push` or manual upload.
- **Trailing Slash 404**: FastAPI endpoints `/fleet` vs `/fleet/`. The frontend strips trailing slashes defensively.
- **Private Space**: API requests fail if the Space is Private. Use Public or set correct CORS headers.
- **vercel.json leak**: Added to `.gitignore` to prevent leaking proxy configurations or private redirect logic.

## Post-Deployment Verification
Check endpoint: `https://aphira-abbey.hf.space/health`
Expected response:
```json
{
  "status": "ok",
  "graph_nodes": 185112,
  "version": "Abbey 1.5"
}
```
