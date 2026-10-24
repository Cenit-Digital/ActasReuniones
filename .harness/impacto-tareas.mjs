#!/usr/bin/env node
// impacto-tareas.mjs — Candidatos del bucle de aprendizaje: los PR e issues anteriores que tocaron los
// mismos ficheros que la rama (o que los ficheros de un plan). Alimentan «Impacto en tareas anteriores»
// del PR y «Tareas relacionadas» del issue.
//
//   node .harness/impacto-tareas.mjs [--base <ref>] [--files <ruta>...] [--no-gh]
//
// Sin --files compara la rama (más lo no confirmado) con su base: --base, o la rama por defecto de origin.
// Con --files usa esas rutas, relativas al directorio actual, para listar lo relacionado al planificar.
// Mira la historia de la base con `git log --first-parent`: el PR sale de «(#N)» (squash) o de «Merge pull
// request #N» (merge commit); un rebase-merge no deja número, así que cada commit sale como candidato
// propio. Los issues salen de «Closes|Fixes|Resolves #N» en asunto y cuerpo. Con `gh` (opcional) suma los
// issues enlazados desde el cuerpo del PR y el título y estado de cada issue; `gh` solo se usa para LEER
// (pr view, issue view). Si falta, no hay sesión o no hay red, sigue con lo que da git. Sin LLM ni
// dependencias. Los títulos vienen de fuera y no son fiables: se pasan a una línea, sin caracteres de
// control, sin comentarios HTML y sin palabras de cierre seguidas de «#N», para que pegarlos en un PR no
// oculte texto ni cierre issues. Topes fijos: 200 ficheros, 10 candidatos, 20 llamadas a gh. Es una ayuda,
// no una puerta: salida 0 si hay resultado (o ninguno) · 2 si el uso es erróneo, no hay repo git o no se
// resuelve la base.

import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

export const TOPE_FICHEROS = 200;
export const TOPE_CANDIDATOS = 10;
export const TOPE_GH = 20;
const MAX_CARACTERES_RUTAS = 16000; // por llamada a git: Windows admite 32767 en toda la línea de órdenes
const GH_TIMEOUT_MS = 15000;
const USO = 'Uso: node .harness/impacto-tareas.mjs [--base <ref>] [--files <ruta>...] [--no-gh]';
const CIERRE = 'close[sd]?|fix(?:e[sd])?|resolve[sd]?';
const PALABRAS_CIERRE = new RegExp(`\\b(?:${CIERRE}):?\\s+#(\\d+)`, 'gi');
const GH_PERMITIDO = [['pr', 'view'], ['issue', 'view']];

/** Una línea y como mucho `n` caracteres, apta para pegar en un PR (ver la cabecera). */
const una = (s, n = 120) => {
  const t = String(s ?? '')
    .replace(/[\p{Cc}\p{Cf}]/gu, ' ')
    .replace(/<!--/g, '‹!--').replace(/-->/g, '--›')
    .replace(new RegExp(`\\b(${CIERRE})(:?\\s+)#(?=\\d)`, 'gi'), '$1$2# ')
    .replace(/\s+/g, ' ').trim();
  return t.length > n ? `${t.slice(0, n - 1)}…` : t;
};
const unicos = (xs) => [...new Set(xs)];

/** Registros de `git log --format=%x1e%h%x1f%ct%x1f%s%x1f%b%x1f --name-only` → commits con PR, issues y ficheros. */
export function parseLog(texto) {
  const out = [];
  for (const rec of String(texto).split('\x1e').slice(1)) { // lo anterior al primer registro no es de ningún commit
    const [hash, ct = '0', asunto = '', cuerpo = '', resto = ''] = rec.split('\x1f');
    const merge = /^Merge pull request #(\d+)\b/.exec(asunto);
    const squash = /\(#(\d+)\)\s*$/.exec(asunto);
    const pr = merge ? Number(merge[1]) : squash ? Number(squash[1]) : null;
    const issues = [...`${asunto}\n${cuerpo}`.matchAll(PALABRAS_CIERRE)].map((m) => Number(m[1]));
    const titulo = (merge ? cuerpo.split('\n').find((l) => l.trim()) : null) ?? asunto;
    out.push({
      hash: hash.trim(), ct: Number(ct) || 0, pr, titulo: una(titulo.replace(/\s*\(#\d+\)\s*$/, '')),
      issues: unicos(issues), ficheros: resto.split('\n').map((l) => l.trim()).filter(Boolean),
    });
  }
  return out.filter((c) => c.ficheros.length > 0);
}

/** Agrupa por PR (o por hash sin PR), pone primero los que más ficheros comparten (a igualdad, el primero de la lista) y corta al tope. */
export function candidatos(commits, tope = TOPE_CANDIDATOS) {
  const grupos = new Map();
  for (const c of commits) {
    const clave = c.pr ? `pr${c.pr}` : c.hash;
    const g = grupos.get(clave);
    if (!g) grupos.set(clave, { ...c, ficheros: unicos(c.ficheros), issues: unicos(c.issues), detalle: {} });
    else { g.ficheros = unicos([...g.ficheros, ...c.ficheros]); g.issues = unicos([...g.issues, ...c.issues]); }
  }
  const todos = [...grupos.values()].sort((a, b) => b.ficheros.length - a.ficheros.length);
  return { lista: todos.slice(0, tope), omitidos: Math.max(0, todos.length - tope) };
}

/** Parte las rutas en lotes que caben en la línea de órdenes de una llamada a git. */
export function lotes(rutas, max = MAX_CARACTERES_RUTAS) {
  const out = [];
  let actual = [];
  let largo = 0;
  for (const r of rutas) {
    if (actual.length && largo + r.length + 1 > max) { out.push(actual); actual = []; largo = 0; }
    actual.push(r);
    largo += r.length + 1;
  }
  if (actual.length) out.push(actual);
  return out;
}

/** Solo lectura por construcción: cualquier otra orden de gh se rechaza antes de lanzarla. */
export function ghArgs(args) {
  if (!GH_PERMITIDO.some(([a, b]) => args[0] === a && args[1] === b)) {
    throw new Error(`gh ${args.slice(0, 2).join(' ')} no está permitido: este script solo lee`);
  }
  return args;
}

/**
 * Suma a cada candidato los issues enlazados desde su PR y el título y estado de cada issue. Devuelve el
 * aviso si gh no está disponible (no arranca, agota el tiempo o falla la primera llamada) o se agotó el
 * tope; un fallo posterior (un issue borrado, un número que no es un PR) solo deja ese elemento sin detalle.
 */
export function enriquecer(lista, gh, tope = TOPE_GH) {
  let llamadas = 0;
  let aviso = null;
  const llamar = (args) => {
    if (aviso) return null;
    if (llamadas >= tope) { aviso = `se agotó el tope de ${tope} llamadas a gh: se sigue solo con git`; return null; }
    llamadas += 1;
    try { return gh(ghArgs(args)); } catch (e) {
      if (e.fatal || llamadas === 1) aviso = `gh no ha respondido (${una(e.message, 80)}): se sigue solo con git`;
      return null;
    }
  };
  for (const c of lista) {
    if (!c.pr) continue;
    const r = llamar(['pr', 'view', String(c.pr), '--json', 'closingIssuesReferences']);
    c.issues = unicos([...c.issues, ...(r?.closingIssuesReferences ?? []).map((i) => i.number)]);
  }
  for (const c of lista) {
    for (const n of c.issues) {
      const r = llamar(['issue', 'view', String(n), '--json', 'title,state']);
      if (r) c.detalle[n] = { titulo: una(r.title), estado: String(r.state ?? '').toLowerCase() === 'open' ? 'abierto' : 'cerrado' };
    }
  }
  return aviso;
}

const issueTxt = (c, n) => (c.detalle[n] ? `#${n} «${c.detalle[n].titulo}» (${c.detalle[n].estado})` : `#${n}`);

/** Texto listo para pegar en el PR o en el issue. */
export function render({ lista, omitidos }, { origen, nFicheros }) {
  const l = [`Candidatos (${origen}; ${nFicheros} fichero${nFicheros === 1 ? '' : 's'}):`];
  if (lista.length === 0) {
    l.push('Ninguno: ningún PR ni issue anterior tocó estos ficheros.');
    return l.join('\n');
  }
  for (const c of lista) {
    const n = c.ficheros.length;
    const nombres = `${c.ficheros.slice(0, 3).map((f) => una(f, 80)).join(', ')}${n > 3 ? `, y ${n - 3} más` : ''}`;
    const issues = c.issues.length ? ` · issues: ${c.issues.map((i) => issueTxt(c, i)).join(', ')}` : '';
    l.push(`- ${c.pr ? `#${c.pr}` : c.hash} «${c.titulo}» · comparte ${n} fichero${n === 1 ? '' : 's'} (${nombres})${issues}`);
  }
  if (omitidos) l.push(`- y ${omitidos} más, con menos ficheros en común (tope ${TOPE_CANDIDATOS})`);
  l.push('Son candidatos por coincidencia de ficheros, no veredictos: marca cada uno «afecta» o «no afecta», con el motivo.');
  return l.join('\n');
}

let errorGit = '';
function git(cwd, args) {
  const r = spawnSync('git', args, { cwd, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, env: { ...process.env, GIT_TERMINAL_PROMPT: '0' } });
  errorGit = r.status === 0 ? '' : String(r.stderr || r.error?.message || `salida ${r.status}`).trim();
  return r.status === 0 ? r.stdout : null;
}

function ghReal(cwd, args) {
  const r = spawnSync('gh', args, { cwd, encoding: 'utf8', timeout: GH_TIMEOUT_MS, env: { ...process.env, GH_PROMPT_DISABLED: '1', GH_NO_UPDATE_NOTIFIER: '1', NO_COLOR: '1' } });
  if (r.error) throw Object.assign(new Error(r.error.code === 'ETIMEDOUT' ? 'tiempo agotado' : r.error.message), { fatal: true });
  if (r.status !== 0) throw new Error(r.stderr || `salida ${r.status}`);
  return JSON.parse(r.stdout);
}

function leerArgumentos(argv) {
  const o = { base: null, files: null, gh: true };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--no-gh') o.gh = false;
    else if (a === '--base' && argv[i + 1] && !argv[i + 1].startsWith('-')) { i += 1; o.base = argv[i]; }
    else if (a === '--files') {
      o.files = [];
      while (argv[i + 1] && !argv[i + 1].startsWith('--')) { i += 1; o.files.push(argv[i]); }
      if (o.files.length === 0) return { error: '--files necesita al menos una ruta' };
    } else return { error: `argumento no válido: ${a}` };
  }
  return o;
}

function resolverBase(cwd, pedida) {
  const opciones = pedida ? [pedida] : [git(cwd, ['symbolic-ref', '--quiet', '--short', 'refs/remotes/origin/HEAD'])?.trim(), 'origin/main', 'origin/master', 'main', 'master'];
  return opciones.find((o) => o && git(cwd, ['rev-parse', '--verify', '--quiet', `${o}^{commit}`]) !== null) ?? null;
}

/** Rutas dadas desde el directorio actual → rutas desde la raíz del repo (null si salen de él). */
function rutasDesdeLaRaiz(files) {
  const prefijo = (git(process.cwd(), ['rev-parse', '--show-prefix']) ?? '').trim();
  const rel = files.map((f) => (path.isAbsolute(f) ? '../' : path.posix.normalize(`${prefijo}${f.replace(/\\/g, '/')}`)));
  return rel.some((r) => r === '..' || r.startsWith('../')) ? null : rel;
}

export function main(argv) {
  const falla = (msg) => { console.log(`[FAIL]  ${msg}`); process.exitCode = 2; };
  const o = leerArgumentos(argv);
  if (o.error) return falla(`${o.error}. ${USO}`);
  const raiz = git(process.cwd(), ['rev-parse', '--show-toplevel'])?.trim();
  if (!raiz) return falla('no es un repositorio git.');
  const base = resolverBase(raiz, o.base);
  if (!base) return falla(`no encuentro la rama base${o.base ? ` «${o.base}»` : ' (origin/HEAD, origin/main, origin/master, main, master)'}: indícala con --base.`);

  let ficheros;
  if (o.files) {
    ficheros = rutasDesdeLaRaiz(o.files);
    if (!ficheros) return falla('--files admite solo rutas relativas dentro del repositorio.');
  } else {
    const mb = git(raiz, ['merge-base', base, 'HEAD'])?.trim();
    const diff = mb ? git(raiz, ['diff', '--name-only', '--no-renames', '-z', mb]) : null;
    if (diff === null) return falla(`no puedo calcular el diff contra ${base}: ${una(errorGit, 100)}`);
    ficheros = diff.split('\0').filter(Boolean);
  }
  if (ficheros.length > TOPE_FICHEROS) {
    console.log(`[WARN]  Son ${ficheros.length} ficheros: se consideran solo los ${TOPE_FICHEROS} primeros.`);
    ficheros = ficheros.slice(0, TOPE_FICHEROS);
  }
  const origen = o.files ? 'ficheros indicados' : `rama contra ${base}`;
  if (ficheros.length === 0) { console.log(`Sin cambios respecto a ${base}: no hay nada que comparar.`); return; }

  const commits = [];
  for (const lote of lotes(ficheros)) {
    const log = git(raiz, ['--literal-pathspecs', '-c', 'core.quotepath=false', 'log', base, '--first-parent', '-m', '--no-show-signature', '--no-renames', '--name-only', '--format=%x1e%h%x1f%ct%x1f%s%x1f%b%x1f', '--', ...lote]);
    if (log === null) return falla(`git log falló sobre ${base}: ${una(errorGit, 100)}`);
    commits.push(...parseLog(log));
  }
  commits.sort((a, b) => b.ct - a.ct);
  const res = candidatos(commits);
  if (o.gh && res.lista.length) {
    const aviso = enriquecer(res.lista, (args) => ghReal(raiz, args));
    if (aviso) console.log(`[WARN]  ${aviso}.`);
  }
  console.log(render(res, { origen, nFicheros: ficheros.length }));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main(process.argv.slice(2));
