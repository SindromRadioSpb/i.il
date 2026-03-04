# LLM Backend: llama.cpp (`llama-server` OpenAI-compatible `/v1`)

This project supports two local LLM backends for `apps/local-engine`:

- `ollama` (legacy/default)
- `llamacpp` (`llama-server` with OpenAI-compatible `/v1` API)

## 1) Prerequisites

- `llama-server` is running and reachable (default: `http://localhost:8001/v1`)
- your model is loaded in server startup args
- local-engine dependencies are installed

Quick checks:

```bash
curl http://localhost:8001/v1/models
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"YOUR_MODEL_ID",
    "messages":[{"role":"user","content":"reply: ok"}],
    "max_tokens":8,
    "temperature":0
  }'
```

## 2) `.env` knobs

In `apps/local-engine/.env`:

```bash
LLM_PROVIDER=llamacpp
LLM_BASE_URL=http://localhost:8001/v1
LLM_MODEL=YOUR_MODEL_ID
LLM_TIMEOUT_SEC=300
LLM_MAX_RETRIES=2
LLM_JSON_MODE=strict

# Keep runs conservative for large local models
MAX_SUMMARIES_PER_RUN=10
```

Notes:

- `LLM_JSON_MODE=strict` retries invalid JSON and validates with pydantic schemas.
- `best_effort` allows extractor fallback earlier.
- Legacy `OLLAMA_*` variables remain supported for backward compatibility.

## 3) Health and proof verification

```bash
cd apps/local-engine
python main.py --health
python main.py --proof-fb
```

Expected:

- health table includes `LlamaCpp` with `[OK]`
- proof run posts 2-3 items (project proof criteria)

## 4) JSON reliability behavior

For JSON-dependent steps (`fact_extract`, `classify_and_tag`):

1. direct JSON parse
2. extractor fallback from mixed prose/fenced output
3. pydantic schema validation
4. automatic retry with stricter instruction: `Return ONLY valid JSON, no prose, no markdown fences.`

## 5) Troubleshooting

### `404 /v1/models` or missing models list

Some builds disable `/models`. Health check falls back to a minimal chat probe.

### `model NOT FOUND`

`LLM_MODEL` must match the model id exposed by server (`/v1/models`).

### frequent timeout / slow generation

- increase `LLM_TIMEOUT_SEC` (for 27B/35B models)
- keep `MAX_SUMMARIES_PER_RUN=10`
- reduce generation limits in prompts if needed

### malformed JSON from model

- keep `LLM_JSON_MODE=strict`
- keep retries (`LLM_MAX_RETRIES>=2`)
- verify model supports instruction-following reliably

### embeddings endpoint

Summary/proof pipeline does not require embeddings.
`cluster_v2` uses embeddings separately; if `/v1/embeddings` is unavailable in your build, keep that path on Ollama or disable v2 clustering experiments.
