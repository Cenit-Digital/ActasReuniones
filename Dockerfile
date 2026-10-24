# Imagen del supervisor de las actas: ghcr.io/cenit-digital/actas-supervisor (workflow imagen.yml).
# Solo Python, psycopg y websockets: Chromium va en su propio contenedor (imagen oficial de Playwright por digest), sin
# ningún Secret. Raíz de solo lectura, sin capacidades y con usuario sin privilegios (lo fija también el pod).

# python:3.12-slim-trixie (Python 3.12.15), manifiesto linux/amd64, leído con `crane digest --platform` el 2026-10-24.
FROM docker.io/library/python:3.12-slim-trixie@sha256:e8a38829209aea82774882e5157e1f7c3e8c8393ff53a697b3580896e57f345c AS construir
# uv 0.13.5 (índice multiplataforma, `crane digest ghcr.io/astral-sh/uv:0.13.5`, 2026-10-24).
COPY --from=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/actas/venv
WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY migraciones ./migraciones
RUN uv sync --locked --no-dev --no-editable

FROM docker.io/library/python:3.12-slim-trixie@sha256:e8a38829209aea82774882e5157e1f7c3e8c8393ff53a697b3580896e57f345c
COPY --from=construir /opt/actas/venv /opt/actas/venv
ENV PATH=/opt/actas/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1
USER 1000:1000
ENTRYPOINT ["/opt/actas/venv/bin/python", "-I", "-u", "-m"]
CMD ["actas"]
