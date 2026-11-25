# language: es
Característica: MCP de solo lectura de las actas para el agente Hermes
  Para que Hermes pueda responder «¿qué se decidió en la última reunión sobre X?» sin ver datos personales de más
  Como panel de actas
  Quiero publicar `/mcp` solo en la red interna, solo con lecturas y con los datos personales enmascarados

  Antecedentes:
    Dado el puerto del MCP (8081) con `ACTAS_MCP_TOKEN_SHA256` y `ACTAS_MCP_HOSTS` configurados

  Escenario: Sin token o con otro no se entra
    Cuando se hace POST a /mcp sin Authorization, con otro Bearer o con otro esquema
    Entonces responde 401 con `WWW-Authenticate: Bearer`

  Escenario: Solo se admite POST
    Cuando se hace GET, PUT, DELETE, PATCH u OPTIONS a /mcp
    Entonces responde 405 con `Allow: POST`

  Escenario: El host debe ser el interno y Hermes no es un navegador
    Cuando se hace POST con un token bueno y un `Host` fuera de la lista, o con cualquier `Origin`
    Entonces responde 403

  Escenario: Sin configuración no hay servidor
    Dado que falta el hash del token o la lista de hosts
    Cuando arranca el panel
    Entonces no se abre el puerto del MCP; y el del panel (8080) nunca sirve `/mcp`

  Escenario: Tres herramientas, todas de solo lectura
    Cuando se pide `tools/list`
    Entonces salen `listar_reuniones`, `leer_acta` y `buscar_en_actas`, todas con `readOnlyHint: true`, y no hay recursos ni prompts

  Escenario: Nunca salen el push, el correo, la sala ni el trabajo
    Dado una reunión con socios, sala y trabajo de transcripción
    Cuando se lee por el MCP
    Entonces salen los nombres de los socios y ni su `push`, ni su correo, ni `sala_id`, ni `trabajo_id`; un socio desconocido sale como «Socio»

  Escenario: Una reunión en la papelera no se lee ni se busca
    Dado una reunión en la papelera
    Cuando se llama a `leer_acta` o a `buscar_en_actas`
    Entonces no sale nada de ella

  Escenario: El correo no sale y del teléfono solo salen 3 dígitos
    Dado un segmento con «escribe a ana@mail.com o llama al +34 612 345 678»
    Cuando se lee por el MCP
    Entonces sale «escribe a [correo] o llama al ···678»; y los años, las fechas con hora y los números cortos no se tocan

  Escenario: El enmascarado alcanza a los fragmentos de la búsqueda
    Dado un fragmento de `ts_headline` con centinelas y caracteres cambiados
    Cuando se busca por el MCP
    Entonces sale texto plano enmascarado, sin centinelas y sin cifras sueltas de un número cortado

  Escenario: Buscar no sirve para adivinar lo enmascarado
    Cuando se busca «612», «ana@mail.com» o «ana arroba mail»
    Entonces responde un error; y «presupuesto», «acta 2026» o «sala 4» se buscan con normalidad

  Escenario: Las actas largas se paginan
    Dado una reunión con más de 200 segmentos o de 20 000 caracteres
    Cuando se llama a `leer_acta`
    Entonces sale una página con `siguiente`, y con `desde` = `siguiente` la siguiente, hasta `siguiente` nulo

  Escenario: Cada llamada se audita sin contenido
    Cuando se llama a cualquier herramienta
    Entonces `auditoria_mcp` recibe una fila con herramienta, resultado y duración, y ningún argumento, id ni contenido

  Escenario: El panel solo puede insertar en la auditoría
    Dado el rol `actas_panel`
    Cuando intenta leer, modificar o borrar `auditoria_mcp`
    Entonces la base lo deniega; y rechaza filas mal formadas

  Escenario: Si no se puede auditar, no sale nada
    Dado que la auditoría falla
    Cuando se llama a una herramienta
    Entonces responde un error y ningún dato

  Escenario: Un fallo interno no cuenta nada
    Dado una consulta que lanza un error con texto de una reunión en su mensaje
    Cuando se llama a la herramienta
    Entonces el agente recibe «Error interno» y ni el log ni la respuesta llevan el mensaje

  Escenario: El token se emite con la CLI y no se imprime
    Cuando se ejecuta `python -m actas.mcp_token emitir --fichero RUTA`
    Entonces el token queda en RUTA con permisos 0600, la salida es solo su SHA-256 y no se sobrescribe un fichero existente
