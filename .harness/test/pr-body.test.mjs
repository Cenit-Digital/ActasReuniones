// pr-body.test.mjs — Tests de .harness/pr-body.mjs (comprobador de la descripción del PR; ADR 0001, D10).
//
// Los casos parten de la plantilla real (.github/pull_request_template.md) para que ambas no se
// separen. Se corre con ruta explícita:
//
//   node --test .harness/test/pr-body.test.mjs

import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { checkBody, SECTIONS, CHECKBOX } from '../pr-body.mjs';

const HARNESS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SCRIPT = path.join(HARNESS, 'pr-body.mjs');
const TEMPLATE = fs.readFileSync(path.join(HARNESS, '..', '.github', 'pull_request_template.md'), 'utf8').replace(/\r\n/g, '\n');
const BOX = `- [x] ${CHECKBOX}`;
const OK = [...SECTIONS.flatMap((s) => [`## ${s}`, 'texto']), BOX].join('\n');
const N = SECTIONS.length + 1; // problemas de una descripción vacía: cada sección y la casilla

/** La plantilla real con texto tras cada encabezado (menos `skip`, que se quita, y `empty`, que queda vacío) y la casilla marcada. */
const fill = ({ skip, empty } = {}) => TEMPLATE
  .replace(/^## (.+)$/gm, (h, t) => (t === skip ? '' : t === empty ? h : `${h}\ntexto`))
  .replace('- [ ]', '- [x]');

test('las secciones y la casilla del comprobador son las de la plantilla de PR', () => {
  assert.deepEqual([...TEMPLATE.matchAll(/^## (.+)$/gm)].map((m) => m[1]), SECTIONS);
  assert.ok(TEMPLATE.includes(`- [ ] ${CHECKBOX}`));
});

test('la plantilla rellena cumple y sin rellenar incumple en todo', () => {
  assert.deepEqual(checkBody(fill()), []);
  assert.equal(checkBody(TEMPLATE).length, N);
});

test('cada sección que falta o está vacía se nombra, y solo ella', () => {
  for (const s of SECTIONS) {
    assert.deepEqual(checkBody(fill({ skip: s })), [`falta la sección «${s}» (encabezado «## ${s}»)`]);
    assert.deepEqual(checkBody(fill({ empty: s })), [`la sección «${s}» está vacía`]);
  }
});

test('una descripción ausente, nula o en blanco incumple todo', () => {
  for (const b of [undefined, null, '', ' \n\t\n']) assert.equal(checkBody(b).length, N);
});

test('vale «Ninguna», sin tildes ni mayúsculas, con «##» de cierre, con CRLF y con la casilla en otras formas', () => {
  const variants = [
    OK.replace(/texto\n- \[x\]/, 'Ninguna\n- [x]'),
    OK.replace('## Qué', '## QUE').replace('## Cómo se probó', '## como SE probo ##').replace('## Por qué', '##   Por   qué  '),
    OK.replace(/\n/g, '\r\n'),
    OK.replace(BOX, `- [X] ${CHECKBOX}`),
    OK.replace(BOX, '* [x] DIFF revisado en local antes de empujar  '),
    OK.replace(BOX, `1. [x] ${CHECKBOX}`),
    `${OK}\n- [ ] ${CHECKBOX}`, // la casilla de la plantilla citada sin marcar no anula la marcada
  ];
  for (const v of variants) assert.deepEqual(checkBody(v), [], v);
});

// [nombre, descripción, mensaje esperado, nº exacto de problemas]
const BAD = [
  ['encabezado de nivel 3', OK.replace('## Qué', '### Qué'), /falta la sección «Qué»/, 1],
  ['sección dentro de un bloque de código', OK.replace('## Pendiente\ntexto', '```\n## Pendiente\ntexto\n```'), /falta la sección «Pendiente»/, 1],
  ['una valla ``` no la cierra una ~~~', OK.replace('## Pendiente\ntexto', '```\n~~~\n## Pendiente\ntexto\n```'), /falta la sección «Pendiente»/, 1],
  ['una valla no la cierra una línea con texto detrás', OK.replace('## Pendiente\ntexto', '```\n## Pendiente\ntexto\n``` sigue\n```'), /falta la sección «Pendiente»/, 1],
  ['sección dentro de un comentario', OK.replace('## Pendiente\ntexto', '<!--\n## Pendiente\ntexto\n-->'), /falta la sección «Pendiente»/, 1],
  ['comentario sin cerrar: se traga el resto', OK.replace('## Por qué', '<!-- ## Por qué'), /falta la sección «Por qué»/, 5],
  ['contenido solo de espacios y comentarios', OK.replace('## Por qué\ntexto', '## Por qué\n  \n\t\n<!-- x -->'), /«Por qué» está vacía/, 1],
  ['contenido bajo otro encabezado', OK.replace('## Por qué\ntexto', '## Por qué\n## Otro\ntexto'), /«Por qué» está vacía/, 1],
  ['casilla sin marcar', OK.replace('[x]', '[ ]'), /no está marcada/, 1],
  ['casilla dentro de un comentario', OK.replace(BOX, `<!-- ${BOX} -->`), /falta la casilla/, 1],
  ['casilla dentro de un bloque de código', OK.replace(BOX, `\`\`\`\n${BOX}\n\`\`\``), /falta la casilla/, 1],
  ['casilla con otro texto', OK.replace('Diff revisado', 'Diff leído'), /falta la casilla/, 1],
  ['la casilla no cuenta como contenido de «Impacto»', OK.replace('texto\n- [x]', '- [x]'), /«Impacto en tareas anteriores» está vacía/, 1],
];
for (const [name, body, re, n] of BAD) {
  test(`incumple: ${name}`, () => {
    assert.match(checkBody(body).join('\n'), re);
    assert.equal(checkBody(body).length, n);
  });
}

const cli = (body) => {
  const env = { ...process.env };
  delete env.PR_BODY;
  if (body !== undefined) env.PR_BODY = body;
  return spawnSync(process.execPath, [SCRIPT], { env, encoding: 'utf8' });
};

test('CLI: sale 0 si cumple, 1 si no, y nunca imprime la descripción', () => {
  const ok = cli(OK);
  assert.equal(ok.status, 0);
  assert.match(ok.stdout, /\[OK\]/);
  const bad = cli(`::error::inyectado\n${OK.replace('## Qué', '## Q')}`);
  assert.equal(bad.status, 1);
  assert.match(bad.stdout, /::error title=Cuerpo del PR::falta la sección «Qué»/);
  assert.doesNotMatch(bad.stdout, /inyectado/);
  const none = cli(undefined);
  assert.equal(none.status, 1);
  assert.match(none.stdout, /PR_BODY no está definido/);
});
