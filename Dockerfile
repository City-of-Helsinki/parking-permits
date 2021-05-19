ARG BASE_IMAGE=python
ARG PYTHON_VERSION=3.9.4
ARG IMAGE_VARIANT=slim

# ==============================
FROM ${BASE_IMAGE}:${PYTHON_VERSION}-${IMAGE_VARIANT} AS base_stage
# ==============================

RUN groupadd --system --gid 2000 non-root-group && \
    useradd  --system --gid      non-root-group --create-home --uid 3000 appuser

WORKDIR /app

EXPOSE 8000

# Add tini init system https://github.com/krallin/tini
ENV TINI_VERSION v0.19.0
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /tini
RUN chmod +x /tini

ENV PYTHONDONTWRITEBYTECODE true
ENV PYTHONUNBUFFERED true

COPY docker-entrypoint.sh /app/
ENTRYPOINT ["/tini", "--", "/app/docker-entrypoint.sh"]

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

# ==============================
FROM base_stage AS development_stage
# ==============================

# git is needed for 'pre-commit install' to work
RUN apt-get update && apt-get install --yes --no-install-recommends git

COPY requirements-dev.txt /app/
RUN pip install --no-cache-dir -r /app/requirements-dev.txt

COPY . /app/

USER appuser:non-root-group

# ==============================
FROM base_stage AS production_stage
# ==============================

COPY . /app/

RUN DJANGO_SECRET_KEY="only-used-for-collectstatic" DATABASE_URL="sqlite:///" \
    python /app/manage.py collectstatic --noinput

USER appuser:non-root-group
