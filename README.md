# ActasReuniones

Supervisor del grabador de las reuniones de socios de Cenit Digital, cliente de la plataforma de transcripción y panel de
actas. Son la F1 y la F2 del
[ADR 0015](https://github.com/Cenit-Digital/KubernetesInfrastructure/blob/main/docs/infraestructura/decisiones/0015-actas-de-reuniones.md)
de KubernetesInfrastructure. Plan y criterios: KubernetesInfrastructure#223 (F1) y KubernetesInfrastructure#287 (F2).

```
panel «Grabar» / actas.sh grabar → reuniones.pedida ─┐
                                                     ├─ supervisor ── CDP ──► Chromium (una página por socio conforme, VDO.Ninja v30.2)
panel «Parar» / actas.sh parar  → parar_pedido_en ───┘     │                  └─► /grabaciones/<reunión>/<socio>_<ms>.webm (tmpfs)
                                                           ├─ POST /api/interno/actas/trabajos  (plataforma de transcripción, ADR 0017 D8)
                                                           ├─ GET  …/{id} hasta «listo» ─► segmentos (PostgreSQL, 12 meses)
                                                           └─ borra el audio del tmpfs ─► purgas (traza sin nombres)
```

- Estados: `pedida → grabando → grabada → transcribiendo → transcrita`, más `error` con su motivo. Tope de 3 h por grabación.
- Panel (`python -m actas.panel`, la misma imagen): lista de reuniones, transcripción con hablante y tiempo, búsqueda en
  español, «Grabar» con los socios conformes y el texto informativo vigente (`textos/informativo-<versión>.md`) y «Parar». Sin
  JavaScript. Escribe solo con `Repositorio.pedir` y `Repositorio.pedir_parada`, con el rol `actas_panel` (migración 0002), y
  se fía de la cabecera `X-Actas-Usuario` que pone el BasicAuth de Traefik. Configuración: `src/actas/panel/__main__.py`.
- Desarrollo: `bin/harness init`, `bin/harness test` y `bin/harness mutate`. Integración con PostgreSQL:
  `export ACTAS_DSN_PRUEBAS="$(scripts/pg-pruebas.sh arrancar)"`; con Chromium: `ACTAS_CHROMIUM=<binario>`.
- Despliegue: KubernetesInfrastructure, `kubernetes/apps/actas/` y `docs/infraestructura/runbooks/actas.md`.

Licencia MIT. Las páginas que abre el grabador son de VDO.Ninja (AGPL-3.0), servidas por `reuniones.cenitdigital.es`; este
repositorio no copia ni distribuye su código.
