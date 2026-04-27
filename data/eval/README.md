# Eval set (dominio: normativa eléctrica chilena)

Cada línea de `queries_chilean_electric.jsonl` es un objeto JSON con:
- `query`: pregunta tal cual la haría un usuario
- `expected_norma`: id canónico (ej. "DECRETO_62")
- `expected_articulo`: número de artículo o `null` si solo norma

Para extender: agregar una línea por cada query nueva. Apuntar a 50-100 queries
para tener métricas estables.

Ejecución:
```
python -m src eval
```
