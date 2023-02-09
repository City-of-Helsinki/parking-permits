from .settings import *  # noqa

FIELD_ENCRYPTION_KEYS = [
    "f164ec6bd6fbc4aef5647abc15199da0f9badcc1d2127bde2087ae0d794a9a0b"
]

# Some of our tests check for error messages, in English,
# so we don't want them to be translated to, for example, Finnish.
LANGUAGE_CODE = "en"

# Debug options. Override these in tests if needed.
DEBUG_SKIP_PARKKIHUBI_SYNC = True
