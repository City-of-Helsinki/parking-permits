from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import PermissionDenied
from helusers.authz import UserAuthorization

import parking_permits.decorators
from parking_permits.admin_resolvers import mutation, query
from users.models import ParkingPermitGroups
from users.tests.factories.user import GroupFactory, UserFactory

SUPER_ADMIN = ParkingPermitGroups.SUPER_ADMIN
SANCTIONS_AND_REFUNDS = ParkingPermitGroups.SANCTIONS_AND_REFUNDS
SANCTIONS = ParkingPermitGroups.SANCTIONS
CUSTOMER_SERVICE = ParkingPermitGroups.CUSTOMER_SERVICE
PREPARATORS = ParkingPermitGroups.PREPARATORS
INSPECTORS = ParkingPermitGroups.INSPECTORS

# GraphQL field -> lowest group allowed to call it.
QUERY_MIN_GROUP = {
    "permits": PREPARATORS,
    "limitedPermits": INSPECTORS,
    "permitDetail": PREPARATORS,
    "zones": CUSTOMER_SERVICE,
    "zoneByLocation": CUSTOMER_SERVICE,
    "customer": CUSTOMER_SERVICE,
    "customers": CUSTOMER_SERVICE,
    "vehicle": CUSTOMER_SERVICE,
    "permitPrices": CUSTOMER_SERVICE,
    "permitPriceChangeList": CUSTOMER_SERVICE,
    "getExtendedPriceList": CUSTOMER_SERVICE,
    "products": SUPER_ADMIN,
    "product": SUPER_ADMIN,
    "refunds": PREPARATORS,
    "refund": CUSTOMER_SERVICE,
    "orders": PREPARATORS,
    "addresses": SUPER_ADMIN,
    "address": SUPER_ADMIN,
    "announcements": SUPER_ADMIN,
    "announcement": SUPER_ADMIN,
}
MUTATION_MIN_GROUP = {
    "createResidentPermit": CUSTOMER_SERVICE,
    "updateResidentPermit": CUSTOMER_SERVICE,
    "extendPermit": CUSTOMER_SERVICE,
    "endPermit": CUSTOMER_SERVICE,
    "updateProduct": SUPER_ADMIN,
    "deleteProduct": SUPER_ADMIN,
    "createProduct": SUPER_ADMIN,
    "requestForApproval": SANCTIONS,
    "acceptRefunds": SANCTIONS_AND_REFUNDS,
    "updateRefund": CUSTOMER_SERVICE,
    "updateAddress": SUPER_ADMIN,
    "deleteAddress": SUPER_ADMIN,
    "createAddress": SUPER_ADMIN,
    "createAnnouncement": SUPER_ADMIN,
    "addTemporaryVehicle": CUSTOMER_SERVICE,
    "removeTemporaryVehicle": CUSTOMER_SERVICE,
}
# Open to any authenticated user (currentUserGroups) or to everyone.
UNRESTRICTED_FIELDS = {("query", "currentUserGroups"), ("query", "addressSearch")}

RESOLVER_CASES = [
    *(("query", field, group) for field, group in QUERY_MIN_GROUP.items()),
    *(("mutation", field, group) for field, group in MUTATION_MIN_GROUP.items()),
]


@contextmanager
def stubbed_resolver_body(resolver):
    """Replace the decorated resolver's body so only its permission check runs.

    The permission decorators wrap the real resolver in a closure (`wrapper`
    calls `f`). Swapping that closure cell lets us exercise the permission
    check without needing a database setup or arguments for every resolver.
    """
    cells = [
        cell
        for cell in resolver.__closure__ or ()
        if cell.cell_contents is getattr(resolver, "__wrapped__", None)
    ]
    assert len(cells) == 1, (
        "Could not find the wrapped resolver body. The permission decorators in "
        "parking_permits/decorators.py may have changed; update this helper."
    )
    (cell,) = cells
    original = cell.cell_contents
    cell.cell_contents = body = Mock(name="resolver_body")
    try:
        yield body
    finally:
        cell.cell_contents = original


def call_resolver(kind, field, auth):
    resolver = {"query": query, "mutation": mutation}[kind]._resolvers[field]
    with (
        stubbed_resolver_body(resolver) as body,
        patch.object(
            parking_permits.decorators.RequestJWTAuthentication,
            "authenticate",
            return_value=auth,
        ),
    ):
        resolver(None, Mock(context={"request": Mock()}))
    return body


@pytest.fixture
def users_by_group(db):
    users = {}
    for group in ParkingPermitGroups:
        user = UserFactory()
        user.groups.add(GroupFactory(name=group.value))
        users[group] = user
    return users


def test_every_resolver_is_covered():
    registered = {("query", field) for field in query._resolvers} | {
        ("mutation", field) for field in mutation._resolvers
    }
    covered = (
        {("query", field) for field in QUERY_MIN_GROUP}
        | {("mutation", field) for field in MUTATION_MIN_GROUP}
        | UNRESTRICTED_FIELDS
    )
    assert registered == covered


@pytest.mark.parametrize(("kind", "field", "min_group"), RESOLVER_CASES)
def test_resolver_allows_only_min_group_and_higher(
    users_by_group, kind, field, min_group
):
    groups = list(ParkingPermitGroups)  # highest to lowest privilege
    allowed = groups[: groups.index(min_group) + 1]
    callers = {
        **{group: UserAuthorization(users_by_group[group], {}) for group in groups},
        "no group": UserAuthorization(UserFactory(), {}),
        "unauthenticated": None,
    }
    for caller, auth in callers.items():
        if caller in allowed:
            assert call_resolver(kind, field, auth).called, caller
        else:
            with pytest.raises(PermissionDenied):
                call_resolver(kind, field, auth)
