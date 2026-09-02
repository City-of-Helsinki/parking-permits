from .settings import *  # noqa

FIELD_ENCRYPTION_KEYS = [
    "f164ec6bd6fbc4aef5647abc15199da0f9badcc1d2127bde2087ae0d794a9a0b"
]

# The `environment` value is required (non-empty) by django-resilient-logger's
# config validation. Make sure it's always set in tests regardless of what
# (if anything) is configured for AUDIT_LOG_ENV in the local environment/.env.
RESILIENT_LOGGER = {**RESILIENT_LOGGER, "environment": "test"}  # noqa: F405

# Some of our tests check for error messages, in English,
# so we don't want them to be translated to, for example, Finnish.
LANGUAGE_CODE = "en"

# Debug options. Override these in tests if needed.
DEBUG_SKIP_PARKKIHUBI_SYNC = True
HELSINKI_ADDRESS_CHECK = True
TALPA_WEBHOOK_WAIT_BUFFER_SECONDS = 0
