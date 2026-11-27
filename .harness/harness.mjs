#!/usr/bin/env node
// harness.mjs — Motor AGNÓSTICO del arnés SSD "Uncle Bob".
//
// No sabe de tu lenguaje: lee `harness.config.json` del directorio actual y ejecuta
// los comandos que TÚ declaras (test, mutación, lint...). Así el mismo motor sirve
// para Python, Node/TS, Go o cualquier stack.
//
//   node .harness/harness.mjs <init|test|mutate [target]|verify|help>
//
// Requisito único: Node.js >= 18 (solo stdlib). Los comandos admiten los tokens {{py}}
// (python3 o python, el que haya), {{target}} (el módulo a mutar) y {{threshold}} /
// {{threshold_pct}} (el umbral de mutación, 0.8 u 80). Ejecútalo desde la raíz de un
// proyecto que contenga `harness.config.json`.

import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const NC = process.env.NO_COLOR ? '' : '\x1b[0m';
const C = (code) => (process.env.NO_COLOR ? '' : `\x1b[${code}m`);
const green = (s) => `${C('0;32')}${s}${NC}`;
const red = (s) => `${C('0;31')}${s}${NC}`;
const yellow = (s) => `${C('0;33')}${s}${NC}`;
const bold = (s) => `${C('1')}${s}${NC}`;

const ok = (s) => console.log(`${green('[OK]')}    ${s}`);
const warn = (s) => console.log(`${yellow('[WARN]')}  ${s}`);
const fail = (s) => console.log(`${red('[FAIL]')}  ${s}`);
const rule = (s) => console.log(`\n── ${s} ${'─'.repeat(Math.max(0, 52 - s.length))}`);

const CWD = process.cwd();
const CONFIG_NAME = 'harness.config.json';

// Los editores de Windows guardan JSON con BOM y JSON.parse no lo tolera.
const stripBom = (s) => (s.charCodeAt(0) === 0xfeff ? s.slice(1) : s);
const readText = (p) => stripBom(fs.readFileSync(p, 'utf8'));

let _py = null;
/** Resuelve el intérprete de Python disponible (para el token {{py}}). */
function resolvePython() {
  if (_py !== null) return _py;
  for (const cand of ['python3', 'python']) {
    const r = spawnSync(cand, ['--version'], { encoding: 'utf8' });
    if (r.status === 0) return (_py = cand);
  }
  return (_py = 'python3'); // por defecto; fallará con mensaje claro si no existe
}

/**
 * Sustituye tokens en un comando: {{py}} → intérprete de Python, {{target}} → objetivo,
 * {{threshold}} → umbral de mutación (0.8), {{threshold_pct}} → ese umbral en % (80).
 */
function resolveCmd(cmd, tokens = {}) {
  if (!cmd) return cmd;
  // Reemplazo por FUNCIÓN: con un string, un `$` en la ruta (`a$&b`) se interpretaría.
  return cmd.replace(/\{\{\s*(py|target|threshold_pct|threshold)\s*\}\}/g, (_, k) => (k === 'py' ? resolvePython() : tokens[k] ?? ''));
}

/** Carga harness.config.json y le aplica los valores por defecto. */
function loadConfig() {
  const p = path.join(CWD, CONFIG_NAME);
  if (!fs.existsSync(p)) {
    fail(`No se encontró ${CONFIG_NAME} en ${CWD}`);
    console.log(
      `\nEjecuta el motor desde la raíz de un proyecto que contenga ${CONFIG_NAME}.\n` +
      `Copia la plantilla de la raíz del template y declara los comandos de tu stack.`,
    );
    process.exit(2);
  }
  let cfg;
  try {
    cfg = JSON.parse(readText(p));
  } catch (e) {
    fail(`${CONFIG_NAME} no es JSON válido: ${e.message}`);
    process.exit(2);
  }
  cfg.paths = Object.assign({ src: 'src', tests: 'tests' }, cfg.paths);
  cfg.commands = Object.assign({ install: '', test: '', mutate: '', lint: '', build: '' }, cfg.commands);
  // Un comando solo-espacios es la AUSENCIA de comando: sin el trim, "   " cuenta como
  // declarado en los `if (cfg.commands.X)` pero run() lo salta con status 0 (falso verde).
  for (const key of Object.keys(cfg.commands)) {
    cfg.commands[key] = cfg.commands[key].trim();
  }
  cfg.mutation = Object.assign({ threshold: 0.8, targets: [] }, cfg.mutation);
  // Tokens de todos los comandos. Entero más próximo y con toFixed antes: 0.8 * 100 es
  // 80.00000000000001 (un ceil daría 81) y 0.575 * 100 es 57.49999999999999 (daría 57).
  cfg.tokens = {
    threshold: String(cfg.mutation.threshold),
    threshold_pct: String(Math.round(Number((cfg.mutation.threshold * 100).toFixed(6)))),
  };
  cfg.standalone ??= true;
  cfg.rules = Object.assign({ require_tests_to_close: true, require_mutation_to_close: true }, cfg.rules);
  return cfg;
}

/** Ejecuta un comando de shell y devuelve su código de salida (0 si está vacío). */
function run(cmd, tokens = {}) {
  const resolved = resolveCmd(cmd, tokens);
  if (!resolved || !resolved.trim()) return 0;
  const res = spawnSync(resolved, { cwd: CWD, shell: true, encoding: 'utf8', stdio: 'inherit' });
  return res.status ?? 1;
}

/** Imprime `$ comando` (ya resuelto) y lo ejecuta; devuelve su código de salida. */
function runEcho(cmd, tokens) {
  console.log(`$ ${resolveCmd(cmd, tokens)}\n`);
  return run(cmd, tokens);
}

function dirHasFiles(dir) {
  try {
    return fs.readdirSync(path.join(CWD, dir)).some((f) => !f.startsWith('.') && f !== '__init__.py');
  } catch {
    return false; // la carpeta no existe
  }
}

// ── MCP-first (docs/mcp-first.md) ────────────────────────────────────────────
// Un repo que declara `"api": true` publica también su servidor MCP: carpeta del
// servidor, `catalogo.json` con la capa de cada herramienta (el formato de la
// centralita del Nodo: L, E, ⚠ o ✕) y un test que compare `tools/list` con él.
// Mientras tanto vale una excepción con fecha (`mcp.exception.until`), que caduca.
const MCP_DOC = 'docs/mcp-first.md';
const CAPAS_MCP = new Set(['L', 'E', '⚠', '✕']);
const SIN_RECORRER = new Set(['node_modules', '.git', '.venv', 'venv', 'target', 'dist', 'build', '__pycache__', '.harness']);

/** Hoy en AAAA-MM-DD (UTC). `HARNESS_TODAY` lo fija en los tests. */
const hoy = () => process.env.HARNESS_TODAY || new Date().toISOString().slice(0, 10);

/** true si `s` es una fecha AAAA-MM-DD que existe en el calendario. */
function fechaValida(s) {
  if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const d = new Date(`${s}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === s;
}

/** Ficheros con «test» o «spec» en el nombre, bajo `dirs` (sin dependencias ni salidas de compilación). */
function ficherosDeTest(dirs) {
  const salida = [];
  const recorrer = (rel, prof) => {
    let entradas;
    try { entradas = fs.readdirSync(path.join(CWD, rel), { withFileTypes: true }); } catch { return; }
    for (const e of entradas) {
      const hijo = path.join(rel, e.name);
      if (e.isDirectory()) { if (!SIN_RECORRER.has(e.name) && prof < 8) recorrer(hijo, prof + 1); }
      else if (/(test|spec)/i.test(e.name)) salida.push(hijo);
    }
  };
  for (const d of new Set(dirs)) recorrer(d, 0);
  return salida;
}

/** Comprueba la regla MCP-first; devuelve 0 si se cumple (o hay excepción vigente) y 1 si no. */
function checkMcpFirst(cfg) {
  const mcp = cfg.mcp && typeof cfg.mcp === 'object' ? cfg.mcp : {};
  const dir = (typeof mcp.dir === 'string' && mcp.dir.trim()) || 'mcp';
  const catalogoRel = path.join(dir, 'catalogo.json').split(path.sep).join('/');
  const ayuda = () => console.log(`        Qué se exige y cómo cumplirlo: ${MCP_DOC}`);

  if (mcp.exception !== undefined) {
    const ex = mcp.exception || {};
    if (!fechaValida(ex.until)) {
      fail('mcp.exception.until debe ser una fecha AAAA-MM-DD: una excepción sin fecha no caduca nunca');
      ayuda();
      return 1;
    }
    const detalle = `${ex.reason || 'sin motivo'}${ex.issue ? `, ${ex.issue}` : ''}`;
    if (hoy() > ex.until) {
      fail(`La excepción MCP-first caducó el ${ex.until} (${detalle}): publica el MCP o renueva la fecha con motivo`);
      ayuda();
      return 1;
    }
    ok(`Excepción MCP-first vigente hasta ${ex.until} (${detalle})`);
    return 0;
  }

  let exit = 0;
  const falta = (msg) => { fail(msg); exit = 1; };
  const absDir = path.join(CWD, dir);
  if (!fs.existsSync(absDir)) {
    falta(`api:true y no existe ${dir}/ con el servidor MCP (o declara mcp.dir)`);
    ayuda();
    return 1;
  }
  const servidor = fs.readdirSync(absDir).filter((f) => !f.startsWith('.') && f !== 'catalogo.json');
  if (servidor.length === 0) falta(`Falta el servidor MCP en ${dir}/ (solo hay catálogo)`);
  else ok(`Servidor MCP en ${dir}/`);

  const absCat = path.join(CWD, catalogoRel);
  if (!fs.existsSync(absCat)) {
    falta(`Falta ${catalogoRel}: la capa (L, E, ⚠ o ✕) de cada herramienta`);
  } else {
    let cat;
    try { cat = JSON.parse(readText(absCat)); } catch (e) { cat = undefined; falta(`${catalogoRel} no es JSON válido: ${e.message}`); }
    if (cat !== undefined) {
      if (!cat || typeof cat !== 'object' || Array.isArray(cat) || Object.keys(cat).length === 0) {
        falta(`${catalogoRel} debe ser un objeto { "herramienta": "L" | "E" | "⚠" | "✕" } con al menos una herramienta`);
      } else {
        const malas = Object.entries(cat)
          .filter(([, v]) => !CAPAS_MCP.has(typeof v === 'object' && v !== null ? v.capa : v))
          .map(([k]) => k);
        if (malas.length) falta(`Capa no válida en ${catalogoRel} (debe ser L, E, ⚠ o ✕): ${malas.join(', ')}`);
        else ok(`${Object.keys(cat).length} herramientas en ${catalogoRel}, todas con capa`);
      }
    }
  }

  const tests = ficherosDeTest([cfg.paths.tests, cfg.paths.src, dir]).filter((f) => {
    try { return fs.statSync(path.join(CWD, f)).size < 1048576 && readText(path.join(CWD, f)).includes('catalogo.json'); }
    catch { return false; }
  });
  if (tests.length === 0) falta(`Falta un test que compare tools/list con ${catalogoRel}`);
  else ok(`Test del catálogo: ${tests[0]}`);

  if (exit) ayuda();
  return exit;
}

function cmdInit() {
  const cfg = loadConfig();
  let exit = 0;

  rule('1. Entorno');
  ok(`node -> ${process.version}`);
  const [maj] = process.versions.node.split('.').map(Number);
  if (maj < 18) {
    fail('Se requiere Node.js >= 18');
    process.exit(1);
  }
  ok('Versión de Node compatible');

  rule('2. Ficheros base del arnés');
  if (cfg.standalone === false) {
    warn('standalone:false — este proyecto hereda el arnés raíz; se omite la comprobación de ficheros base.');
  } else {
    for (const f of ['AGENTS.md', 'CLAUDE.md', 'CHECKPOINTS.md']) {
      if (fs.existsSync(path.join(CWD, f))) ok(`Existe ${f}`);
      else {
        fail(`Falta archivo base: ${f}`);
        exit = 1;
      }
    }
  }

  // Lint y tests no corren sobre un árbol vacío (clon limpio): muchos linters salen
  // distinto de 0 sin ficheros. Los tests se buscan en `tests` Y en `src`: Go y Rust
  // los colocan junto al código.
  const hasCode = dirHasFiles(cfg.paths.tests) || dirHasFiles(cfg.paths.src);
  if (cfg.commands.lint) {
    rule('3. Lint');
    if (!hasCode) {
      warn(`Sin código todavía en ${cfg.paths.tests}/ ni ${cfg.paths.src}/ (nada que lintar)`);
    } else {
      if (runEcho(cfg.commands.lint, cfg.tokens) === 0) ok('Lint sin errores');
      else {
        fail('Lint con errores');
        exit = 1;
      }
    }
  }

  rule(cfg.commands.lint ? '4. Tests' : '3. Tests');
  if (!cfg.commands.test) {
    warn('No hay comando de tests declarado (commands.test vacío)');
  } else if (!hasCode) {
    warn(`Sin código todavía en ${cfg.paths.tests}/ ni ${cfg.paths.src}/ (nada que testear)`);
  } else {
    if (runEcho(cfg.commands.test, cfg.tokens) === 0) ok('Todos los tests pasan');
    else {
      fail('Hay tests rotos');
      exit = 1;
    }
  }

  if (cfg.api === true) {
    rule(cfg.commands.lint ? '5. MCP-first' : '4. MCP-first');
    if (checkMcpFirst(cfg) !== 0) exit = 1;
  }

  rule('Resumen');
  if (exit === 0) ok('Entorno listo. Puedes empezar a trabajar.');
  else fail('Entorno NO está listo. Resuelve los errores antes de avanzar.');
  process.exit(exit);
}

function cmdTest() {
  const cfg = loadConfig();
  if (!cfg.commands.test) {
    warn('commands.test vacío');
    process.exit(0);
  }
  process.exit(run(cfg.commands.test, cfg.tokens));
}

/**
 * Ejecuta la prueba de mutación. Un objetivo explícito (`mutate <target>`) manda sobre
 * `mutation.targets`; una lista vacía corre el comando una vez, sin {{target}}.
 * Verde (true) solo si TODOS los objetivos superan el umbral.
 */
function runMutation(cfg, explicitTarget = '') {
  const targets = explicitTarget ? [explicitTarget] : cfg.mutation.targets;
  if (targets.some((t) => !t.trim())) {
    fail('Objetivo de mutación vacío o en blanco: usa rutas reales en mutation.targets o en `mutate <módulo>`.');
    return false;
  }
  const list = targets.length ? targets : [''];
  const failures = [];
  for (const t of list) {
    if (list.length > 1) rule(`Mutación · ${t}`);
    if (runEcho(cfg.commands.mutate, { ...cfg.tokens, target: t }) !== 0) failures.push(t || '(proyecto)');
  }
  if (failures.length) {
    fail(`Mutación por debajo del umbral en: ${failures.join(', ')}`);
    return false;
  }
  ok(`Prueba de mutación superada (${list.length} objetivo${list.length > 1 ? 's' : ''}).`);
  return true;
}

function cmdMutate() {
  const cfg = loadConfig();
  if (!cfg.commands.mutate) {
    fail('commands.mutate vacío: declara la prueba de mutación en harness.config.json');
    process.exit(2);
  }
  const target = process.argv[3] || '';
  process.exit(runMutation(cfg, target) ? 0 : 1);
}

function cmdVerify() {
  const initRes = spawnSync(process.execPath, [__filename, 'init'], { cwd: CWD, stdio: 'inherit' });
  if ((initRes.status ?? 1) !== 0) {
    fail('verify abortado: init falló.');
    process.exit(1);
  }
  const cfg = loadConfig();
  // `init` solo AVISA si falta el comando de tests; verify, la verificación de entrega,
  // no da verde sin suite que ejecutar (ni sin mutador, más abajo).
  if (cfg.rules.require_tests_to_close && !cfg.commands.test) {
    fail('verify abortado: require_tests_to_close es true pero commands.test está vacío.');
    console.log(
      `\n  La puerta de tests es obligatoria para cerrar y no hay suite que ejecutar.\n` +
      `  Declara "commands": { "test": "..." } en ${CONFIG_NAME}, o pon\n` +
      `  "rules": { "require_tests_to_close": false } si este proyecto no cierra por tests.`,
    );
    process.exit(1);
  }
  if (cfg.rules.require_mutation_to_close) {
    rule('Prueba de mutación');
    if (!cfg.commands.mutate) {
      fail('verify abortado: require_mutation_to_close es true pero commands.mutate está vacío.');
      console.log(
        `\n  La puerta de mutación es obligatoria para cerrar y no hay mutador que ejecutar.\n` +
        `  Declara "commands": { "mutate": "..." } en ${CONFIG_NAME}, o pon\n` +
        `  "rules": { "require_mutation_to_close": false } si este proyecto no cierra por mutación.`,
      );
      process.exit(1);
    }
    if (!runMutation(cfg)) {
      fail('verify abortado: la prueba de mutación no supera el umbral.');
      process.exit(1);
    }
  }
  console.log(`\n${green(bold('[verify] Todo verde.'))}`);
  process.exit(0);
}

function help() {
  console.log(`${bold('Arnés SSD "Uncle Bob" — motor agnóstico')}

  node .harness/harness.mjs <comando>

  ${bold('init')}     Verifica entorno, ficheros base, lint y tests.
  ${bold('test')}     Ejecuta config.commands.test.
  ${bold('mutate')}   Ejecuta la prueba de mutación (config.commands.mutate [target]).
  ${bold('verify')}   init + mutación completa (verificación de entrega).
  ${bold('help')}     Esta ayuda.

  Configuración: ${CONFIG_NAME} (declara paths, commands, mutation, rules).
  Token {{py}} en commands → se resuelve a python3/python disponible.`);
}

const cmd = (process.argv[2] || 'help').toLowerCase();
const COMMANDS = { init: cmdInit, test: cmdTest, mutate: cmdMutate, verify: cmdVerify, help };
try {
  if (!Object.hasOwn(COMMANDS, cmd)) {
    fail(`Comando desconocido: ${cmd}`);
    help();
    process.exit(2);
  }
  COMMANDS[cmd]();
} catch (e) {
  fail(`Error inesperado: ${e.message} (¿${CONFIG_NAME} mal formado?)`);
  process.exit(2);
}
