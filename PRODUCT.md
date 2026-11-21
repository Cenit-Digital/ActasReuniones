# Product

<!-- impeccable:product-schema 1 -->

> Escrito sin entrevista: el agente que lo redactó trabajaba sin nadie a quien preguntar. Todo sale del repositorio
> (`AGENTS.md`, `features/actas.feature`, `src/actas/panel/`, los tests del panel) y del encargo del 20-11-2026. Lo
> inferido lleva «(inferido)»; repásalo con `/impeccable init`.

## Platform

web

## Users

- **Los socios de Cénit Digital** (Pablo, Roberto y los que se den de alta en «Salas y socios»): entran al panel
  (`actas.cenitdigital.es`) con la autenticación básica de Traefik para grabar las reuniones de socios, consultar sus
  transcripciones y compartirlas.
- Nadie más: no hay registro ni usuarios externos. El grabador (supervisor) y la plataforma de transcripción no ven el
  panel; hablan con él por PostgreSQL.

## Product Purpose

Panel del grabador de actas: pedir que se grabe una reunión de VDO.Ninja con los socios conformes, pararla, programar
reuniones (también semanales), seguir su estado (pedida, grabando, grabada, transcribiendo, transcrita, error),
diagnosticar un fallo, leer y buscar en las transcripciones, compartirlas y llevar a la papelera lo que sobra. Tiene
éxito si una reunión de socios queda transcrita sin tocar la línea de órdenes y si, cuando algo falla, el panel dice
qué pasó y qué hacer.

## Positioning

Son datos personales (la voz y las palabras de los socios): solo se graba a quien da su conformidad con el texto
informativo vigente, el audio se borra en cuanto el texto está guardado (o a los 7 días) y ningún secreto sale en los
registros. El panel lo dice donde importa («Grabar», el pie) y nunca ofrece lo que esas reglas prohíben.

## Operating Context

- Herramienta interna de trabajo (modo Operate): se usa antes, durante y después de una reunión, desde el escritorio
  y a veces desde el móvil.
- Estados que cambian en minutos u horas (la transcripción tarda); la página enseña el estado al cargarse.
- Tema claro y oscuro: el del sistema por defecto, con un botón que lo cambia y se recuerda en el navegador.
- En producción en k3s (espacio `actas`), detrás de Traefik, que añade el usuario y el secreto del proxy.

## Capabilities and Constraints

- Rutas: la lista de reuniones (`/`), el detalle de una reunión (con su diagnóstico, transcripción y conformidades),
  «Grabar», la búsqueda, «Programación» (programar, modificar, cancelar), la papelera, «Salas y socios» (alta de sala y
  contraseña) y «Compartir».
- Starlette con plantillas Jinja2, sin framework de cliente. JavaScript solo para mejorar (tema y copiar): sin él todo
  se ve y funciona, y cada acción es un formulario POST del propio panel.
- CSP estricta: sin scripts ni estilos en línea, sin peticiones a terceros (fuentes autoalojadas).

## Brand Commitments

- Producto de **Cénit Digital**: marca Cénit (Bosque & Limón de día, Noche & Oro de noche, Outfit y DM Sans). El
  detalle visual vive en `DESIGN.md`, copiado de WebEmpresa y adaptado al panel.
- Voz cercana, en español de España, tuteando, sin jerga.
- Sin excepciones al detector de Impeccable en la marca propia (decisión de Pablo, 19-11-2026).

## Evidence on Hand

- Datos de demostración solo en los dobles de los tests (`tests/integracion/panel_falso.py`, servidos por
  `tests/integracion/panel_demo.py`): no son reuniones reales y no se usan como prueba de nada.

## Product Principles

- El estado manda: cada reunión dice en qué punto está con texto y glifo; el color solo acompaña (@a42).
- Un fallo se explica: el diagnóstico dice qué pasó, cuándo y qué se puede hacer.
- La privacidad se ve: quién dio su conformidad, con qué texto, y cuándo se borra el audio.

## Accessibility & Inclusion

- WCAG 2.2 AA: axe sin infracciones en 1280 y 390 px, en tema claro y oscuro, y sin desplazamiento horizontal
  (`tests/integracion/test_panel_navegador.py`, @a41); objetivos táctiles de 44 px.
