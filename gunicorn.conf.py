# https://docs.gunicorn.org/en/stable/settings.html

wsgi_app = "project.wsgi"
bind = "0.0.0.0:8888"
limit_request_field_size = 65536

accesslog = "-"  # '-' makes gunicorn log to stdout
errorlog = "-"  # '-' makes gunicorn log to stderr
