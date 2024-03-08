import dataclasses
from decimal import Decimal

from parking_permits.utils import calc_vat_price, format_currency, quantize


@dataclasses.dataclass(frozen=True)
class Pricing:
    gross: Decimal = Decimal(0)
    net: Decimal = Decimal(0)
    vat: Decimal = Decimal(0)

    def __add__(self, other):
        return self.__class__(
            gross=self.gross + other.gross,
            net=self.net + other.net,
            vat=self.vat + other.vat,
        )

    @classmethod
    def calculate(cls, gross_price, vat_rate):
        """
        Calculates the VAT and net prices, returning the correctly rounded values:

            1. Calculates the VAT price from the gross.
            2. Rounds up values of gross and VAT price.
            3. Subtracts gross-VAT to provide Net price.
            4. Converts all 3 to string values.
            5. Converts VAT to string value.
        """
        vat_price = calc_vat_price(gross_price, vat_rate)

        gross_price = quantize(gross_price)
        vat_price = quantize(vat_price)

        net_price = gross_price - vat_price

        return cls(gross=gross_price, net=net_price, vat=vat_price)

    def format_gross(self):
        return format_currency(self.gross)

    def format_net(self):
        return format_currency(self.net)

    def format_vat(self):
        return format_currency(self.vat)
