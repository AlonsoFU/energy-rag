
## gen8a_v2 — 2026-08-09 19:52
PRUEBA del reporte automatico (experimento ya conocido: debe dar -16 y trade-off)

```
cita_ok      OFF 260/267  ->  ON 244/267   (gano 1, perdio 17)
McNemar p=0.0001  (SIGNIFICATIVO NEGATIVO)
cita_limpia(>=0.5)  OFF 169/267  ->  ON 185/267   (+16)
cita_perfecta(1.0)   OFF  84/267  ->  ON 124/267   (+40)
precision           OFF   0.58      ->  ON   0.66
citas unicas        OFF   3.04      ->  ON   1.84
```

Flips:
- PIERDE `qué es Reposición`
- PIERDE `qué es Proyecto`
- GANA  `qué es Energía de Regulación`
- PIERDE `qué significa Informe Definitivo`
- PIERDE `qué es Sistema de Transmisión`
- PIERDE `definición de Sistema de Transmisión`
- PIERDE `qué significa Sistema de Transmisión`
- PIERDE `qué es Infracciones gravísimas`
- PIERDE `definición de Infracciones gravísimas`
- PIERDE `qué significa Infracciones gravísimas`
- PIERDE `qué significa Coordinador`
- PIERDE `definición de DIP`
- PIERDE `qué es Infracciones graves`
- PIERDE `definición de Infracciones graves`
- PIERDE `qué es Costo de Falla de Larga Duración`
- PIERDE `qué significa Costo de Falla de Corta Duración`
- PIERDE `qué es Superintendencia`
- PIERDE `definición de Infracciones leves`

**LECTURA AUTOMATICA: TRADE-OFF** (cita_ok -16 pero cita_limpia +16) — decision de producto, NO adoptar solo.

## gen12_hybrid — 2026-08-09 19:55
HIBRIDO think: intento 0 con think=True; si rechaza o no deja cita valida, reintenta con think=False.

```
cita_ok      OFF 260/267  ->  ON 250/267   (gano 1, perdio 11)
McNemar p=0.0063  (SIGNIFICATIVO NEGATIVO)
cita_limpia(>=0.5)  OFF 170/267  ->  ON 185/267   (+15)
cita_perfecta(1.0)   OFF  85/267  ->  ON 123/267   (+38)
precision           OFF   0.59      ->  ON   0.66
citas unicas        OFF   3.03      ->  ON   1.96
```

Flips:
- PIERDE `qué es Reposición`
- GANA  `qué es Energía de Regulación`
- PIERDE `qué significa Informe Definitivo`
- PIERDE `qué es Sistema de Transmisión`
- PIERDE `definición de Sistema de Transmisión`
- PIERDE `qué significa Sistema de Transmisión`
- PIERDE `qué es Infracciones gravísimas`
- PIERDE `definición de Infracciones gravísimas`
- PIERDE `qué significa Infracciones gravísimas`
- PIERDE `qué es Infracciones graves`
- PIERDE `definición de Infracciones graves`
- PIERDE `definición de Infracciones leves`

**LECTURA AUTOMATICA: TRADE-OFF** (cita_ok -10 pero cita_limpia +15) — decision de producto, NO adoptar solo.

## gen2_selfcons — 2026-08-10 02:01
GEN2 self-consistency N=3: se queda con la respuesta que mas respalda el consenso de citas (>=2 de 3).

```
cita_ok      OFF 260/267  ->  ON 259/267   (gano 3, perdio 4)
McNemar p=1.0000  (ruido/flat)
cita_limpia(>=0.5)  OFF 170/267  ->  ON 188/267   (+18)
cita_perfecta(1.0)   OFF  85/267  ->  ON 114/267   (+29)
precision           OFF   0.59      ->  ON   0.66
citas unicas        OFF   3.03      ->  ON   2.35
```

Flips:
- PIERDE `qué es Reposición`
- GANA  `qué es Energía de Regulación`
- PIERDE `definición de Sistema de Transmisión`
- GANA  `qué es Coordinador`
- PIERDE `definición de Infracciones graves`
- GANA  `qué significa Infracciones graves`
- PIERDE `definición de Infracciones leves`

**LECTURA AUTOMATICA: TRADE-OFF** (cita_ok -1 pero cita_limpia +18) — decision de producto, NO adoptar solo.
