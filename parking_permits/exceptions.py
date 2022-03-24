class ParkingPermitBaseException(Exception):
    pass


class PermitLimitExceeded(ParkingPermitBaseException):
    pass


class PriceError(ParkingPermitBaseException):
    pass


class InvalidUserZone(ParkingPermitBaseException):
    pass


class InvalidContractType(ParkingPermitBaseException):
    pass


class RefundError(ParkingPermitBaseException):
    pass


class NonDraftPermitUpdateError(ParkingPermitBaseException):
    pass


class PermitCanNotBeDelete(ParkingPermitBaseException):
    pass


class PermitCanNotBeEnded(ParkingPermitBaseException):
    pass


class ObjectNotFound(ParkingPermitBaseException):
    pass


class CreateTalpaProductError(ParkingPermitBaseException):
    pass


class OrderCreationFailed(ParkingPermitBaseException):
    pass


class UpdatePermitError(ParkingPermitBaseException):
    pass


class ProductCatalogError(ParkingPermitBaseException):
    pass


class ParkingZoneError(ParkingPermitBaseException):
    pass


class ParkkihubiPermitError(ParkingPermitBaseException):
    pass


class AddressError(ParkingPermitBaseException):
    pass
