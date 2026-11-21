---
name: Cénit Digital
description: Sistema de diseño de la marca Cénit Digital (copia de WebEmpresa@e7cbdaa) adaptado al panel de Actas, una superficie de producto en modo Operar.
colors:
  bosque: '#1e7a4f'
  bosque-tinta: '#1a6c46'
  limon: '#e3d34a'
  niebla: '#f2f4ef'
  niebla-alterna: '#e5e7e2'
  franja: '#d5d8d3'
  superficie: '#fafbf9'
  tarjeta: '#ffffff'
  tinta: '#0f1d17'
  tinta-suave: 'rgba(17, 32, 26, 0.74)'
  tinta-tenue: 'rgba(17, 32, 26, 0.66)'
  borde: 'rgba(17, 32, 26, 0.14)'
  franja-borde: 'rgba(17, 32, 26, 0.16)'
  superficie-tintada: 'rgba(30, 122, 79, 0.1)'
  etiqueta-tinta: '#175d3c'
  etiqueta-fondo: 'rgba(30, 122, 79, 0.13)'
  peligro: '#b3261e'
  aviso: '#8a5a00'
  velo: 'rgba(7, 33, 31, 0.55)'
  oro: '#c9a84c'
  oro-claro: '#d9c27a'
  noche: '#0e1512'
  noche-alterna: '#16201b'
  noche-franja: '#1a2520'
  bosque-noche: '#4f9a6e'
  marfil: '#f7f4ee'
  marfil-suave: 'rgba(247, 244, 238, 0.7)'
  marfil-tenue: 'rgba(247, 244, 238, 0.6)'
  borde-noche: 'rgba(201, 168, 76, 0.24)'
  franja-borde-noche: 'rgba(247, 244, 238, 0.12)'
  superficie-noche: 'rgba(247, 244, 238, 0.05)'
  tarjeta-noche: 'rgba(247, 244, 238, 0.045)'
  superficie-tintada-noche: 'rgba(201, 168, 76, 0.16)'
  etiqueta-fondo-noche: 'rgba(201, 168, 76, 0.22)'
  peligro-noche: '#f2b8b5'
  exito-noche: '#8fd0a3'
  aviso-noche: '#e8a85a'
  # Panel de Actas (ver «Superficie: panel de Actas»): estado «programada» y los ocho colores de hablante, día / noche.
  informacion: '#2f5a7a'
  informacion-noche: '#a9c3d3'
  hablante-verde: '#1a6c46'
  hablante-ocre: '#8a5a00'
  hablante-teja: '#a2431f'
  hablante-pizarra: '#2f5a7a'
  hablante-oliva: '#535e1d'
  hablante-vino: '#8a3a4a'
  hablante-arena: '#6b4f2a'
  hablante-tinta: '#0f1d17'
  hablante-verde-noche: '#8fd0a3'
  hablante-ocre-noche: '#e8a85a'
  hablante-teja-noche: '#e89870'
  hablante-pizarra-noche: '#a9c3d3'
  hablante-oliva-noche: '#c4cb8c'
  hablante-vino-noche: '#e6a3b0'
  hablante-arena-noche: '#e6cba9'
  hablante-marfil-noche: '#f7f4ee'
typography:
  display-xl:
    fontFamily: 'Outfit, system-ui, -apple-system, sans-serif'
    fontSize: '62px'
    fontWeight: 600
    lineHeight: 1.04
    letterSpacing: '-0.015em'
  display:
    fontFamily: 'Outfit, system-ui, -apple-system, sans-serif'
    fontSize: '44px'
    fontWeight: 600
    lineHeight: 1.08
    letterSpacing: '-0.01em'
  headline-lg:
    fontFamily: 'Outfit, system-ui, -apple-system, sans-serif'
    fontSize: '34px'
    fontWeight: 600
    lineHeight: 1.08
  headline:
    fontFamily: 'Outfit, system-ui, -apple-system, sans-serif'
    fontSize: '28px'
    fontWeight: 600
    lineHeight: 1.1
  title-lg:
    fontFamily: 'Outfit, system-ui, -apple-system, sans-serif'
    fontSize: '24px'
    fontWeight: 600
    lineHeight: 1.2
  title:
    fontFamily: 'Outfit, system-ui, -apple-system, sans-serif'
    fontSize: '20px'
    fontWeight: 600
    lineHeight: 1.25
  lead:
    fontFamily: 'DM Sans, system-ui, -apple-system, sans-serif'
    fontSize: '17px'
    fontWeight: 400
    lineHeight: 1.7
  body-lg:
    fontFamily: 'DM Sans, system-ui, -apple-system, sans-serif'
    fontSize: '16px'
    fontWeight: 400
    lineHeight: 1.65
  body:
    fontFamily: 'DM Sans, system-ui, -apple-system, sans-serif'
    fontSize: '15px'
    fontWeight: 400
    lineHeight: 1.65
  body-sm:
    fontFamily: 'DM Sans, system-ui, -apple-system, sans-serif'
    fontSize: '14px'
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: 'DM Sans, system-ui, -apple-system, sans-serif'
    fontSize: '13px'
    fontWeight: 600
    lineHeight: 1.4
  caption:
    fontFamily: 'DM Sans, system-ui, -apple-system, sans-serif'
    fontSize: '12px'
    fontWeight: 600
    lineHeight: 1.4
  code:
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'
    fontSize: '13px'
    fontWeight: 400
    lineHeight: 1.5
rounded:
  xs: '4px'
  sm: '8px'
  md: '12px'
  lg: '16px'
  xl: '20px'
  pill: '999px'
spacing:
  xs: '8px'
  sm: '14px'
  md: '22px'
  lg: '34px'
  xl: '54px'
  gutter: '26px'
  section: '84px'
components:
  button-primary:
    backgroundColor: '{colors.bosque}'
    textColor: '{colors.tarjeta}'
    typography: '{typography.body}'
    rounded: '{rounded.pill}'
    padding: '14px 28px'
  button-primary-noche:
    backgroundColor: '{colors.oro}'
    textColor: '{colors.noche}'
    typography: '{typography.body}'
    rounded: '{rounded.pill}'
    padding: '14px 28px'
  button-secondary:
    backgroundColor: 'transparent'
    textColor: '{colors.tinta}'
    typography: '{typography.body}'
    rounded: '{rounded.pill}'
    padding: '13px 27px'
  tag:
    backgroundColor: '{colors.etiqueta-fondo}'
    textColor: '{colors.etiqueta-tinta}'
    typography: '{typography.caption}'
    rounded: '{rounded.pill}'
    padding: '6px 13px'
  card:
    backgroundColor: '{colors.tarjeta}'
    rounded: '{rounded.xl}'
    padding: '36px 32px'
  input:
    backgroundColor: '{colors.superficie}'
    textColor: '{colors.tinta}'
    typography: '{typography.body-lg}'
    rounded: '{rounded.md}'
    padding: '13px 14px'
  nav-band:
    backgroundColor: '{colors.franja}'
    textColor: '{colors.tinta}'
    typography: '{typography.body}'
---

# Design System: Cénit Digital · Actas

> Copia del `DESIGN.md` de marca Cénit (repo Cenit-Digital/WebEmpresa, `main` en `e7cbdaa`, citado como
> `WebEmpresa@e7cbdaa`) con lo propio del panel de Actas al final, en «Superficie: panel de Actas», y sus colores
> propios añadidos al final de `colors` en el frontmatter. El resto del frontmatter y del texto es el de la marca y es
> normativo; la implementación está en `src/actas/panel/estatico/estilo.css`, con los valores de
> `WebEmpresa@e7cbdaa:src/styles/_tokens.scss` asignados a las variables del panel. Se diseña y se revisa con la skill
> Impeccable (`docs/impeccable.md`): **0 hallazgos del detector, sin excepciones en la marca propia** (decisión de
> Pablo, 19-11-2026). Si cambia la marca, se cambia primero en WebEmpresa y se vuelve a copiar.

## Overview

**Creative North Star: "El punto más alto del día"**

Cénit es el punto del cielo justo encima de quien mira: la marca lo dibuja como una órbita (anillo), una trayectoria
que sube y baja (onda) y un punto en lo más alto (cénit). El sistema traduce esa idea a dos luces del mismo paisaje:
**Bosque & Limón** de día (verde bosque sobre niebla, con el limón como sol) y **Noche & Oro** de noche (el mismo
bosque a oscuras, con el oro como luz). Es una marca cercana y concreta para pymes: geométrica pero cálida, con
superficies limpias, una sola voz de acento por pantalla y movimiento solo donde explica algo.

Tiene **dos registros** con las mismas piezas:

- **Persuadir (web de marketing):** secciones a sangre completa que alternan niebla y niebla alterna, titulares
  grandes en Outfit, entradillas en DM Sans, una llamada principal por bloque y aire generoso.
- **Operar (paneles y herramientas internas):** la marca aporta solo tipografía, paleta, densidad y su gesto
  propio (el punto cénit como marca del estado activo). La navegación y los controles son los estándar de la web;
  la pantalla se lee primero como producto de su categoría y después como Cénit.

**Key Characteristics:**

- Dos temas completos (claro y oscuro) conmutados con `data-theme` en `<html>`; ningún color fuera de `var(--color-…)`.
- Outfit para titulares y la marca, DM Sans para texto e interfaz, monoespaciada del sistema solo para datos técnicos.
- Una escala tipográfica cerrada (12 → 62 px) y una de radios cerrada (4 → 20 px y píldora).
- Jerarquía por tamaño, peso y espacio: nada de etiquetas diminutas en mayúsculas encima de los títulos.
- Contraste AA mínimo (4,5:1) en todo texto, en los dos temas.

### Qué cambió respecto a la marca anterior y por qué

La marca venía de un diseño de Claude Design (histórico en `design/`). Para cumplir el detector de Impeccable sin
excepciones se rediseñó así:

- **Sin kickers ni eyebrows.** Las etiquetas en mayúsculas espaciadas sobre los títulos («Soluciones digitales para
  pymes», «Lo que hacemos», «A quién ayudamos», «Paquetes», «Contacto») activaban `hero-eyebrow-chip` y
  `kicker-above-heading`. El título ya nombra la sección; cuando la etiqueta decía algo más, ese sentido pasa a la
  entradilla (p. ej. el hero abre su entradilla con «Soluciones digitales para pymes»).
- **Noche sin violeta.** El tema oscuro usaba un fondo noche violáceo (`#12082a`) y un violeta (`#7c5cbf`) como
  segundo color, en degradados oro → violeta y en textos de 3,2–3,8:1. Violeta sobre oscuro y sus degradados son la
  firma más reconocible de interfaz generada (`ai-color-palette`) y además no llegaba a AA. La noche pasa a ser el
  propio bosque a oscuras (`noche` `#0e1512`), el oro sigue de protagonista y el segundo color es el verde
  `bosque-noche` (`#4f9a6e`): el día y la noche comparten paisaje.
- **Verde legible como texto.** El verde bosque `#1e7a4f` daba 4,3:1 sobre la niebla alterna. Se conserva como color
  de relleno (botones, anillo, iconos) y el texto verde usa `bosque-tinta` (`#1a6c46`, 5,1:1).
- **Tinta tenue con AA.** La tinta tenue (`rgba(17,32,26,.45)`, 2,7:1) sube a 0,66 de opacidad (4,9:1); la suave, a
  0,74. En oscuro, 0,6 y 0,7.
- **Nada por debajo de 12 px.** «digital» del logotipo (8 px) y las notas «Ejemplo» (9,5 px) activaban
  `undersized-ui-text`. El logotipo pasa a 24 px + 12 px y las notas a 12 px en caja normal.
- **Escalas cerradas.** Había 31 tamaños de letra y 17 radios distintos; con `DESIGN.md` el detector exige que
  cada valor esté en la escala (`design-system-font-size`, `design-system-radius`).
- **Se quedan** Outfit y DM Sans (no están en la lista de tipografías sobreusadas del detector y son la marca
  desde RF-MARCA-001), la paleta Bosque & Limón y el oro. No había texto con degradado: los degradados de la marca
  son de superficie (onda del logotipo, cabeceras de sector, miniaturas) y nunca van detrás de texto.

## Colors

Dos paletas del mismo paisaje: verdes fríos y limón de día, oro sobre bosque nocturno de noche. Una sola voz de
acento por pantalla (verde de día, oro de noche); el segundo color solo decora (degradados de la onda, punto cénit).

### Primary

- **Verde Bosque** (`bosque`): relleno de la acción principal, anillo del logotipo, iconos y bordes activos en el
  tema claro. Con texto blanco encima da 5,3:1.
- **Bosque Tinta** (`bosque-tinta`): todo texto verde del tema claro (palabras destacadas de los títulos, teléfono,
  cifras, botón contorno). Sobre `franja` (cabecera y pie) da 4,45:1: ahí el texto verde
  es `etiqueta-tinta`.
- **Oro** (`oro`): acción principal, anillo, punto cénit y texto destacado del tema oscuro (8,1:1 sobre `noche`).
  Sobre el oro el texto es `noche`.

### Secondary

- **Limón** (`limon`): el sol del tema claro. Punto cénit del logotipo y final de los degradados de superficie.
  Nunca es color de texto ni de fondo de texto.
- **Bosque de Noche** (`bosque-noche`): segundo color del tema oscuro, final de los degradados oro → verde.

### Neutral

- **Niebla** (`niebla`) y **Niebla Alterna** (`niebla-alterna`): fondos de sección alternos del tema claro.
- **Franja** (`franja`): banda de la cabecera y el pie.
- **Superficie** (`superficie`) y **Tarjeta** (`tarjeta`): campos, notas y tarjetas.
- **Tinta** (`tinta`), **Tinta Suave** (`tinta-suave`) y **Tinta Tenue** (`tinta-tenue`): texto principal,
  secundario y metadatos. Las tres cumplen AA sobre cualquier fondo claro del sistema.
- **Noche** (`noche`), **Noche Alterna** (`noche-alterna`) y **Franja de Noche** (`noche-franja`): los mismos papeles en
  oscuro. **Marfil** (`marfil`, `marfil-suave`, `marfil-tenue`): textos del tema oscuro.
- **Borde** (`borde`, `borde-noche`; en la franja, `franja-borde` y `franja-borde-noche`): separadores y contornos de
  1 px.
- **Superficies tintadas** (`superficie-tintada`, `superficie-tintada-noche`) y, en oscuro, `superficie-noche`,
  `tarjeta-noche` y `etiqueta-fondo-noche`: los mismos papeles que sus equivalentes claros, como velos de marfil u
  oro sobre la noche.
- **Velo** (`velo`): fondo del menú móvil abierto.

### Estados (sobre todo en paneles)

- **Peligro** (`peligro` / `peligro-noche`), **Éxito** (`bosque-tinta` / `exito-noche`) y **Aviso** (`aviso` /
  `aviso-noche`). Siempre acompañados de texto o icono: el color confirma, no informa solo.

### Named Rules

**The One Voice Rule.** Un solo color de acento por tema: verde de día, oro de noche. Ningún tercer color de acento.

**The No Violet Night Rule.** Ni violeta ni cian sobre fondos oscuros, ni en degradados ni como tinta. La noche de
Cénit es bosque, no espacio.

**The Ink Rule.** El texto verde del tema claro es siempre `bosque-tinta`; `bosque` es solo de relleno.

## Typography

**Display Font:** Outfit (con system-ui, -apple-system, sans-serif)
**Body Font:** DM Sans (con system-ui, -apple-system, sans-serif)
**Label/Mono Font:** ui-monospace, SFMono-Regular, Menlo, Consolas, monospace (solo datos técnicos en paneles)

**Character:** Outfit es geométrica y redonda como la órbita del logotipo; DM Sans es una sans de lectura tranquila
que no compite con ella. Se cargan con `@fontsource` (400, 500, 600 y 700).

### Hierarchy

- **Display XL** (600, `clamp(34px, 5.4vw, 62px)`, 1,04): el titular del hero, una vez por página.
- **Display** (600, `clamp(28px, 4vw, 44px)`, 1,08): títulos de sección (h2).
- **Headline** (600, 28–34 px): título de tarjeta grande, cifras del hero (`clamp(28px, 8vw, 34px)`), títulos de
  página en paneles.
- **Title** (600, 20–24 px): títulos de tarjeta, paquete y sector; el nombre «cénit» del logotipo (24 px).
- **Lead** (400, 17 px, 1,7): entradillas de sección; la del hero crece a `clamp(17px, 4.4vw, 20px)`. Entre 46 y 62ch según la columna.
- **Body** (400, 15–16 px, 1,65): texto corrido y botones. Los campos de formulario van a 16 px.
- **Body SM** (400, 14 px): listas de características, pie, texto de tabla en paneles.
- **Label** (600, 13 px): etiquetas de campo, errores, notas.
- **Caption** (600, 12 px): etiquetas píldora, «digital» del logotipo y texto de las miniaturas. Es el mínimo.

### Named Rules

**The Closed Ramp Rule.** Solo los tamaños del frontmatter (12, 13, 14, 15, 16, 17, 20, 24, 28, 34, 44, 62 px).
Un `clamp()` solo une dos tamaños de la escala.

**The No Kicker Rule.** Nunca una etiqueta pequeña en mayúsculas espaciadas como bloque propio encima de un título
(ni con forma de píldora en el hero). Si la información importa, va en el título o en la entradilla.

**The 12px Floor Rule.** Ningún texto por debajo de 12 px, tampoco dentro de ilustraciones o miniaturas.

## Layout

- **Contenedor:** 1180 px máximo (`--maxw`), centrado, con margen lateral fluido `clamp(18px, 5vw, 26px)`.
- **Ritmo vertical:** cada sección lleva `clamp(56px, 9vw, 84px)` arriba y abajo; las secciones alternan `niebla` /
  `niebla-alterna` (o `noche` / `noche-alterna`) a sangre completa para marcar el cambio sin líneas.
- **Espaciado:** agrupaciones estrechas (8–14 px) dentro de un componente, 22–34 px entre piezas hermanas y 54 px
  entre la cabecera de una sección y su contenido.
- **Rejillas:** servicios en filas de dos columnas alternas (texto / miniatura), sectores 2 × 2, paquetes 3 columnas,
  contacto 1 : 1,1. Por debajo de 880 px todo pasa a una columna; por debajo de 560 px se reducen los rellenos.
- **Cabecera:** fija arriba, franja translúcida con desenfoque; por debajo de 768 px la navegación pasa a un panel
  lateral.
- **Títulos y párrafos:** `text-wrap: balance` en títulos y `text-wrap: pretty` en párrafos, para no dejar
  palabras sueltas.

### Superficies de producto (modo Operate)

- Estructura estándar de herramienta: barra lateral o superior de navegación sobre `franja`, área de trabajo sobre
  `niebla` y tarjetas o tablas sobre `tarjeta`. En oscuro, `noche-franja`, `noche` y `noche-alterna`.
- Densidad mayor que la web: texto base 14 px (`body-sm`), filas de tabla de 40–44 px, separaciones de 8 y 14 px.
- Títulos de página a 28 px (`headline`), de bloque a 20 px (`title`); nunca `display` en un panel.
- Cifras clave en Outfit 600 con su unidad y su contexto; los datos técnicos (ids, rutas, registros) en la
  monoespaciada a 13 px.
- **Gesto propio:** el punto cénit (círculo relleno de 6–8 px en `limon` de día y `oro` de noche) marca el elemento
  activo de la navegación o el elemento seleccionado. No parpadea ni late.

## Elevation & Depth

Sistema plano con una sola sombra ambiental. La profundidad la dan los fondos alternos y los bordes de 1 px; la
sombra se reserva para las piezas que flotan sobre la sección (tarjetas de servicio, de sector, el paquete
destacado y el formulario).

### Shadow Vocabulary

- **Ambiental** (`box-shadow: 0 18px 45px rgba(0, 0, 0, 0.12)` en claro; `0 22px 55px rgba(0, 0, 0, 0.5)` en
  oscuro): tarjetas que flotan sobre su sección.
- **Panel lateral** (`box-shadow: -20px 0 60px rgba(0, 0, 0, 0.25)`): solo el menú móvil abierto.

### Named Rules

**The Neutral Shadow Rule.** Sombras siempre negras y neutras. Nada de halos de color ni brillos.

## Shapes

Formas suaves y redondas, como la órbita: botones y etiquetas en píldora, tarjetas grandes con 20 px, miniaturas
con 16 px, campos y notas con 12 px, piezas pequeñas de las miniaturas con 8 y 4 px, y círculos (50 %) para puntos y
avatares. Los anillos finos de 1,5 px (eco del logotipo) decoran las cabeceras de sector. Sin bordes laterales de
acento.

## Components

### Buttons

- **Shape:** píldora (999 px).
- **Primary:** relleno `bosque` (oro en oscuro), texto blanco (`noche` en oscuro), DM Sans 600 a 15 px,
  `14px 28px`.
- **Hover / Focus:** brillo +8 % y elevación de 1 px; foco con contorno de 2 px del color primario y 2 px de
  separación.
- **Secondary:** transparente con borde de 1,5 px `borde`, texto `tinta`; al pasar por encima, el borde pasa al
  primario.

### Chips

- **Style:** chip de categoría de una tarjeta: píldora rellena `etiqueta-fondo` con texto `etiqueta-tinta`, DM Sans
  600 a 12 px, **en caja normal y sin espaciado**. Es metadato de la tarjeta (su categoría), no un kicker: nunca va en
  mayúsculas espaciadas ni encima de un título de sección o del hero.
- **Insignia del paquete destacado:** píldora primaria, en caja normal, a caballo del borde superior de la tarjeta.

### Cards / Containers

- **Corner Style:** 20 px (`xl`); sectores igual.
- **Background:** `tarjeta` (en oscuro, marfil al 4,5 %).
- **Shadow Strategy:** sombra ambiental (ver Elevation & Depth).
- **Border:** 1 px `borde`; el paquete destacado y la tarjeta al pasar por encima usan el primario.
- **Internal Padding:** de 22 a 36 px según la tarjeta (servicios 36 × 32, paquetes 32 × 28, formulario 30); en móvil,
  22 px. Nunca una tarjeta dentro de otra.

### Inputs / Fields

- **Style:** fondo `superficie`, borde de 1 px `borde`, radio 12 px, 16 px de texto, `13px 14px`.
- **Focus:** borde primario y contorno de 2 px.
- **Error / Disabled:** mensaje en `peligro` a 13 px bajo el campo; el botón desactivado baja al 60 % de opacidad.

### Navigation

- Franja fija con el logotipo a la izquierda y los enlaces (DM Sans 500, 15 px) a la derecha, el botón de tema y la
  llamada «Hablamos» en píldora primaria. En móvil, botón de menú y panel lateral sobre el velo.

### Logotipo «Órbita»

- Anillo (`--color-ring`), onda con degradado primario → secundario y punto cénit (`--color-zenith`); los colores
  salen siempre de los tokens, nunca se redibuja ni se fija un hex.
- Wordmark: «cénit» en Outfit 600 a 24 px y «digital» en DM Sans a 12 px, en minúsculas y con 0,2 em de espaciado.

### Miniaturas de servicio

- Ilustraciones decorativas (`aria-hidden`) de una interfaz real: navegador, chat, red social, mapa, calendario y
  flujo. Usan los mismos tokens, radios de 16, 12, 8 y 4 px y textos de 12 a 24 px. Debajo, una nota «Ejemplo»
  (12 px, 600, en caja normal) explica el caso. Son estáticas: el único movimiento es el punto que recorre el flujo web → ERP
  (que explica la sincronización y se para con `prefers-reduced-motion`); nada de indicadores que laten.

## Do's and Don'ts

### Do:

- **Do** consumir los colores solo con `var(--color-…)` y declarar cualquier color nuevo primero aquí.
- **Do** usar solo los tamaños de la escala cerrada y los radios 4, 8, 12, 16, 20 px, píldora o 50 %.
- **Do** comprobar el contraste AA (4,5:1) de todo texto en los dos temas antes de entregar.
- **Do** pasar el detector en los dos modos (`node .harness/impeccable-gate.mjs` y `--rendered`) hasta 0, también con
  el tema oscuro forzado en local.
- **Do** escribir el gesto del punto cénit como marca de estado activo en los paneles.

### Don't:

- **Don't** poner etiquetas en mayúsculas espaciadas encima de los títulos (kickers, eyebrows, chips en el hero).
- **Don't** usar violeta, púrpura o cian sobre fondos oscuros, ni degradados en esos tonos.
- **Don't** poner texto con degradado (`background-clip: text`) ni texto sobre los degradados de superficie.
- **Don't** usar `bosque` (#1e7a4f) como color de texto sobre `niebla-alterna`: usa `bosque-tinta`.
- **Don't** bajar de 12 px ningún texto, tampoco en miniaturas o logotipos.
- **Don't** usar Inter, Roboto, Fraunces, Geist, Plus Jakarta Sans ni Space Grotesk; la marca es Outfit + DM Sans.
- **Don't** añadir halos de color, brillos, puntos que laten ni marquesinas.

## Superficie: panel de Actas

El panel del grabador de actas (`actas.cenitdigital.es`, `src/actas/panel/`) es una herramienta interna en modo
**Operar**: Starlette con plantillas Jinja2, sin framework de cliente, con una CSP estricta (`style-src 'self'`,
`font-src 'self'`, sin nada en línea). Hasta el 20-11-2026 llevaba los tokens «Terracota Clásica» de Transcribir;
desde entonces lleva la marca Cénit.

### Tema

- **Sigue al sistema** (`prefers-color-scheme`): oscuro (Noche & Oro) por defecto en `:root` y claro (Bosque & Limón)
  cuando el sistema lo pide. El botón «Tema claro» de la cabecera (`tema.js`) lo fija con `data-tema` en `<html>`
  (`claro` u `oscuro`) y lo recuerda en el navegador. Es el equivalente del `data-theme` de la marca: no se renombra
  porque `tema.js` y sus pruebas lo usan, y la puerta de la CI solo mide el tema que llega por `prefers-color-scheme`.
- Las variables del panel (`--bg`, `--surface`, `--text`, `--muted`, `--accent-dark`…) toman los valores de la marca:
  `--bg` = `niebla` / `noche`, `--surface` = `tarjeta` / `tarjeta-noche`, `--surface2` = `niebla-alterna` /
  `noche-alterna`, `--cabecera` = `franja` / `noche-franja`, `--text` = `tinta` / `marfil`, `--muted` = `tinta-suave` /
  `marfil-suave`, `--ink` (enlaces) = `bosque-tinta` / `oro`, `--accent-dark` (acción principal y foco) = `bosque` /
  `oro`, `--line` = `borde` / `borde-noche`.

### Tipografía

- Outfit 600 para el nombre del panel en la cabecera (24 px, `title-lg`), los títulos de página (28 px, `headline`) y
  el título del texto informativo (24 px); DM Sans para todo lo demás, con el texto base a 15 px (`body`). Los datos
  técnicos (identificadores, horas, enlaces de sala) van en la monoespaciada del sistema a 13 px.
- Fuentes autoalojadas en `estatico/fuentes/` (las mismas `@fontsource` de Scrapear, con sus licencias OFL): la CSP no
  deja cargar Google Fonts.
- Las etiquetas de columna de las tablas y los títulos de bloque de la ficha de una reunión van en caja normal: nada
  de mayúsculas espaciadas.

### Estados y hablantes

- Cada estado de una reunión es una píldora con texto y glifo (@a42: el color solo acompaña): grabando y error en
  `peligro`, transcrita en `bosque-tinta` / `exito-noche`, pedida, grabada y transcribiendo en `aviso`, programada en
  `informacion` (pizarra), cancelada en `tinta-suave`.
- La transcripción da a cada hablante uno de ocho colores (`hablante-*`), siempre junto a su nombre. Son tonos de
  tierra y bosque, sin violeta ni cian (The No Violet Night Rule), y todos pasan AA (4,5:1) sobre `niebla`,
  `tarjeta` y `niebla-alterna` de día y sobre `noche`, `tarjeta-noche` y `noche-alterna` de noche.

### Formas y densidad

- Botones y píldoras de estado en píldora; campos y casillas de opción con 12 px; tarjetas, tablas y avisos con 16 px
  (más densos que las tarjetas de 20 px de la web); el resaltado de la búsqueda, 4 px.
- Controles de 44 px de alto como mínimo (objetivo táctil), contenedor de 1180 px como la marca.
- Títulos con `text-wrap: balance`, párrafos y elementos de lista con `text-wrap: pretty`; el texto informativo de
  «Grabar» se limita a 52ch (unos 75 caracteres por línea en DM Sans).
- La ficha de una reunión abre con dos columnas iguales (transcripción e historial; comprobaciones, datos y
  conformidades), que pasan a una cuando el contenido baja de 880 px (unos 944 px de ventana); «Pedir ayuda a Claude» va debajo, a todo el ancho. Así
  ninguna columna se alarga muy por debajo de la otra.

