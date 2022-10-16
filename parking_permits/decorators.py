from functools import wraps

from django.core.exceptions import PermissionDenied
from helusers.oidc import AuthenticationError, RequestJWTAuthentication


def user_passes_test(test_func):
    def decorator(f):
        @wraps(f)
        def wrapper(obj, info, *args, **kwargs):
            request = info.context["request"]
            try:
                auth = RequestJWTAuthentication().authenticate(request)
            except AuthenticationError as e:
                raise PermissionDenied(e)

            if auth and test_func(auth.user):
                request.user = auth.user
                return f(obj, info, *args, **kwargs)
            raise PermissionDenied()

        return wrapper

    return decorator


is_authenticated = user_passes_test(lambda u: u.is_authenticated)
is_super_admin = user_passes_test(lambda u: u.is_super_admin)
is_sanctions_and_returns = user_passes_test(lambda u: u.is_sanctions_and_returns)
is_sanctions = user_passes_test(lambda u: u.is_sanctions)
is_customer_service = user_passes_test(lambda u: u.is_customer_service)
is_preparators = user_passes_test(lambda u: u.is_preparators)
is_inspectors = user_passes_test(lambda u: u.is_inspectors)


def require_user_passes_test(test_func):
    def decorator(f):
        @wraps(f)
        def wrapper(request, *args, **kwargs):
            try:
                auth = RequestJWTAuthentication().authenticate(request)
            except AuthenticationError as e:
                raise PermissionDenied(e)

            if auth and test_func(auth.user):
                request.user = auth.user
                return f(request, *args, **kwargs)
            raise PermissionDenied()

        return wrapper

    return decorator


require_super_admin = require_user_passes_test(lambda u: u.is_super_admin)
