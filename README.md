# Conduit

**Self-hosted LLM Gateway — One API, every provider.**

Route, monitor, and control access to OpenAI, Anthropic, Google, Mistral,
and more through a single OpenAI-compatible API.

[![CI](https://github.com/sagar-shirwalkarconduit/actions/workflows/ci.yml/badge.svg)](https://github.com/conduit-llm/conduit/actions)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)

---

## Features

For teams using multiple LLM providers, Conduit offers **one API** that handles:

- **Authentication**: API keys with RBAC, budgets, and expiry
- **Smart Routing**: Priority-based fallback across providers
- **Cost Tracking**: Per-key, per-team spend with budget enforcement
- **Observability**: Request logging, latency tracking, error rates
- **Guardrails**: PII redaction, content filtering, prompt injection detection *(Phase 3)*
- **Semantic Cache**: Deduplicate similar prompts to save $$$ *(Phase 3)*

**Drop-in compatible with OpenAI SDKs**:just change the base URL

---

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/conduit-llm/conduit.git
cd conduit
docker compose -f docker/docker-compose.yml up -d
```

### Register a provider

```bash
curl -X POST http://localhost:8000/admin/v1/models/deployments/ \
  -H "Authorization: Bearer cnd_admin_dev_key_do_not_use_in_prod" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-gpt5",
    "provider": "openai",
    "model_name": "gpt-5.2",
    "api_base": "https://api.openai.com/v1",
    "api_key": "sk-your-openai-key"
  }'
```

### Create an API key

```bash
curl -X POST http://localhost:8000/admin/v1/keys/ \
  -H "Authorization: Bearer cnd_admin_dev_key_do_not_use_in_prod" \
  -H "Content-Type: application/json" \
  -d '{
    "user_email": "dev@yourcompany.com",
    "alias": "dev-key",
    "budget_limit_usd": 50.00
  }'
```

### Use it

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="cnd_sk_...",  # key from above
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

## Documentation

Once running, visit:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Development

### Clone and setup

```bash
git clone https://github.com/conduit-llm/conduit.git
cd conduit
bash scripts/dev_setup.sh
```

### Run tests

```bash
make test
```

### Start dev server

```bash
make dev
```

## Architecture

Client -> [Auth] -> [Rate Limit] -> [Cache] -> [Router] -> [Provider] -> Response
                                                                |
                                                        [Cost Calc + Log]
