from decimal import Decimal

from ariadne import load_schema_from_path
from ariadne.contrib.federation import make_federated_schema
from ariadne_django.views import GraphQLView
from django.db.models import QuerySet
from graphql import GraphQLFloat, get_nullable_type

from parking_permits import admin_resolvers, resolvers
from parking_permits.error_formatter import error_formatter
from project.settings import BASE_DIR


def resolve_queryset_synchronously(next_, root, info, **kwargs):
    result = next_(root, info, **kwargs)
    if isinstance(result, QuerySet):
        return list(result)
    return result


def resolve_decimal_float(next_, root, info, **kwargs):
    result = next_(root, info, **kwargs)
    if (
        isinstance(result, Decimal)
        and get_nullable_type(info.return_type) is GraphQLFloat
    ):
        return float(result)
    return result


type_defs = load_schema_from_path(
    BASE_DIR / "parking_permits" / "schema" / "parking_permit.graphql"
)
schema = make_federated_schema(
    type_defs, resolvers.schema_bindables, convert_names_case=True
)
view = GraphQLView.as_view(
    schema=schema,
    error_formatter=error_formatter,
    middleware=[resolve_queryset_synchronously, resolve_decimal_float],
)

admin_type_defs = load_schema_from_path(
    BASE_DIR / "parking_permits" / "schema" / "parking_permit_admin.graphql"
)
schema = make_federated_schema(
    admin_type_defs, admin_resolvers.schema_bindables, convert_names_case=True
)
admin_view = GraphQLView.as_view(
    schema=schema,
    error_formatter=error_formatter,
    middleware=[resolve_queryset_synchronously, resolve_decimal_float],
)
