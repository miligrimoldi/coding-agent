---
title: Prisma Client - Filtrado y ordenamiento
ecosystem: prisma
source_type: official_documentation_summary
source_url: https://www.prisma.io/docs/orm/prisma-client/queries/filtering-and-sorting
---

# Filtros con where

Prisma Client permite filtrar resultados mediante la propiedad where. Los filtros pueden aplicarse sobre uno o varios campos del modelo.

Cuando un filtro es opcional, el código puede construir dinámicamente el objeto where e incluir solamente las propiedades recibidas.

# Enums

Los campos enum definidos en schema.prisma generan tipos que pueden utilizarse desde Prisma Client. Los valores enviados a las consultas deben coincidir con los valores definidos en el enum.

# Listados

Los filtros pueden combinarse con findMany. También pueden combinarse con orderBy, paginación y filtros sobre relaciones.