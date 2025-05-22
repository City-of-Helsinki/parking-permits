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

## Setting up local development environment with PyEnv and VirtualEnvWrapper

```
pyenv install -v 3.11.9
pyenv virtualenv 3.11.9 parking_permits
pyenv local parking_permits
pyenv virtualenvwrapper
```

Install packages

```
pip install -U pip pip-tools
pip-compile -U requirements.in
pip-compile -U requirements-dev.in
pip-sync requirements.txt requirements-dev.txt
```


## Managing project packages

- We use `pip-tools` to manage python packages we need
- After adding a new package to requirements(-dev).in file, compile it and re-build the Docker image so that the container would have access to the new package

  ```bash
  docker-compose up --build
  ```

## Running tests

- You can run all the tests with:
  ```bash
  docker-compose exec api pytest
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
