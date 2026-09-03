# Local AI

## Role

AI is the conversational explanation and purchase-advice layer on top of
structured valuation data. **It is not the valuation engine.** Every number the
AI mentions is produced by the deterministic backend and handed to the model as
context.

The core application — vehicle lookup, comparable selection, market statistics,
valuation, confidence — works completely without it.

## Provider abstraction

```
AIProvider  (interface)
└── OllamaProvider   local Ollama HTTP API
```

No Ollama-specific request shapes leak into services, routes or the frontend, so
another local inference engine could be added later. No hosted provider is
implemented.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `EAW_AI_ENABLED` | `true` | Master switch for the AI layer |
| `EAW_OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama endpoint |
| `EAW_OLLAMA_MODEL` | `qwen2.5:7b-instruct` | Model name — configuration, never hardcoded |
| `EAW_OLLAMA_TIMEOUT_SECONDS` | `60` | Request timeout |

Any locally runnable instruct model (Qwen, Llama, Mistral, Gemma, …) is
acceptable; nothing in the application is built around one specific model.

## Guardrails

The model must never fabricate listings, market prices, options, mileage,
specifications, valuation results, comparable counts or confidence scores. If
information is missing it says so; if confidence is low it says that too.

It must always keep three concepts distinct:

- **vraagprijs** — what the seller asks
- **geschatte marktwaarde** — the estimated market value
- **aanbevolen aankoopprijs** — the recommended purchase/negotiation range

These are never interchangeable.

## Tone

Dutch, practical, concise, transparent, non-salesy, skeptical when the evidence
is weak, light on jargon.

## Failure behaviour

If Ollama is unreachable or times out, the valuation request still succeeds.
`/health` reports the `ai` component as unavailable while overall status stays
`ok`, and the interface states that AI advice is temporarily unavailable.
**AI failure never causes valuation failure.**

*Status: implemented in Phase 7.*
