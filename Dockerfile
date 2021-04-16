ARG BASE_IMAGE=python
ARG PYTHON_VERSION=3.9.4
ARG IMAGE_VARIANT=slim

# ==============================
FROM ${BASE_IMAGE}:${PYTHON_VERSION}-${IMAGE_VARIANT} AS base_stage
# ==============================

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

COPY requirements-dev.txt /app/
RUN pip install --no-cache-dir -r /app/requirements-dev.txt

COPY . /app/

# ==============================
FROM base_stage AS production_stage
# ==============================

COPY . /app/

RUN DJANGO_SECRET_KEY="only-used-for-collectstatic" \
    python /app/manage.py collectstatic --noinput
