import logging
from unittest.mock import MagicMock

from django.db import models

MockLogRecord = lambda *args, **kwargs: MagicMock(  # noqa: E731
    spec=logging.LogRecord, *args, **kwargs
)
MockModel = lambda *args, **kwargs: MagicMock(  # noqa: E731
    spec=models.Model, *args, **kwargs
)
