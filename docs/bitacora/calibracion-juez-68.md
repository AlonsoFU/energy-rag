# Calibración del juez de fidelidad (exp #73a) — 2026-09-07

**Pregunta**: el juez de #68 (qwen3:30b-a3b, think, temp 0) dice PARCIAL en 34 % (dev) / 20 %
(held-out) de las frases. ¿Es real o es el juez estricto? Los controles (pos 100 / neg 0)
dicen que no regala ni inventa, pero no miden estrictez sobre paráfrasis.

**Método**: 30 frases PARCIAL al azar (15 dev, 15 held-out, semilla 21), leídas contra el
texto del artículo citado por **Claude (no humano)** y clasificadas. 4 no verificables
(la definición cae fuera de los 3500 chars mostrados). Caveat: segundo LLM, no juez humano;
sesgo a favor de la lectura "razonable".

| clase | n | ejemplos |
|---|---|---|
| **SOPORTADA** (juez estricto) | **12 / 26** | Art. 126 de 1146553 casi textual; Art. 5 de 1216930 "Aviso" copiado literal; Art. 102 "cociente ≤ 5, Sistema Zonal" |
| PARCIAL justo | 6 / 26 | "mayor a 200 MW" por "superior o igual"; "se determina" por "podrán utilizar"; "Ley 21804 define" (nota BCN) |
| borderline | 6 / 26 | omite "diferencia entre" (Art. 151); agrega finalidad "para garantizar" (Art. 207-5); omite excepción de 4 mensualidades (Art. 92) |
| no verificable | 4 | glosarios largos truncados |

**5 de los 12 estrictos** tienen la nota BCN partiendo una palabra en el texto que leyó el
juez (`En|Ley 20402...|ergía`, `re|Decreto 70...|tirada`). #69b los saca.

**Lectura**: ~46 % de los PARCIAL son SOPORTADA. Corregido a mano, frase-SOPORTADA queda en
~76 % dev / ~78 % held-out (de 60 / 69). Sigue lejos de 90. Los errores reales (6 + parte de
los borderline) son los de #70/#71: cifra parafraseada, modalidad cambiada, condición omitida.

**Consecuencias**:
- #72 (borrar frases no SOPORTADA con este juez) borraría de más: se corre en modo `laxo`
  (borra solo NO_SOPORTADA) además del estricto, y su criterio no usa este juez.
- #73b (juez qwen3.6:27b sin think) mide lo mismo con otro modelo; si baja el PARCIAL a la
  mitad confirma esto.
- fiel_estricto 29/39 % es un PISO pesimista, no la verdad. La verdad está entre eso y ~55 %.
