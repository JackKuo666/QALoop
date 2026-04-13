# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QA Annotation System (qa_annotate) - a FastAPI web application for managing and annotating QA dataset pairs. Supports multi-user annotation workflows with role-based access control (superusers manage projects/datasets, regular users perform annotations).

## Commands

```bash
# Run dev server
uvicorn qa_annotate.main:app --reload --host 0.0.0.0 --port 8000

# Or via the installed entry point
qa

# Create superuser
python scripts/create_superuser.py

# Lint/format (via pre-commit or directly)
ruff check --fix .
ruff format .
```

Pre-commit hooks run ruff linting + formatting and standard checks (trailing whitespace, YAML/JSON/TOML validation, etc.).

## Architecture

### Backend (Python/FastAPI)

Three-layer architecture inside `qa_annotate/`:

- **`api/`** - FastAPI routers. Each domain has its own module (auth, user, dataset, annotation, project, seed_question, system_config, analysis). All routes are mounted under `/api` prefix.
- **`database/`** - SQLAlchemy ORM models (`models.py`) and CRUD operations (`crud.py`). Models use `from_pydantic()` / `to_pydantic()` conversion methods to bridge between SQLAlchemy and Pydantic. DB sessions are provided via `get_db()` generator dependency.
- **`schema/`** - Pydantic models for request/response validation. Separate schemas for create, update, and read operations.

Configuration is in `qa_annotate/config.py` using pydantic-settings, reading from `.env` file and environment variables. Key settings: `SECRET_KEY`, `HOST`, `PORT`, `ENVIRONMENT`.

### Frontend (Vanilla JS)

- **`qa_annotate/html/`** - One HTML file per page (auth, manager, user, annotation, etc.). Pages are served by a catch-all route in `main.py` that maps `/{path}` to `html/{path}.html`.
- **`qa_annotate/static/js/`** - One JS file per HTML page, plus shared utilities (`pagination.js`, `project-api.js`). No frontend framework.
- **`qa_annotate/static/css/`** - Component-specific stylesheets.
- **`qa_annotate/static/locales/`** - i18n translation files.

### Key Domain Concepts

- **Project** → contains **Datasets** → each dataset contains **QA Pairs** (question + answer + optional extra fields)
- **AnnotationConfig** defines annotation task settings (type: score/category/text/multi_choice/single_choice/binary, plus optional reason and confidence fields). Configs are linked to datasets or projects via many-to-many association tables.
- **AnnotationResult** stores individual annotation values, linked to a specific QA pair, dataset, config, and annotator.
- **SeedQuestion** - predefined question templates organized by type/subtype.
- **SystemConfig** - key-value store for system-wide settings.

### Database

- SQLite only (stored in `data/annotations.db`, configurable via `DB_DIR`/`DB_NAME` settings).
- Auto-creates tables on startup via `init_db()`.
- Passwords are SHA-256 hashed client-side before storage (see `qa_annotate/utils/password.py`).

### Auth

JWT-based authentication. Roles: superuser (full access to management pages) vs regular user (annotation tasks only). Token stored in localStorage on the frontend.
