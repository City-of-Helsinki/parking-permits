import json
from decimal import Decimal
from unittest.mock import patch

import pytest
from ariadne import QueryType, make_executable_schema
from django.urls import reverse
from helusers.authz import UserAuthorization

from parking_permits.decorators import RequestJWTAuthentication
from parking_permits.graphql import admin_view, view
from parking_permits.models import Customer, Product
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.product import ProductFactory
from users.tests.factories.user import GroupFactory, UserFactory


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


@pytest.mark.parametrize("graphql_view", [view, admin_view])
@pytest.mark.parametrize("vat", [Decimal("0.255"), Decimal("0"), None])
def test_graphql_serializes_decimal_float_fields(rf, graphql_view, vat):
    product = Product(vat=vat, unit_price=Decimal("30.50"))
    query = QueryType()
    query.set_field("product", lambda *_: product)
    schema = make_executable_schema(
        """
        type Product { vat: Float, unitPrice: Float!, exactPrice: String! }
        type Query { product: Product! }
        """,
        query,
        convert_names_case=True,
    )
    product.exact_price = Decimal("30.50")
    graphql_test_view = graphql_view.view_class.as_view(
        **{**graphql_view.view_initkwargs, "schema": schema}
    )
    request = rf.post(
        "/",
        {"query": "{ product { vat unitPrice exactPrice } }"},
        content_type="application/json",
    )

    response = graphql_test_view(request)

    assert response.status_code == 200
    assert json.loads(response.content) == {
        "data": {
            "product": {
                "vat": float(vat) if vat is not None else None,
                "unitPrice": 30.5,
                "exactPrice": "30.50",
            }
        }
    }


@pytest.mark.django_db
def test_admin_graphql_serializes_product_prices(client):
    product = ProductFactory(
        vat=Decimal("0.255"),
        unit_price=Decimal("30.50"),
        low_emission_discount=Decimal("0.5"),
    )
    admin = UserFactory()
    admin.groups.add(GroupFactory(name="super_admin"))
    with patch.object(
        RequestJWTAuthentication,
        "authenticate",
        return_value=UserAuthorization(admin, {}),
    ):
        response = client.post(
            reverse("parking_permits:admin-graphql"),
            {
                "query": """
                    query Product($id: ID!) {
                        product(productId: $id) {
                            vat
                            vatPercentage
                            unitPrice
                            lowEmissionDiscount
                            lowEmissionDiscountPercentage
                            secondaryVehicleIncreaseRate
                        }
                    }
                """,
                "variables": {"id": str(product.pk)},
            },
            content_type="application/json",
        )

    assert response.status_code == 200
    assert response.json() == {
        "data": {
            "product": {
                "vat": 0.255,
                "vatPercentage": 25.5,
                "unitPrice": 30.5,
                "lowEmissionDiscount": 0.5,
                "lowEmissionDiscountPercentage": 50.0,
                "secondaryVehicleIncreaseRate": 0.5,
            }
        }
    }
