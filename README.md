[![Build Status](https://dev.azure.com/City-of-Helsinki/pysakoinnin-verkkokauppa/_apis/build/status/parking-permits-backend%20Test?repoName=City-of-Helsinki%2Fparking-permits&branchName=develop)](https://dev.azure.com/City-of-Helsinki/pysakoinnin-verkkokauppa/_build/latest?definitionId=639&repoName=City-of-Helsinki%2Fparking-permits&branchName=develop)
[![Continuous Integration](https://github.com/City-of-Helsinki/parking-permits/actions/workflows/ci.yml/badge.svg)](https://github.com/City-of-Helsinki/parking-permits/actions/workflows/ci.yml)
[![SonarCloud Analysis](https://github.com/City-of-Helsinki/parking-permits/actions/workflows/analyze-code.yml/badge.svg)](https://github.com/City-of-Helsinki/parking-permits/actions/workflows/analyze-code.yml)

# Parking Permits API

Backend repository for parking permits service in City of Helsinki.

Instructions in this README.md are written with an experienced Python developer in mind. For example,
"docker-compose up" means you already know what docker and docker-compose are, and you already have both installed locally.
This helps to keep the README.md concise.

## Setting up local development environment with Docker

In order to create placeholder for your own environment variables file, make a local `.env.template` copy:

```bash
$ cp .env.template .env
```

Then you can run docker image with:

  ```bash
  docker-compose up
  ```

- Access development server on [localhost:8888](http://localhost:8888)

- Login to admin interface with `admin` and 🥥

- Done!

## Setting up local development environment with uv

### Required system packages

- python3-dev
- libpq-dev

### Required user packages

- [uv](https://docs.astral.sh/uv/getting-started/installation/)

Install Python 3.12 (if not already available) and the project dependencies, including the
development dependencies, into a local `.venv`:

```bash
uv python install 3.12
uv sync
```

Run Python commands inside the project environment with `uv run`, e.g.:

```bash
uv run manage.py migrate
uv run manage.py runserver
```

## Managing project packages

- We use [uv](https://docs.astral.sh/uv/) to manage Python packages. Dependencies are declared in
  `pyproject.toml` and locked in `uv.lock`:
  - Production dependencies are listed in `[project].dependencies`
  - Development dependencies are listed in `[dependency-groups].dev`
  - Production-only dependencies (e.g. `gunicorn`) are listed in `[dependency-groups].prod`
- Add a new package with `uv add <package>` (or `uv add --group dev <package>` for a development dependency)
- Upgrade all locked packages with `uv lock --upgrade`, or a single package with `uv lock --upgrade-package <package>`
- For supply chain protection, `[tool.uv] exclude-newer = "P3D"` makes uv only resolve package versions
  that have been published at least three days ago
- After changing dependencies, re-build the Docker image so that the container would have access to the new packages

  ```bash
  docker-compose up --build
  ```

## Code formatting and linting

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting, and
[pre-commit](https://pre-commit.com/) to run the checks automatically on commit.

Install pre-commit and enable the hooks:

```bash
uv tool install pre-commit
pre-commit install
```

If you want to use ruff without the pre-commit hooks (e.g. from your editor), install it separately:

```bash
uv tool install ruff
ruff check --fix
ruff format
```

## Running tests

- You can run all the tests with:
  ```bash
  docker-compose exec api pytest
  ```
  or locally with:
  ```bash
  uv run pytest
  ```
- If you want to run the tests continously while developing:

  - Install [fd](https://github.com/sharkdp/fd) using `brew` or equivalent
  - Install [entr](https://github.com/eradman/entr) using `brew` or equivalent
  - Run pytest whenever a Python file changes with:

    ```bash
    fd --extension py | entr -c docker-compose exec api pytest
    ```

## Testing emails locally with [Mailpit](https://github.com/axllent/mailpit)
- Start Mailpit with `docker compose up mailpit`
- In your `.env` file, set `EMAIL_HOST=0.0.0.0`, `EMAIL_PORT=1025` and `DEBUG_MAILPIT=True`
- Emails sent by the application will be visible in Mailpit's web interface at [localhost:8025](http://localhost:8025)
