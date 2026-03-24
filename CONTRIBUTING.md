# Contributing to OmniRoute

Thanks for your interest in contributing to OmniRoute.

OmniRoute is a transportation operations simulation and intelligence platform built with a FastAPI backend, a React console, CrewAI orchestration, and PostgreSQL with pgvector-backed incident retrieval. We welcome improvements across the codebase, documentation, bug reports, operational workflows, testing, and developer experience.

Before you start, read the relevant section below. It helps keep contributions focused, reviewable, and aligned with the current project setup.

---

## Quick Setup Checklist

Before you dive in, make sure you have these installed:

```bash
# Check Python (3.11+ recommended)
python --version

# Check Node.js (18+ recommended)
node --version

# Check npm
npm --version

# Check Docker
docker --version
docker compose version

# Check Git
git --version
```

New to contributing?

1. Open an issue or pick an existing one to work on.
2. Fork the repo and create a branch from `develop`.
3. Follow the local setup guide below.
4. Run the app locally and verify your change before opening a PR.

## Table of contents

- [How do I...?](#how-do-i)
- [Branching model](#branching-model)
- [Commit conventions](#commit-conventions)
- [Code guidelines](#code-guidelines)
- [Pull request checklist](#pull-request-checklist)
- [Thank you](#thank-you)

---

## How do I...

### Get help or ask a question?

- Start with the main project docs in [`README.md`](./README.md), [`SECURITY.md`](./SECURITY.md), [`DISCLAIMER.md`](./DISCLAIMER.md), and the documentation under [`docs`](./docs).
- Review architecture and platform-specific docs such as [`docs/architecture.md`](./docs/architecture.md), [`docs/api.md`](./docs/api.md), [`docs/db.md`](./docs/db.md), [`docs/security.md`](./docs/security.md), and [`docs/ui.md`](./docs/ui.md).
- If something is still unclear, open a GitHub issue with your question and the context you already checked.

### Report a bug?

1. Search existing issues first.
2. If the bug is new, open a GitHub issue.
3. Include your environment, what happened, what you expected, and exact steps to reproduce.
4. Add screenshots, logs, request details, or response payloads if relevant.

### Suggest a new feature?

1. Open a GitHub issue describing the feature.
2. Explain the problem, who it helps, and how it fits OmniRoute.
3. If the change is large, get alignment in the issue before writing code.

### Fork and clone the repo?

All contributions should come from a **fork** of the repository. This keeps the upstream repo clean and lets maintainers review changes via pull requests.

#### Step 1: Fork the repository

Click the **Fork** button at the top-right of the OmniRoute repository to create a copy under your GitHub account.

#### Step 2: Clone your fork

```bash
git clone https://github.com/<your-username>/OmniRoute.git
cd OmniRoute
```

#### Step 3: Add the upstream remote

```bash
git remote add upstream https://github.com/<upstream-org>/OmniRoute.git
```

This lets you pull in the latest changes from the original repo.

#### Step 4: Create a branch

Always branch off `develop`. See [Branching model](#branching-model) for naming conventions.

```bash
git checkout develop
git pull upstream develop
git checkout -b <type>/<short-description>
```

### Set up OmniRoute locally?

#### Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- Git
- Docker with Docker Compose v2
- PostgreSQL and pgvector available through Docker Compose

#### Option 1: Docker

From the repository root:

```bash
docker compose up --build
```

This starts the project stack defined by the root Compose configuration.

Core services typically include:

- FastAPI backend
- React admin console
- PostgreSQL with pgvector
- Supporting workers or simulation services

Use this option if you want the closest match to the intended local development environment.

#### Option 2: Component-by-component local development

If you are working on one part of the stack, you may prefer to run services individually.

##### Backend

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

##### Frontend

Open a second terminal:

```bash
cd client
npm install
npm run dev
```

##### Access the application

- Frontend: `http://localhost:5173`
- Backend health check: `http://localhost:8000/health`
- API docs: `http://localhost:8000/docs`

If the exact entrypoints differ in your local branch, follow the current repo scripts and Compose definitions.

#### Common troubleshooting

- If ports are already in use, stop the conflicting process before starting OmniRoute.
- If Docker fails to build, rerun with `docker compose up --build`.
- If the frontend cannot reach the API, confirm the configured API base URL points to `http://localhost:8000`.
- If chat responses are empty or low quality, confirm the database contains seeded route, trip, reservation, and incident data.
- If incident similarity is not working, confirm pgvector is enabled and incident embeddings are configured.
- If Python packages fail to install, confirm you are using a supported Python version.

### Start contributing code?

1. Open or choose an issue.
2. [Fork the repo](#fork-and-clone-the-repo) and create a feature branch from `develop`.
3. Keep the change focused on a single problem.
4. Run the app locally and verify the affected workflow.
5. Update docs when behavior, setup, configuration, or architecture changes.
6. Open a pull request back to upstream `develop`.

### Improve the documentation?

Documentation updates are welcome. Relevant files currently live in:

- [`README.md`](./README.md)
- [`CONTRIBUTING.md`](./CONTRIBUTING.md)
- [`SECURITY.md`](./SECURITY.md)
- [`DISCLAIMER.md`](./DISCLAIMER.md)
- [`docs`](./docs)

### Submit a pull request?

1. Push your branch to your fork.
2. Go to the OmniRoute repository and click **Compare & pull request**.
3. Set the base branch to `develop`.
4. Fill in the PR template if one is provided.
5. Submit the pull request.

A maintainer will review your PR. You may be asked to make changes. Push additional commits to the same branch and they will be added to the PR automatically.

Before opening your PR, sync with upstream to avoid merge conflicts:

```bash
git fetch upstream
git rebase upstream/develop
```

Follow the checklist below and the [Pull request checklist](#pull-request-checklist) section.

---

## Branching model

- Fork the repo and base new work from `develop`.
- Open pull requests against upstream `develop`.
- Use descriptive branch names with a type prefix:

| Prefix | Use |
|---|---|
| `feat/` | New features or enhancements |
| `fix/` | Bug fixes |
| `docs/` | Documentation changes |
| `refactor/` | Code restructuring without intended behavior change |
| `test/` | Test additions or fixes |
| `chore/` | Dependency updates, CI changes, tooling |

Examples: `feat/add-incident-filters`, `fix/chat-sql-timeout`, `docs/update-local-setup`

---

## Commit conventions

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```text
<type>(<optional scope>): <short description>
```

Examples:

```bash
git commit -m "feat(api): add route utilization summary endpoint"
git commit -m "fix(client): correct incident details rendering"
git commit -m "docs: update Docker setup notes"
```

Keep commits focused. One logical change per commit is the target.

---

## Code guidelines

- Follow the existing project structure and patterns before introducing new abstractions.
- Keep frontend changes consistent with the React admin console in [`client`](./client).
- Keep backend changes consistent with the FastAPI service layout under [`server`](./server).
- Preserve the planner plus exactly 3 specialist agent model unless a reviewed architectural decision explicitly changes it.
- Keep PostgreSQL as the source of truth for structured operational data.
- Use pgvector only for incident narratives, explanation support, and incident similarity.
- Keep AI responses grounded in SQL results and optional incident vector retrieval. Do not introduce speculative or ungrounded answers.
- Use strict schemas, parameterized SQL, structured logging, and version-controlled migrations.
- Do not add direct database access from the frontend.
- Keep simulation updates consistent with database invariants.
- Avoid unrelated refactors in the same pull request.
- Do not commit secrets, local `.env` files, proprietary credentials, or sensitive operational data.
- Update documentation when contributor setup, behavior, environment variables, or API usage changes.

---

## Pull request checklist

Before submitting your pull request, confirm the following:

- You tested the affected flow locally.
- The application still starts successfully in the environment you changed.
- You removed debug code, stray logs, and commented-out experiments.
- You documented any new setup steps, environment variables, or behavior changes.
- You kept the pull request scoped to one issue or topic.
- You added screenshots for UI changes when relevant.
- You did not commit secrets or local generated data.
- You are opening the pull request against `develop`.

If one or more of these are missing, the pull request may be sent back for changes before review.

---

## Thank you

Thanks for contributing to OmniRoute. Whether you're fixing a bug, improving the docs, refining the simulation engine, or strengthening grounded operational intelligence, your work helps keep the project useful and maintainable.
