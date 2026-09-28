# OpenCode + Ollama local + el skill de casos difíciles

Objetivo: correr el skill `resolver-fuente-definicion` con un **agente local y gratis**
(OpenCode como harness + Ollama como motor), para curar asistido los casos `needs_review`.

> Estado: OpenCode **no está instalado** en esta máquina. Esto es la guía para montarlo.
> El skill ya existe en `.claude/skills/resolver-fuente-definicion/SKILL.md` (OpenCode lo
> lee desde ahí). El producto RAG en producción NO usa OpenCode — sigue siendo
> Python + Ollama; OpenCode es solo para la **curación asistida** de lo dudoso.

## 1. Instalar OpenCode (lo corres tú)

```bash
# opción npm
npm i -g opencode-ai
# o el instalador
curl -fsSL https://opencode.ai/install | bash
opencode --version
```

## 2. Modelo en Ollama con tool-use + contexto grande

OpenCode necesita un modelo que **soporte herramientas** y **≥64k de contexto**
(Ollama por defecto pone 4k → hay que subirlo). En una GPU de 8 GB (GTX 1080) cabe
algo tipo `qwen3-coder` chico o `qwen2.5-coder`; modelos grandes harán offload a CPU
(lento). Ejemplo:

```bash
ollama pull qwen3-coder      # o el coder tool-capable que te quepa
```

## 3. `opencode.json` (en la raíz del repo)

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama (local)",
      "options": { "baseURL": "http://localhost:11434/v1" },
      "models": {
        "qwen3-coder": {
          "name": "qwen3-coder",
          "options": { "num_ctx": 65536 }
        }
      }
    }
  }
}
```

## 4. Correr con el skill

```bash
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
opencode            # o: opencode run "..."
```
OpenCode descubre `.claude/skills/resolver-fuente-definicion/SKILL.md` y lo carga
on-demand vía su skill tool. Le pides curar un concepto `needs_review` y el agente
sigue el procedimiento (reunir candidatos → criterios jerarquía/fecha/especialidad →
decisión tentativa + fundamento → escribir en la cola de revisión).

## Caveat honesto (capacidad del modelo)

El **mecanismo** (harness + skills + local) lo tienes; el cuello es la **capacidad**:
un modelo que entra en 8 GB sigue un procedimiento multi-paso con herramientas
**peor** que Claude → más errores en los casos difíciles. Para curación asistida
(pocos casos, con tu revisión) es aceptable; para autonomía total, no aún.

## Alternativas al motor local

- Otros harness: Cline / Continue.dev (en el IDE), PI Agent, Goose.
- Otros servidores locales: llama.cpp, vLLM, LM Studio (en vez de Ollama).
- El mismo `SKILL.md` sirve en todos los harness que soporten el estándar
  (Claude Code, OpenCode, Cursor, Codex, Copilot…).
