import copy
import functools
import logging
from typing import Callable, Union

from audit_logger.data import AuditMessage
from audit_logger.enums import Status


def TARGET_RETURN(return_val, *_, **__):
    return return_val


class AuditLoggerAdapter(logging.LoggerAdapter):
    """
    An adapter that sets default values to AuditMessage.

    Useful for reducing the number of repeated lines in a file.
    E.g. if most of the logs have the same origin, you can set up the adapter like this::

        adapter = AuditLoggerAdapter(logger, dict(origin="foo-bar"))

    """

    def __init__(self, logger, extra, autolog_config: dict = None):
        super().__init__(logger, extra)
        self.autolog_config = autolog_config or dict()

    def autolog(
        self,
        base_msg: AuditMessage,
        *,
        autoactor: Callable = None,
        autotarget: Callable = None,
        autostatus: bool = False,
        add_kwarg: Union[bool, str] = None,
        kwarg_name: str = None,
    ):
        """
        Decorator that automatically creates an audit log record after the wrapped
        function is finished.

        :param base_msg: Audit message used as the base.
        :param autoactor: Callable that gets the actor for the audit message. Won't
                          override existing values.
        :param autotarget: Callable that gets the target for the audit message. Won't
                           override existing values.
        :param autostatus: Set audit message's status based on whether it raised an
                           exception (failure) or not (success). Won't override
                           existing values.
        :param add_kwarg: If True, adds the audit message as a kwarg (either as
                          kwarg_name's value or "audit_msg"). If an str, it uses the
                          supplied str as the kwarg name.
        :param kwarg_name: Determines the name of the added kwarg if add_kwarg is True.
        :return:
        """
        autoactor = autoactor or self.autolog_config.get("autoactor", None)
        autotarget = autotarget or self.autolog_config.get("autotarget", None)
        add_kwarg = (
            add_kwarg
            if add_kwarg is not None
            else self.autolog_config.get("add_kwarg", False)
        )
        kwarg_name = kwarg_name or self.autolog_config.get("kwarg_name", "audit_msg")
        autostatus = autostatus or self.autolog_config.get(autostatus, False)

        def _autostatus(msg, status: Status):
            if msg.status is None and autostatus:
                msg.status = status

        def decorator_autolog(f):
            @functools.wraps(f)
            def wrapper_autolog(*args, **kwargs):
                msg = copy.copy(base_msg)
                value = None
                exc = None

                # Add kwarg to kwargs, if applicable.
                if add_kwarg:
                    if isinstance(add_kwarg, str):
                        kwargs[add_kwarg] = msg
                    else:
                        kwargs[kwarg_name] = msg

                try:
                    value = f(*args, **kwargs)
                    _autostatus(msg, Status.SUCCESS)
                except Exception as e:
                    exc = e
                    _autostatus(msg, Status.FAILURE)
                    raise
                finally:
                    # Replacing with nothing creates a new AuditMessage, re-initializing date_time.
                    msg = msg.replace()

                    if msg.target is None and autotarget:
                        msg.target = autotarget(value, *args, **kwargs)

                    if msg.actor is None and autoactor:
                        msg.actor = autoactor(*args, **kwargs)

                    if exc:
                        self.exception(msg)
                    elif msg.status == Status.FAILURE:
                        self.error(msg)
                    else:
                        self.info(msg)

                return value

            return wrapper_autolog

        return decorator_autolog

    def process(self, msg: AuditMessage, kwargs):
        msg.set_defaults(**self.extra)
        return msg, kwargs


def getAuditLoggerAdapter(name, extra) -> AuditLoggerAdapter:
    """
    Gets a logger and creates an AuditLoggerAdapter that uses that logger.
    """
    logger = logging.getLogger(name)
    return AuditLoggerAdapter(logger, extra)
