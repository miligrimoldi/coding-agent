---
title: NestJS - Validación de DTOs
ecosystem: nestjs
source_type: official_documentation_summary
source_url: https://docs.nestjs.com/techniques/validation
---

# ValidationPipe

NestJS permite validar datos de entrada mediante ValidationPipe. Las reglas de validación suelen declararse en clases DTO utilizando decoradores de class-validator.

La aplicación puede configurar ValidationPipe de manera global para que todos los controllers utilicen el mismo comportamiento.

# Whitelist y transform

La opción whitelist elimina propiedades que no estén declaradas en el DTO. La opción transform permite convertir los valores recibidos a los tipos esperados cuando la metadata disponible lo permite.

Para parámetros enum se puede declarar una propiedad tipada y utilizar IsEnum para rechazar valores que no pertenezcan al conjunto permitido.

# DTOs de query

Los filtros opcionales de un endpoint pueden representarse mediante un DTO de query. Las propiedades opcionales pueden combinar IsOptional con validadores como IsEnum, IsString o IsInt.