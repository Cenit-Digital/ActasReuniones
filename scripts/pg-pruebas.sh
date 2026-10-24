#!/usr/bin/env bash
# pg-pruebas.sh — PostgreSQL 18 local y efímero para los tests de integración, sin root y sin Docker.
#
# Uso:
#   scripts/pg-pruebas.sh instalar   # extrae los binarios de la imagen oficial fijada por digest (crane)
#   scripts/pg-pruebas.sh arrancar   # initdb en un directorio temporal y arranca (imprime el DSN)
#   scripts/pg-pruebas.sh dsn        # imprime el DSN (export ACTAS_DSN_PRUEBAS="$(scripts/pg-pruebas.sh dsn)")
#   scripts/pg-pruebas.sh parar      # para el servidor y borra los datos
#
# Procedencia de los binarios: la imagen OFICIAL de PostgreSQL fijada por digest
# (postgres:18.6-trixie, la misma que el PostgreSQL compartido del servidor, ADR 0019 de KubernetesInfrastructure).
# `crane export` la descarga del registro verificando el digest (direccionamiento por contenido) y se extraen
# solo usr/lib/postgresql, usr/share/postgresql y las bibliotecas, sin las de glibc (se usa la del sistema).
# Los binarios de Debian son reubicables (bin/ y share/ conservan su ruta relativa). Necesita `crane` en el PATH
# (imagenes/herramientas.sh lo instala verificado).
#
# Variables:
#   PG_PRUEBAS_RAIZ  dónde se extraen los binarios (por defecto ~/.local/opt/postgresql-18.6)
#   PG_PRUEBAS_DIR   datos del clúster efímero (por defecto ${TMPDIR:-/tmp}/actas-pg)
# El socket Unix va dentro de PG_PRUEBAS_DIR si la ruta cabe en el límite de 107 bytes de sun_path; si no,
# en un directorio corto creado con mktemp. El servidor no escucha por TCP.
set -euo pipefail

AQUI="$(cd "$(dirname "$0")/.." && pwd)"
# postgres:18.6-trixie, la misma imagen que el PostgreSQL compartido del servidor (ADR 0019 de KubernetesInfrastructure).
IMAGEN_PG="docker.io/library/postgres:18.6-trixie@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6"
RAIZ="${PG_PRUEBAS_RAIZ:-$HOME/.local/opt/postgresql-18.6}"
DATOS_DIR="${PG_PRUEBAS_DIR:-${TMPDIR:-/tmp}/actas-pg}"
BIN="$RAIZ/usr/lib/postgresql/18/bin"
export LD_LIBRARY_PATH="$RAIZ/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
BASE="actas_pruebas"

falla() { echo "[pg-pruebas] ERROR: $*" >&2; exit 1; }

instalar() {
  if [ -x "$BIN/postgres" ] && "$BIN/postgres" --version | grep -q " 18\."; then
    echo "[pg-pruebas] ya instalado en $RAIZ"; return
  fi
  [ "$(uname -m)" = "x86_64" ] || falla "solo amd64"
  [ -n "$IMAGEN_PG" ] || falla "no se encontró IMAGEN_PG"
  command -v crane >/dev/null || falla "falta crane en el PATH"
  mkdir -p "$RAIZ"
  # Sin LD_LIBRARY_PATH mientras se extrae: tar y rm no deben cargar las bibliotecas de la imagen.
  local ldp="$LD_LIBRARY_PATH"; unset LD_LIBRARY_PATH
  crane export --platform linux/amd64 "$IMAGEN_PG" - |
    tar -x -C "$RAIZ" --no-same-owner --no-same-permissions --wildcards \
      'usr/lib/postgresql/*' 'usr/share/postgresql/*' 'usr/lib/x86_64-linux-gnu/*'
  for l in libc.so.6 libm.so.6 libpthread.so.0 libdl.so.2 librt.so.1 libresolv.so.2 ld-linux-x86-64.so.2 \
           libmvec.so.1 libutil.so.1 libanl.so.1 libnss_files.so.2 libnss_dns.so.2; do
    rm -f "$RAIZ/usr/lib/x86_64-linux-gnu/$l"
  done
  export LD_LIBRARY_PATH="$ldp"
  "$BIN/postgres" --version
}

socket_dir() {
  if [ -f "$DATOS_DIR/socket" ]; then cat "$DATOS_DIR/socket"; return; fi
  local candidato="$DATOS_DIR/s"
  # sun_path admite 107 bytes; el nombre del socket añade «/.s.PGSQL.5432».
  if [ $((${#candidato} + 15)) -gt 100 ]; then candidato="$(mktemp -d "${TMPDIR:-/tmp}/pgs.XXXXXX")"; fi
  mkdir -p "$candidato"; chmod 700 "$candidato"
  echo "$candidato" > "$DATOS_DIR/socket"
  echo "$candidato"
}

dsn() {
  [ -f "$DATOS_DIR/socket" ] || falla "no arrancado (scripts/pg-pruebas.sh arrancar)"
  echo "postgresql:///$BASE?host=$(cat "$DATOS_DIR/socket")&user=$(id -un)"
}

arrancar() {
  [ -x "$BIN/postgres" ] || instalar
  mkdir -p "$DATOS_DIR"; chmod 700 "$DATOS_DIR"
  local sock; sock="$(socket_dir)"
  if [ ! -f "$DATOS_DIR/datos/PG_VERSION" ]; then
    "$BIN/initdb" -D "$DATOS_DIR/datos" -U "$(id -un)" -A trust -E UTF8 --locale=C.UTF-8 >/dev/null
  fi
  if ! "$BIN/pg_ctl" -D "$DATOS_DIR/datos" status >/dev/null 2>&1; then
    # Ligero para no molestar a producción: sin JIT, buffers pequeños y sin fsync (los datos son desechables).
    nice -n 19 "$BIN/pg_ctl" -D "$DATOS_DIR/datos" -l "$DATOS_DIR/postgres.log" -w -s start -o \
      "-c listen_addresses='' -c unix_socket_directories='$sock' -c jit=off -c shared_buffers=32MB \
       -c max_connections=20 -c fsync=off -c synchronous_commit=off -c full_page_writes=off"
  fi
  "$BIN/psql" -h "$sock" -d postgres -Atqc "SELECT 1 FROM pg_database WHERE datname='$BASE'" | grep -q 1 \
    || "$BIN/createdb" -h "$sock" "$BASE"
  dsn
}

parar() {
  if [ -f "$DATOS_DIR/datos/PG_VERSION" ]; then
    "$BIN/pg_ctl" -D "$DATOS_DIR/datos" -m fast -w -s stop || true
  fi
  if [ -f "$DATOS_DIR/socket" ]; then
    local sock; sock="$(cat "$DATOS_DIR/socket")"
    case "$sock" in "$DATOS_DIR"/*) ;; *) rm -rf "$sock" ;; esac
  fi
  rm -rf "$DATOS_DIR"
  echo "[pg-pruebas] parado y borrado"
}

case "${1:-}" in
  instalar) instalar ;;
  arrancar) arrancar ;;
  dsn) dsn ;;
  parar) parar ;;
  *) echo "uso: $0 {instalar|arrancar|dsn|parar}" >&2; exit 2 ;;
esac
