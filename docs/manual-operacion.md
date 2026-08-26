# Manual de operación

Pasos, no prosa. Cada sección responde *"pasó X, ¿qué hago?"*.

Todo se corre desde `/home/alonso/Documentos/Github/energy-rag-postgres-rag`.

---

## Uso normal

```bash
PYTHONPATH=. venv/bin/python scripts/preguntar.py "¿cada cuánto se reliquida el peaje?"
PYTHONPATH=. venv/bin/python scripts/preguntar.py --obligaciones coordinador
PYTHONPATH=. venv/bin/python scripts/preguntar.py --plazos
PYTHONPATH=. venv/bin/python scripts/preguntar.py --procesos
PYTHONPATH=. venv/bin/python scripts/preguntar.py --impacto 1160108   # si cambia esta norma...
PYTHONPATH=. venv/bin/python scripts/preguntar.py --cambios
PYTHONPATH=. venv/bin/python scripts/preguntar.py --bitacora          # preguntas reales
```
Una respuesta tarda **~100 s**. No está colgado. Ver *"por qué tarda tanto"* al final.

---

## No responde

Los tres servicios, en orden de probabilidad de ser el culpable:

```bash
docker start energy_rag_pg                    # 1. la base (se apagaba sola; ya no)
curl -s http://localhost:11434/api/tags       # 2. el modelo -> si falla: systemctl restart ollama (pide sudo)
nvidia-smi                                     # 3. la GPU
```
`preguntar.py` ya levanta Postgres solo si se cayó, y reintenta si un servicio muere a mitad
de consulta (`src/core/resiliencia.py`). Si igual falla, el mensaje dice cuál de los tres fue.

**Dice "el modelo no devolvió respuesta"**: Ollama agotó sus reintentos. `ollama ps` — si hay
otro modelo cargado, la VRAM no alcanza (el modelo ocupa ~20.5 de 24.5 GiB).

---

## El monitor avisa un cambio

El monitor corre solo los **lunes 06:00** sobre las 70 normas en dominio (~40 min).

```bash
scripts/monitor_run.sh                        # forzar una pasada ahora
cat docs/monitor-ultimo-informe.md            # qué encontró
PYTHONPATH=. venv/bin/python scripts/preguntar.py --cambios
tail -50 logs/monitor_$(date +%Y%m%d).log
```

**Antes de creerle a un evento**, mirar la `similitud` que guarda:
```
similitud >= 0.995  ->  cambio COSMÉTICO de BCN, no se registra evento
similitud <  0.995  ->  cambio real
```
Ya pasó una vez que 13 de 13 eventos eran cosméticos, y otra que un texto de largo
**idéntico** (30.087 chars, similitud 0.9997) se marcó como "CAMBIO REAL".

Con un cambio real: `--impacto <id_norma>` dice qué procesos toca antes de tocar nada.

---

## Hay que agregar una norma

```bash
PYTHONPATH=. venv/bin/python -m scripts.bajar_candidatas          # baja de BCN
PYTHONPATH=. venv/bin/python -m scripts.ingerir_nuevas            # parsea e ingesta
PYTHONPATH=. venv/bin/python -m scripts.marcar_fuera_dominio      # simula la frontera
PYTHONPATH=. venv/bin/python -m scripts.marcar_fuera_dominio --aplicar
PYTHONPATH=. venv/bin/python -m scripts.estructura_articulado --aplicar   # procesos
```
⚠️ **El buscador de BCN busca solo por número.** Pedir `DECRETO 44` (Reglamento del Panel de
Expertos) devolvió el `ACUERDO 44/2001` del Ministerio de **Educación** sobre el Instituto
Profesional Zipter; `DECRETO 88` devolvió un decreto exento de Educación de 1994. Antes eran
8 de 24 descargas erradas.

`bajar_candidatas` ahora tiene dos guardas —**no las tenía**, y por eso esas dos se guardaron:
```
identidad_ok()   tipo Y numero deben coincidir  -> ACUERDO 44 se RECHAZA
dominio_sim()    materia por ARTICULADO         -> Educacion dio 0.217 y 0.230 (corte 0.30)
```
La segunda **guarda igual y avisa**, no descarta: la frontera es una decisión aparte y
descartar en silencio escondería un acierto legítimo mal puntuado. Igual conviene mirar el
título de lo que bajó antes de ingerir.

---

## Se llena el disco

**Todo modelo vive en `/home/alonso/datos`, NUNCA en la raíz.** La raíz ya se llenó una vez con
253 GB de Ollama y el equipo se cayó.

```bash
df -h /                                       # raíz
du -sh /home/alonso/datos/ollama /home/alonso/datos/hf
ollama list                                   # borrar los que no se usan: ollama rm <modelo>
du -sh logs/ data/eval/results/               # logs y resultados: se pueden borrar, son reproducibles
```

---

## Se cortó una corrida larga

Todo runner guarda tras cada par y **retoma solo**. No hay que reiniciar desde cero.

```bash
crontab -l                                    # watchdog 15 min · retomar 3 h · monitor lunes
touch .watchdog_off                           # PAUSAR el watchdog
rm .watchdog_off                              # reanudar (retomar.sh también lo quita solo)
tail -20 logs/watchdog.log logs/retomar.log
```

---

## Ruido de la GPU

```bash
sudo nvidia-smi -pl 180                       # 180 W: silenciosa
```
`retomar.sh` la vuelve a 180 W cada 3 h (el límite no sobrevive un reinicio).
**Subir el límite no sirve de nada**: con este modelo la tarjeta nunca pasa de 230 W — es MoE
y el cuello es el ancho de banda de memoria, no la potencia.

---

## Por qué tarda ~100 s, y por qué no se arregla

Dos caminos probados y cerrados con medición:

```
exp #55  answer_doc_limit    el mejor valor deja 125.9 s   (objetivo 45 s)
exp #56  3 generaciones en   13.8 s secuencial  vs  25.0 s en paralelo
         paralelo            NUM_PARALLEL=3 llena la VRAM y cada token cuesta el doble
```
El tiempo lo domina generar **3 respuestas** (`self_consistency_n=3`), que es lo que sostiene
la precisión de las citas. Bajarlo a 1 va 3× más rápido y hace caer `cita_limpia` 12 puntos
(exp #54): acierta más, pero **rociando citas**, y en materia legal eso es peor.

Queda vLLM como única vía abierta. ⚠️ Su cuello es la **RAM de 14 GB** (distinto del cuello de
VRAM de exp #56).

---

## Diagnosticar una norma "truncada"

`texto_completo` con el placeholder `Loading` **no significa que el corpus esté roto**. El
retrieval no lee `texto_completo`: lee `fragmentos`, que salen de `articulos`. Lo que hay que
comparar es cuánto del documento cubre el articulado.

```sql
SELECT n.tipo, n.numero, length(n.texto_completo) tc,
       count(a.id) arts, coalesce(sum(length(a.texto)),0) suma
FROM normas n LEFT JOIN articulos a ON a.id_norma = n.id_norma
WHERE n.texto_completo ILIKE '%Loading%'
GROUP BY 1,2,3;
```

```
suma / tc  >= 0.9   el articulado cubre el documento -> NO tocar
suma / tc  <  0.9   articulado incompleto -> re-scrape + scripts.actualizar_norma
suma >> tc          los articulos vienen de otra pasada y estan completos -> NO tocar
```

Medido el 26-08 sobre las 8 normas en dominio con `Loading`: **sólo 3** tenían el articulado
incompleto (LEY 20936 0.63, LEY 20999 0.58, LEY 21667 0.53). El `DFL 4` daba la peor pinta
—10.075 caracteres de `texto_completo`— y es el que está **mejor**: sus 330 artículos suman
496.409 caracteres.

⚠️ `scripts/actualizar_norma.py` aborta si el articulado caería bajo el 90 %. Pasó con el
`DFL 4`: el texto nuevo era 58× más grande y aun así el reemplazo lo habría dejado en 278
artículos de 330. **El texto puede crecer y el articulado encoger igual.**
