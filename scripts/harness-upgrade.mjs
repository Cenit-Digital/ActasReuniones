#!/usr/bin/env node
// harness-upgrade.mjs — Compara y actualiza un proyecto derivado con la plantilla SSD.
//
//   node scripts/harness-upgrade.mjs --check | --diff | --apply [--yes] [--replace-json <ruta>]...
//                                    [--ref <tag|rama>] [--repo <url|ruta>]
//
// Modelo pull, 0 tokens. Clona la plantilla (git clone --depth 1 de un tag o rama,
// no un SHA) a un directorio temporal y compara el proyecto (cwd) con ella según su
// harness.manifest.json. Sin --ref usa el último tag vX.Y.Z.
//   --check  SOLO LECTURA: lista la deriva.
//   --diff   SOLO LECTURA: lo mismo, y muestra el diff de cada fichero que difiere.
//   --apply  reemplaza los ficheros `template` que difieren, tras mostrar el diff y pedir
//            confirmación (--yes la omite). Nunca borra ni toca `project`. El bloque
//            gestionado de AGENTS.md (entre marcadores harness:begin/end; su texto lo define
//            blockSource en la plantilla) se compara y se reemplaza sin tocar el resto del
//            fichero, y si falta se añade al final. Un JSON mixto solo se reemplaza si se
//            nombra con --replace-json. Rechaza enlaces simbólicos (de la plantilla y del
//            proyecto) y ediciones sin confirmar en lo que pisaría. Lo aplicado queda
//            añadido al índice (git add), con el bit ejecutable fijado.
// Un fichero `optional` del manifiesto es de la plantilla pero no se exige: se compara y se reemplaza
// solo si existe en el proyecto; si falta no es deriva y --apply no lo crea.
// Salida: 0 sin deriva (o aplicado) · 1 deriva en ficheros de plantilla o en el bloque (o
// aplicación rechazada) · 2 error de uso, descarga, manifiesto o guarda. Requiere Node >= 18 y git.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createInterface } from 'node:readline';
import { pathToFileURL } from 'node:url';

const paint = (code) => (s) => (process.env.NO_COLOR ? s : `\x1b[${code}m${s}\x1b[0m`);
const ok = (s) => console.log(`${paint('0;32')('[OK]')}    ${s}`);
const warn = (s) => console.log(`${paint('0;33')('[WARN]')}  ${s}`);
const fail = (s) => console.log(`${paint('0;31')('[FAIL]')}  ${s}`);

const USAGE = 'Uso: node scripts/harness-upgrade.mjs --check | --diff | --apply [--yes] [--replace-json <ruta>]... [--ref <tag|rama>] [--repo <url|ruta>]';
const DEFAULT_REPO = 'https://github.com/Cenit-Digital/TemplateSSDUncleBob.git';
const MODES = ['--check', '--diff', '--apply'];
const ROOT = process.cwd();
const die = (msg) => { throw new Error(msg); };

/** BOM inicial y CRLF fuera: .gitattributes fuerza CRLF en *.ps1 y LF en el resto. */
const norm = (s) => (s.charCodeAt(0) === 0xfeff ? s.slice(1) : s).replace(/\r\n/g, '\n');
const read = (p) => norm(fs.readFileSync(p, 'utf8'));
const safe = (p) => typeof p === 'string' && p !== '' && !p.includes('\\')
  && !path.posix.isAbsolute(p) && !/^[A-Za-z]:/.test(p) && !p.split('/').includes('..');
const covers = (entry, file) => (entry.endsWith('/') ? file.startsWith(entry) : file === entry);

/** Ejecuta git sin prompts. Con `soft` devuelve null si falla; si no, aborta (salida 2). */
function git(args, cwd, soft = false) {
  const r = spawnSync('git', args, {
    cwd, encoding: 'utf8', env: { ...process.env, GIT_TERMINAL_PROMPT: '0', GIT_ASKPASS: '' },
  });
  if (r.status === 0) return r.stdout;
  if (soft) return null;
  return die(`git ${args[0]} falló: ${(r.error?.message ?? r.stderr).trim().split('\n').pop()}`);
}

/** Una línea de stdin (TTY o pipe); '' si se cierra sin respuesta. */
const ask = (question) => new Promise((resolve) => {
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  rl.once('close', () => resolve(''));
  rl.question(question, (answer) => { resolve(answer); rl.close(); });
});

function parseArgs(argv) {
  const o = { mode: null, yes: false, json: [], ref: null, repo: DEFAULT_REPO };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (MODES.includes(a)) {
      if (o.mode) die(`Usa un solo modo (${o.mode} y ${a}). ${USAGE}`);
      o.mode = a;
    } else if (a === '--yes') o.yes = true;
    else if (a === '--ref' || a === '--repo' || a === '--replace-json') {
      const v = argv[++i];
      if (!v || v.startsWith('--')) die(`${a} necesita un valor. ${USAGE}`);
      if (a === '--replace-json') o.json.push(v);
      else o[a.slice(2)] = v;
    } else die(`Argumento desconocido: ${a}. ${USAGE}`);
  }
  if (!o.mode) die(`Falta el modo. ${USAGE}`);
  if ((o.yes || o.json.length) && o.mode !== '--apply') die(`--yes y --replace-json solo valen con --apply. ${USAGE}`);
  if (fs.existsSync(o.repo)) o.repo = pathToFileURL(path.resolve(o.repo)).href;
  return o;
}

/** Último tag vX.Y.Z del repo remoto (orden de versión de git, no léxico). */
function latestTag(repo) {
  const tags = git(['ls-remote', '--tags', '--refs', '--sort=-v:refname', repo]).split('\n')
    .map((l) => l.split('refs/tags/')[1]).filter((t) => /^v\d+\.\d+\.\d+$/.test(t ?? ''));
  return tags[0] ?? die('La plantilla no tiene tags vX.Y.Z; indica una rama con --ref (p. ej. --ref main).');
}

/** Lee y valida el manifiesto de la plantilla descargada (sus rutas son datos no fiables). */
function loadManifest(dir, files) {
  let m;
  try { m = JSON.parse(read(path.join(dir, 'harness.manifest.json'))); } catch (e) {
    die(`La plantilla no trae un harness.manifest.json válido (${e.code ?? e.message}).`);
  }
  if (m && typeof m === 'object' && m.optional === undefined) m.optional = []; // clave opcional: sin ella el manifiesto sigue siendo válido
  for (const k of ['template', 'optional', 'executable', 'mixedBlock', 'mixedJson', 'project', 'excluded']) {
    if (!Array.isArray(m?.[k]) || !m[k].every(safe)) die(`harness.manifest.json: "${k}" debe ser una lista de rutas relativas seguras.`);
  }
  for (const e of [...m.template, ...m.optional, ...m.mixedBlock, ...m.mixedJson]) {
    if (!files.some((f) => covers(e, f))) die(`El manifiesto lista "${e}", que no existe en la plantilla.`);
  }
  if (m.mixedBlock.length > 0 && !(safe(m.blockSource) && files.includes(m.blockSource))) {
    die('harness.manifest.json: "blockSource" debe ser la ruta relativa segura de un fichero de la plantilla (hay mixedBlock).');
  }
  const clash = (a, b) => {
    for (const e of m[a]) {
      const x = m[b].find((p) => covers(e, p) || covers(p, e));
      if (x) die(`El manifiesto pone "${e}" en ${a} y "${x}" en ${b}, y se solapan.`);
    }
  };
  for (const a of ['template', 'optional', 'executable', 'mixedBlock', 'mixedJson']) for (const b of ['project', 'excluded']) clash(a, b);
  for (const b of ['template', 'executable', 'mixedBlock', 'mixedJson']) clash('optional', b);
  return m;
}

/** true/false según el bit ejecutable del derivado; null si no se puede saber (Windows sin git). */
function isExecutable(rel) {
  const mode = git(['ls-files', '-s', '--', rel], ROOT, true)?.trim().split(/\s+/)[0];
  if (mode) return mode === '100755';
  return process.platform === 'win32' ? null : (fs.statSync(path.join(ROOT, rel)).mode & 0o111) !== 0;
}

const FENCE = /^ {0,3}(`{3,}|~{3,})(.*)$/;
const MARK = /^ {0,3}<!--\s*harness:(begin|end)(?:\s.*)?-->\s*$/;

/** Marcadores [tipo, nº de línea] fuera de las vallas de código (reglas CommonMark; el código sangrado 4+ tampoco cuenta). */
function markers(lines) {
  const found = [];
  let fence = null;
  lines.forEach((line, i) => {
    const f = FENCE.exec(line);
    const mark = MARK.exec(line);
    if (fence) {
      if (f && f[1][0] === fence[0] && f[1].length >= fence.length && f[2].trim() === '') fence = null;
    } else if (f && !(f[1][0] === '`' && f[2].includes('`'))) fence = f[1];
    else if (mark) found.push([mark[1], i]);
  });
  return found;
}

/** {start, end} (índices de línea) del único bloque gestionado; null si no hay; aborta si hay duplicados o desbalance. */
function blockRange(lines) {
  const ms = markers(lines);
  if (ms.length === 0) return null;
  const [b, e] = ['begin', 'end'].map((k) => ms.filter(([t]) => t === k).map(([, i]) => i));
  if (b.length !== 1 || e.length !== 1 || b[0] > e[0]) {
    die(`marcadores harness:begin/harness:end duplicados o desbalanceados (${b.length} begin, ${e.length} end) o en orden inverso; corrígelos a mano`);
  }
  return { start: b[0], end: e[0] };
}

/** Compara el bloque de `raw` con `block`: {kind:'ok'} o {kind:'replace'|'add', next}. Lo de fuera del bloque queda byte a byte. */
function placeBlock(raw, block, verify = true) {
  const lines = raw.split('\n'); // cada línea conserva su \r final
  const clean = lines.map((l, i) => (i === 0 ? l.replace(/^\uFEFF/, '') : l).replace(/\r$/, ''));
  const r = blockRange(clean);
  if (r && clean.slice(r.start, r.end + 1).join('\n') === block.join('\n')) return { kind: 'ok' };
  const cr = raw.includes('\r\n') ? '\r' : '';
  const mine = block.map((l) => l + cr);
  let n = lines.length;
  while (!r && n > 0 && clean[n - 1] === '') n--;
  const out = r ? [...lines.slice(0, r.start), ...mine, ...lines.slice(r.end + 1)] : [...lines.slice(0, n), ...(n ? [cr] : []), ...mine, ''];
  const next = out.join('\n');
  // Si tras colocarlo no queda "ok" (p. ej. una valla sin cerrar se lo traga), abortar evita acumular un bloque nuevo en cada ejecución.
  if (verify && placeBlock(next, block, false).kind !== 'ok') die('no puedo colocar el bloque (¿hay un bloque de código sin cerrar antes?)');
  return { kind: r ? 'replace' : 'add', next };
}

/** Líneas del bloque gestionado (blockSource): debe ser un único bloque que ocupe todo el fichero. */
function loadBlock(dir, m) {
  const lines = read(path.join(dir, m.blockSource)).replace(/\n+$/, '').split('\n');
  const r = blockRange(lines);
  if (!r || r.start !== 0 || r.end !== lines.length - 1) die(`${m.blockSource} debe ser un único bloque entre marcadores, sin nada fuera.`);
  return lines;
}

/** Rutas de `rels` que el proyecto registra como enlace simbólico (modo 120000 del índice; vale también donde Windows las deja como fichero). */
const projectLinks = (rels) => (rels.length === 0 ? [] : (git(['ls-files', '-s', '-z', '--', ...rels], ROOT, true) ?? '').split('\0'))
  .filter((l) => l.startsWith('120000')).map((l) => l.slice(l.indexOf('\t') + 1));

/** Diff de `rel` (proyecto → plantilla, o → `next` si es un string) con git; las copias old/ y new/ dan cabeceras legibles. */
function showDiff(tmp, rel, next) {
  const stage = path.join(tmp, '.stage');
  for (const [side, src] of [['old', path.join(ROOT, rel)], ['new', path.join(tmp, rel)]]) {
    const dst = path.join(stage, side, rel);
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    if (side === 'new' && typeof next === 'string') fs.writeFileSync(dst, next);
    else if (fs.existsSync(src)) fs.copyFileSync(src, dst);
    else fs.writeFileSync(dst, '');
  }
  spawnSync('git', ['--no-pager', 'diff', '--no-index', '--no-ext-diff', '--no-color', '--ignore-cr-at-eol', '--', `old/${rel}`, `new/${rel}`], { cwd: stage, stdio: 'inherit' });
}

/** Valida todo antes de escribir, pide confirmación, copia y añade al índice. Devuelve la salida. */
async function applyChanges(tmp, m, todo, yes) {
  const rels = [...todo.keys()];
  if (rels.length === 0) { ok('Nada que aplicar.'); return 0; }
  const dirty = git(['status', '--porcelain', '--', ...rels], ROOT, true);
  if (dirty === null) warn('El proyecto no es un repo git: no puedo comprobar si hay cambios sin confirmar.');
  else if (dirty.trim()) die(`Hay cambios sin confirmar en ficheros que se reemplazarían; confírmalos o descártalos antes:\n${dirty.trimEnd()}`);
  if (!yes && !/^(s|sí|si|y|yes)$/i.test((await ask(`¿Aplicar ${rels.length} cambio(s)? [s/N] `)).trim())) {
    warn('No se ha escrito nada.');
    return 1;
  }
  for (const [f, content] of todo) {
    if (!content) continue;
    const dest = path.join(ROOT, f);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    if (typeof content === 'string') fs.writeFileSync(dest, content);
    else fs.copyFileSync(path.join(tmp, f), dest);
  }
  ok(`${rels.length} cambio(s) aplicado(s).`);
  if (dirty === null || git(['add', '--', ...rels], ROOT, true) === null) {
    warn('Sin git: añade lo aplicado a mano y fija el bit ejecutable (chmod +x) donde haga falta.');
    return 0;
  }
  for (const f of rels.filter((r) => m.executable.includes(r))) git(['update-index', '--chmod=+x', '--', f], ROOT, true);
  ok('Añadido al índice (git add) con el bit ejecutable fijado; revisa con `git diff --cached` y confirma.');
  return 0;
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const ref = opts.ref ?? latestTag(opts.repo);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'harness-upgrade-'));
  try {
    git(['-c', 'advice.detachedHead=false', 'clone', '--depth', '1', '--quiet', '--branch', ref, opts.repo, tmp]);
    const modes = new Map(git(['ls-files', '-s', '-z'], tmp).split('\0').filter(Boolean)
      .map((r) => [r.slice(r.indexOf('\t') + 1), r.split(' ')[0]]));
    const files = [...modes.keys()];
    const m = loadManifest(tmp, files);
    ok(`plantilla ${ref} (${git(['rev-parse', '--short', 'HEAD'], tmp).trim()}) de ${opts.repo}`);
    for (const f of opts.json) if (!m.mixedJson.includes(f)) die(`--replace-json ${f}: no es un JSON mixto del manifiesto.`);

    const owned = files.filter((f) => m.template.some((e) => covers(e, f)));
    const optional = files.filter((f) => m.optional.some((e) => covers(e, f)));
    const links = [...owned, ...optional, ...m.mixedJson, m.blockSource].filter((f) => modes.get(f) === '120000');
    if (links.length > 0) die(`La plantilla trae enlaces simbólicos entre lo que se propaga (no se reemplazan): ${links.join(', ')}`);
    const block = m.mixedBlock.length > 0 ? loadBlock(tmp, m) : null;
    const todo = new Map(); // ruta → true si hay que copiar su contenido, false si solo el bit ejecutable
    const differs = []; // rutas cuyo contenido difiere (las que enseña --diff)
    let drift = 0;
    for (const f of owned) {
      const mine = path.join(ROOT, f);
      if (!fs.existsSync(mine)) { fail(`falta: ${f}`); drift++; todo.set(f, true); differs.push(f); continue; }
      if (read(mine) !== read(path.join(tmp, f))) { fail(`difiere: ${f}`); drift++; todo.set(f, true); differs.push(f); }
      if (m.executable.includes(f) && isExecutable(f) === false) { fail(`sin bit ejecutable: ${f} (git update-index --chmod=+x)`); drift++; todo.set(f, todo.get(f) ?? false); }
    }
    const absent = []; // opcionales que el proyecto no tiene: no son deriva y --apply no los crea
    for (const f of optional) {
      const mine = path.join(ROOT, f);
      if (!fs.existsSync(mine)) { absent.push(f); continue; }
      if (read(mine) !== read(path.join(tmp, f))) { fail(`difiere: ${f}`); drift++; todo.set(f, true); differs.push(f); }
    }
    if (drift === 0) ok(`${owned.length + optional.length - absent.length} ficheros de plantilla sin deriva.`);
    if (absent.length > 0) ok(`opcionales que no tienes (no son deriva): ${absent.join(', ')}`);

    for (const f of m.mixedBlock) {
      const gone = !fs.existsSync(path.join(ROOT, f));
      let r;
      try { r = placeBlock(gone ? '' : fs.readFileSync(path.join(ROOT, f), 'utf8'), block); } catch (e) {
        if (opts.mode === '--apply') die(`${f}: ${e.message}`);
        fail(`${f}: ${e.message}`); drift++; continue;
      }
      if (r.kind === 'ok') { ok(`${f}: bloque gestionado al día.`); continue; }
      fail(`${f}: ${gone ? 'falta' : r.kind === 'add' ? 'sin bloque gestionado' : 'el bloque gestionado difiere de la plantilla'}`);
      drift++; todo.set(f, r.next); differs.push(f);
    }
    for (const f of m.mixedJson) {
      const gone = !fs.existsSync(path.join(ROOT, f));
      if (!gone && read(path.join(ROOT, f)) === read(path.join(tmp, f))) { ok(`${f}: igual que la plantilla.`); continue; }
      differs.push(f);
      if (opts.json.includes(f)) { todo.set(f, true); warn(`${f}: se reemplazará (--replace-json).`); }
      else warn(`${f}: ${gone ? 'falta' : 'difiere de la plantilla'} (JSON mixto; revísalo, el reemplazo es explícito: --apply --replace-json ${f}).`);
    }
    const linked = projectLinks([...todo.keys()]);
    if (linked.length > 0) {
      const msg = `${linked.join(', ')}: enlace(s) simbólico(s) en el proyecto; no se escribe a través de ellos. Si es AGENTS.md: haz que sea el fichero real. CLAUDE.md es de la plantilla: usa su CLAUDE.md mínimo (con @AGENTS.md), no un enlace.`;
      if (opts.mode === '--apply') die(msg);
      fail(msg); drift++;
    }
    if (opts.mode !== '--check') for (const f of differs) if (opts.mode === '--diff' || todo.has(f)) showDiff(tmp, f, todo.get(f));
    if (drift > 0 && opts.mode !== '--apply') fail(`Deriva en ${drift} comprobación(es).`);
    process.exitCode = opts.mode === '--apply' ? await applyChanges(tmp, m, todo, opts.yes) : Number(drift > 0);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

main().catch((e) => { fail(e.message); process.exitCode = 2; });
