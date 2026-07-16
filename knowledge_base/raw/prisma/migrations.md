---
title: Prisma Migrate - Cambios de schema
ecosystem: prisma
source_type: official_documentation_summary
source_url: https://www.prisma.io/docs/orm/prisma-migrate
---

# Prisma Migrate

Prisma Migrate permite mantener sincronizado el schema de Prisma con la estructura de la base de datos y conservar un historial de archivos de migración.

# Flujo de desarrollo

Durante desarrollo, prisma migrate dev puede generar una migración a partir de cambios realizados en schema.prisma y aplicarla sobre la base de datos de desarrollo.

Las migraciones deben revisarse antes de aplicarse, especialmente cuando agregan campos obligatorios, modifican enums o afectan datos existentes.

# Validación

El comando prisma validate permite comprobar que el schema de Prisma tenga una estructura válida sin aplicar una migración.