---
title: Jest y TypeScript - Tests compatibles con ESLint y Prettier
ecosystem: jest
source_type: internal_engineering_guideline
source_url: internal://jest/testing-and-linting
---

# Conservación de tests existentes

Cuando se amplía cobertura, se deben mantener los tests existentes y agregar
nuevos casos sin eliminar comportamientos ya cubiertos.

Antes de modificar un archivo `spec` o `test`, se debe leer completo. Como
`write_file` reemplaza todo el archivo, la nueva versión debe conservar los
imports, mocks, setup y tests que sigan siendo válidos.

# Tipado en tests TypeScript

Los tests deben respetar TypeScript, ESLint y Prettier.

Evitar:

- `as any`
- asignaciones provenientes de valores `any`
- aserciones de tipo innecesarias
- imports usados solamente para realizar casts
- comentarios `eslint-disable` para ocultar errores

Cuando un argumento ya sea compatible con el método, se debe permitir que
TypeScript infiera su tipo.

Preferir:

```ts
await service.findAll({
  status: 'OPEN',
});
```

En lugar de:

```ts
await service.findAll({
  status: 'OPEN',
} as FindTicketsDto);
```

Los objetos simulados deben declarar directamente los campos necesarios:

```ts
const ticket = {
  id: 1,
  title: 'Sample',
  description: null,
  status: 'OPEN',
  createdAt: new Date(),
};
```

Evitar:

```ts
const ticket = {
  id: 1,
  title: 'Sample',
} as any;
```

# Mocks de Jest

Los mocks deben incluir todos los métodos utilizados por el servicio y los
nuevos casos de prueba.

Cada test debe configurar explícitamente sus respuestas mediante
`mockResolvedValue`, `mockRejectedValue` u otros métodos equivalentes.

Después de cada test, los mocks deben limpiarse siguiendo la convención del
repositorio.

# ESLint y Prettier

Los errores de ESLint y Prettier son fallas de implementación, aunque los tests
y el build pasen.

Se deben corregir especialmente:

- `@typescript-eslint/no-unsafe-assignment`
- `@typescript-eslint/no-unnecessary-type-assertion`
- `@typescript-eslint/no-explicit-any`
- imports sin utilizar
- `prettier/prettier`

No se deben silenciar estas reglas salvo que el repositorio ya tenga una
justificación explícita.

# Reintentos después del Tester

Los errores informados por el Tester deben tratarse como evidencia autoritativa.

En cada reintento, el Implementer debe:

1. Leer nuevamente el archivo actual.
2. Corregir todos los errores reportados.
3. Conservar los comportamientos que ya pasaban.
4. No repetir exactamente la implementación fallida.
5. No declarar éxito mientras quede algún check fallido.

# Validación final

Una implementación TypeScript se considera completa solamente cuando pasan
todos los comandos disponibles del repositorio:

```bash
npm run lint
npm run build
npm run test
```

## 2. Mejorar la detección de Jest en `Researcher`

Actualmente Jest se activa solamente cuando una dependencia contiene
literalmente `jest` y el pedido incluye términos de testing. Esto falla cuando
el Explorer detecta `@nestjs/testing` o archivos `.spec.ts`, pero no informa
`jest` como dependencia.

Reemplazar el bloque actual por:

```python
has_test_files = any(
    (
        ".spec." in path
        or ".test." in path
        or path.startswith("test/")
        or "/test/" in f"/{path}"
        or path.startswith("tests/")
        or "/tests/" in f"/{path}"
    )
    for path in relevant_files
)

uses_jest = bool(
    any(
        (
            "jest" in dependency
            or "@nestjs/testing" in dependency
        )
        for dependency in dependencies
    )
    or has_test_files
)

testing_terms = (
    "test",
    "tests",
    "testing",
    "prueba",
    "pruebas",
    "e2e",
    "spec",
    "coverage",
    "cobertura",
    "mock",
    "mocks",
)

has_testing_request = any(
    term in request
    for term in testing_terms
)

if uses_jest and (
    has_testing_request
    or has_test_files
):
    ecosystems.append(
        "jest"
    )
```

El resultado esperado es:

```json
{
  "ecosystems_searched": [
    "nestjs",
    "prisma",
    "jest"
  ]
}
```

## Componentes que no requieren cambios

No es necesario modificar:

- `DocumentLoader`
- `MarkdownChunker`
- `OpenAIEmbeddingProvider`
- `ChromaVectorStore`
- `Retriever`

El loader ya recorre subdirectorios, toma `ecosystem` del frontmatter y el
vector store conserva ese valor como metadata.