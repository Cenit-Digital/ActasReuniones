#!/usr/bin/env node
// impeccable-gate.mjs — Puerta de diseño de la CI: el detector de Impeccable sobre la web del proyecto.
//
//   node .harness/impeccable-gate.mjs                     código fuente (`ui.paths`); lo corre el workflow de la plantilla
//   node .harness/impeccable-gate.mjs --rendered <url>    páginas renderizadas (`ui.routes` sobre <url>); lo corre la CI
//                                                         de cada proyecto con la app ya servida (docs/impeccable.md)
//
// Lee `ui` de harness.config.json, que es obligatorio. `"paths": []` declara que no hay web: lo dice y sale con 0 sin
// ejecutar el detector.
// Con web, exige:
//   1. La skill instalada en .claude/skills/impeccable y .agents/skills/impeccable, en la versión que fija esta puerta,
//      con su LICENSE y su NOTICE.md.
//   2. Hooks de Impeccable apagados: ni en .claude/settings.json ni en .codex/hooks.json, y `hook.enabled: false` si
//      existe .impeccable/config.json (el agente sin interfaz no puede aprobarlos).
//   3. Excepciones solo justificadas: nada en detector.ignoreRules ni detector.ignoreFiles (silencian demasiado), ni
//      designSystem.enabled: false, ni un .impeccable/config.local.json en el repo; cada detector.ignoreValues nombra un
//      valor concreto y lleva motivo, y cada comentario `impeccable-disable…` nombra sus reglas y lleva motivo.
//   4. `ui.routes` declarado: el análisis del código solo aplica las reglas por patrón; las de página (contraste,
//      tamaños, jerarquía…) necesitan la página renderizada.
//   5. Código: cada ruta de `ui.paths` existe y tiene algo que analizar (una carpeta vacía saldría con 0 sin mirar nada).
//   6. `impeccable detect --json` sin ninguna entrada y sin nada en stderr. Cuentan los avisos («advisory», que el
//      detector deja salir con 0), los ignorados en línea que ya no ignoran nada (`--report-unused-ignores`, solo en
//      código) y cualquier diagnóstico de análisis incompleto (p. ej. una hoja de estilos que no pudo leer).
//      Renderizado: cada ruta en escritorio (1280x800) y en móvil (390x844), en cada tema de `ui.themes` (por defecto
//      ["light"]; con "dark" el navegador sirve `prefers-color-scheme: dark`).
// Códigos del detector (comprobados a mano con la 4.10.0): 0 sin hallazgos, 2 con hallazgos, 1 si no pudo escanear.
// En una URL no cuentan los comentarios en línea ni las excepciones acotadas a un fichero: solo las de valor del config.
// Salida: 0 limpio o sin web · 1 hallazgos o una comprobación falla · 2 error de uso, configuración, navegador o escaneo.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

export const VERSION = '4.10.0';
export const SKILL_DIRS = ['.claude/skills/impeccable', '.agents/skills/impeccable'];
/** Extensiones que analiza el detector: las de la lista de reference/hooks.md de la skill y también .js/.ts/.mjs/.cjs (comprobado con la 4.10.0). */
export const UI_EXT = ['.html', '.htm', '.css', '.scss', '.sass', '.less', '.jsx', '.tsx', '.vue', '.svelte', '.astro', '.js', '.ts', '.mjs', '.cjs'];
export const VIEWPORTS = ['1280x800', '390x844'];
/**
 * Esquema de color de cada tema, forzado en Chromium con la preferencia de Blink `preferredColorScheme` (0 oscuro,
 * 1 claro): así `prefers-color-scheme` responde lo mismo en local y en la CI (comprobado con Chromium 1248 y el
 * detector 4.10.0: una página con colores distintos en `@media (prefers-color-scheme: dark)` da hallazgos distintos).
 */
export const THEMES = { light: 1, dark: 0 };
const SKIP_DIRS = new Set(['node_modules', '.git']);
const INLINE = /impeccable-disable(?:-next-line|-line)?(?![\w-])(.*)$/;
const USAGE = 'Uso: node .harness/impeccable-gate.mjs [--rendered <url base>]';

const paint = (code) => (s) => (process.env.NO_COLOR ? s : `\x1b[${code}m${s}\x1b[0m`);
const out = {
  ok: (s) => console.log(`${paint('0;32')('[OK]')}    ${s}`),
  fail: (s) => console.log(`${paint('0;31')('[FAIL]')}  ${s}`),
};

export class GateError extends Error {}
const safe = (p) => typeof p === 'string' && p !== '' && !p.startsWith('-') && !p.includes('\\')
  && !path.posix.isAbsolute(p) && !/^[A-Za-z]:/.test(p) && !p.split('/').includes('..');
const route = (r) => typeof r === 'string' && /^\/[^\s?#]*(?:\?[^\s#]*)?(?:#\S*)?$/.test(r) && !r.split('/').includes('..');

/** `ui` de harness.config.json: {paths, routes, themes}, listas validadas (paths y routes vacías si no hay; themes, ["light"]). */
export function uiConfig(root) {
  let cfg;
  try { cfg = JSON.parse(fs.readFileSync(path.join(root, 'harness.config.json'), 'utf8')); } catch (e) {
    throw new GateError(`harness.config.json ilegible (${e.code ?? e.message}).`);
  }
  // Sin la clave `ui` no se sabe si hay web: se exige declararla (`"paths": []` explícito = sin web).
  if (!cfg?.ui || typeof cfg.ui !== 'object' || !('paths' in cfg.ui)) {
    throw new GateError('harness.config.json: falta "ui.paths". Declara la web (`"ui": { "paths": ["web/src"], "routes": ["/"] }`) o que no la hay (`"ui": { "paths": [], "routes": [] }`); ver docs/impeccable.md.');
  }
  const paths = cfg.ui.paths;
  const routes = cfg.ui.routes ?? [];
  if (!Array.isArray(paths) || !paths.every(safe)) throw new GateError('harness.config.json: "ui.paths" debe ser una lista de rutas relativas seguras.');
  if (!Array.isArray(routes) || !routes.every(route)) throw new GateError('harness.config.json: "ui.routes" debe ser una lista de rutas de la web que empiezan por "/" (p. ej. "/", "/reservar").');
  const themes = 'themes' in cfg.ui ? cfg.ui.themes : ['light'];
  if (!Array.isArray(themes) || themes.length === 0 || !themes.every((t) => typeof t === 'string' && Object.hasOwn(THEMES, t)) || new Set(themes).size !== themes.length) {
    throw new GateError(`harness.config.json: "ui.themes" debe ser una lista sin repetir de ${Object.keys(THEMES).map((t) => `"${t}"`).join(' y ')} (por defecto ["light"]).`);
  }
  return { paths, routes, themes };
}

/** Ficheros que el detector analiza bajo `rel` (un fichero o una carpeta), sin node_modules ni .git. */
export function uiFiles(root, rel) {
  const found = [];
  const walk = (abs) => {
    const st = fs.statSync(abs);
    if (st.isFile()) { if (UI_EXT.includes(path.extname(abs).toLowerCase())) found.push(abs); return; }
    if (!st.isDirectory()) return;
    for (const e of fs.readdirSync(abs)) if (!SKIP_DIRS.has(e)) walk(path.join(abs, e));
  };
  walk(path.join(root, rel));
  return found;
}

/** Versión del front matter de un SKILL.md; null si no la tiene. */
export function skillVersion(root, dir) {
  const f = path.join(root, dir, 'SKILL.md');
  if (!fs.existsSync(f)) return null;
  const m = /^---\r?\n([\s\S]*?)\r?\n---/.exec(fs.readFileSync(f, 'utf8'));
  // Claude la pone en `version:`; Codex, en `metadata:` → `  version:` (sangrada).
  return m ? (/^\s*version:\s*["']?([^"'\s]+)/m.exec(m[1])?.[1] ?? null) : null;
}

/** Problemas de instalación y de hooks (lista de textos; vacía si todo está bien). */
export function checkInstall(root) {
  const problems = [];
  for (const dir of SKILL_DIRS) {
    const v = skillVersion(root, dir);
    if (v !== VERSION) problems.push(`${dir}: ${v === null ? 'falta la skill' : `versión ${v}`}; esta puerta fija la ${VERSION} (npx impeccable@${VERSION} install -y --scope=project --providers=claude,codex --no-hooks).`);
    for (const lic of ['LICENSE', 'NOTICE.md']) if (!fs.existsSync(path.join(root, dir, lic))) problems.push(`${dir}/${lic}: falta (Apache-2.0 exige conservarlo).`);
  }
  // Solo la clave `hooks`: un permiso como `Bash(npx impeccable@… detect:*)` en settings.json no es un hook.
  for (const f of ['.claude/settings.json', '.codex/hooks.json']) {
    const p = path.join(root, f);
    if (!fs.existsSync(p)) continue;
    let hooks;
    try { hooks = JSON.parse(fs.readFileSync(p, 'utf8'))?.hooks; } catch (e) { throw new GateError(`${f} ilegible (${e.code ?? e.message}).`); }
    if (/impeccable/i.test(JSON.stringify(hooks ?? null))) problems.push(`${f}: trae un hook de Impeccable; van apagados (instala con --no-hooks).`);
  }
  if (fs.existsSync(path.join(root, '.github', 'hooks', 'impeccable.json'))) problems.push('.github/hooks/impeccable.json: hook de Impeccable para Copilot; van apagados.');
  return problems;
}

/** Problemas de .impeccable/config.json: hooks encendidos y excepciones sin justificar. */
export function checkConfig(root) {
  const problems = [];
  // El detector también aplica config.local.json (personal y fuera de git): versionado, silenciaría reglas sin revisión.
  if (fs.existsSync(path.join(root, '.impeccable', 'config.local.json'))) problems.push('.impeccable/config.local.json: es personal; no puede estar en el repo (va en .gitignore) ni en la CI.');
  const f = path.join(root, '.impeccable', 'config.json');
  if (!fs.existsSync(f)) return problems;
  let cfg;
  try { cfg = JSON.parse(fs.readFileSync(f, 'utf8')); } catch (e) {
    throw new GateError(`.impeccable/config.json ilegible (${e.code ?? e.message}).`);
  }
  if (cfg?.hook?.enabled !== false) problems.push('.impeccable/config.json: hook.enabled debe ser false (`impeccable hooks off`).');
  const d = cfg?.detector ?? {};
  for (const k of ['ignoreRules', 'ignoreFiles']) {
    if ((d[k] ?? []).length > 0) problems.push(`.impeccable/config.json: detector.${k} no está permitido (${d[k].join(', ')}); corrige el diseño o usa una excepción justificada por valor.`);
  }
  if (d.designSystem?.enabled === false) problems.push('.impeccable/config.json: detector.designSystem.enabled: false apaga las reglas de DESIGN.md; no está permitido.');
  for (const v of d.ignoreValues ?? []) {
    if (typeof v?.reason !== 'string' || v.reason.trim() === '') problems.push(`.impeccable/config.json: la excepción ${v?.rule}=${v?.value} no tiene motivo (--reason).`);
    if (typeof v?.value !== 'string' || v.value.trim() === '' || v.value.trim() === '*') problems.push(`.impeccable/config.json: la excepción ${v?.rule}=${v?.value} no nombra un valor concreto; un comodín apaga la regla entera.`);
  }
  return problems;
}

/**
 * Comentarios `impeccable-disable…` mal formados en los ficheros web: cada uno nombra sus reglas (sin «*») y lleva su
 * motivo tras «:» o « -- », dentro del comentario (lo que sigue a `-->` o `*\/` es código, no motivo).
 */
export function checkInline(root, files) {
  const problems = [];
  for (const f of files) {
    fs.readFileSync(f, 'utf8').split('\n').forEach((line, i) => {
      const m = INLINE.exec(line);
      if (!m) return;
      const where = `${path.relative(root, f)}:${i + 1}`;
      const close = m[1].search(/-->|\*\//);
      const body = (close === -1 ? m[1] : m[1].slice(0, close)).replace(/\s*\}?\s*$/, '');
      const sep = /:|\s--\s/.exec(body);
      const rules = (sep ? body.slice(0, sep.index) : body).split(/[\s,]+/).filter(Boolean);
      const reason = sep ? body.slice(sep.index + sep[0].length).trim() : '';
      if (rules.length === 0 || rules.includes('*')) problems.push(`${where}: la excepción no nombra sus reglas (o usa «*», que silencia todo).`);
      if (!reason) problems.push(`${where}: excepción sin motivo («impeccable-disable… <regla>: <motivo>»).`);
    });
  }
  return problems;
}

const executable = (p) => { try { fs.accessSync(p, fs.constants.X_OK); return fs.statSync(p).isFile(); } catch { return false; } };

/** Navegador para el modo renderizado: IMPECCABLE_BROWSER, uno del PATH o el Chromium de Playwright; null si no hay. */
export function findBrowser(env = process.env) {
  if (env.IMPECCABLE_BROWSER) return executable(env.IMPECCABLE_BROWSER) ? env.IMPECCABLE_BROWSER : null;
  for (const name of ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge']) {
    for (const dir of (env.PATH ?? '').split(path.delimiter).filter(Boolean)) if (executable(path.join(dir, name))) return path.join(dir, name);
  }
  // Imagen oficial de Playwright: /ms-playwright; instalación de usuario: ~/.cache/ms-playwright.
  for (const base of [env.PLAYWRIGHT_BROWSERS_PATH, '/ms-playwright', path.join(env.HOME ?? os.homedir(), '.cache', 'ms-playwright')].filter(Boolean)) {
    if (!fs.existsSync(base)) continue;
    for (const d of fs.readdirSync(base).filter((x) => /^chromium-\d+$/.test(x)).sort().reverse()) {
      for (const sub of ['chrome-linux64', 'chrome-linux']) if (executable(path.join(base, d, sub, 'chrome'))) return path.join(base, d, sub, 'chrome');
    }
  }
  return null;
}

/**
 * Envoltorio que añade --no-sandbox: en los contenedores de la CI (root o sin espacios de nombres de usuario) Chromium
 * no arranca con el sandbox. Solo abre la app del propio proyecto servida en local.
 */
function sandboxless(browser, themes) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'impeccable-gate-'));
  const wrappers = {};
  for (const t of themes) {
    wrappers[t] = path.join(dir, `chrome-${t}`);
    const flags = `--no-sandbox --blink-settings=preferredColorScheme=${THEMES[t]}`;
    fs.writeFileSync(wrappers[t], `#!/bin/sh\nexec '${browser.replace(/'/g, `'\\''`)}' ${flags} "$@"\n`, { mode: 0o755 });
  }
  return { wrappers, cleanup: () => fs.rmSync(dir, { recursive: true, force: true }) };
}

/** Lanza el detector fijado con `args` = [...opciones, [destinos]] y devuelve {code, findings, stderr} (findings null si la salida no es JSON). */
export function detect(root, args, env = process.env) {
  const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';
  // Sin el aviso de versión nueva de npm ni otros avisos suyos: fuera de la CI (sin CI=true) caerían en stderr.
  const quiet = { ...env, npm_config_update_notifier: 'false', npm_config_loglevel: 'error', npm_config_fund: 'false', npm_config_audit: 'false' };
  const r = spawnSync(npx, ['--yes', `impeccable@${VERSION}`, 'detect', '--json', ...args.slice(0, -1), '--', ...args.at(-1)], {
    cwd: root, encoding: 'utf8', env: quiet, maxBuffer: 64 * 1024 * 1024, shell: process.platform === 'win32',
  });
  let findings = null;
  try { findings = JSON.parse(r.stdout); } catch { /* findings queda en null */ }
  return { code: r.status ?? -1, findings: Array.isArray(findings) ? findings : null, stderr: (r.stderr ?? '').trim(), error: r.error?.message };
}

/**
 * Código HTTP de `url` sin seguir redirecciones (null si no responde). Una ruta que redirige (p. ej. a /login) haría
 * que el detector analizara otra página. Síncrono: un node hijo con fetch.
 */
export function probe(url) {
  const r = spawnSync(process.execPath, ['-e', 'fetch(process.argv[1], { redirect: "manual" }).then((r) => console.log(r.status), () => console.log(0))', url], { encoding: 'utf8', timeout: 60_000 });
  const code = Number.parseInt(r.stdout, 10);
  return code > 0 ? code : null;
}

/** ¿Algún workflow del proyecto ejecuta la puerta en modo renderizado? */
export function renderedWired(root) {
  const dir = path.join(root, '.github', 'workflows');
  if (!fs.existsSync(dir)) return false;
  return fs.readdirSync(dir).filter((f) => /\.ya?ml$/.test(f))
    .some((f) => /impeccable-gate\.mjs\s+--rendered\s/.test(fs.readFileSync(path.join(dir, f), 'utf8')));
}

/** Interpreta una ejecución del detector: 0 limpio, 1 con entradas, 2 si no pudo escanear o el escaneo fue incompleto. */
function judge(root, label, r) {
  if (r.code === 1 || r.findings === null || (r.code !== 0 && r.code !== 2)) {
    out.fail(`${label}: el detector no pudo escanear (código ${r.code}${r.error ? `, ${r.error}` : ''}).${r.stderr ? `\n${r.stderr}` : ''}`);
    return 2;
  }
  if (r.stderr) {
    out.fail(`${label}: análisis incompleto, el detector avisó por stderr:\n${r.stderr}`);
    return 2;
  }
  if (r.code === 2 && r.findings.length === 0) {
    out.fail(`${label}: código 2 sin entradas en el JSON.`);
    return 2;
  }
  for (const x of r.findings) {
    const file = x.file && !/^https?:/.test(x.file) ? path.relative(root, x.file) || x.file : x.file;
    out.fail(`${label} ${file ?? ''}${typeof x.line === 'number' ? `:${x.line}` : ''} [${x.antipattern}]${x.advisory ? ' (aviso)' : ''} ${x.snippet ?? x.name ?? ''}`);
  }
  return r.findings.length === 0 ? 0 : 1;
}

/** Ejecuta la puerta en `root`. `rendered` es la URL base del modo renderizado; `run` sustituye al detector en los tests. */
export function gate(root, { rendered = null, run = detect, env = process.env, check = probe } = {}) {
  const { paths, routes, themes } = uiConfig(root);
  const problems = checkInstall(root);
  if (paths.length === 0) {
    problems.forEach(out.fail);
    if (problems.length > 0) return 1;
    if (rendered !== null) { out.fail('--rendered sin web declarada (ui.paths vacío en harness.config.json).'); return 2; }
    out.ok(`Impeccable ${VERSION} instalado; el proyecto no declara web (ui.paths vacío en harness.config.json): el detector no se ejecuta.`);
    return 0;
  }
  problems.push(...checkConfig(root));
  if (routes.length === 0) problems.push('harness.config.json: con web (ui.paths) hace falta "ui.routes": el análisis del código no aplica las reglas de página.');
  if (!renderedWired(root)) problems.push('.github/workflows: con web, un job de la CI tiene que servir la app y ejecutar `node .harness/impeccable-gate.mjs --rendered <url>` (docs/impeccable.md).');

  if (rendered === null) {
    const files = [];
    for (const p of paths) {
      if (!fs.existsSync(path.join(root, p))) { problems.push(`${p}: no existe (ui.paths).`); continue; }
      const found = uiFiles(root, p);
      if (found.length === 0) problems.push(`${p}: no tiene nada que el detector analice (${UI_EXT.join(' ')}).`);
      files.push(...found);
    }
    problems.push(...checkInline(root, files));
    if (problems.length > 0) { problems.forEach(out.fail); return 1; }
    // La lista exacta de ficheros, no las carpetas: el detector se salta por su cuenta carpetas como dist/ o build/.
    const targets = files.map((f) => path.relative(root, f));
    const code = judge(root, 'código', run(root, ['--report-unused-ignores', targets], env));
    if (code === 0) out.ok(`Impeccable ${VERSION}, código: 0 hallazgos y 0 avisos en ${paths.join(', ')} (${files.length} ficheros). Solo reglas por patrón: las de página las comprueba --rendered.`);
    else if (code === 1) out.fail(`Impeccable ${VERSION}, código: hay hallazgos. Corrígelos (/impeccable audit, polish); una excepción solo con motivo.`);
    return code;
  }

  let base;
  try { base = new URL(rendered); } catch { throw new GateError(`--rendered: «${rendered}» no es una URL. ${USAGE}`); }
  if (!/^https?:$/.test(base.protocol)) throw new GateError(`--rendered: la URL debe ser http(s). ${USAGE}`);
  if (problems.length > 0) { problems.forEach(out.fail); return 1; }
  const browser = findBrowser(env);
  if (!browser) {
    out.fail('--rendered: no hay navegador (IMPECCABLE_BROWSER, Chrome o Chromium en el PATH, o el Chromium de Playwright).');
    return 2;
  }
  const { wrappers, cleanup } = sandboxless(browser, themes);
  let worst = 0;
  try {
    for (const r of routes) {
      const url = new URL(r.replace(/^\//, ''), base.href.endsWith('/') ? base.href : `${base.href}/`).href;
      const status = check(url.split('#')[0]);
      if (status === null || status < 200 || status >= 300) {
        out.fail(`${url}: responde ${status ?? 'nada'}, no 2xx; una redirección (p. ej. a /login) haría analizar otra página.`);
        worst = Math.max(worst, status !== null && status >= 300 && status < 400 ? 1 : 2);
        continue;
      }
      for (const t of themes) {
        for (const vp of VIEWPORTS) {
          const code = judge(root, `${url} @${vp} ${t}`, run(root, ['--viewport', vp, [url]], { ...env, IMPECCABLE_BROWSER: wrappers[t] }));
          worst = Math.max(worst, code);
        }
      }
    }
  } finally { cleanup(); }
  if (worst === 0) out.ok(`Impeccable ${VERSION}, renderizado: 0 hallazgos y 0 avisos en ${routes.length} ruta(s) × ${VIEWPORTS.length} tamaños (${VIEWPORTS.join(', ')}) × ${themes.length} tema(s) (${themes.join(', ')}).`);
  else if (worst === 1) out.fail(`Impeccable ${VERSION}, renderizado: hay hallazgos. Corrígelos (/impeccable audit, polish); una excepción solo de valor y con motivo.`);
  return worst;
}

function parseArgs(argv) {
  if (argv.length === 0) return { rendered: null };
  if (argv[0] === '--rendered' && argv.length === 2 && !argv[1].startsWith('--')) return { rendered: argv[1] };
  throw new GateError(`Argumentos no válidos: ${argv.join(' ')}. ${USAGE}`);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  try { process.exitCode = gate(process.cwd(), parseArgs(process.argv.slice(2))); } catch (e) {
    out.fail(e.message);
    process.exitCode = 2;
  }
}
