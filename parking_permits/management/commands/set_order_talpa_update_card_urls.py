from django.core.management.base import BaseCommand

from parking_permits.models import Order
from parking_permits.models.order import OrderStatus


class Command(BaseCommand):
    help = "Fetch missing Talpa update card URL for orders."

    def handle(self, *args, **kwargs):
        """Only handle CONFIRMED orders."""
        orders = (
            Order.objects.filter(
                status=OrderStatus.CONFIRMED,
                talpa_update_card_url="",
            )
            .exclude(talpa_receipt_url="")
            .distinct()
        )

        if num_orders := orders.count():
            self.stdout.write(f"Orders missing update card url: {num_orders}")
            Order.objects.bulk_update(
                self._set_update_card_urls(orders),
                fields=["talpa_update_card_url"],
            )

        else:
            self.stdout.write("No orders to update")

    def _set_update_card_urls(self, orders):
        """URL can be parsed from receipt URL:

        e.g.: /{ORDERID}/receipt?user={USERID}
        result: /{ORDERID}/update-card?user={USERID}
        """

        for order in orders:
            order.talpa_update_card_url = order.talpa_receipt_url.replace(
                "/receipt?", "/update-card?"
            )
            yield order
