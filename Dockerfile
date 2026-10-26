# ==============================
FROM helsinki.azurecr.io/ubi9/python-312-gdal AS appbase
# ==============================

COPY --from=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff /uv /uvx /usr/local/bin/

ENV STATIC_ROOT=/srv/app/static
ENV TZ="Europe/Helsinki"

ENV UV_PROJECT_ENVIRONMENT=/opt/app-root \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
USER root

COPY pyproject.toml uv.lock ./

RUN dnf install -y \
    nmap-ncat \
    gettext \
    postgresql \
    libpq-devel \
    python3-devel \
    && uv sync --locked --no-dev --group prod \
    && mkdir -p /srv/app/static \
    && dnf clean all

ENTRYPOINT ["./docker-entrypoint.sh"]
EXPOSE 8000/tcp

# ==============================
FROM appbase AS development
# ==============================

ENV DEV_SERVER=True

RUN uv sync --locked --group prod

COPY . .

USER default

# ==============================
FROM appbase AS production
# ==============================
COPY . .

RUN SECRET_KEY="only-used-for-collectstatic" DATABASE_URL="sqlite:///" \
    python manage.py collectstatic --noinput && \
    python manage.py compilemessages

USER default
