# https://docs.gunicorn.org/en/stable/settings.html

wsgi_app = "project.wsgi"
bind = "0.0.0.0:8888"
limit_request_field_size = 65536

logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "context": {
            "()": "logger_extra.filter.LoggerContextFilter",
        }
    },
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
        "json_error": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["context"],
            "stream": "ext://sys.stdout",
        },
        "error_console": {
            "class": "logging.StreamHandler",
            "formatter": "json_error",
            "filters": ["context"],
            "stream": "ext://sys.stderr",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "gunicorn.access": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "gunicorn.error": {
            "level": "INFO",
            "handlers": ["error_console"],
            "propagate": False,
        },
    },
}
