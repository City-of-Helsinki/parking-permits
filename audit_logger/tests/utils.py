import logging
from itertools import count
from unittest.mock import MagicMock

from django.db import models

MockLogRecord = lambda *args, **kwargs: MagicMock(  # noqa: E731
    spec=logging.LogRecord, *args, **kwargs
)


def make_mock_model(name: str = "MockModel"):
    class _BaseModel(models.Model):
        class Meta:
            abstract = True

    _BaseModel.__name__ = name

    class _Model(MagicMock):
        _id_count = count(1)

        def __init__(self, *args, **kwargs):
            super(_Model, self).__init__(*args, spec=_BaseModel, **kwargs)

            if kwargs.get("id"):
                _Model._id_count = count(kwargs.get("id"))

            self.id = next(_Model._id_count)

    return _Model
