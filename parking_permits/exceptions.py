class ParkingPermitBaseError(Exception):
    pass


class PermitLimitExceededError(ParkingPermitBaseError):
    pass


class DuplicatePermitError(ParkingPermitBaseError):
    pass


class PriceError(ParkingPermitBaseError):
    pass


class InvalidUserAddressError(ParkingPermitBaseError):
    pass


class InvalidContractTypeError(ParkingPermitBaseError):
    pass


class RefundError(ParkingPermitBaseError):
    pass


class NonDraftPermitUpdateError(ParkingPermitBaseError):
    pass


class PermitCanNotBeDeletedError(ParkingPermitBaseError):
    pass


class PermitCanNotBeExtendedError(ParkingPermitBaseError):
    pass


class PermitCanNotBeEndedError(ParkingPermitBaseError):
    pass


class ObjectNotFoundError(ParkingPermitBaseError):
    pass


class CreateTalpaProductError(ParkingPermitBaseError):
    pass


class OrderValidationError(ParkingPermitBaseError):
    pass


class SubscriptionValidationError(ParkingPermitBaseError):
    pass


class OrderCancelError(ParkingPermitBaseError):
    pass


class SubscriptionCancelError(ParkingPermitBaseError):
    pass


class SetTalpaFlowStepsError(ParkingPermitBaseError):
    pass


class OrderCreationFailedError(ParkingPermitBaseError):
    pass


class UpdatePermitError(ParkingPermitBaseError):
    pass


class CreatePermitError(ParkingPermitBaseError):
    pass


class EndPermitError(ParkingPermitBaseError):
    pass


class ProductCatalogError(ParkingPermitBaseError):
    pass


class ParkingZoneError(ParkingPermitBaseError):
    pass


class ParkkihubiPermitError(ParkingPermitBaseError):
    pass


class AddressError(ParkingPermitBaseError):
    pass


class TraficomFetchVehicleError(ParkingPermitBaseError):
    pass


class DVVIntegrationError(ParkingPermitBaseError):
    pass


class SearchError(ParkingPermitBaseError):
    pass


class TemporaryVehicleValidationError(ParkingPermitBaseError):
    pass


class DeletionNotAllowedError(ParkingPermitBaseError):
    pass
