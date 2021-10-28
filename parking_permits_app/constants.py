from enum import Enum

from django.utils.translation import gettext_lazy as _


class Zone(Enum):
    A = _("A")
    B = _("B")
    C = _("C")
    D = _("D")
    E = _("E")
    F = _("F")
    H = _("H")
    I = _("I")
    J = _("J")
    K = _("K")
    L = _("L")
    M = _("M")
    N = _("N")
    O = _("O")
    P = _("P")


class VehicleCategory(Enum):
    M1 = _("M1")
    M2 = _("M2")
    N1 = _("N1")
    N2 = _("N2")
    L3e = _("L3e")
    L4e = _("L4e")
    L5e = _("L5e")
    L6e = _("L6e")


class ContractType(Enum):
    FIXED_PERIOD = _("FIXED_PERIOD")
    OPEN_ENDED = _("OPEN_ENDED")


class StartType(Enum):
    IMMEDIATELY = _("IMMEDIATELY")
    FROM = _("FROM")


class VehicleType(Enum):
    BENSIN = _("Bensin")
    DIESEL = _("Diesel")
    BIFUEL = _("Bifuel")


class EmissionType(Enum):
    EURO = _("EURO")
    NEDC = _("NEDC")
    WLTP = _("WLTP")


class ParkingPermitStatus(Enum):
    DRAFT = _("DRAFT")
    PROCESSING = _("PROCESSING")
    VALID = _("VALID")
    CANCELLED = _("CANCELLED")
    EXPIRED = _("EXPIRED")


LOW_EMISSION_DISCOUNT = 50
SECONDARY_VEHICLE_PRICE_INCREASE = 50
VAT_PERCENTAGE = 24
