# Arquitectura — qué significa «hacer un buen trabajo»

> Este documento define el estándar de calidad de TU proyecto. Quien revisa el trabajo evalúa el código contra este archivo. **Si no está aquí, no es un requisito.** Rellénalo al arrancar el proyecto.

## Principios (agnósticos, ajústalos a tu stack)

1. **Capas claras y pocas.** Define las capas de tu proyecto y no introduzcas más (servicios, repositorios, ORMs, capas de abstracción) sin una razón concreta escrita en el plan. Un ejemplo: `storage` (persistencia) → `model` (dominio) → `cli`/`ui` (interfaz).
2. **Dependencias mínimas y justificadas.** Cada dependencia externa se discute en el plan antes de añadirla.
3. **Errores explícitos.** Las funciones que pueden fallar lanzan excepciones nombradas (o devuelven un `Result`/error tipado en stacks que lo prefieran), no valores nulos silenciosos.
4. **Inmutabilidad por defecto.** El estado del dominio se modela inmutable; modificar = crear una nueva instancia.
5. **Atomicidad en disco / efectos controlados.** Toda escritura persistente es atómica (temporal + rename); nunca dejar el estado a medio escribir.

## Plantilla: define aquí las capas de tu proyecto

```
usuario  ─→  <capa de interfaz>
              │
              ├─ construye <modelo de dominio>
              │
              └─→  <capa de persistencia>
                       │
                       └─→  <almacén>
```

## Qué NO hacer (rellena con tus antipatrones)

- No mezclar IO con lógica de dominio.
- No leer/escribir el almacén dentro de un bucle: carga al inicio, modifica en memoria, guarda al final.
- No añadir sistemas de configuración prematuros.
