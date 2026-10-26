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

  # Panel de F2 (KubernetesInfrastructure#287): python -m actas.panel, detrás de NetBird y BasicAuth.

  Escenario: @a22 búsqueda en el panel
    Dado una reunión transcrita con un segmento de sociopruebaa que dice «presupuesto»
    Cuando se busca «presupuesto» en el panel
    Entonces aparece la reunión con ese segmento, su hablante y su tiempo hh:mm:ss
    Y el resaltado sale escapado: un segmento con <script> se muestra como texto

  Escenario: @a29 grabar desde el panel
    Dado el formulario «Grabar» con una casilla por socio conocido y la versión del texto informativo
    Cuando se envía sin socios, con un streamID que no es de un socio conocido o con otra versión
    Entonces responde 400 y no hay ninguna fila nueva
    Pero con socios válidos se crea la reunión pedida, una conformidad por socio y pedido_por con el usuario de BasicAuth

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
    Cuando intenta un DELETE, un UPDATE de segmentos o un DDL
    Entonces PostgreSQL lo rechaza
