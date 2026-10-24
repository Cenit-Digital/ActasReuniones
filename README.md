# ActasReuniones

Supervisor del grabador de las reuniones de socios de Cenit Digital y cliente de la plataforma de transcripción. Es la F1 del
[ADR 0015](https://github.com/Cenit-Digital/KubernetesInfrastructure/blob/main/docs/infraestructura/decisiones/0015-actas-de-reuniones.md)
de KubernetesInfrastructure. Plan y criterios: KubernetesInfrastructure#223.

```
actas.sh grabar → reuniones.pedida ─┐
                                    ├─ supervisor ── CDP ──► Chromium (una página por socio conforme, VDO.Ninja v30.2)
actas.sh parar  → parar_pedido_en ──┘      │                    └─► /grabaciones/<reunión>/<socio>_<ms>.webm (tmpfs)
                                           ├─ POST /api/interno/actas/trabajos  (plataforma de transcripción, ADR 0017 D8)
                                           ├─ GET  …/{id} hasta «listo» ─► segmentos (PostgreSQL, 12 meses)
                                           └─ borra el audio del tmpfs ─► purgas (traza sin nombres)
```

- Estados: `pedida → grabando → grabada → transcribiendo → transcrita`, más `error` con su motivo. Tope de 3 h por grabación.
- Desarrollo: `bin/harness init`, `bin/harness test` y `bin/harness mutate`. Integración con PostgreSQL:
  `export ACTAS_DSN_PRUEBAS="$(scripts/pg-pruebas.sh arrancar)"`; con Chromium: `ACTAS_CHROMIUM=<binario>`.
- Despliegue: KubernetesInfrastructure, `kubernetes/apps/actas/` y `docs/infraestructura/runbooks/actas.md`.

Licencia MIT. Las páginas que abre el grabador son de VDO.Ninja (AGPL-3.0), servidas por `reuniones.cenitdigital.es`; este
repositorio no copia ni distribuye su código.
