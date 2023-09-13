import datetime
from datetime import timezone as dt_tz
from decimal import Decimal
from unittest.mock import patch

import requests_mock
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone as tz
from freezegun import freeze_time
from helusers.settings import api_token_auth_settings
from jose import jwt
from rest_framework.test import APIClient, APITestCase

from parking_permits.exceptions import DeletionNotAllowed
from parking_permits.models.driving_licence import DrivingLicence
from parking_permits.models.order import (
    Order,
    OrderPaymentType,
    OrderStatus,
    OrderValidator,
    Subscription,
    SubscriptionStatus,
    SubscriptionValidator,
)
from parking_permits.models.parking_permit import ParkingPermit, ParkingPermitStatus
from parking_permits.models.refund import Refund, RefundStatus
from parking_permits.models.vehicle import VehicleUser
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.order import (
    OrderFactory,
    OrderItemFactory,
    SubscriptionFactory,
)
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.vehicle import VehicleFactory
from users.tests.factories.user import UserFactory

from ..models import Customer
from ..models.common import SourceSystem
from .keys import rsa_key


def get_validated_order_data(talpa_order_id, talpa_order_item_id):
    return {
        "orderId": talpa_order_id,
        "lastValidPurchaseDateTime": "2023-06-01T15:46:05.000Z",
        "checkoutUrl": "https://test.com",
        "loggedInCheckoutUrl": "https://test.com",
        "receiptUrl": "https://test.com",
        "items": [
            {
                "orderItemId": talpa_order_item_id,
                "lastValidPurchaseDateTime": "2023-06-01T15:46:05.000Z",
                "startDate": "2023-06-01T15:46:05",
                "priceGross": "45.00",
                "rowPriceTotal": "45.00",
                "vatPercentage": 24,
                "quantity": 1,
            }
        ],
    }


def get_validated_subscription_data(
    talpa_subscription_id, talpa_order_id, talpa_order_item_id, permit_id
):
    return {
        "subscriptionId": talpa_subscription_id,
        "meta": [
            {
                "orderId": talpa_order_id,
                "orderItemId": talpa_order_item_id,
                "subscriptionId": talpa_subscription_id,
                "key": "permitId",
                "value": permit_id,
                "visibleInCheckout": "false",
            }
        ],
    }


class PaymentViewTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()

    def test_payment_view_should_return_bad_request_if_talpa_order_id_missing(self):
        url = reverse("parking_permits:payment-notify")
        data = {
            "eventType": "PAYMENT_PAID",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    @override_settings(DEBUG=True)
    def test_payment_view_should_update_order_and_permits_status(self):
        talpa_order_id = "d86ca61d-97e9-410a-a1e3-4894873b1b35"
        permit_1 = ParkingPermitFactory(status=ParkingPermitStatus.PAYMENT_IN_PROGRESS)
        permit_2 = ParkingPermitFactory(status=ParkingPermitStatus.PAYMENT_IN_PROGRESS)
        order = OrderFactory(talpa_order_id=talpa_order_id, status=OrderStatus.DRAFT)
        order.permits.add(permit_1, permit_2)
        url = reverse("parking_permits:payment-notify")
        data = {"eventType": "PAYMENT_PAID", "orderId": talpa_order_id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        permit_1.refresh_from_db()
        permit_2.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CONFIRMED)
        self.assertEqual(permit_1.status, ParkingPermitStatus.VALID)
        self.assertEqual(permit_2.status, ParkingPermitStatus.VALID)


class RightOfPurchaseViewTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()

    def test_right_of_purchase_view_should_return_bad_request_if_talpa_order_id_missing(
        self,
    ):
        url = reverse("parking_permits:talpa-right-of-purchase")
        data = {
            "permitId": "80000001",
            "userId": "d86ca61d-97e9-410a-a1e3-4894873b1b46",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, 400)

    def test_right_of_purchase_view_should_return_bad_request_if_permit_id_missing(
        self,
    ):
        url = reverse("parking_permits:talpa-right-of-purchase")
        data = {
            "orderId": "d86ca61d-97e9-410a-a1e3-4894873b1b35",
            "userId": "d86ca61d-97e9-410a-a1e3-4894873b1b46",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, 400)

    def test_right_of_purchase_view_should_return_bad_request_if_user_id_missing(self):
        url = reverse("parking_permits:talpa-right-of-purchase")
        data = {
            "permitId": "80000001",
            "orderId": "d86ca61d-97e9-410a-a1e3-4894873b1b35",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, 400)

    def test_right_of_purchase_view_permit_not_found(self):
        talpa_order_id = "d4745a07-de99-33f8-94d6-64595f7a8bc6"
        talpa_order_item_id = "2f20c06d-2a9a-4a60-be4b-504d8a2f8c02"
        user_id = "d86ca61d-97e9-410a-a1e3-4894873b1b46"
        permit_id = "80000001"
        url = reverse("parking_permits:talpa-right-of-purchase")
        data = {
            "orderId": talpa_order_id,
            "namespace": "asukaspysakointi",
            "userId": user_id,
            "orderItem": {
                "merchantId": "00243b8a-b30c-4370-af19-90631bf9a370",
                "orderItemId": talpa_order_item_id,
                "orderId": talpa_order_id,
                "meta": [
                    {
                        "orderItemMetaId": "ee04456f-b330-4dab-a277-12d5cd24a4b7",
                        "orderItemId": talpa_order_item_id,
                        "orderId": talpa_order_id,
                        "key": "permitId",
                        "value": permit_id,
                        "label": None,
                        "visibleInCheckout": "false",
                        "ordinal": None,
                    },
                ],
            },
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("rightOfPurchase"), False)
        self.assertEqual(response.data.get("userId"), user_id)
        self.assertEqual(
            response.data.get("errorMessage"),
            "ParkingPermit matching query does not exist.",
        )

    @override_settings(
        DEBUG=True,
        TRAFICOM_CHECK=False,
    )
    @patch.object(Customer, "fetch_vehicle_detail")
    @patch.object(Customer, "fetch_driving_licence_detail")
    def test_right_of_purchase_view_is_valid(
        self, mock_fetch_driving_licence_detail, mock_fetch_vehicle_detail
    ):
        talpa_order_id = "d4745a07-de99-33f8-94d6-64595f7a8bc6"
        talpa_order_item_id = "2f20c06d-2a9a-4a60-be4b-504d8a2f8c02"
        talpa_subscription_id = "f769b803-0bd0-489d-aa81-b35af391f391"
        user = UserFactory(uuid="a571a903-b0d2-4b36-80ff-348173e6d085")
        customer = CustomerFactory(user=user)
        permit_start_time = datetime.datetime(
            2023, 9, 12, 13, 46, 0, tzinfo=datetime.timezone.utc
        )
        permit_end_time = datetime.datetime(
            2023, 10, 11, 23, 59, 0, tzinfo=datetime.timezone.utc
        )
        permit = ParkingPermitFactory(
            id="80000163",
            status=ParkingPermitStatus.VALID,
            customer=customer,
            start_time=permit_start_time,
            end_time=permit_end_time,
        )
        order = OrderFactory(
            talpa_order_id=talpa_order_id,
            customer=customer,
            status=OrderStatus.CONFIRMED,
            paid_time=tz.make_aware(
                datetime.datetime.strptime(
                    "2023-09-12T13:46:00.000Z", "%Y-%m-%dT%H:%M:%S.%fZ"
                )
            ),
        )
        order.permits.add(permit)
        order.save()
        subscription = SubscriptionFactory(
            talpa_subscription_id=talpa_subscription_id,
            status=SubscriptionStatus.CONFIRMED,
        )
        unit_price = Decimal(30)
        product = ProductFactory(
            talpa_product_id="68db99cb-2ae5-36fd-bc18-51d30f1116bd",
            unit_price=unit_price,
        )
        OrderItemFactory(
            talpa_order_item_id=talpa_order_item_id,
            order=order,
            product=product,
            permit=permit,
            subscription=subscription,
        )

        vehicle = VehicleFactory(
            registration_number="ABC-123", last_inspection_date="2050-01-01"
        )
        vehicle.users.add(
            VehicleUser.objects.create(national_id_number=customer.national_id_number)
        )
        DrivingLicence.objects.create(
            customer=customer,
            start_date=datetime.datetime.strptime("2023-01-01", "%Y-%m-%d").date(),
            active=True,
        )

        mock_fetch_driving_licence_detail.return_value = None
        mock_fetch_vehicle_detail.return_value = vehicle

        url = reverse("parking_permits:talpa-right-of-purchase")
        data = {
            "orderId": talpa_order_id,
            "namespace": "asukaspysakointi",
            "userId": str(user.uuid),
            "orderItem": {
                "merchantId": "00243b8a-b30c-4370-af19-90631bf9a370",
                "orderItemId": talpa_order_item_id,
                "orderId": talpa_order_id,
                "productId": product.talpa_product_id,
                "productName": "Pysäköintialue K",
                "productLabel": "Ajoneuvo: FLN-835 Mercedes-Benz Vito Tourer Yksikerroksinen (CI) 3ov 1950cm3 A",
                "productDescription": "12.09.2023 - 11.10.2023",
                "unit": "kk",
                "quantity": 1,
                "rowPriceNet": "34.20",
                "rowPriceVat": "10.80",
                "rowPriceTotal": "45.00",
                "vatPercentage": "24",
                "priceNet": "34.20",
                "priceVat": "10.80",
                "priceGross": "45.00",
                "originalPriceNet": None,
                "originalPriceVat": None,
                "originalPriceGross": None,
                "periodFrequency": 1,
                "periodUnit": "weekly",
                "periodCount": None,
                "startDate": "2023-09-12T13:46:00",
                "billingStartDate": None,
                "invoicingDate": None,
                "invoicingStatus": None,
                "meta": [
                    {
                        "orderItemMetaId": "9a672f56-2bad-4510-9831-3c4dad12928f",
                        "orderItemId": talpa_order_item_id,
                        "orderId": talpa_order_id,
                        "key": "permitDuration",
                        "value": "Määräaikainen 1 kk",
                        "label": "Pysäköintitunnuksen kesto",
                        "visibleInCheckout": "true",
                        "ordinal": "1",
                    },
                    {
                        "orderItemMetaId": "d1d4ba0a-dc0e-41ac-b52a-1845de02dcee",
                        "orderItemId": talpa_order_item_id,
                        "orderId": talpa_order_id,
                        "key": "endDate",
                        "value": "11.10.2023 23:59",
                        "label": "Pysäköintitunnuksen päättymispäivä",
                        "visibleInCheckout": "true",
                        "ordinal": "3",
                    },
                    {
                        "orderItemMetaId": "22f4bad6-3410-479e-8acb-acd890f6013b",
                        "orderItemId": talpa_order_item_id,
                        "orderId": talpa_order_id,
                        "key": "startDate",
                        "value": "11.09.2023",
                        "label": "Pysäköintitunnuksen alkamispäivä*",
                        "visibleInCheckout": "true",
                        "ordinal": "2",
                    },
                    {
                        "orderItemMetaId": "30579a8c-51af-42d1-bce4-a8afdc381a6e",
                        "orderItemId": talpa_order_item_id,
                        "orderId": talpa_order_id,
                        "key": "terms",
                        "value": "* Tunnus on voimassa valitsemastasi alkamispäivästä lähtien, "
                        + "kun maksusuoritus on hyväksytty.",
                        "label": "",
                        "visibleInCheckout": "true",
                        "ordinal": "4",
                    },
                    {
                        "orderItemMetaId": "c4caf437-d4ee-43e6-b547-f32e89929773",
                        "orderItemId": talpa_order_item_id,
                        "orderId": talpa_order_id,
                        "key": "sourceOrderItemId",
                        "value": "243",
                        "label": None,
                        "visibleInCheckout": "false",
                        "ordinal": "0",
                    },
                    {
                        "orderItemMetaId": "ee04456f-b330-4dab-a277-12d5cd24a4b7",
                        "orderItemId": talpa_order_item_id,
                        "orderId": talpa_order_id,
                        "key": "permitId",
                        "value": permit.id,
                        "label": None,
                        "visibleInCheckout": "false",
                        "ordinal": None,
                    },
                ],
            },
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("rightOfPurchase"), True)
        self.assertEqual(response.data.get("userId"), str(user.uuid))


class OrderViewTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()

    def test_order_view_should_return_bad_request_if_talpa_order_id_missing(self):
        url = reverse("parking_permits:order-notify")
        data = {
            "eventType": "SUBSCRIPTION_RENEWAL_ORDER_CREATED",
            "subscriptionId": "f769b803-0bd0-489d-aa81-b35af391f391",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    def test_order_view_should_return_bad_request_if_talpa_subscription_id_missing(
        self,
    ):
        url = reverse("parking_permits:order-notify")
        data = {
            "eventType": "SUBSCRIPTION_RENEWAL_ORDER_CREATED",
            "orderId": "d86ca61d-97e9-410a-a1e3-4894873b1b35",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    @override_settings(DEBUG=True)
    @patch.object(OrderValidator, "validate_order")
    def test_subscription_renewal(self, mock_validate_order):
        talpa_existing_order_id = "d86ca61d-97e9-410a-a1e3-4894873b1b35"
        talpa_existing_order_item_id = "7c779368-7e5f-42dc-9ffe-554915cb5540"
        talpa_new_order_id = "c6f70a98-23d1-46f0-b9cd-c01c6f78e075"
        talpa_new_order_item_id = "5720b2dd-7226-498f-84c8-2ddb1fa1bada"
        talpa_subscription_id = "f769b803-0bd0-489d-aa81-b35af391f391"
        customer = CustomerFactory()
        permit_start_time = datetime.datetime(
            2023, 4, 30, 10, 00, 0, tzinfo=datetime.timezone.utc
        )
        permit_end_time = datetime.datetime(
            2023, 5, 29, 23, 59, 0, tzinfo=datetime.timezone.utc
        )
        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            customer=customer,
            start_time=permit_start_time,
            end_time=permit_end_time,
        )
        order = OrderFactory(
            talpa_order_id=talpa_existing_order_id,
            customer=customer,
            status=OrderStatus.CONFIRMED,
            paid_time=tz.make_aware(
                datetime.datetime.strptime(
                    "2023-06-01T15:46:05.000Z", "%Y-%m-%dT%H:%M:%S.%fZ"
                )
            ),
        )
        order.permits.add(permit)
        order.save()
        subscription = SubscriptionFactory(
            talpa_subscription_id=talpa_subscription_id,
            status=SubscriptionStatus.CONFIRMED,
        )
        unit_price = Decimal(30)
        product = ProductFactory(unit_price=unit_price)
        OrderItemFactory(
            talpa_order_item_id=talpa_existing_order_item_id,
            order=order,
            product=product,
            permit=permit,
            subscription=subscription,
        )

        url = reverse("parking_permits:order-notify")
        data = {
            "eventType": "SUBSCRIPTION_RENEWAL_ORDER_CREATED",
            "subscriptionId": talpa_subscription_id,
            "orderId": talpa_new_order_id,
        }

        mock_validate_order.return_value = get_validated_order_data(
            talpa_new_order_id, talpa_new_order_item_id
        )

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        subscription.refresh_from_db()
        subscription_order = subscription.order_items.first().order
        self.assertEqual(str(subscription.talpa_subscription_id), talpa_subscription_id)
        self.assertEqual(
            str(subscription_order.talpa_order_id), talpa_existing_order_id
        )
        self.assertEqual(subscription.status, SubscriptionStatus.CONFIRMED)
        self.assertEqual(str(subscription.talpa_subscription_id), talpa_subscription_id)
        order = Order.objects.get(talpa_order_id=talpa_new_order_id)
        permit.refresh_from_db()
        self.assertEqual(str(order.talpa_order_id), talpa_new_order_id)
        self.assertEqual(order.customer, permit.customer)
        self.assertEqual(order.status, OrderStatus.CONFIRMED)
        self.assertEqual(order.payment_type, OrderPaymentType.ONLINE_PAYMENT)
        self.assertEqual(permit.status, ParkingPermitStatus.VALID)
        self.assertEqual(
            permit.end_time,
            datetime.datetime(2023, 6, 29, 23, 59, 0, tzinfo=datetime.timezone.utc),
        )


class SubscriptionViewTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()

    def test_subscription_view_should_return_bad_request_if_talpa_order_id_missing(
        self,
    ):
        url = reverse("parking_permits:subscription-notify")
        data = {
            "eventType": "SUBSCRIPTION_CREATED",
            "subscriptionId": "f769b803-0bd0-489d-aa81-b35af391f391",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    def test_subscription_view_should_return_bad_request_if_talpa_order_item_id_missing(
        self,
    ):
        url = reverse("parking_permits:subscription-notify")
        data = {
            "eventType": "SUBSCRIPTION_CREATED",
            "orderId": "d86ca61d-97e9-410a-a1e3-4894873b1b36",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    def test_subscription_view_should_return_bad_request_if_talpa_subscription_id_missing(
        self,
    ):
        url = reverse("parking_permits:subscription-notify")
        data = {
            "eventType": "SUBSCRIPTION_CREATED",
            "orderId": "d86ca61d-97e9-410a-a1e3-4894873b1b35",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    @override_settings(DEBUG=True)
    @patch.object(SubscriptionValidator, "validate_subscription")
    @patch.object(OrderValidator, "validate_order")
    def test_subscription_creation(
        self, mock_validate_order, mock_validate_subscription
    ):
        talpa_order_id = "d86ca61d-97e9-410a-a1e3-4894873b1b35"
        talpa_order_item_id = "819daecd-5ebb-4a94-924e-9710069e9285"
        talpa_subscription_id = "f769b803-0bd0-489d-aa81-b35af391f391"
        customer = CustomerFactory()
        permit_1 = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID, customer=customer
        )
        permit_2 = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID, customer=customer
        )
        order = OrderFactory(
            talpa_order_id=talpa_order_id,
            customer=customer,
            status=OrderStatus.CONFIRMED,
        )
        order.permits.add(permit_1, permit_2)
        order.save()
        unit_price = Decimal(30)
        product = ProductFactory(unit_price=unit_price)
        OrderItemFactory(
            order=order,
            product=product,
            permit=permit_1,
        )
        url = reverse("parking_permits:subscription-notify")
        data = {
            "eventType": "SUBSCRIPTION_CREATED",
            "subscriptionId": talpa_subscription_id,
            "orderId": talpa_order_id,
            "orderItemId": talpa_order_item_id,
        }

        mock_validate_order.return_value = get_validated_order_data(
            talpa_order_id, order.order_items.first().talpa_order_item_id
        )

        mock_validate_subscription.return_value = get_validated_subscription_data(
            talpa_subscription_id, talpa_order_id, talpa_order_item_id, permit_1.id
        )

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        subscription = Subscription.objects.get(
            talpa_subscription_id=talpa_subscription_id
        )
        subscription_order_item = subscription.order_items.first()
        subscription_order = subscription_order_item.order
        self.assertEqual(str(subscription.talpa_subscription_id), talpa_subscription_id)
        self.assertEqual(
            str(subscription_order_item.talpa_order_item_id), talpa_order_item_id
        )
        self.assertEqual(str(subscription_order.talpa_order_id), talpa_order_id)
        self.assertEqual(subscription.status, SubscriptionStatus.CONFIRMED)
        order.refresh_from_db()
        self.assertEqual(subscription_order, order)
        self.assertEqual(subscription_order.status, OrderStatus.CONFIRMED)
        self.assertEqual(permit_1.status, ParkingPermitStatus.VALID)
        self.assertEqual(permit_2.status, ParkingPermitStatus.VALID)

    @override_settings(DEBUG=True)
    @patch.object(OrderValidator, "validate_order")
    @freeze_time("2023-05-30")
    def test_subscription_cancellation(self, mock_validate_order):
        talpa_order_id = "d86ca61d-97e9-410a-a1e3-4894873b1b35"
        talpa_order_item_id = "819daecd-5ebb-4a94-924e-9710069e9285"
        talpa_subscription_id = "f769b803-0bd0-489d-aa81-b35af391f391"
        customer = CustomerFactory()
        permit_start_time = datetime.datetime(
            2023, 5, 29, 10, 00, 0, tzinfo=datetime.timezone.utc
        )
        permit_end_time = datetime.datetime(
            2023, 6, 28, 23, 59, 0, tzinfo=datetime.timezone.utc
        )
        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            customer=customer,
            start_time=permit_start_time,
            end_time=permit_end_time,
        )
        order = OrderFactory(
            talpa_order_id=talpa_order_id,
            customer=customer,
            status=OrderStatus.CONFIRMED,
        )
        order.permits.add(permit)
        order.save()
        unit_price = Decimal(30)
        product = ProductFactory(unit_price=unit_price)
        subscription = SubscriptionFactory(
            talpa_subscription_id=talpa_subscription_id,
            status=SubscriptionStatus.CONFIRMED,
        )
        OrderItemFactory(
            order=order,
            product=product,
            permit=permit,
            subscription=subscription,
        )

        url = reverse("parking_permits:subscription-notify")
        data = {
            "eventType": "SUBSCRIPTION_CANCELLED",
            "subscriptionId": talpa_subscription_id,
            "orderId": talpa_order_id,
            "orderItemId": talpa_order_item_id,
        }

        mock_validate_order.return_value = get_validated_order_data(
            talpa_order_id, order.order_items.first().talpa_order_item_id
        )

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        subscription.refresh_from_db()
        subscription_order = subscription.order_items.first().order
        self.assertEqual(str(subscription.talpa_subscription_id), talpa_subscription_id)
        self.assertEqual(str(subscription_order.talpa_order_id), talpa_order_id)
        self.assertEqual(subscription.status, SubscriptionStatus.CANCELLED)
        order.refresh_from_db()
        self.assertEqual(subscription_order, order)
        self.assertEqual(subscription_order.status, OrderStatus.CANCELLED)
        self.assertEqual(permit.status, ParkingPermitStatus.VALID)

    @override_settings(DEBUG=True)
    @patch.object(OrderValidator, "validate_order")
    @freeze_time("2023-05-30")
    def test_subscription_cancellation_with_refund(self, mock_validate_order):
        talpa_order_id = "d86ca61d-97e9-410a-a1e3-4894873b1b35"
        talpa_order_item_id = "819daecd-5ebb-4a94-924e-9710069e9285"
        talpa_subscription_id = "f769b803-0bd0-489d-aa81-b35af391f391"
        customer = CustomerFactory()
        permit_start_time = datetime.datetime(
            2023, 3, 16, 10, 00, 0, tzinfo=datetime.timezone.utc
        )
        permit_end_time = datetime.datetime(
            2023, 7, 15, 23, 59, 0, tzinfo=datetime.timezone.utc
        )
        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            customer=customer,
            start_time=permit_start_time,
            end_time=permit_end_time,
        )
        order = OrderFactory(
            talpa_order_id=talpa_order_id,
            customer=customer,
            status=OrderStatus.CONFIRMED,
        )
        order.permits.add(permit)
        order.save()
        unit_price = Decimal(30)
        product = ProductFactory(unit_price=unit_price)
        subscription = SubscriptionFactory(
            talpa_subscription_id=talpa_subscription_id,
            status=SubscriptionStatus.CONFIRMED,
        )
        OrderItemFactory(
            order=order,
            product=product,
            permit=permit,
            subscription=subscription,
        )

        url = reverse("parking_permits:subscription-notify")
        data = {
            "eventType": "SUBSCRIPTION_CANCELLED",
            "subscriptionId": talpa_subscription_id,
            "orderId": talpa_order_id,
            "orderItemId": talpa_order_item_id,
        }

        mock_validate_order.return_value = get_validated_order_data(
            talpa_order_id, order.order_items.first().talpa_order_item_id
        )

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        subscription.refresh_from_db()
        subscription_order = subscription.order_items.first().order
        self.assertEqual(str(subscription.talpa_subscription_id), talpa_subscription_id)
        self.assertEqual(str(subscription_order.talpa_order_id), talpa_order_id)
        self.assertEqual(subscription.status, SubscriptionStatus.CANCELLED)
        order.refresh_from_db()
        self.assertEqual(subscription_order, order)
        self.assertEqual(subscription_order.status, OrderStatus.CANCELLED)
        self.assertEqual(permit.status, ParkingPermitStatus.VALID)
        refund = Refund.objects.get(order=order)
        self.assertEqual(refund.order, order)
        self.assertEqual(refund.amount, unit_price)
        self.assertEqual(refund.name, permit.customer.full_name)
        self.assertEqual(refund.status, RefundStatus.OPEN)


@override_settings(
    OIDC_API_TOKEN_AUTH={
        "AUDIENCE": "test_audience",
        "API_SCOPE_PREFIX": "testprefix",
        "ISSUER": "http://localhost/openid",
        "TOKEN_AUTH_REQUIRE_SCOPE_PREFIX": True,
    },
    GDPR_API_QUERY_SCOPE="testprefix.gdprquery",
    GDPR_API_DELETE_SCOPE="testprefix.gdprdelete",
)
class ParkingPermitsGDPRAPIViewTestCase(APITestCase):
    CUSTOMER_SOURCE_ID = "profile-source-id"

    def create_customer(self):
        user = UserFactory()
        customer = CustomerFactory(
            user=user,
            source_system=SourceSystem.HELSINKI_PROFILE,
            source_id=self.CUSTOMER_SOURCE_ID,
        )
        ParkingPermitFactory(
            customer=customer,
            status=ParkingPermitStatus.CLOSED,
            end_time=tz.localtime(datetime.datetime(2020, 2, 1, tzinfo=dt_tz.utc)),
        )
        return customer

    def assert_customer_deleted(self):
        self.assertFalse(
            Customer.objects.filter(source_id=self.CUSTOMER_SOURCE_ID).exists()
        )
        self.assertFalse(ParkingPermit.objects.exists())

    def assert_customer_not_deleted(self):
        self.assertTrue(
            Customer.objects.filter(source_id=self.CUSTOMER_SOURCE_ID).exists()
        )
        self.assertTrue(ParkingPermit.objects.exists())

    def get_auth_header(self, user, scopes, req_mock):
        audience = api_token_auth_settings.AUDIENCE
        issuer = api_token_auth_settings.ISSUER
        auth_field = api_token_auth_settings.API_AUTHORIZATION_FIELD
        config_url = f"{issuer}/.well-known/openid-configuration"
        jwks_url = f"{issuer}/jwks"
        configuration = {
            "issuer": issuer,
            "jwks_uri": jwks_url,
        }
        keys = {"keys": [rsa_key.public_key_jwk]}

        now = datetime.datetime.now()
        expire = now + datetime.timedelta(days=14)
        jwt_data = {
            "iss": issuer,
            "aud": audience,
            "sub": str(user.uuid),
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
            auth_field: scopes,
        }
        encoded_jwt = jwt.encode(
            jwt_data, key=rsa_key.private_key_pem, algorithm=rsa_key.jose_algorithm
        )

        req_mock.get(config_url, json=configuration)
        req_mock.get(jwks_url, json=keys)

        return f"{api_token_auth_settings.AUTH_SCHEME} {encoded_jwt}"

    @requests_mock.Mocker()
    def test_get_profile_should_return_customer_profile_detail(self, req_mock):
        customer = self.create_customer()
        auth_header = self.get_auth_header(
            customer.user, [settings.GDPR_API_QUERY_SCOPE], req_mock
        )
        url = reverse("parking_permits:gdpr_v1", kwargs={"id": customer.source_id})
        self.client.credentials(HTTP_AUTHORIZATION=auth_header)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    @requests_mock.Mocker()
    def test_get_profile_should_be_forbidden_with_wrong_scope(self, req_mock):
        customer = self.create_customer()
        auth_header = self.get_auth_header(
            customer.user, ["testprefix.invalid"], req_mock
        )
        url = reverse("parking_permits:gdpr_v1", kwargs={"id": customer.source_id})
        self.client.credentials(HTTP_AUTHORIZATION=auth_header)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    @requests_mock.Mocker()
    def test_delete_profile_should_delete_profile_and_related_data(self, req_mock):
        with freeze_time(datetime.datetime(2020, 1, 1)):
            customer = self.create_customer()

        with freeze_time(datetime.datetime(2022, 3, 1)):
            auth_header = self.get_auth_header(
                customer.user, [settings.GDPR_API_DELETE_SCOPE], req_mock
            )
            url = reverse("parking_permits:gdpr_v1", kwargs={"id": customer.source_id})
            self.client.credentials(HTTP_AUTHORIZATION=auth_header)
            response = self.client.delete(url)
            self.assertEqual(response.status_code, 204)
            self.assert_customer_deleted()

    @requests_mock.Mocker()
    def test_delete_profile_should_be_forbidden_when_using_wrong_scope(self, req_mock):
        with freeze_time(datetime.datetime(2020, 1, 1)):
            customer = self.create_customer()

        with freeze_time(datetime.datetime(2022, 3, 1)):
            auth_header = self.get_auth_header(
                customer.user, ["testprefix.wrong_scope"], req_mock
            )
            url = reverse("parking_permits:gdpr_v1", kwargs={"id": customer.source_id})
            self.client.credentials(HTTP_AUTHORIZATION=auth_header)
            response = self.client.delete(url)
            self.assertEqual(response.status_code, 403)
            self.assert_customer_not_deleted()

    @requests_mock.Mocker()
    def test_delete_profile_should_be_forbidden_if_customer_cannot_be_deleted(
        self, req_mock
    ):
        with freeze_time(datetime.datetime(2020, 1, 1)):
            customer = self.create_customer()
            ParkingPermitFactory(
                customer=customer,
                status=ParkingPermitStatus.CLOSED,
                end_time=tz.localtime(datetime.datetime(2020, 2, 1, tzinfo=dt_tz.utc)),
            )

        with freeze_time(datetime.datetime(2022, 1, 15)):
            auth_header = self.get_auth_header(
                customer.user, [settings.GDPR_API_DELETE_SCOPE], req_mock
            )
            url = reverse("parking_permits:gdpr_v1", kwargs={"id": customer.source_id})
            self.client.credentials(HTTP_AUTHORIZATION=auth_header)
            with self.assertRaises(DeletionNotAllowed):
                self.client.delete(url)
            self.assert_customer_not_deleted()

    @requests_mock.Mocker()
    def test_delete_profile_should_keep_profile_and_related_data_when_dry_run(
        self, req_mock
    ):
        with freeze_time(datetime.datetime(2020, 1, 1)):
            customer = self.create_customer()
            ParkingPermitFactory(
                customer=customer,
                status=ParkingPermitStatus.CLOSED,
                end_time=tz.localtime(datetime.datetime(2020, 2, 1, tzinfo=dt_tz.utc)),
            )

        with freeze_time(datetime.datetime(2022, 3, 1)):
            auth_header = self.get_auth_header(
                customer.user, [settings.GDPR_API_DELETE_SCOPE], req_mock
            )
            url = reverse("parking_permits:gdpr_v1", kwargs={"id": customer.source_id})
            self.client.credentials(HTTP_AUTHORIZATION=auth_header)
            # make sure we do not deleted the profile when client specify different types of true values
            true_values = ["true", "True", "TRUE", "1", 1, True]
            for true_value in true_values:
                response = self.client.delete(url, data={"dry_run": true_value})
                self.assertEqual(response.status_code, 204)
                self.assert_customer_not_deleted()
