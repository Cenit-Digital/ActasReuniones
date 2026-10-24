# Adaptador: Java

Mapea el arnés a un proyecto Java con Maven. El runner de tests es `mvn test`; la
mutación usa [PIT](https://pitest.org/quickstart/maven/) (pitest 1.30.1). Ver
también `generic.md`.

## `harness.config.json`

```json
{
  "language": "java",
  "commands": {
    "lint": "mvn -q checkstyle:check",
    "test": "mvn -q test",
    "mutate": "mvn test-compile org.pitest:pitest-maven:mutationCoverage -DmutationThreshold={{threshold_pct}} -DtargetClasses=\"{{target}}\""
  },
  "paths": { "src": "src/main/java", "tests": "src/test/java" },
  "mutation": { "threshold": 0.8, "targets": ["com.example.notes.*"] }
}
```

- Las comillas dobles de `-DtargetClasses` van escapadas por ser JSON; en la
  shell protegen el glob.
- `mutationThreshold` está en escala 0–100 y **entera** (salvo que
  `thresholdPrecision` > 0), justo lo que da `{{threshold_pct}}`; 0 = desactivado.
  Se pasa por `-D` igual que `targetClasses`.
- `targetClasses` filtra las clases por globs de nombres cualificados
  (`com.example.notes.*`), no por fichero; los tests se acotan con `targetTests`.
  Como el comando usa `{{target}}`, no dejes `targets` vacío.
- Código de salida al no alcanzar el umbral: NO VERIFICADO en la documentación
  de PIT (su código fuente lanza `MojoFailureException`). Plugin de PIT para
  JUnit 5: NO VERIFICADO en esta pasada.

## Layout típico

Maven separa fuente y test bajo `src/`, con el árbol de paquetes replicado:

```
pom.xml
src/main/java/com/example/notes/Notes.java
src/test/java/com/example/notes/NotesTest.java
```

## Alternativa: Gradle

Con el plugin [`info.solidsoft.pitest`](https://github.com/szpak/gradle-pitest-plugin)
(1.19.0) el umbral y las clases viven en `build.gradle`:

```groovy
pitest { mutationThreshold = 80; targetClasses = ['com.example.notes.*'] }
```

No hay override nativo por línea de comandos: el README del plugin remite a
gradle-override-plugin, que no soporta `Set`, así que no vale para
`targetClasses`. Por tanto el umbral no puede viajar por token: **mantén
`mutationThreshold` alineado a mano con `mutation.threshold`** (0.8 → `80`), el
comando no usa `{{target}}`, `targets` va vacío y `mutate <módulo>` no acota nada.
El nombre de la tarea Gradle que ejecuta PIT: NO VERIFICADO aquí; ver el README
del plugin.

Mutantes equivalentes: exclúyelos con los filtros nativos de PIT y documenta por
qué en el PR; sus nombres (`excludedMethods`, `excludedClasses`): NO VERIFICADO.

Verificado el 2026-10-17 en: https://pitest.org/quickstart/maven/ · https://pitest.org/quickstart/commandline/ · https://github.com/szpak/gradle-pitest-plugin
