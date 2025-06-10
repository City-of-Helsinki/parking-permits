# ==============================
FROM helsinki.azurecr.io/ubi9/python-312-gdal AS base
# ==============================

ENV STATIC_ROOT /srv/app/static

WORKDIR /app

RUN dnf update -y && \
    TZ="Europe/Helsinki" DEBIAN_FRONTEND=noninteractive dnf install -y \
    nano \
    uwsgi \
    uwsgi-plugin-python3 \
    git-core \
    netcat \
    gettext \
    unzip \
    postgresql \
    libpq-devel && \
    ln -s /usr/bin/pip3.12 /usr/local/bin/pip && \
    ln -s /usr/bin/pip3.12 /usr/local/bin/pip3 && \
    ln -s /usr/bin/python3.12 /usr/local/bin/python && \
    ln -s /usr/bin/python3.12 /usr/local/bin/python3 && \
    python3.12 -m ensurepip && \
    mkdir -p /srv/app/static

# ==============================
FROM base AS development
# ==============================

COPY requirements.in .
COPY requirements-dev.in .

RUN pip install -U pip pip-tools && \
    pip-compile -U requirements.in && \
    pip-compile -U requirements-dev.in && \
    pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

COPY . .

RUN DJANGO_SECRET_KEY="only-used-for-collectstatic" DATABASE_URL="sqlite:///" \
    python manage.py collectstatic --noinput && \
    python manage.py compilemessages

# Openshift starts the container process with group zero and random ID
# we mimic that here with nobody and group zero
USER nobody:0

ENTRYPOINT ["./docker-entrypoint.sh"]

# ==============================
FROM base AS production
# ==============================

COPY requirements.in .

RUN pip install -U pip pip-tools && \
    pip-compile -U requirements.in && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN DJANGO_SECRET_KEY="only-used-for-collectstatic" DATABASE_URL="sqlite:///" \
    python manage.py collectstatic --noinput && \
    python manage.py compilemessages

# Openshift starts the container process with group zero and random ID
# we mimic that here with nobody and group zero
USER nobody:0

ENTRYPOINT ["./docker-entrypoint.sh"]
