# AI platform compatibility

The workflow engine stays deterministic by default and can optionally use a provider-neutral AI execution step. The shared `AIClient` interface supports OpenAI/OpenAI-compatible chat APIs, Anthropic Claude, and Google Gemini.

## Offline verification

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

The tests use fake/mocked providers and require no API key.

## Select a provider

```bash
# OpenAI or OpenAI-compatible
export AI_PROVIDER=openai
export AI_API_KEY="YOUR_KEY"
export AI_MODEL="YOUR_CHAT_MODEL"
# Optional: export AI_BASE_URL="https://provider.example/v1"
```

```bash
# Anthropic Claude
export AI_PROVIDER=anthropic
export AI_API_KEY="YOUR_KEY"
export AI_MODEL="YOUR_CLAUDE_MODEL"
```

```bash
# Google Gemini
export AI_PROVIDER=gemini
export AI_API_KEY="YOUR_KEY"
export AI_MODEL="YOUR_GEMINI_MODEL"
```

## Run an AI-backed workflow

```bash
python - <<'PY'
from ai_features import make_ai_execute
from ai_platform import create_ai_client
from engine import Step, Workflow, classify, plan

client = create_ai_client()
workflow = Workflow([
    Step("classify", classify),
    Step("plan", plan),
    Step("ai_execute", make_ai_execute(client)),
])
result = workflow.run({"request": "Compare two RAG architectures"})
print(result)
PY
```

The workflow orchestration, retries, conditions, and approval controls remain vendor-independent. Only the optional execution step calls the selected model provider.
