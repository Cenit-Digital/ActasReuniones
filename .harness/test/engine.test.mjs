// engine.test.mjs — Tests de caracterización del motor del arnés (.harness/harness.mjs).
//
// El motor es TODA la cadena de verificación de la plantilla (init / test / mutate /
// verify). Cada caso fija una conducta con una configuración VÁLIDA (la que
// acepta harness.schema.json) contra futuras regresiones. El motor no valida la forma
// de lo que lee: ante un fichero mal formado solo se exige que termine con un [FAIL]
// legible y el exit 2 de la red de seguridad, sin traza (ver el último bloque).
//
// Sin dependencias npm: usa `node:test` (estable desde Node 18, el único requisito del
// arnés). Se corre con la RUTA DE FICHERO explícita:
//
//   node --test .harness/test/engine.test.mjs
//
// (no `node --test .harness/test/`: en Node 22 la forma de directorio intenta cargar la
// carpeta como módulo y revienta con MODULE_NOT_FOUND; la ruta de fichero explícita
// funciona en Node 18+, el mínimo del arnés). El job `Motor (tests)` de
// .github/workflows/harness-ci.yml corre este mismo comando.
//
// El motor llama a `process.exit()` y escribe con console.log, así que cada caso lo
// lanza como SUBPROCESO en un directorio temporal y comprueba el código de salida y la
// salida combinada (stdout+stderr). NO_COLOR=1 evita códigos ANSI.

import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ENGINE = path.resolve(HERE, '..', 'harness.mjs');

const _tmpDirs = [];
after(() => {
  for (const d of _tmpDirs) {
    try { fs.rmSync(d, { recursive: true, force: true }); } catch { /* best effort */ }
  }
});

/** Crea un directorio temporal aislado y registra su borrado al final. */
function tmp() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'harness-eng-'));
  _tmpDirs.push(d);
  return d;
}

/** Escribe un fichero (creando subdirectorios) dentro de `dir`. */
function write(dir, rel, content) {
  const p = path.join(dir, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, content);
}

/** Serializa un objeto de config de forma legible. */
const json = (obj) => JSON.stringify(obj, null, 2);

/**
 * Monta un escenario: escribe harness.config.json (objeto o string crudo) y
 * cualquier fichero extra, y devuelve el directorio.
 *   files: { 'harness.config.json': <obj|string>, 'src/foo.txt': <string>, ... }
 */
function scenario(files) {
  const dir = tmp();
  for (const [rel, content] of Object.entries(files)) {
    const body = typeof content === 'string' ? content : json(content);
    write(dir, rel, body);
  }
  return dir;
}

/** Lanza el motor en `cwd` con `args`; devuelve { status, out }. */
function runEngine(cwd, args = []) {
  const r = spawnSync(process.execPath, [ENGINE, ...args], {
    cwd, encoding: 'utf8', env: { ...process.env, NO_COLOR: '1' },
  });
  return { status: r.status, out: `${r.stdout || ''}${r.stderr || ''}` };
}

// Config mínima que hace pasar `init` en verde: hereda el arnés raíz
// (standalone:false, se saltan los ficheros base).
const GREEN_FILES = {
  'harness.config.json': { project: 't', standalone: false, commands: {} },
};

// ── init: entorno y ficheros ────────────────────────────────────────────────

test('init: árbol mínimo válido termina en verde (exit 0)', () => {
  const dir = scenario(GREEN_FILES);
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 0);
  assert.match(out, /Entorno listo/);
});

test('init: sin harness.config.json falla con exit 2 y mensaje claro', () => {
  const dir = tmp();
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 2);
  assert.match(out, /No se encontró harness\.config\.json/);
});

test('init: harness.config.json con JSON roto falla con exit 2 y mensaje claro', () => {
  const dir = scenario({ 'harness.config.json': '{ "project": ' });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 2);
  assert.match(out, /harness\.config\.json no es JSON válido/);
});

// ── restos del seguimiento anterior: el motor no los lee ─────────────────────

test('init: standalone:true basta con AGENTS.md, CLAUDE.md y CHECKPOINTS.md; ni docs/workflow.md ni el seguimiento antiguo se miran', () => {
  const dir = scenario({
    'harness.config.json': { project: 't', commands: {} },
    'AGENTS.md': '# base\n', 'CLAUDE.md': '# base\n', 'CHECKPOINTS.md': '# base\n',
    'feature_list.json': '{ "features": [', // JSON roto: antes habría fallado
    'progress/current.md': '# sesión\n',
  });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 0, out);
  assert.doesNotMatch(out, /feature_list|progress|Falta archivo base/);
  assert.match(out, /Entorno listo/);
});

test('init: ignora feature_list.json, progress/ y las claves viejas de la config aunque incumplan sus reglas antiguas', () => {
  // Un derivado conserva su historia y su config con las claves viejas. El feature_list.json
  // de aquí rompería la validación antigua: dos in_progress, un estado inválido y una
  // feature sdd en curso sin su .feature.
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false, commands: {},
      paths: { features: 'features', progress: 'progress', spec: 'project-spec.md', feature_list: 'feature_list.json' },
      rules: { one_feature_at_a_time: true, require_approved_spec_to_implement: true },
    },
    'feature_list.json': {
      features: [
        { id: 1, name: 'a', status: 'in_progress', sdd: true },
        { id: 2, name: 'b', status: 'wip' },
        { id: 3, name: 'c', status: 'in_progress' },
      ],
    },
    'progress/history.md': '# historia\n',
  });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 0, out);
  assert.doesNotMatch(out, /feature_list|progress|\.feature/);
});

test('config: "paths" y "rules" con solo claves heredadas siguen aplicando los defaults', () => {
  // Una config antigua sin paths.src ni las dos reglas de verify: los defaults siguen mandando.
  const legacy = { paths: { features: 'specs' }, rules: { one_feature_at_a_time: false } };
  for (const dir of ['src', 'tests']) { // paths.src y paths.tests por defecto: hay código, los tests corren
    const failing = scenario({
      'harness.config.json': { project: 't', standalone: false, commands: { test: 'node -e "process.exit(1)"' }, ...legacy },
      [`${dir}/foo.txt`]: 'x',
    });
    const init = runEngine(failing, ['init']);
    assert.equal(init.status, 1, init.out);
    assert.match(init.out, /Hay tests rotos/);
  }

  // Reglas de verify por defecto (true): sin suite aborta por tests; con suite y sin mutador, por mutación.
  for (const [commands, abortsOn] of [[{}, 'require_tests_to_close'], [{ test: 'node -e "process.exit(0)"' }, 'require_mutation_to_close']]) {
    const dir = scenario({ 'harness.config.json': { project: 't', standalone: false, commands, ...legacy } });
    const verify = runEngine(dir, ['verify']);
    assert.equal(verify.status, 1, verify.out);
    assert.match(verify.out, new RegExp(`${abortsOn} es true`));
  }
});

// ── config: valores por defecto y valores límite válidos ─────────────────────

test('config: "mutation.threshold" 1.0 (extremo válido del schema) sigue en verde', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false, commands: {},
      mutation: { threshold: 1.0, targets: [] },
    },
  });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 0, out);
  assert.match(out, /Entorno listo/);
});

test('config: "mutation.threshold" 0 (otro extremo válido) sigue en verde', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false, commands: {},
      mutation: { threshold: 0, targets: [] },
    },
  });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 0, out);
  assert.match(out, /Entorno listo/);
});

test('config: "mutation.threshold" ausente asume el default (0.8), sin exigir el campo', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false, commands: {},
      mutation: { targets: [] },
    },
  });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 0, out);
  assert.match(out, /Entorno listo/);
});

test('config: "standalone" false omite los ficheros base y sigue en verde', () => {
  const dir = scenario({
    'harness.config.json': { project: 't', standalone: false, commands: {} },
  });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 0, out);
  assert.match(out, /hereda el arnés raíz/);
  assert.match(out, /Entorno listo/);
});

test('config: tolera BOM UTF-8 al parsear harness.config.json', () => {
  const raw = '﻿' + json({ project: 't', standalone: false, commands: {} });
  const dir = scenario({ 'harness.config.json': raw });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 0, out);
  assert.match(out, /Entorno listo/);
});

// ── init: puerta "¿hay código?" para los tests ───────────────────────────────

test('init: corre los tests si hay código en src/ aunque tests/ esté vacío', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false,
      commands: { test: 'node -e "process.exit(3)"' },
    },
    'src/foo.txt': 'código',
  });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 1); // el comando de tests corrió y falló
  assert.match(out, /Hay tests rotos/);
});

test('init: sin código en src/ ni tests/ avisa pero no falla', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false,
      commands: { test: 'node -e "process.exit(3)"' },
    },
  });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 0); // el comando de tests NO corrió: nada que testear
  assert.match(out, /nada que testear/);
});

// ── init: puerta "¿hay código?" para el lint ─────────────────────────────────

test('init: NO corre el lint si src/ y tests/ están vacíos (clon limpio, avisa sin fallar)', () => {
  // Muchos linters salen distinto de 0 cuando su patrón no casa ningún fichero. El
  // comando de aquí SIEMPRE falla: si corriera, init saldría 1.
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false,
      commands: { lint: 'node -e "process.exit(1)"' },
    },
  });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 0, out); // el linter NO corrió: nada que lintar
  assert.match(out, /nada que lintar/);
  assert.doesNotMatch(out, /Lint con errores/);
});

test('init: corre el lint si hay código en src/ aunque tests/ esté vacío', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false,
      commands: { lint: 'node -e "process.exit(1)"' },
    },
    'src/foo.txt': 'código',
  });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 1); // el comando de lint corrió y falló
  assert.match(out, /Lint con errores/);
});

test('init: lint que pasa con código presente termina en verde', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false,
      commands: { lint: 'node -e "process.exit(0)"' },
    },
    'src/foo.txt': 'código',
  });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 0, out);
  assert.match(out, /Lint sin errores/);
  assert.match(out, /Entorno listo/);
});

// ── comando solo-espacios == sin comando (no falso verde) ────────────────────

test('commands.mutate solo-espacios == vacío → mutate falla con exit 2, no en falso verde', () => {
  // "   " no es un comando: sin el recorte en loadConfig, se contaría como declarado y
  // run() lo saltaría con status 0, imprimiendo "Prueba de mutación superada" sin mutador.
  const dir = scenario({
    'harness.config.json': {
      project: 't',
      commands: { mutate: '   ' },
      mutation: { targets: ['src/x.py'] },
    },
  });
  const { status, out } = runEngine(dir, ['mutate']);
  assert.equal(status, 2);
  assert.match(out, /commands\.mutate vacío/);
  assert.doesNotMatch(out, /Prueba de mutación superada/); // no certifica sin mutador
});

test('commands.test solo-espacios == vacío → init avisa, no "Todos los tests pasan"', () => {
  // Con código en src/ para aislar que la causa del WARN es el comando en blanco.
  const dir = scenario({
    'harness.config.json': { project: 't', standalone: false, commands: { test: '   ' } },
    'src/foo.txt': 'código',
  });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 0, out);
  assert.match(out, /No hay comando de tests declarado/);
  assert.doesNotMatch(out, /Todos los tests pasan/); // no dice que pasan si no corrió nada
});

test('un comando real con espacios de borde se recorta y SE EJECUTA (no se salta)', () => {
  // Si corre, init falla con exit 1 (el comando sale 4); si se saltara, saldría verde.
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false,
      commands: { test: '  node -e "process.exit(4)"  ' },
    },
    'src/foo.txt': 'código',
  });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 1);
  assert.match(out, /Hay tests rotos/); // el comando real corrió y falló (no se saltó)
});

// ── test ─────────────────────────────────────────────────────────────────────

test('test: propaga el exit code del comando de tests', () => {
  const dir = scenario({
    'harness.config.json': { project: 't', commands: { test: 'node -e "process.exit(7)"' } },
  });
  assert.equal(runEngine(dir, ['test']).status, 7);
});

test('test: commands.test vacío avisa y sale 0', () => {
  const dir = scenario({ 'harness.config.json': { project: 't', commands: {} } });
  const { status, out } = runEngine(dir, ['test']);
  assert.equal(status, 0);
  assert.match(out, /commands\.test vacío/);
});

// ── mutate: objetivos, umbral y sustitución de tokens ────────────────────────

test('mutate: commands.mutate vacío falla con exit 2', () => {
  const dir = scenario({ 'harness.config.json': { project: 't', commands: {} } });
  const { status, out } = runEngine(dir, ['mutate']);
  assert.equal(status, 2);
  assert.match(out, /commands\.mutate vacío/);
});

test('mutate: {{target}} con `$` se inserta literal, no vía reemplazo especial', () => {
  // Con un reemplazo string, "a$$b" se colapsaba a "a$b". El motor imprime el comando
  // resuelto ("$ ...") antes de ejecutarlo: esa línea debe contener el objetivo literal.
  const dir = scenario({
    'harness.config.json': {
      project: 't',
      commands: { mutate: `node -e "console.log('ok')" {{target}}` },
      mutation: { targets: ['a$$b'] },
    },
  });
  const { status, out } = runEngine(dir, ['mutate']);
  assert.equal(status, 0, out);
  assert.match(out, /a\$\$b/);
});

test('mutate: {{py}} se resuelve al intérprete de Python disponible', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't',
      commands: { mutate: '{{py}} --version' },
      mutation: { targets: ['x'] },
    },
  });
  const { out } = runEngine(dir, ['mutate']);
  assert.match(out, /python3?/); // 'python3' o 'python', nunca el token crudo
  assert.doesNotMatch(out, /\{\{\s*py\s*\}\}/);
});

test('mutate <target> explícito ignora la lista de la config', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't',
      commands: { mutate: `node -e "console.log('ran')" {{target}}` },
      mutation: { targets: ['AAA', 'BBB'] },
    },
  });
  const { status, out } = runEngine(dir, ['mutate', 'CCC']);
  assert.equal(status, 0, out);
  assert.match(out, /CCC/);
  assert.doesNotMatch(out, /AAA|BBB/);
});

test('mutate: un objetivo vacío o en blanco en mutation.targets falla (exit 1) sin lanzar el mutador', () => {
  for (const bad of ['', '   ']) {
    const dir = scenario({
      'harness.config.json': {
        project: 't',
        commands: { mutate: `node -e "console.log('ran')" {{target}}` },
        mutation: { targets: ['src/a.py', bad] },
      },
    });
    const { status, out } = runEngine(dir, ['mutate']);
    assert.equal(status, 1, out);
    assert.match(out, /Objetivo de mutación vacío o en blanco/);
    assert.doesNotMatch(out, /^ran$/m); // un verde sin medir nada sería peor que el fallo
  }
});

test('mutate <target> en blanco falla (exit 1) sin lanzar el mutador', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't',
      commands: { mutate: `node -e "console.log('ran')" {{target}}` },
      mutation: { targets: ['src/a.py'] },
    },
  });
  const { status, out } = runEngine(dir, ['mutate', '   ']);
  assert.equal(status, 1, out);
  assert.match(out, /Objetivo de mutación vacío o en blanco/);
  assert.doesNotMatch(out, /^ran$/m);
});

test('mutate: verde solo si TODOS los objetivos superan el umbral', () => {
  // El comando "pasa" (exit 0) solo cuando el objetivo es "ok".
  const dir = scenario({
    'harness.config.json': {
      project: 't',
      commands: { mutate: `node -e "process.exit(process.argv[1]==='ok'?0:1)" {{target}}` },
      mutation: { targets: ['ok', 'bad'] },
    },
  });
  const { status, out } = runEngine(dir, ['mutate']);
  assert.equal(status, 1);
  assert.match(out, /por debajo del umbral en:.*bad/);
});

test('mutate: lista vacía corre el mutador una vez sobre todo el proyecto', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't',
      commands: { mutate: 'node -e "process.exit(0)"' },
      mutation: { targets: [] },
    },
  });
  const { status, out } = runEngine(dir, ['mutate']);
  assert.equal(status, 0, out);
  assert.match(out, /superada \(1 objetivo\)/);
});

// ── tokens {{threshold}} y {{threshold_pct}} (opt-in) ────────────────────────
// Un comando que los usa recibe el umbral de mutation.threshold en la escala que pida
// la herramienta: 0.8 → "0.8" y "80". El motor sigue sin medir nada: pasa el valor y
// propaga el exit code del comando. Los derivados que no usan los tokens no cambian.

/** Imprime los dos tokens: la salida `t=<threshold> p=<pct>` es lo que recibió el comando. */
const SHOW_TOKENS = `node -e "console.log('t=' + process.argv[1] + ' p=' + process.argv[2])" {{threshold}} {{threshold_pct}}`;

for (const [threshold, plain, pct] of [[0.8, '0.8', '80'], [1, '1', '100'], [0.75, '0.75', '75'], [0.29, '0.29', '29'], [0.575, '0.575', '58'], [0, '0', '0']]) {
  test(`tokens: mutation.threshold ${threshold} → {{threshold}}="${plain}" y {{threshold_pct}}="${pct}" (entero más próximo)`, () => {
    // 0.8 * 100 es 80.00000000000001 (ceil daría 81); 0.29 * 100 es 28.999999999999996 (floor
    // daría 28); 0.575 * 100 es 57.49999999999999 (un Math.round a secas daría 57).
    const dir = scenario({
      'harness.config.json': { project: 't', commands: { mutate: SHOW_TOKENS }, mutation: { threshold, targets: [] } },
    });
    const { status, out } = runEngine(dir, ['mutate']);
    assert.equal(status, 0, out);
    assert.match(out, new RegExp(`^t=${plain.replace('.', '\\.')} p=${pct}$`, 'm')); // lo que ejecutó
    assert.match(out, new RegExp(` ${plain.replace('.', '\\.')} ${pct}\\r?\\n`)); // el eco "$ ..." lo muestra resuelto
    assert.doesNotMatch(out, /\{\{/);
  });
}

test('tokens: sin "mutation" en la config el umbral por defecto es 0.8 (→ "0.8" y "80")', () => {
  const dir = scenario({ 'harness.config.json': { project: 't', commands: { mutate: SHOW_TOKENS } } });
  const { status, out } = runEngine(dir, ['mutate']);
  assert.equal(status, 0, out);
  assert.match(out, /^t=0\.8 p=80$/m);
});

test('tokens: un mutate que exige {{threshold_pct}} = 80 sale 0 con el umbral por defecto', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't',
      commands: { mutate: `node -e "process.exit(process.argv[1]==='80'?0:1)" {{threshold_pct}}` },
    },
  });
  const { status, out } = runEngine(dir, ['mutate']);
  assert.equal(status, 0, out);
  assert.match(out, /Prueba de mutación superada/);
});

test('tokens: el mismo comando sale 1 si mutation.threshold es otro (el valor es el configurado)', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't',
      commands: { mutate: `node -e "process.exit(process.argv[1]==='80'?0:1)" {{threshold_pct}}` },
      mutation: { threshold: 0.5 },
    },
  });
  const { status, out } = runEngine(dir, ['mutate']);
  assert.equal(status, 1);
  assert.match(out, /por debajo del umbral/);
});

test('tokens: admiten espacios dentro de las llaves y conviven con {{target}} (con `$` literal)', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't',
      commands: { mutate: `node -e "console.log('ran')" {{ target }} {{ threshold }} {{ threshold_pct }}` },
      mutation: { threshold: 0.9, targets: ['a$$b'] },
    },
  });
  const { status, out } = runEngine(dir, ['mutate']);
  assert.equal(status, 0, out);
  assert.match(out, / a\$\$b 0\.9 90\r?\n/);
});

test('tokens: también se resuelven en commands.test (bin/harness test)', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't',
      commands: { test: `node -e "process.exit(process.argv[1]==='75'?0:1)" {{threshold_pct}}` },
      mutation: { threshold: 0.75 },
    },
  });
  const { status, out } = runEngine(dir, ['test']);
  assert.equal(status, 0, out);
});

test('tokens: init los resuelve en lint y tests, y el eco "$ ..." muestra el comando ya resuelto', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false,
      commands: {
        lint: `node -e "process.exit(process.argv[1]==='0.75'?0:1)" {{threshold}}`,
        test: `node -e "process.exit(process.argv[1]==='75'?0:1)" {{threshold_pct}}`,
      },
      mutation: { threshold: 0.75 },
    },
    'src/foo.txt': 'código',
  });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 0, out);
  assert.match(out, /Lint sin errores/);
  assert.match(out, /Todos los tests pasan/);
  assert.match(out, /\$ node .* 0\.75\r?\n/);
  assert.match(out, /\$ node .* 75\r?\n/);
});

// ── comando desconocido y verify ─────────────────────────────────────────────

test('comando desconocido (también el retirado `status`) falla con exit 2 y muestra la ayuda', () => {
  const dir = scenario(GREEN_FILES);
  for (const name of ['frobnicate', 'status']) {
    const { status, out } = runEngine(dir, [name]);
    assert.equal(status, 2, out);
    assert.match(out, new RegExp(`Comando desconocido: ${name}`));
  }
});

test('comando heredado del prototipo de Object (constructor) también es desconocido, no un exit 0 mudo', () => {
  const dir = scenario(GREEN_FILES);
  for (const name of ['constructor', 'toString']) {
    const { status, out } = runEngine(dir, [name]);
    assert.equal(status, 2, out);
    assert.match(out, /Comando desconocido/);
  }
});

test('verify: si init falla aborta con exit 1 y no da verde', () => {
  // standalone por defecto (true) sin los ficheros base → init falla → verify no sigue.
  const dir = scenario({
    'harness.config.json': { project: 't', commands: { test: 'node -e "process.exit(0)"', mutate: 'node -e "process.exit(0)"' } },
  });
  const { status, out } = runEngine(dir, ['verify']);
  assert.equal(status, 1);
  assert.match(out, /verify abortado: init falló/);
  assert.doesNotMatch(out, /Todo verde/);
});

// ── verify: las comprobaciones no pueden quedar en falso verde ───────────────

test('verify: require_mutation_to_close:true con commands.mutate VACÍO aborta, no en falso verde', () => {
  // Con la regla obligatoria (el default) y sin mutador declarado, verify no da
  // verde. require_tests_to_close:false aísla la comprobación de mutación: sin él, la de
  // tests (default true, commands.test vacío) fallaría primero.
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false, commands: {},
      rules: { require_tests_to_close: false, require_mutation_to_close: true },
    },
  });
  const { status, out } = runEngine(dir, ['verify']);
  assert.equal(status, 1);
  assert.match(out, /require_mutation_to_close es true pero commands\.mutate está vacío/);
  assert.doesNotMatch(out, /Todo verde/); // no da verde
});

test('verify: require_mutation_to_close:false con commands.mutate vacío omite la comprobación y sigue en verde', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false, commands: {},
      rules: { require_tests_to_close: false, require_mutation_to_close: false },
    },
  });
  const { status, out } = runEngine(dir, ['verify']);
  assert.equal(status, 0, out);
  assert.match(out, /Todo verde/);
});

test('verify: require_mutation_to_close:true con mutador que pasa termina en verde', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false,
      commands: { mutate: 'node -e "process.exit(0)"' },
      mutation: { targets: [] },
      rules: { require_tests_to_close: false, require_mutation_to_close: true },
    },
  });
  const { status, out } = runEngine(dir, ['verify']);
  assert.equal(status, 0, out);
  assert.match(out, /Prueba de mutación superada/);
  assert.match(out, /Todo verde/);
});

test('verify: require_mutation_to_close:true con mutador que NO supera el umbral aborta', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false,
      commands: { mutate: 'node -e "process.exit(1)"' },
      mutation: { targets: [] },
      rules: { require_tests_to_close: false, require_mutation_to_close: true },
    },
  });
  const { status, out } = runEngine(dir, ['verify']);
  assert.equal(status, 1);
  assert.match(out, /no supera el umbral/);
  assert.doesNotMatch(out, /Todo verde/);
});

test('verify: require_tests_to_close:true con commands.test VACÍO aborta, no en falso verde', () => {
  // `init` con commands.test vacío solo AVISA y sale 0; verify no da verde sin suite.
  // Se apaga la mutación para aislar la comprobación de tests.
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false, commands: {},
      rules: { require_tests_to_close: true, require_mutation_to_close: false },
    },
  });
  const { status, out } = runEngine(dir, ['verify']);
  assert.equal(status, 1);
  assert.match(out, /require_tests_to_close es true pero commands\.test está vacío/);
  assert.doesNotMatch(out, /Todo verde/);
});

test('verify: require_tests_to_close:false con commands.test vacío omite la comprobación y sigue en verde', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false, commands: {},
      rules: { require_tests_to_close: false, require_mutation_to_close: false },
    },
  });
  const { status, out } = runEngine(dir, ['verify']);
  assert.equal(status, 0, out);
  assert.match(out, /Todo verde/);
});

test('verify: require_mutation_to_close:true con commands.mutate solo-espacios aborta', () => {
  // "   " se recorta a "" y toma la misma rama que el vacío.
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false,
      commands: { mutate: '   ' },
      rules: { require_tests_to_close: false, require_mutation_to_close: true },
    },
  });
  const { status, out } = runEngine(dir, ['verify']);
  assert.equal(status, 1);
  assert.match(out, /require_mutation_to_close es true pero commands\.mutate está vacío/);
  assert.doesNotMatch(out, /Todo verde/);
});

test('verify: require_tests_to_close:true con commands.test solo-espacios aborta', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false,
      commands: { test: '  ' },
      rules: { require_tests_to_close: true, require_mutation_to_close: false },
    },
  });
  const { status, out } = runEngine(dir, ['verify']);
  assert.equal(status, 1);
  assert.match(out, /require_tests_to_close es true pero commands\.test está vacío/);
  assert.doesNotMatch(out, /Todo verde/);
});

test('verify: require_tests_to_close:true con commands.test declarado pasa la comprobación y da verde', () => {
  const dir = scenario({
    'harness.config.json': {
      project: 't', standalone: false,
      commands: { test: 'node -e "process.exit(0)"' },
      rules: { require_tests_to_close: true, require_mutation_to_close: false },
    },
  });
  const { status, out } = runEngine(dir, ['verify']);
  assert.equal(status, 0, out);
  assert.match(out, /Todo verde/);
});

// ── standalone:true: ficheros base obligatorios ──────────────────────────────

test('init: sin "standalone" (default true) y sin ficheros base falla nombrando cada uno', () => {
  const dir = scenario({ 'harness.config.json': { project: 't', commands: {} } });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 1);
  assert.match(out, /Falta archivo base: AGENTS\.md/);
  assert.match(out, /Falta archivo base: CLAUDE\.md/);
  assert.match(out, /Falta archivo base: CHECKPOINTS\.md/);
});

// ── red de seguridad: un fichero mal formado termina en [FAIL], no en una traza ──
// El motor no valida la forma de lo que lee. Cualquier excepción inesperada la recoge
// el despacho y la convierte en un mensaje de una línea con exit 2.

test('un harness.config.json mal formado termina en [FAIL] con exit 2 y sin traza', () => {
  const dir = scenario({
    'harness.config.json': { project: 't', standalone: false, commands: { test: 5 } },
  });
  const { status, out } = runEngine(dir, ['init']);
  assert.equal(status, 2);
  assert.match(out, /\[FAIL\]\s+Error inesperado: .*harness\.config\.json mal formado/);
  assert.doesNotMatch(out, /\n\s+at /); // sin traza de pila
});
