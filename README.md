<p align="center">
  <img src="docs/assets/InnovationHub-HeaderImage.png" width="220" alt="OmniRoute">
</p>

# OmniRoute

AI-powered multi-agent platform for transportation operations.

---

## License

This project is licensed under our [LICENSE](./LICENSE.md) file for details.

---

## Disclaimer

**FinSights** is provided as-is for analysis and informational purposes. While we strive for accuracy:

- Always verify AI-generated summaries against original documents
- Do not rely solely on AI summaries for investment decisions
- Consult financial advisors for investment guidance
- Test thoroughly before using in production environments

For full disclaimer details, see [DISCLAIMER.md](./DISCLAIMER.md)

## Table of Contents

- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Get Started](#get-started)
  - [Prerequisites](#prerequisites)
  - [Quick Start](#quick-start)
  - [Database Migration](#database-migration)
  - [Data Engine Run Modes](#data-engine-run-modes)
  - [Local Development](#local-development)
- [Project Structure](#project-structure)
- [Usage Guide](#usage-guide)
- [Environment Variables](#environment-variables)
- [Technology Stack](#technology-stack)
- [Troubleshooting](#troubleshooting)
- [Additional Documentation](#additional-documentation)

---

## Project Overview

**OmniRoute** is a multi-agent AI platform for transportation operations, designed around natural-language workflows. It uses three specialized agents - Operations, Reservations, and Insights - to answer queries about routes, trips, bookings, and delays, returning grounded responses directly from real operational data.

### How It Works

1. **Start with available data**: If the database is empty, the system first prompts users to upload transportation data through CSV files or run the Data Engine to generate data before asking questions.
2. **Route it to the right agent**: A planner sends the request to Operations, Reservations, or Insights.
3. **Let agents work together when needed**: An agent can call another agent for follow-up work on supported multi-step questions.
4. **Return a grounded answer**: The final response is built from database results and incident similarity only when needed.

The core focus of OmniRoute is the multi-agent AI workflow itself: routing transportation questions, letting specialist agents perform their part of the task, and returning grounded answers for routes, trips, reservations, utilization, delays, and incidents.

---

## Architecture

OmniRoute uses a layered architecture centered on multi-agent AI orchestration. The frontend collects the user request, the backend runs the planner and specialist agents, agents retrieve grounded data from PostgreSQL, and the final answer is returned to the UI. When needed, agents can call other agents for supported follow-up work, and pgvector is used only for incident narrative similarity.

### Architecture Summary

- React frontend for upload, simulation, and chat
- FastAPI backend for APIs, orchestration, and data workflows
- One planner agent and three specialist agents
- PostgreSQL as the source of truth
- pgvector only for incident narrative similarity
- Optional data engine and ingest flows for loading and updating data

### Multi-Agent Query Flow

This is the main runtime path for the application:

```mermaid
flowchart TB
    subgraph UI["Frontend Layer"]
        A[React Frontend]
    end

    subgraph API["Backend Layer"]
        B[FastAPI API]
        C[Planner Agent]
        D[Operations Agent]
        E[Reservations Agent]
        F[Insights Agent]
    end

    subgraph DATA["Data Layer"]
        G[(PostgreSQL)]
        H[(pgvector for incident narratives)]
    end

    subgraph ENGINE["Supporting Data Workflows"]
        I[Data Engine]
        J[CSV Ingest]
    end

    A -->|UI requests| B
    B -->|route question| C
    C -->|operations queries| D
    C -->|reservation queries| E
    C -->|incident and trend queries| F
    D -->|agent handoff when needed| E
    D -->|agent handoff when needed| F
    E -->|agent handoff when needed| D
    F -->|agent handoff when needed| D
    D -->|SQL| G
    E -->|SQL| G
    F -->|SQL| G
    F -->|incident similarity| H
    I -->|seed and tick updates| G
    J -->|validated upserts| G
    J -->|incident embeddings| H
```


### What The Agents Actually Do

1. **Planner Agent** classifies the question and selects the primary specialist.
2. **Operations Agent** answers route, trip, status, delay, and capacity questions.
3. **Reservations Agent** answers reservation, booking, cancellation, and utilization questions.
4. **Insights Agent** answers incident explanation, trend, and similarity questions.
5. **Agent collaboration** allows one specialist to call another specialist when a question spans more than one area.

### System Components

1. **React Operations Console** serves the home, upload, simulation, and chat interfaces.
2. **FastAPI API** exposes health, operational data, upload, incident, simulation, and query endpoints.
3. **AI Orchestration Layer** coordinates the planner, specialist tasks, and agent collaboration.
4. **Query Understanding Layer** parses user text into validated intent and allowlisted internal plans.
5. **PostgreSQL** stores structured operational data and remains the system of record.
6. **pgvector** stores only incident narrative embeddings for similarity retrieval.
7. **Answer Synthesis** converts SQL and vector evidence into one grounded response.
8. **Data Engine and Ingest Flows** support data loading and background operational updates.

---

## Get Started

### Prerequisites

Before running OmniRoute, make sure you have:

- **Docker** and **Docker Compose**
- **Make** for the provided helper commands
- An **OpenAI API key** or another **OpenAI-compatible provider** for chat
  and embeddings

You need both LLM and embedding configuration for the AI workflow to work
correctly.

#### Verify Installation

```bash
docker --version
docker compose version
make --version
docker ps
```

### Quick Start

#### 1. Fork and clone the repository

First fork this repository to your own GitHub account, then clone your fork:

```bash
git clone <your-fork-url>
cd OmniRoute
```

All remaining commands in this section should be run from the repository root.

#### 2. Copy the environment file

Create your local environment file from the example:

```bash
cp .env.example .env
```

#### 3. Fill in the required `.env` values

If you are using the standard Docker Compose setup, you usually only need to
provide the LLM and embedding values from your side. The default database URL
in `.env.example` already matches the Docker setup.

Required values to fill in:

```bash
LLM_API_KEY=your_openai_api_key_here
EMBEDDING_API_KEY=your_openai_api_key_here
```

What you must provide from your side:

- `LLM_API_KEY`
- `EMBEDDING_API_KEY`

If you are using OpenAI for both, you can use the same key value for both
fields.

If you are not using OpenAI, update these as well:

- `LLM_PROVIDER`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `EMBEDDING_PROVIDER`
- `EMBEDDING_BASE_URL`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIM`

For the normal Docker setup, you can keep:

```bash
DATABASE_URL=postgresql+asyncpg://omnroute:omnroute@postgres:5432/omnroute
```

#### 4. Start the required services

```bash
docker compose up -d --build
```

This starts:

- PostgreSQL with pgvector
- FastAPI API on `http://localhost:8000`
- React web app on `http://localhost:5173`

#### 5. Create the database schema

The schema is **not** applied automatically. From the repository root, run:

```bash
make db-init
```

This command runs the Alembic migrations for the API service and prepares the
database schema required by OmniRoute.

#### 6. Load or generate data before asking questions

OmniRoute needs transportation data before the AI workflow can answer
questions. You have two options:

- Open the Upload page in the UI and import CSV files
- Run the Data Engine to generate and update sample operational data

#### 7. Optional: use the Data Engine

The Data Engine is a supporting service that simulates real-time transportation
activity. Its purpose is to generate routes, trips, reservations, and incidents
so users do not need to prepare all the data manually before trying the
application.

If you want sample data right away, seed the system from the repository root:

```bash
make engine-seed
```

If you want continuous updates that simulate live operational changes, run:

```bash
make engine-run
```

#### 8. Open the application

- **Frontend**: `http://localhost:5173`
- **API**: `http://localhost:8000`
- **API Docs**: `http://localhost:8000/docs`
- **Health Check**: `http://localhost:8000/health`

#### 9. Stop the stack

```bash
docker compose down
```

---

### Database Migration

Database migrations are version-controlled schema changes for PostgreSQL. They
are how OmniRoute creates and updates tables, columns, constraints, and
extensions in a consistent way across environments.

For normal setup, you only need:

```bash
make db-init
```

That command applies the current migration set and prepares the database for
the application.

Advanced migration commands:

- `make db-upgrade`
  Applies any newer migrations to bring the database up to the latest schema.
- `make db-downgrade`
  Rolls back the most recent migration step. Use this during development if you
  need to reverse a recent schema change.
- `make db-revision MSG="describe your schema change"`
  Creates a new Alembic migration file when you intentionally change the
  database schema in development.
- `docker compose exec postgres psql -U omnroute -d omnroute`
  Opens a PostgreSQL shell if you need to inspect tables or run manual queries.

---

### Data Engine Run Modes

The Data Engine is a separate service. It does not start during a normal `docker compose up` because it is behind the `simulation` profile.

A `tick` is one simulation cycle. In one tick, the Data Engine advances the
transportation state by running a single update step, such as creating or
updating trips, reservations, cancellations, delays, or incidents.

Use these helper commands when needed:

```bash
make engine-seed
make engine-tick
make engine-run
```

What each command does:

- `make engine-seed`: runs a one-off seed job and exits
- `make engine-tick`: runs one simulation cycle and exits
- `make engine-run`: starts the long-running `data-engine` container, which seeds automatically when empty and then keeps ticking on the configured interval

Equivalent Docker commands:

```bash
docker compose run --rm data-engine seed
docker compose run --rm data-engine tick
docker compose run --rm data-engine status
docker compose --profile simulation up data-engine
```

Recommended flow for a fresh environment:

```bash
docker compose up -d --build
make db-init
make engine-seed
make engine-run
```

If you only want sample data without continuous ticking, stop after `make engine-seed`.

---

### Local Development

For hot reload during development, use the compose override:

```bash
make dev-up
```

Then apply the schema:

```bash
make db-init
```

Development behavior:

- API runs with `uvicorn --reload`
- Web runs with Vite dev server
- Source code is bind-mounted into containers

Stop local dev mode with:

```bash
make dev-down
```

If you prefer running services directly outside Docker, the rough flow is:

```bash
# API
cd server/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ../..
uvicorn api.main:app --app-dir server --reload --host 0.0.0.0 --port 8000

# Web
cd client
npm install
npm run dev
```

For that mode, you still need a PostgreSQL instance with pgvector available and
a valid `DATABASE_URL`.

If you run the API outside Docker, the Docker service hostname `postgres` will
usually not work from your host machine. In that case, point `DATABASE_URL` to
your local or reachable PostgreSQL instance instead, for example:

```bash
DATABASE_URL=postgresql+asyncpg://omnroute:omnroute@localhost:5432/omnroute
```

---

## Project Structure

```text
OmniRoute/
├── client/
│   ├── src/
│   │   ├── components/          # Shared UI and layout pieces
│   │   ├── lib/                 # API client utilities
│   │   └── pages/               # Home, upload, chat, and operations pages
│   ├── Dockerfile
│   └── package.json
├── server/
│   ├── api/
│   │   ├── routes/              # FastAPI routes
│   │   ├── services/            # Query layer, simulation, ingest, embeddings
│   │   ├── models/              # SQLAlchemy + Pydantic models
│   │   ├── middleware/          # Request, logging, and error middleware
│   │   ├── main.py              # FastAPI entrypoint
│   │   ├── config.py            # Environment-backed settings
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── db/
│   │   └── migrations/          # Alembic migrations
│   ├── ingest/                  # Ingest and embedding helpers
│   └── agents/                  # Agent-side support files
├── docs/                        # Architecture, API, DB, UI, and design notes
├── docker-compose.yml
├── docker-compose.dev.yml
├── Makefile
├── .env.example
└── README.md
```

---

## Usage Guide

### Typical Operator Flow

1. Open `http://localhost:5173`
2. Go to **Upload**
3. Upload CSV files for operations, reservations, or incidents
4. Or go to the **Data** page and seed baseline simulated data
5. If you want live simulation, start the engine container with `make engine-run`
6. Use the **Simulation** page to start, stop, tick, and tune the Data Engine
7. Open **Chat**
8. Ask grounded questions about routes, trips, reservations, delays, utilization, or incidents

### Notes About Chat

- Chat requires route data to exist in the database
- If no route data exists, the UI redirects operators to the Upload page
- Answers should stay grounded in SQL results and incident vector matches only when incident narrative context is needed

### Typical Questions

- `Show delayed trips for today`
- `Which routes have the most incidents`
- `Compare reservation activity across active routes`
- `Why is route 21 delayed`

---

## Environment Variables

OmniRoute reads configuration from the root `.env` file.

### Core Application

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | Async SQLAlchemy database URL | `postgresql+asyncpg://omnroute:omnroute@postgres:5432/omnroute` |
| `CORS_ALLOW_ORIGINS` | Allowed frontend origins | `http://localhost:5173,http://127.0.0.1:5173` |

### LLM Settings

| Variable | Description | Default |
|---|---|---|
| `LLM_PROVIDER` | LLM provider name | `openai` |
| `LLM_MODEL` | Chat model used by the query layer | `gpt-4o-mini` |
| `LLM_API_KEY` | API key for LLM calls | empty |
| `LLM_BASE_URL` | Base URL for an OpenAI-compatible endpoint | `https://api.openai.com/v1` |
| `LLM_TEMPERATURE` | Generation temperature | `0` |
| `LLM_TIMEOUT_SECONDS` | Timeout for LLM requests | `30` |

## LLM Provider Configuration

OmniRoute supports OpenAI and OpenAI-compatible LLM APIs. Choose the provider that best fits your setup.

### OpenAI

**Best for**: production deployments and the default hosted setup

- **Get API Key**: https://platform.openai.com/account/api-keys
- **Provider value**: `openai`
- **Change these fields**:

```bash
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

### Groq

**Best for**: fast inference through an OpenAI-compatible API

- **Get API Key**: https://console.groq.com/keys
- **Provider value in OmniRoute**: `openai_compatible`
- **Change these fields**:

```bash
LLM_PROVIDER=openai_compatible
LLM_API_KEY=gsk_...
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=your-groq-model
```

### Ollama

**Best for**: local deployment, privacy, and no per-request API cost

- **Install**: https://ollama.com/download
- **Provider value in OmniRoute**: `openai_compatible`
- **Change these fields**:

If OmniRoute runs directly on your host:

```bash
LLM_PROVIDER=openai_compatible
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen3:4b
```

If OmniRoute runs with Docker Compose and Ollama runs on your host machine:

```bash
LLM_PROVIDER=openai_compatible
LLM_API_KEY=ollama
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=qwen3:4b
```

Basic setup:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull qwen3:4b

# Verify Ollama is running
curl http://localhost:11434/api/tags
```

### OpenRouter

**Best for**: accessing multiple models through one OpenAI-compatible endpoint

- **Get API Key**: https://openrouter.ai/keys
- **Provider value in OmniRoute**: `openai_compatible`
- **Change these fields**:

```bash
LLM_PROVIDER=openai_compatible
LLM_API_KEY=sk-or-...
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=your-openrouter-model
```

### Custom OpenAI-Compatible API

**Best for**: internal gateways, proxy layers, or other compatible providers

Any API that implements the OpenAI-compatible format used by OmniRoute can work.

```bash
LLM_PROVIDER=openai_compatible
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://your-custom-endpoint.com/v1
LLM_MODEL=your-model-name
```

### Switching Providers

To switch providers, update the root `.env` file and restart the affected services:

```bash
# Restart API only
docker compose restart api

# Or restart the full stack
docker compose down
docker compose up -d
```

### Embeddings

| Variable | Description | Default |
|---|---|---|
| `EMBEDDING_PROVIDER` | Embedding provider name | `openai` |
| `EMBEDDING_MODEL` | Embedding model for incidents | `text-embedding-3-small` |
| `EMBEDDING_DIM` | Embedding dimension | `1536` |
| `EMBEDDING_API_KEY` | API key for embeddings | empty |
| `EMBEDDING_BASE_URL` | Base URL for embeddings endpoint | `https://api.openai.com/v1` |
| `EMBEDDING_BATCH_SIZE` | Embedding batch size | `32` |
| `EMBEDDING_TIMEOUT_SECONDS` | Embedding timeout | `30` |

### Data Engine

| Variable | Description | Default |
|---|---|---|
| `DATA_ENGINE_MODE` | Engine mode | `run` |
| `DATA_ENGINE_TICK_INTERVAL_SECONDS` | Tick interval | `30` |
| `DATA_ENGINE_SEED_IF_EMPTY` | Seed when database is empty | `true` |
| `DATA_ENGINE_SEED_ROUTES` | Number of routes to seed | `6` |
| `DATA_ENGINE_SEED_DAYS` | Number of future days to seed | `3` |
| `DATA_ENGINE_BOOKING_RATE_PER_TICK` | Reservation simulation intensity | `3.0` |
| `DATA_ENGINE_CANCELLATION_RATE_PER_TICK` | Cancellation intensity | `0.8` |
| `DATA_ENGINE_INCIDENT_RATE_PER_TICK` | Incident intensity | `0.4` |
| `DATA_ENGINE_DELAY_SENSITIVITY` | Delay propagation sensitivity | `1.0` |
| `DATA_ENGINE_ENABLE_CASCADING_DELAYS` | Enable cascading delays | `true` |

### Optional Tracing

| Variable | Description | Default |
|---|---|---|
| `LANGSMITH_TRACING` | Enable LangSmith tracing | `false` |
| `LANGSMITH_API_KEY` | LangSmith API key | empty |
| `LANGSMITH_ENDPOINT` | LangSmith endpoint | `https://api.smith.langchain.com` |
| `LANGSMITH_PROJECT` | LangSmith project name | `omniroute` |
| `LANGSMITH_WORKSPACE_ID` | Optional workspace ID | empty |

---

## Technology Stack

### Backend

- FastAPI
- SQLAlchemy
- Alembic
- PostgreSQL
- pgvector
- CrewAI
- OpenAI-compatible LLM and embedding APIs

### Frontend

- React 18
- Vite
- React Router
- Tailwind CSS

### Infrastructure

- Docker
- Docker Compose
- Python 3.12 container runtime
- Node 22 Alpine container runtime

---

## Troubleshooting

### Build or startup issues

```bash
docker compose ps
docker compose logs api --tail 100
docker compose logs web --tail 100
docker compose logs postgres --tail 100
```

### Database schema not found

If tables are missing, migrations probably have not been run yet:

```bash
make db-init
```

### API health check

```bash
curl http://localhost:8000/health
```

### Data Engine is not running

Check the current engine status:

```bash
docker compose run --rm data-engine status
```

Start the continuous engine process:

```bash
make engine-run
```

If the Simulation page says the runtime is stopped, resume it there or call the start action from the UI after the container is running.

### Frontend cannot reach the API

Check:

- API container is running
- `VITE_API_URL` or `VITE_API_BASE_URL` points to `http://localhost:8000`
- CORS origins include your frontend host

### Chat has no useful answers

Check:

- Routes and trips exist in the database
- Incident embeddings are configured if you need incident similarity
- `LLM_API_KEY` and `EMBEDDING_API_KEY` are valid

---
