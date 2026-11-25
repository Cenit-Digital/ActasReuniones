# ADR 0004 — MCP de solo lectura de las actas para Hermes, con datos personales enmascarados

- **Estado:** Aceptado. Encargo H2 del plan maestro «Cénit IA» (Pablo, 2026-11-25). Especificación: `EcosistemaAgentes/contenido/especificaciones/centralita-mcp.md`, punto 2.4. Escenarios de `features/mcp.feature`. Gemelo del ADR 0003 de PlataformaParaTranscribirAudios.
- **Alcance:** `POST /mcp` en un puerto propio del proceso del panel, con tres herramientas de lectura: `listar_reuniones`, `leer_acta` y `buscar_en_actas`. Sin escrituras (llegan en H3, con aprobación), sin audio, sin sala ni claves.

## Contexto

- Hermes tiene que contestar «¿qué se decidió en la última reunión de socios sobre X?». Las transcripciones nombran a terceros: los nombres de los socios se dejan; los correos y los teléfonos no salen.
- El panel es HTML y todo él va detrás de Traefik (secreto `X-Actas-Proxy`, usuario de BasicAuth, CSRF). No tiene tokens ni ámbitos.
- El MCP del Portal (ADR 0010 del Panel) y el de Transcribir (ADR 0003) siguen el mismo molde.

## Decisión

1. **API JSON = la capa de servicio, sin HTTP nuevo.** El encargo pide «una API JSON mínima de solo lectura sobre las mismas funciones». `actas.lectura_mcp` es esa capa: llama a `Repositorio.ultimas`, `detalle`, `buscar` y `socios`, las mismas que el panel, y el MCP se apoya en ella. No se abre una segunda superficie HTTP (más rutas = más que proteger).
2. **Puerto propio (8081), no el del panel (8080).** El 8080 exige el secreto de Traefik y un usuario, y trae rutas que escriben (grabar, parar, eliminar). Servir `/mcp` ahí obligaría a saltarse su guardia. El servidor del MCP es un segundo `uvicorn.Server` en un hilo del mismo proceso (uvicorn solo instala señales en el hilo principal: el panel las atiende y, al salir, para el MCP) que no sirve más que `/mcp`. URL: `http://actas-panel.actas.svc.cluster.local:8081/mcp`. El encargo citaba el 8080: se desvía por esto.
3. **Token: solo el SHA-256 en el entorno** (`ACTAS_MCP_TOKEN_SHA256`; el panel ya recibe sus secretos por entorno y ficheros, no hay tabla de tokens que ampliar). Se compara el SHA-256 del Bearer con `hmac.compare_digest`. La CLI `python -m actas.mcp_token emitir --fichero RUTA` genera `tmcp_` + 32 bytes, lo escribe con 0600 (creación exclusiva) y solo imprime el hash: no toca la base. Rotar: borrar el fichero, emitir otro y cambiar el hash. Sin hash o sin `ACTAS_MCP_HOSTS` no hay servidor MCP.
4. **Rechazos antes del SDK, en este orden:** método ≠ POST (405, `Allow: POST`), `Host` fuera de `ACTAS_MCP_HOSTS` (403, exacto, con puerto), cualquier `Origin` (403) y Bearer ausente o no válido (401, `WWW-Authenticate`). Cuerpo de hasta 64 KiB. `Cache-Control: no-store`.
5. **SDK `mcp` 2.3.0** (la vigente el 2026-11-25), fijado en `uv.lock` como el resto de dependencias del repo. `MCPServer` sin estado y con respuesta JSON; el gestor de sesiones se ejecuta en el lifespan de la app del MCP (el del panel va apagado). El logger `mcp` sube a WARNING.
6. **Lista blanca de salida** (`actas.lectura_mcp`): campo a campo. Nunca salen el `push` de un socio (su clave de VDO.Ninja; un socio desconocido sale como «Socio»), su correo, `sala_id`, `trabajo_id`, `pedido_por`, ni las conformidades. Una reunión en la papelera no se lee ni se busca (el panel tampoco enseña lo que dijeron). Topes: 25 reuniones por página (sobre las 100 últimas, como el panel), 20 resultados de búsqueda y, en `leer_acta`, 200 segmentos o 20 000 caracteres por página sin partir un segmento (2 000 como máximo), con `siguiente`. Páginas acotadas a 10 000.
7. **Enmascarado** (`actas.enmascarar`, el mismo que el de Transcribir) en todo texto libre (título, motivo, texto de los segmentos y de los fragmentos de búsqueda, nombres): correo → `[correo]` (también «ana arroba mail punto com», `(at)`, `@` con espacios, formas Unicode, sin dominio); teléfono (≥ 9 cifras con separadores, `+34`/`0034`, pegado a letras, cifras sueltas dictadas) → `···` y los 3 últimos. Una fecha con hora («2026-11-25 09:00») no es un teléfono. Coste lineal con textos largos. Los fragmentos de `ts_headline` llegan con los centinelas y los `<`, `>` y `&` cambiados de `busqueda.py`: se deshacen antes de enmascarar y se descartan las cifras sueltas de los bordes (un número cortado). Límite conocido: un correo o un teléfono dictados en palabras («seis uno dos…») no se reconocen.
8. **La búsqueda no es un oráculo de lo enmascarado:** `buscar_en_actas` rechaza `@`, «arroba» y tres cifras seguidas (salvo un año suelto).
9. **Auditoría propia:** la tabla `auditoria_mcp` (migración 0010): herramienta, resultado, duración y origen `mcp`; nunca los argumentos, el id de la reunión ni lo devuelto. `eventos` no sirve: es de las reuniones, el panel solo la lee y su lista de tipos es otra. `actas_panel` solo puede insertar (ni leer, ni modificar, ni borrar; los CHECK rechazan filas mal formadas). Si no se puede auditar, la herramienta responde un error y no sale ningún dato.
10. **Errores:** los de dominio llevan su mensaje fijo; cualquier otro es «Error interno» y al log solo va el tipo de la excepción (el DETAIL de PostgreSQL puede llevar la fila entera).

## Consecuencias

- KubernetesInfrastructure: puerto 8081 en el Deployment y el Service `actas-panel`, `ACTAS_MCP_HOSTS` y `ACTAS_MCP_TOKEN_SHA256`, NetworkPolicy de entrada desde `agente/app.kubernetes.io/name=hermes` (un solo `from`) y `/mcp` fuera de la IngressRoute. La migración 0010 la aplica `actas_owner` en el initContainer (el rol `actas_panel` ya existe).
- Las filas de `auditoria_mcp` no llevan datos personales; no se purgan solas (las limpia el dueño cuando haga falta).
- El panel y el MCP comparten proceso: si el panel cae, cae el MCP (y al revés, no).
