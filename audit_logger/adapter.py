import logging

from audit_logger.data import AuditMessage


class AuditLoggerAdapter(logging.LoggerAdapter):
    """
    An adapter that sets default values to AuditMessage.

    Useful for reducing the number of repeated lines in a file.
    E.g. if most of the logs have the same origin, you can set up the adapter like this::

        adapter = AuditLoggerAdapter(logger, dict(origin="foo-bar"))

    """

    def process(self, msg: AuditMessage, kwargs):
        msg.set_defaults(**self.extra)
        return msg, kwargs


def getAuditLoggerAdapter(name, extra) -> AuditLoggerAdapter:
    """
    Gets a logger and creates an AuditLoggerAdapter that uses that logger.
    """
    logger = logging.getLogger(name)
    return AuditLoggerAdapter(logger, extra)
