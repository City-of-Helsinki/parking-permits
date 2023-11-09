from decimal import Decimal

import factory

from parking_permits.models import Order, OrderItem, Subscription

from ...models.order import OrderStatus, SubscriptionStatus
from .customer import CustomerFactory
from .parking_permit import ParkingPermitFactory
from .product import ProductFactory


class OrderFactory(factory.django.DjangoModelFactory):
    customer = factory.SubFactory(CustomerFactory)
    talpa_order_id = factory.Faker("uuid4")
    talpa_checkout_url = factory.Faker("url")
    talpa_receipt_url = factory.Faker("url")
    status = OrderStatus.DRAFT

    class Meta:
        model = Order


class SubscriptionFactory(factory.django.DjangoModelFactory):
    talpa_subscription_id = factory.Faker("uuid4")
    status = SubscriptionStatus.CONFIRMED

    class Meta:
        model = Subscription


class OrderItemFactory(factory.django.DjangoModelFactory):
    order = factory.SubFactory(OrderFactory)
    product = factory.SubFactory(ProductFactory)
    permit = factory.SubFactory(ParkingPermitFactory)
    subscription = factory.SubFactory(SubscriptionFactory)
    unit_price = Decimal(30)
    payment_unit_price = Decimal(30)
    vat = Decimal(0.24)
    quantity = 6

    class Meta:
        model = OrderItem
