FROM public.ecr.aws/ubuntu/ubuntu:20.04 as base

ENV STATIC_ROOT /srv/app/static

WORKDIR /app

RUN apt-get -o Acquire::Check-Valid-Until=false -o Acquire::Check-Date=false update && \
    apt-get install -y software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    TZ="Europe/Helsinki" DEBIAN_FRONTEND=noninteractive apt-get install -y \
    nano \
    python3.11 \
    python3.11-distutils \
    python3.11-venv \
    apt-transport-https \
    gdal-bin \
    uwsgi \
    uwsgi-plugin-python3 \
    libgdal26 \
    git-core \
    postgresql-client \
    netcat \
    gettext \
    libpq-dev \
    unzip && \
    ln -s /usr/bin/pip3.11 /usr/local/bin/pip && \
    ln -s /usr/bin/pip3.11 /usr/local/bin/pip3 && \
    ln -s /usr/bin/python3.11 /usr/local/bin/python && \
    ln -s /usr/bin/python3.11 /usr/local/bin/python3 && \
    python3.11 -m ensurepip && \
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
