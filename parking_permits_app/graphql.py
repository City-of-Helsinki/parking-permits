from ariadne import load_schema_from_path
from ariadne.contrib.django.views import GraphQLView
from ariadne.contrib.federation import make_federated_schema

from parking_permits_app import resolvers
from project.settings import BASE_DIR

type_defs = load_schema_from_path(
    BASE_DIR / "parking_permits_app" / "schema" / "parking_permit.graphql"
)
schema = make_federated_schema(type_defs, resolvers.schema_bindables)
view = GraphQLView.as_view(schema=schema)
