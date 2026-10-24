#!/usr/bin/env node
// pr-body.mjs — Comprueba que la descripción de un PR sigue .github/pull_request_template.md.
//
//   PR_BODY="$descripcion" node .harness/pr-body.mjs
//
// Exige las cinco secciones (encabezados "## ") con contenido y la casilla de revisión local
// marcada: sin esa comprobación la plantilla se salta con facilidad (`gh pr create --body-file`,
// `--fill`). No cuenta lo que GitHub no muestra (comentarios HTML y bloques de código) y no
// distingue mayúsculas ni tildes. Solo reconoce encabezados "## " (un título subrayado no vale).
// Sin LLM ni dependencias. NUNCA imprime la descripción: una línea "::..." sería un comando del
// workflow. Salida: 0 cumple · 1 incumple.

import { pathToFileURL } from 'node:url';

export const SECTIONS = ['Qué', 'Por qué', 'Cómo se probó', 'Pendiente', 'Impacto en tareas anteriores'];
export const CHECKBOX = 'Diff revisado en local antes de empujar';

const norm = (s) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replace(/\s+/g, ' ').trim();
const FENCE = /^ {0,3}(`{3,}|~{3,})(.*)$/;
const HEADING = /^ {0,3}(#{1,2})[ \t]+(.*?)[ \t]*$/;
const TASK = /^\s*(?:[-*+]|\d+[.)])\s+\[([ xX])\]\s+(.*)$/;

/** Líneas que GitHub muestra: sin comentarios HTML (aunque no cierren) ni bloques de código. */
function visibleLines(body) {
  const out = [];
  let fence = null;
  let comment = false;
  for (const raw of String(body ?? '').replace(/\r\n?/g, '\n').split('\n')) {
    if (!comment) {
      const f = FENCE.exec(raw);
      if (fence) {
        if (f && f[1][0] === fence[0] && f[1].length >= fence.length && f[2].trim() === '') fence = null;
        continue;
      }
      if (f && !(f[1][0] === '`' && f[2].includes('`'))) { fence = f[1]; continue; }
    }
    let rest = raw;
    let line = '';
    for (;;) {
      if (comment) {
        const end = rest.indexOf('-->');
        if (end < 0) break;
        rest = rest.slice(end + 3);
        comment = false;
      }
      const start = rest.indexOf('<!--');
      if (start < 0) { line += rest; break; }
      line += rest.slice(0, start);
      rest = rest.slice(start + 4);
      comment = true;
    }
    out.push(line);
  }
  return out;
}

/** Problemas de la descripción respecto a la plantilla; lista vacía si cumple. */
export function checkBody(body) {
  const wanted = new Set(SECTIONS.map(norm));
  const filled = new Map(); // título normalizado → ¿tiene contenido?
  const box = norm(CHECKBOX);
  let marked = null; // null: no hay casilla · false: sin marcar · true: marcada
  let current = null;
  for (const line of visibleLines(body)) {
    const h = HEADING.exec(line);
    if (h) {
      const title = h[1].length === 2 ? norm(h[2].replace(/[ \t]+#+$/, '')) : '';
      current = wanted.has(title) ? title : null;
      if (current && !filled.has(current)) filled.set(current, false);
      continue;
    }
    const t = TASK.exec(line);
    if (t && norm(t[2]) === box) { marked = Boolean(marked) || t[1] !== ' '; continue; }
    if (current && line.trim() !== '') filled.set(current, true);
  }
  const problems = [];
  for (const s of SECTIONS) {
    const has = filled.get(norm(s));
    if (has === undefined) problems.push(`falta la sección «${s}» (encabezado «## ${s}»)`);
    else if (!has) problems.push(`la sección «${s}» está vacía`);
  }
  if (marked === null) problems.push(`falta la casilla «${CHECKBOX}»`);
  else if (!marked) problems.push(`la casilla «${CHECKBOX}» no está marcada`);
  return problems;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const body = process.env.PR_BODY;
  if (body === undefined) console.log('[WARN]  PR_BODY no está definido: se trata como una descripción vacía.');
  const problems = checkBody(body);
  if (problems.length === 0) {
    console.log('[OK]    La descripción del PR cumple la plantilla (.github/pull_request_template.md).');
  } else {
    for (const p of problems) {
      console.log(`[FAIL]  ${p}`);
      console.log(`::error title=Cuerpo del PR::${p}`);
    }
    console.log('Rellénalo en la descripción del PR; el check se repite al editarla.');
    process.exitCode = 1;
  }
}
