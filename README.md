# Ghost

Production-oriented AI assistant platform with FastAPI backend, secure auth, streaming chat, contextual UI, and one-command startup.

## Quick Start

1. `cd ghost`
2. `cp .env.example .env`
3. Edit `.env` with secure values.
4. `./start.sh`
5. Open `http://localhost:8080`

## Security Defaults

- BCrypt password hashing
- JWT access + refresh with rotation
- HttpOnly auth cookies
- Session inactivity timeout (60 min)
- Brute-force login protection
- Session revocation and compromised-token handling
- Rate limiting middleware
- Exception reporting by async email

## Adaptive Model Optimizer (AMO)

- Internal intent detection via lightweight heuristics (`detect_intent`)
- Internal tier routing (`select_model`):
  - `TIER_LIGHT` for casual chat
  - `TIER_STANDARD` for normal questions
  - `TIER_REASONING` for coding/debugging/long prompts
  - `TIER_VISION` for image analysis
- Cost safety:
  - Strong-tier cap: max 3 consecutive high-cost routes
  - Usage-spike downgrade to standard tier
  - Provider failure fallback to standard tier
- Streaming compatible with hidden model switching
- Internal telemetry logs persist:
  - intent
  - chosen tier
  - routing decision time
  - response time

## API

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `POST /auth/revoke-all`
- `GET /auth/me`
- `POST /chat/image`
- `POST /chat/stream` (SSE)
- `GET /healthz`
