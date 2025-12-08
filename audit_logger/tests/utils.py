import logging
from itertools import count
from unittest.mock import MagicMock

from django.db import models


def mock_log_record(*args, **kwargs):  # noqa: B026
    return MagicMock(
        spec=logging.LogRecord,
        *args,  # noqa: B026
        **kwargs,  # noqa: B026
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
