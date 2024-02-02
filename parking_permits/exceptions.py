class ParkingPermitBaseException(Exception):
    pass


class PermitLimitExceeded(ParkingPermitBaseException):
    pass


class DuplicatePermit(ParkingPermitBaseException):
    pass


class PriceError(ParkingPermitBaseException):
    pass


class InvalidUserAddress(ParkingPermitBaseException):
    pass


class InvalidContractType(ParkingPermitBaseException):
    pass


class RefundError(ParkingPermitBaseException):
    pass


class NonDraftPermitUpdateError(ParkingPermitBaseException):
    pass


class PermitCanNotBeDeleted(ParkingPermitBaseException):
    pass


class PermitCanNotBeExtended(ParkingPermitBaseException):
    pass


class PermitCanNotBeEnded(ParkingPermitBaseException):
    pass


class ObjectNotFound(ParkingPermitBaseException):
    pass


class CreateTalpaProductError(ParkingPermitBaseException):
    pass


class OrderValidationError(ParkingPermitBaseException):
    pass


class SubscriptionValidationError(ParkingPermitBaseException):
    pass


class OrderCancelError(ParkingPermitBaseException):
    pass


class SubscriptionCancelError(ParkingPermitBaseException):
    pass


class SetTalpaFlowStepsError(ParkingPermitBaseException):
    pass


class OrderCreationFailed(ParkingPermitBaseException):
    pass


class UpdatePermitError(ParkingPermitBaseException):
    pass


class CreatePermitError(ParkingPermitBaseException):
    pass


class EndPermitError(ParkingPermitBaseException):
    pass


class ProductCatalogError(ParkingPermitBaseException):
    pass


class ParkingZoneError(ParkingPermitBaseException):
    pass


class ParkkihubiPermitError(ParkingPermitBaseException):
    pass


class AddressError(ParkingPermitBaseException):
    pass


class TraficomFetchVehicleError(ParkingPermitBaseException):
    pass


class DVVIntegrationError(ParkingPermitBaseException):
    pass


class SearchError(ParkingPermitBaseException):
    pass


class TemporaryVehicleValidationError(ParkingPermitBaseException):
    pass


class DeletionNotAllowed(ParkingPermitBaseException):
    pass
