#!/usr/bin/env pwsh
# init.ps1 — Verificación e inicialización del arnés SSD Uncle Bob (Windows/PowerShell).
# Equivalente a init.sh; delega en el motor agnóstico (Node).
$ErrorActionPreference = 'Stop'
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Write-Host '[FAIL] node no está instalado (requerido por el arnés)'
  exit 1
}
# Gancho opcional del proyecto: si existe scripts/pre-init.ps1 corre antes del motor y, si sale con error, init se
# detiene (docs/configuration.md). $LASTEXITCODE se pone a 0 antes: un gancho sin programas nativos lo deja en $null.
$preInit = Join-Path (Join-Path $PSScriptRoot 'scripts') 'pre-init.ps1'
if (Test-Path -LiteralPath $preInit) {
  $global:LASTEXITCODE = 0
  & $preInit
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
# Join-Path anidado: Windows PowerShell 5.1 solo admite dos segmentos por llamada.
$engine = Join-Path (Join-Path $PSScriptRoot '.harness') 'harness.mjs'
& node $engine init
exit $LASTEXITCODE
