# 🚀 Guía: Descarga Masiva de Normas BCN

## ¿Qué hace este script?

**`scripts/DOWNLOAD_ALL_NORMS.py`** descarga automáticamente el **texto completo con artículos** de todas las 2,031 normas del dataset.

### Características

- ✅ **Progreso incremental**: Si se interrumpe, puedes continuar donde quedó
- ✅ **Anti-bloqueo**: Delays automáticos para evitar ban de BCN
- ✅ **Barra de progreso**: Visualización en tiempo real
- ✅ **Checkpoint automático**: Guarda cada 10 normas
- ✅ **Estimación de tiempo**: Te dice cuánto falta
- ✅ **Modo background**: Puede correr 24/7 sin supervisión

---

## 🎯 Uso Rápido

### 1. Descargar TODAS las 2,031 normas (24-48 horas)

```bash
# En una terminal normal
python3 scripts/DOWNLOAD_ALL_NORMS.py

# O en background (recomendado para 24h+)
nohup python3 scripts/DOWNLOAD_ALL_NORMS.py &> download.log &

# Ver progreso en tiempo real
tail -f download.log
```

**Tiempo estimado:** 24-48 horas (30s delay entre cada norma)

---

### 2. Descargar solo TOP 50 más importantes (2 horas)

```bash
python3 scripts/DOWNLOAD_ALL_NORMS.py --top 50
```

**Tiempo estimado:** ~30 minutos - 1 hora

---

### 3. Descargar solo TOP 200 (10 horas)

```bash
# En background
nohup python3 scripts/DOWNLOAD_ALL_NORMS.py --top 200 &> download.log &
```

**Tiempo estimado:** ~3-5 horas

---

### 4. Continuar descarga interrumpida

```bash
# Si presionaste Ctrl+C o se cortó la conexión
python3 scripts/DOWNLOAD_ALL_NORMS.py --resume
```

El script retoma desde donde quedó usando el archivo `data/download_progress.json`

---

### 5. Modo rápido (más riesgo de bloqueo)

```bash
# 15s delay en lugar de 30s
python3 scripts/DOWNLOAD_ALL_NORMS.py --fast

# Tiempo: ~12-24 horas para todas
# ⚠️ Mayor riesgo de ban de BCN
```

---

## 📊 Lo que verás durante la descarga

```
======================================================================
🚀 DESCARGA MASIVA DE NORMAS BCN - TEXTO COMPLETO
======================================================================

📊 Estadísticas:
  Total en dataset: 2031
  Ya descargadas: 9
  Pendientes: 2022

⚙️  Configuración:
  Delay entre descargas: 30s
  Checkpoint cada: 10 normas
  Directorio salida: data/normas_completas

----------------------------------------------------------------------
📥 INICIANDO DESCARGA...
----------------------------------------------------------------------

[1/2022] ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 0.0%
  ✅ DECRETO 10
  ⏱️  ETA: 16:51:00
  📈 Éxito: 1 | Errores: 0

[2/2022] ███░░░░░░░░░░░░░░░░░░░░░░░░░░░ 0.1%
  ✅ LEY 20936
  ⏱️  ETA: 16:48:30
  📈 Éxito: 2 | Errores: 0

...
```

---

## 📁 Estructura de salida

Las normas se guardan organizadas por tipo:

```
data/normas_completas/
├── decretos/
│   ├── decreto_10.json
│   ├── decreto_62.json
│   └── decreto_70.json
├── leyes/
│   ├── ley_19940.json
│   └── ley_20936.json
├── dfl/
│   └── dfl_4.json
├── resoluciones/
│   └── resolucion_711.json
└── otros/
    └── ...
```

Cada archivo JSON contiene:
```json
{
  "id_norma": "250604",
  "tipo": "DECRETO",
  "numero": "62",
  "titulo": "APRUEBA REGLAMENTO DE TRANSFERENCIAS...",
  "texto_completo": "Artículo 1º: ...\nArtículo 2º: ...",  // ← ESTO ES LO NUEVO
  "fecha_publicacion": "2006-06-16",
  "organismo": "MINISTERIO DE ECONOMÍA",
  "vinculaciones": {...},
  "versiones": [...]
}
```

---

## ⚠️ Interrumpir la descarga

### Si necesitas parar:

1. **Presiona `Ctrl+C`** (se guardará el progreso automáticamente)
2. **Para continuar después:**
   ```bash
   python3 scripts/DOWNLOAD_ALL_NORMS.py --resume
   ```

### Si está en background:

```bash
# Encontrar el proceso
ps aux | grep DOWNLOAD_ALL_NORMS

# Matarlo suavemente (permite guardar progreso)
kill -SIGINT <PID>

# O forzar (menos recomendado)
kill -9 <PID>
```

---

## 📈 Estrategia Recomendada

### Opción 1: Pragmática (MI RECOMENDACIÓN) ⭐

**HOY:**
```bash
# Descargar TOP 50 (tarda ~1 hora)
python3 scripts/DOWNLOAD_ALL_NORMS.py --top 50
```

**ESTA NOCHE:**
```bash
# Descargar TOP 200 en background
nohup python3 scripts/DOWNLOAD_ALL_NORMS.py --top 200 --resume &> download.log &
```

**ESTE FIN DE SEMANA:**
```bash
# Completar todas las 2,031
nohup python3 scripts/DOWNLOAD_ALL_NORMS.py --resume &> download.log &
```

**Resultado:** Sistema funcional hoy + dataset completo en 3-5 días

---

### Opción 2: All-in (para valientes) 🚀

```bash
# Lanzar descarga completa ahora
nohup python3 scripts/DOWNLOAD_ALL_NORMS.py &> download.log &

# Monitorear
tail -f download.log

# Dejar corriendo 24-48 horas
```

---

## 🔧 Troubleshooting

### "ModuleNotFoundError: playwright"
```bash
pip install playwright playwright-stealth
playwright install chromium
```

### "FileNotFoundError: normas_completas.json"
```bash
# Asegúrate de estar en la raíz del proyecto
cd dark-data-scrapers/pagina_bcn
```

### "Connection timeout" o errores de red
```bash
# Usar delays más largos
python3 scripts/DOWNLOAD_ALL_NORMS.py --delay 60

# O continuar después
python3 scripts/DOWNLOAD_ALL_NORMS.py --resume
```

### Bloqueo por BCN (error 403/429)
```bash
# Esperar 1 hora
sleep 3600

# Reintentar con delays más largos
python3 scripts/DOWNLOAD_ALL_NORMS.py --resume --delay 90
```

---

## 💡 Tips

### 1. Ejecutar en servidor remoto (óptimo)
```bash
# SSH a servidor
ssh usuario@servidor

# Ejecutar en screen/tmux
screen -S descarga_bcn
python3 scripts/DOWNLOAD_ALL_NORMS.py

# Detach: Ctrl+A, D
# Reattach: screen -r descarga_bcn
```

### 2. Verificar progreso desde otro terminal
```bash
# Ver cuántas ya se descargaron
find data/normas_completas -name "*.json" | wc -l

# Ver las últimas 5 descargadas
find data/normas_completas -name "*.json" -type f -printf '%T+ %p\n' | sort -r | head -5
```

### 3. Calcular tiempo restante
```bash
# Ver progreso actual
cat data/download_progress.json | jq '.stats'

# Ejemplo:
# {
#   "descargadas": 156,
#   "errores": 4,
#   "tiempo_inicio": "2025-01-24T10:30:00"
# }
#
# Restantes = 2031 - 156 = 1875
# Tiempo = 1875 × 30s = 56,250s = 15.6 horas
```

---

## 🎯 Siguiente paso después de la descarga

Una vez terminada la descarga, tendrás:
- ✅ 2,031 normas con texto completo
- ✅ ~200-300 artículos por norma
- ✅ Total: ~500,000 artículos para embeddings

**Paso siguiente:**
```bash
# Implementar búsqueda semántica sobre artículos
python3 scripts/implementar_busqueda_semantica.py
```

---

## 📞 Soporte

Si tienes problemas:
1. Revisa el archivo `download.log`
2. Verifica `data/download_progress.json`
3. Usa `--resume` para continuar

---

## ⏱️ Estimaciones de Tiempo

| Opción | Normas | Delay | Tiempo Total |
|--------|--------|-------|--------------|
| TOP 50 | 50 | 30s | ~30-60 min |
| TOP 200 | 200 | 30s | ~3-5 horas |
| TOP 500 | 500 | 30s | ~8-12 horas |
| TODAS | 2,031 | 30s | **24-48 horas** |
| TODAS (fast) | 2,031 | 15s | **12-24 horas** ⚠️ |

---

**¡Listo! Ya tienes todo para descargar el texto completo de todas las normas.**
