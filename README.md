# Self Reflective Critic Agent

Deterministic task-metric checks with a Python CLI, FastAPI service, a browser-only evaluator, and an in-memory HMAC audit chain. This repository also retains a separate legacy `reflect_critic` package and an enrichment module.

**Scope:** The rules are illustrative thresholds, not validated hallucination detection, clinical decision support, or a comprehensive PHI screening/de-identification system. Do not submit patient information or other sensitive records.

## Browser console

Open `web/index.html` locally to use the standalone evaluator, which runs entirely in the browser without Python or an API. It reports the evaluation source as **browser-local (unsigned)** and can export a JSON result. No data is sent to the project server in this mode.

When the same interface is served at the root of the FastAPI service, it uses `POST /api/audit` and produces process-local signed audit entries. If the server is unreachable, the interface clearly identifies the switch to local evaluation. The Python modules cannot run directly on GitHub Pages; the static evaluator uses JavaScript with equivalent trigger conditions.

## Rule definitions

The current `agents` worker pipeline applies:

| Trigger | Alert |
| --- | --- |
| Primary metric > 25 | Elevated |
| Secondary metric > 12 | Elevated |
| Critical flag enabled | Critical |
| Status contains `DISCORDANT`, `ANOMALY`, `MUTANT`, `VIOLATION`, `FAIL`, or `REJECT` | Elevated |

The overall tier is critical if any critical alert occurs, otherwise elevated if any elevated alert occurs, otherwise routine. These rules do not infer truthfulness from generated text or assess clinical validity.

## Installation and usage

Requires Python 3.10+.

```bash
python -m pip install -e ".[api]"
python cli.py audit --task-id T-001 --target TARGET-01 --primary 29.4 --secondary 14.8
python cli.py batch --input sample.csv --output results.csv
python cli.py verify-audit
python cli.py serve --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` for the served console; API documentation is available at `/docs`.

The installed CLI entry points are `self-reflective-critic-agent` (newer worker pipeline) and `self-reflective-critic-engine` (legacy package). The latter also supports `audit`, `batch`, `chat`, and `serve`.

API endpoints: `GET /health`, `POST /api/audit`, `POST /api/chat` (deterministic mock response), `GET /api/audit/logs`, `GET /metrics` (JSON), and `GET /metrics/prometheus` (Prometheus text).

## Audit and privacy considerations

- Audit entries include metadata and a SHA-256 hash of the serialized event details, plus a chain of HMAC-SHA256 signatures. Verification checks signatures and chain links.
- `AUDIT_SECRET_KEY` may be supplied through a secure environment variable. Without it, the process generates an ephemeral secret: signatures cannot be verified independently after restart. The trail itself is memory-only and is not an immutable external audit log.
- Basic regex checks attempt to reject some obvious identifiers, including ones nested in request attributes. They do **not** establish HIPAA compliance or guarantee removal of all personal data.
- The FastAPI endpoints are **unauthenticated**. Bind to loopback or use appropriate authentication and network controls before any externally reachable deployment.
- The static browser evaluator does not contact a server in browser-only mode. JSON exports are saved by the user's browser. No analytics are included in the static app.

## Testing

```bash
python -m pip install -e ".[api]" pytest httpx
python -m pytest -q
node --check web/app.js
node --test web/app.test.cjs
```

GitHub Actions runs the Python tests on Python 3.10, 3.11, and 3.12, plus JavaScript syntax and rule tests.

## Docker

```bash
cp .env.example .env
# Replace the example value with a long random signing key before running.
docker compose up --build
```

Compose binds the service to `127.0.0.1:8000` by default. No signing key is embedded in the source or image.

## Technology and compatibility

Python 3.10+, Pydantic v2, FastAPI, Uvicorn, standard-library HMAC/SHA-256; plain HTML, CSS, and JavaScript for the browser interface. Current Chrome, Firefox, Safari, and Edge releases are the intended browser targets. The static site requires JavaScript and does not require WebAssembly, Pyodide, or a backend.

## License

MIT; see [LICENSE](LICENSE).
