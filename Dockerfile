# Imagen del supervisor de las actas: ghcr.io/cenit-digital/actas-supervisor (workflow imagen.yml). La misma imagen sirve el
# panel de F2 con otro argumento (`args: ["actas.panel"]`, KubernetesInfrastructure#287).
# Solo Python, psycopg, websockets y lo del panel (Starlette, Jinja2, python-multipart y uvicorn): Chromium va en su propio
# contenedor (imagen oficial de Playwright por digest), sin ningún Secret. Raíz de solo lectura, sin capacidades y con usuario
# sin privilegios (lo fija también el pod).

# Python 3.12.16, manifiesto linux/amd64. La base aún no incorpora la corrección de zlib de Debian DSA-6613-1 ni la de libzstd1
# (CVE-2026-124851, HIGH, arreglada en -1+deb13u1; trivy de la CI lo marca desde el 2026-11-25).
FROM docker.io/library/python:3.12-slim-trixie@sha256:05a994d2344eb364cc186910f4fc8786a38215f39f00d0acc25bff33a08f4177 AS base
RUN apt-get update && apt-get install -y --no-install-recommends zlib1g=1:1.3.dfsg+really1.3.1-1+deb13u1 \
    libzstd1=1.5.7+dfsg-1+deb13u1 \
    && rm -rf /var/lib/apt/lists/*

FROM base AS construir
# uv 0.13.5 (índice multiplataforma, `crane digest ghcr.io/astral-sh/uv:0.13.5`, 2026-10-24).
COPY --from=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/actas/venv
WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY migraciones ./migraciones
COPY textos ./textos
RUN uv sync --locked --no-dev --no-editable

FROM base
COPY --from=construir /opt/actas/venv /opt/actas/venv
ENV PATH=/opt/actas/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1
USER 1000:1000
# El commit de la imagen, para el latido del supervisor (V4 de KubernetesInfrastructure#298): lo pasa imagen.yml (build-args).
# Al final, para no invalidar la caché de las capas de arriba.
ARG REVISION=""
ENV ACTAS_REVISION=$REVISION
ENTRYPOINT ["/opt/actas/venv/bin/python", "-I", "-u", "-m"]
CMD ["actas"]
