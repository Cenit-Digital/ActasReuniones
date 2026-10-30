# language: es
Característica: Captura y transcripción de las reuniones de socios (F1, ADR 0015)

  Escenario: @a6 sin socios conformes no se graba
    Dado una petición de grabar sin ningún socio conforme
    Cuando se envía con actas.sh grabar
    Entonces se rechaza y el supervisor no abre ninguna página

  Escenario: @a6 una conformidad por socio
    Dado una petición de grabar con sociopablo y socioroberto y la versión v1 del texto informativo
    Cuando se guarda
    Entonces hay una fila en conformidades por socio con su fecha y la versión v1
    Y solo se abren las páginas de esos streamIDs

  Escenario: @a7 tope de 3 h
    Dado una reunión grabando que nadie para
    Cuando pasan 3 h
    Entonces el supervisor la para de forma ordenada y la reunión pasa a grabada con el motivo tope_3h

  Escenario: @a8 transcripción por la plataforma
    Dado una reunión grabada con uno o varios <socio>_<ms>.webm por socio
    Cuando la plataforma devuelve listo
    Entonces la petición llevó una pista por fichero con su streamID y su desfase
    Y los segmentos quedan con hablante, inicio, fin y texto, ordenados por tiempo, y la reunión pasa a transcrita

  Escenario: @a10 borrado del audio
    Dado el audio de una reunión transcrita, o cualquiera de más de 7 días
    Cuando se ejecuta la purga
    Entonces los ficheros ya no existen y queda su traza en purgas, sin nombres

  Escenario: @a24 token no válido
    Dado el supervisor con un token incorrecto
    Cuando envía una reunión a la plataforma
    Entonces la reunión pasa a error con el motivo token y el audio se conserva para reintentar

  Escenario: @a25 aviso del grabador
    Dado una grabación en la que un socio conforme no publica en la sala
    Cuando pasa 1 min
    Entonces actas_aviso_sin_coincidencia vale 1

  # Grabadores huérfanos (reuniones del 2026-10-28 y del 2026-10-30): VDO.Ninja no para la grabación de un socio que cuelga.

  Escenario: @a63 el socio que cuelga deja su pista entera
    Dado una grabación en la que un socio cuelga y su par sale de session.rpcs con el grabador abierto
    Cuando pasan dos vigilancias, o se pide parar
    Entonces su grabador se para y su <socio>_<ms>.webm termina de descargarse
    Y el grabador de un socio que sigue en la sala no se toca

  Escenario: @a64 nada a medias se pierde en silencio
    Dado una parada tras la que queda un <socio>_<ms>.webm.crdownload con contenido webm
    Cuando el grabador para
    Entonces lo enlaza a <socio>_<ms>.webm antes de cerrar las páginas, la reunión se envía y el historial dice cuántas se rescataron
    Y una descarga a medias que no se puede rescatar consta en el historial como perdida, en rojo

  Escenario: @a65 aviso de un socio que publica sin grabarse
    Dado una grabación en la que un socio conforme publica en la sala y su página no graba
    Cuando pasa 1 min
    Entonces actas_socios_sin_grabar vale 1 y el historial lo dice en rojo

  # Panel de F2 (KubernetesInfrastructure#287): python -m actas.panel, detrás de NetBird y BasicAuth.

  Escenario: @a22 búsqueda en el panel
    Dado una reunión transcrita con un segmento de sociopruebaa que dice «presupuesto»
    Cuando se busca «presupuesto» en el panel
    Entonces aparece la reunión con ese segmento, su hablante y su tiempo hh:mm:ss
    Y el resaltado sale escapado: un segmento con <script> se muestra como texto

  Escenario: @a29 grabar desde el panel
    Dado el formulario «Grabar» con las salas, una casilla por socio activo y la versión del texto informativo
    Cuando se envía sin sala, sin socios, con un streamID que no es de un socio activo o con otra versión
    Entonces responde 400 y no hay ninguna fila nueva
    Pero con sala y socios válidos se crea la reunión pedida en esa sala, una conformidad por socio y pedido_por con el usuario
      de BasicAuth

  Escenario: @a30 parar desde el panel
    Dado una reunión grabando
    Cuando se pulsa «Parar»
    Entonces queda parar_pedido_en y el supervisor hace la parada ordenada
    Pero sin grabación activa el panel lo dice y no escribe nada

  Escenario: @a31 defensa CSRF
    Dado un POST a «Grabar» o «Parar» con Sec-Fetch-Site cross-site, con Origin de otro sitio o null, o sin ninguna de las dos
    Cuando llega al panel
    Entonces responde 403 y no hay ninguna fila nueva
    Pero el formulario del propio panel, enviado desde un navegador, lleva el Origin del panel (Referrer-Policy same-origin) y se acepta

  Escenario: @a32 sin rastro en los registros
    Dado una búsqueda con una marca única
    Cuando se mira el registro del panel
    Entonces la marca no aparece, ni la cabecera Authorization ni ningún texto de un segmento

  Escenario: @a33 mínimo privilegio del panel en la base
    Dado el rol actas_panel
    Cuando intenta un DELETE, un UPDATE de segmentos, salas, socios o su auditoría, o un DDL
    Entonces PostgreSQL lo rechaza

  # Panel v2 (V1 de KubernetesInfrastructure#298, ADR 0023): el aspecto de transcribir, la misma funcionalidad que F2.
  Escenario: @a40 tokens de transcribir y solo recursos propios
    Dado el panel v2
    Cuando se pide «/», «/reuniones/{id}», «/buscar» o «/grabar»
    Entonces la página usa los tokens Terracota Clásica, con tema oscuro y claro
    Y carga solo recursos del propio panel, fuentes incluidas, sin estilos ni scripts en línea
    Y la CSP lleva script-src 'self' sin unsafe-inline

  Escenario: @a41 accesible en escritorio y en móvil
    Dado cada pantalla del panel
    Cuando se audita con axe en 1280 y en 390 px, en tema oscuro y en claro
    Entonces no hay infracciones WCAG 2.2 AA ni barra de desplazamiento horizontal en la página

  Escenario: @a42 estados con texto y glifo
    Dado la lista con reuniones en grabando, programada, transcribiendo, transcrita, error y cancelada
    Cuando se muestra
    Entonces cada estado se distingue por su texto y su glifo, no solo por el color
    Y una reunión en error saca un aviso con enlace a su diagnóstico, en su ficha

  Escenario: @a62 enlaces con transcribir, lado del panel
    Dado una reunión cuyo audio se transcribió en transcribir
    Cuando transcribir enlaza a «/reuniones?trabajo=<id del trabajo>»
    Entonces el panel redirige a la ficha de la reunión, o da un 404 claro si ninguna tiene ese trabajo
    Y la ficha enlaza al trabajo en transcribir

  # Salas, socios y enlaces (V2 de KubernetesInfrastructure#298, ADR 0023 decisiones 3 y 4).
  Escenario: @a43 crear una sala
    Dado «Crear sala nueva» en el panel
    Cuando Pablo la confirma
    Entonces se guarda una sala con room y contraseña aleatorias
    Y la contraseña queda cifrada con AES-GCM: el valor en claro no aparece en la base y descifrarla con otra clave falla

  Escenario: @a44 enlace de cada socio
    Dado una sala y un socio activo
    Cuando se pide su enlace
    Entonces lleva room, hash (el de analisis.hash_sala de F0), push y label
    Y no lleva la contraseña

  Escenario: @a45 mostrar o copiar la contraseña
    Dado la ficha de una sala, con la contraseña oculta
    Cuando Pablo confirma «Mostrar»
    Entonces aparece la contraseña, con su botón «Copiar»
    Y la base anota clave_vista con el usuario y la sala, sin el valor, antes de dar la contraseña cifrada
    Pero el panel no puede leer la contraseña cifrada de ninguna otra forma

  Escenario: @a46 el supervisor graba en la sala de la reunión
    Dado una reunión pedida con su sala
    Cuando el supervisor la arranca
    Entonces abre las páginas espectadoras con la sala y la contraseña de esa reunión, no con SALA ni CLAVE del entorno
    Pero una reunión sin sala, o con una sala que no se descifra, pasa a error con el motivo «sala»

  Escenario: @a47 alta de socios sin guiones
    Dado «Salas y socios»
    Cuando Pablo da de alta un socio con un push con guiones
    Entonces el panel lo rechaza y la base también, y no hay ninguna fila nueva

  Escenario: la sonda de vida no depende de las conexiones ociosas
    Dado conexiones keep-alive ociosas de Traefik con el panel
    Cuando el kubelet pide «/salud»
    Entonces responde 200, y el tope de peticiones en curso no cuenta la sonda

  # V4 de KubernetesInfrastructure#298: registros, diagnóstico y reintentar (ADR 0023, decisión 7).

  Escenario: @a54 cada transición del supervisor deja su evento
    Dado el supervisor atendiendo una reunión
    Cuando la reunión cambia de estado (empezar, parar, enviar, transcribir, error, rescate o reintento)
    Entonces queda una fila en «eventos», en la misma transacción que el cambio, con su tipo y un detalle de la lista blanca
    Y también quedan las respuestas de transcribir, el aviso de socios y el borrado del audio

  Escenario: @a55 el historial no admite nada fuera de la lista blanca
    Dado un detalle con una clave fuera de la lista blanca, un valor que no es un código o una cadena con la contraseña de la sala
    Cuando se intenta insertar
    Entonces se rechaza: la base, por la lista blanca; el supervisor, además, por los secretos que solo él conoce

  Escenario: @a56 diagnóstico de una reunión en error
    Dado una reunión en error
    Cuando Pablo abre su ficha
    Entonces ve el motivo en lenguaje claro, «qué hacer» y el historial
    Y las comprobaciones: latido de menos de 30 s, Chromium, transcribir, espacio de grabación y versiones
    Y un enlace a los registros crudos en la consola

  Escenario: @a56 la reunión real en error por pistas, anterior al historial
    Dado la reunión de 6 s en «error: pistas», con la parada pedida a los 4 s y sin eventos
    Cuando Pablo abre su ficha
    Entonces el panel dice lo que duró, que no consta qué pista falló y que «Reintentar» no lo arregla
    Y no ofrece «Reintentar»

  Escenario: @a57 reintentar desde el panel
    Dado una reunión en error cuyo motivo se arregla reenviando y con el audio aún en el supervisor
    Cuando Pablo pulsa «Reintentar»
    Entonces el supervisor la pasa a «grabada» y la reenvía, sin terminal
    Y si el audio ya no está, la petición se descarta y la reunión sigue en error

  Escenario: @a58 copiar mensaje para los socios (compartir, nivel 1)
    Dado una reunión con transcripción y sala
    Cuando Pablo elige en «Compartir» la transcripción o el enlace de la sala y a qué socios
    Entonces el panel prepara un mensaje por socio, en un texto que se copia, y un mailto con el mismo contenido
    Y la transcripción va entera, con un .txt para adjuntarla si no cabe en el mailto
    Y cada socio recibe su propio enlace a la sala, nunca la contraseña: esa se copia desde la sala y va por otro canal
    Y el panel no envía nada: sale por el correo o la mensajería de Pablo

  Escenario: @a60 copiar diagnóstico para Claude
    Dado una reunión en error
    Cuando Pablo pulsa «Copiar diagnóstico para Claude»
    Entonces copia un bloque con el motivo, el diagnóstico, los eventos, las comprobaciones y las versiones
    Y los socios van como S1-S3 y los usuarios del panel como U1…
    Y no lleva contraseñas, hash, enlaces, la sala ni texto de los segmentos

  Escenario: @a48 una reunión programada empieza a su hora
    Dado una reunión «programada» para T con la conformidad de todos sus socios
    Cuando el reloj de la base llega a T
    Entonces el supervisor la pasa a «grabando» en su siguiente vuelta (cada 5 s)
    Y si falta la conformidad de algún socio, la pasa a «error» con el motivo conformidad
    Y si pasada su espera no pudo empezar, la pasa a «error» con el motivo no_empezo

  Escenario: si no entra nadie, se cancela
    Dado una reunión programada que ya graba con una espera de N minutos
    Cuando en esos N minutos no publica ningún socio conforme
    Entonces el supervisor la para, borra su audio y la deja «cancelada» con el motivo nadie_entro

  Escenario: @a49 modificar solo mientras está programada
    Dado una reunión «programada»
    Cuando Pablo cambia la fecha, la sala, el tope o los socios
    Entonces se guarda por la función modificar_programada y queda en el historial
    Y en una reunión que ya graba, la base lo rechaza (trigger), también al supervisor

  Escenario: @a50 cancelar sin borrar filas
    Dado una reunión «programada»
    Cuando Pablo confirma «Cancelar»
    Entonces pasa a «cancelada» sin borrar ninguna fila
    Y «esta y las siguientes» deja de repetirla

  Escenario: @a51 eliminar a la papelera y borrar a los 7 días
    Dado una reunión terminada
    Cuando Pablo escribe su título y confirma «Eliminar»
    Entonces va a la papelera, desde donde se puede recuperar
    Y a los 7 días la purga diaria la borra con borrar_reunion, con sus dependientes, y deja una fila en purgas sin contenido
    Y ni actas_panel ni actas_app tienen DELETE directo en ninguna tabla

  Escenario: @a52 purga de 12 meses
    Dado una transcripción de hace más de 12 meses
    Cuando pasa la purga diaria
    Entonces se borra y queda una fila en purgas con el motivo plazo_12m

  Escenario: @a53 la siguiente de una serie
    Dado una reunión con repetir semanal o mensual
    Cuando sale de «programada» (empieza, no puede empezar o se cancela solo ella)
    Entonces el supervisor crea la siguiente «programada» con la misma sala, tope, espera y socios, y sin conformidades
    Y la mensual va el mismo día o, si el mes no lo tiene, el último

  Escenario: @a61 parar el pod a mitad de una reunión no pierde el audio
    Dado una reunión «grabando» y un despliegue, un rollout o un borrado del pod
    Cuando el preStop del supervisor pide el drenaje
    Entonces no empieza ninguna reunión nueva y la que graba sigue hasta «Parar», el tope o el grabador caído
    Y el pod no termina hasta que sus pistas están enviadas a la plataforma (o vence el plazo de gracia de 4 h)
    Y Chromium sigue vivo mientras haya una grabación activa
