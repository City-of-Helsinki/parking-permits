from ariadne import load_schema_from_path
from ariadne.contrib.federation import make_federated_schema
from ariadne_django.views import GraphQLView

from parking_permits import admin_resolvers, resolvers
from parking_permits.error_formatter import error_formatter
from project.settings import BASE_DIR

type_defs = load_schema_from_path(
    BASE_DIR / "parking_permits" / "schema" / "parking_permit.graphql"
)
schema = make_federated_schema(type_defs, resolvers.schema_bindables)
view = GraphQLView.as_view(schema=schema, error_formatter=error_formatter)

admin_type_defs = load_schema_from_path(
    BASE_DIR / "parking_permits" / "schema" / "parking_permit_admin.graphql"
)
schema = make_federated_schema(admin_type_defs, admin_resolvers.schema_bindables)
admin_view = GraphQLView.as_view(schema=schema, error_formatter=error_formatter)
