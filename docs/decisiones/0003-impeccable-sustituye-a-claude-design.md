# ADR 0003 — Impeccable sustituye a Claude Design en el panel de actas

- **Estado:** aceptada al fusionarse el PR de adopción de la plantilla v0.5.0 (v0.5.1). Decisión de Pablo (CTO) del
  19-11-2026 para todos los repos de Cenit-Digital.
- **Alcance:** el panel (`src/actas/panel/`), `DESIGN.md`, `PRODUCT.md` y la CI de diseño.

## Contexto

La plantilla TemplateSSDUncleBob v0.5.0 retira Claude Design y la skill `frontend-design` y trae la skill
**Impeccable**, con una puerta de CI que exige 0 hallazgos del detector en el código y en las páginas servidas
(`docs/impeccable.md`). Este repo no usaba ninguna de las dos (no hay prototipos `.dc.html` ni instrucciones de Claude
Design), pero su panel llevaba los tokens «Terracota Clásica» y las fuentes (Gilda Display, Manrope, JetBrains Mono)
de la plataforma de transcripción, no la marca Cénit. Antes de este cambio, la puerta daba 16 hallazgos en el código
(con `DESIGN.md` de la marca) y 82 en las páginas servidas (fondo crema, palabras sueltas, líneas de más de 80
caracteres, columnas desequilibradas).

## Decisión

1. **El sistema de diseño es `DESIGN.md`:** la copia del de marca Cénit (`WebEmpresa@e7cbdaa`) con lo propio del panel
   al final («Superficie: panel de Actas») y sus colores (estado «programada» y los ocho hablantes) añadidos al
   frontmatter. `PRODUCT.md` recoge el producto. Toda pantalla nueva o cambio visual se trabaja con la skill.
2. **El panel pasa a la marca Cénit:** las variables del panel toman los valores de
   `WebEmpresa@e7cbdaa:src/styles/_tokens.scss` (Noche & Oro y Bosque & Limón), las fuentes son Outfit y DM Sans
   autoalojadas (las de `@fontsource` que ya sirve el panel de Scrapear) y la monoespaciada es la del sistema. El
   mecanismo del tema no cambia: sigue a `prefers-color-scheme` y el botón lo fija con `data-tema`.
3. **La puerta corre en los dos modos:**
   - Código: `node .harness/impeccable-gate.mjs` (workflow «Diseño (Impeccable)») sobre `src/actas/panel/estatico`
     (CSS y JavaScript). Las plantillas Jinja quedan fuera de `ui.paths`: enlazan `/estilo.css` con ruta absoluta, el
     detector no lo resuelve, avisa por stderr y la puerta suspende con el análisis incompleto (igual que en el ADR
     0006 de Scrapear). Esas plantillas, compuestas y con su CSS, las analiza el modo renderizado.
   - Renderizado: `--rendered` sobre el panel de demostración (`tests/integracion/panel_demo.py`: el panel real con
     el repositorio de mentira de los tests de navegador y las dos cabeceras de Traefik), en tema claro y oscuro,
     en el job `diseno-renderizado` de la CI y en su gemelo `diseno-renderizado-propio`. `ui.routes` son todas las
     pantallas que esa demo sirve con 200; un test lo comprueba.
4. **`upgrade.test.mjs` deja de correr en la CI de este derivado:** desde la v0.5.0 `harness.manifest.json` es el de
   la plantilla, idéntico, y no clasifica los ficheros del stack (`pyproject.toml`, `uv.lock`, `migraciones/`…), como
   ya pasa en Scrapear, el Portal de Citas y RAGchatbotIA. El comprobador del PR (`pr-body.test.mjs`) sigue corriendo.
5. **Histórico:** las menciones a «Terracota Clásica» en issues y PR anteriores (V1 de KubernetesInfrastructure#298,
   ADR 0023 de KubernetesInfrastructure) describen el panel de entonces y no guían el trabajo. Donde chocan con
   `DESIGN.md`, manda `DESIGN.md`.

## Consecuencias

- El panel cambia de aspecto (colores, tipografía, radios) sin cambiar textos ni funcionalidad; las pruebas de axe
  (@a41) siguen exigiendo WCAG 2.2 AA en 1280 y 390 px y en los dos temas.
- Las pantallas que solo salen con un 4xx (la página de mensaje: «no existe», el 400 de «Compartir» o de «Grabar» sin
  socios) no las mide la puerta, que pide 2xx: las cubre axe en `test_panel_navegador.py`.
