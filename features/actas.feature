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
