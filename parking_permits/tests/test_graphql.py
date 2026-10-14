import json

import pytest
from ariadne import QueryType, make_executable_schema

from parking_permits.graphql import admin_view, view
from parking_permits.models import Customer
from parking_permits.tests.factories.customer import CustomerFactory


@pytest.mark.django_db
@pytest.mark.parametrize("graphql_view", [view, admin_view])
@pytest.mark.parametrize("customer_count", [0, 2])
def test_graphql_serializes_querysets_synchronously(rf, graphql_view, customer_count):
    customers = CustomerFactory.create_batch(customer_count)
    queryset = Customer.objects.filter(pk__in=[c.pk for c in customers]).order_by("pk")
    query = QueryType()
    query.set_field("customers", lambda *_: queryset)
    query.set_field("page", lambda *_: {"objects": queryset})
    schema = make_executable_schema(
        """
        type Customer { id: ID! }
        type Page { objects: [Customer!]! }
        type Query { customers: [Customer!]!, page: Page! }
        """,
        query,
    )
    graphql_test_view = graphql_view.view_class.as_view(
        **{**graphql_view.view_initkwargs, "schema": schema}
    )
    request = rf.post(
        "/",
        {"query": "{ customers { id } page { objects { id } } }"},
        content_type="application/json",
    )

    response = graphql_test_view(request)

    expected = [{"id": str(customer.pk)} for customer in customers]
    assert response.status_code == 200
    assert json.loads(response.content) == {
        "data": {"customers": expected, "page": {"objects": expected}}
    }
