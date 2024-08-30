FROM public.ecr.aws/ubuntu/ubuntu:20.04 as base

WORKDIR /app

RUN apt-get -o Acquire::Check-Valid-Until=false -o Acquire::Check-Date=false update && \
    apt-get install -y software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    TZ="Europe/Helsinki" DEBIAN_FRONTEND=noninteractive apt-get install -y nano python3.11 python3.11-distutils python3.11-venv apt-transport-https gdal-bin uwsgi uwsgi-plugin-python3 libgdal26 git-core postgresql-client netcat gettext libpq-dev unzip && \
    ln -s /usr/bin/pip3.11 /usr/local/bin/pip && \
    ln -s /usr/bin/pip3.11 /usr/local/bin/pip3 && \
    ln -s /usr/bin/python3.11 /usr/local/bin/python && \
    ln -s /usr/bin/python3.11 /usr/local/bin/python3

RUN python3.11 -m ensurepip

FROM base

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV STATIC_ROOT /srv/app/static
RUN mkdir -p /srv/app/static

RUN DJANGO_SECRET_KEY="only-used-for-collectstatic" DATABASE_URL="sqlite:///" \
    python manage.py collectstatic --noinput


RUN DJANGO_SECRET_KEY="only-used-for-collectstatic" DATABASE_URL="sqlite:///" \
    python manage.py compilemessages

# Openshift starts the container process with group zero and random ID
# we mimic that here with nobody and group zero
USER nobody:0

ENTRYPOINT ["./docker-entrypoint.sh"]
