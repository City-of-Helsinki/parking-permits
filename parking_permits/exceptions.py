class ParkingPermitBaseError(Exception):
    pass


class ParkingPermitValidationError(ParkingPermitBaseError):
    """
    Base class for expected validation errors, i.e. invalid input or
    a violated business rule, e.g. a vehicle fetched from Traficom that
    doesn't meet the permit requirements.

    These errors are logged without a traceback and are not reported to
    Sentry, as the error type and message are sufficient to identify the
    cause. Integration failures (Talpa, Traficom, DVV, Parkkihubi, ...)
    may inherit from this class only if the failure is already logged as
    an error where it occurs, so that it still gets reported.
    """


class PermitLimitExceededError(ParkingPermitValidationError):
    pass


class DuplicatePermitError(ParkingPermitValidationError):
    pass


class PriceError(ParkingPermitBaseError):
    pass


class InvalidUserAddressError(ParkingPermitValidationError):
    pass


class InvalidContractTypeError(ParkingPermitValidationError):
    pass


class RefundError(ParkingPermitBaseError):
    pass


class NonDraftPermitUpdateError(ParkingPermitValidationError):
    pass


class PermitCanNotBeDeletedError(ParkingPermitValidationError):
    pass


class PermitCanNotBeExtendedError(ParkingPermitValidationError):
    pass


class PermitCanNotBeEndedError(ParkingPermitValidationError):
    pass


class ObjectNotFoundError(ParkingPermitValidationError):
    pass


class CreateTalpaProductError(ParkingPermitBaseError):
    pass


class OrderValidationError(ParkingPermitBaseError):
    pass


class SubscriptionValidationError(ParkingPermitBaseError):
    pass


class OrderCancelError(ParkingPermitBaseError):
    pass


class SubscriptionCancelError(ParkingPermitValidationError):
    pass


class SetTalpaFlowStepsError(ParkingPermitBaseError):
    pass


class OrderCreationFailedError(ParkingPermitBaseError):
    pass


class UpdatePermitError(ParkingPermitValidationError):
    pass


class CreatePermitError(ParkingPermitValidationError):
    pass


class EndPermitError(ParkingPermitValidationError):
    pass


class ProductCatalogError(ParkingPermitBaseError):
    pass


class ParkingZoneError(ParkingPermitValidationError):
    pass


class ParkkihubiPermitError(ParkingPermitBaseError):
    pass


class AddressError(ParkingPermitValidationError):
    pass


class TraficomFetchVehicleError(ParkingPermitValidationError):
    pass


class DVVIntegrationError(ParkingPermitBaseError):
    pass


class SearchError(ParkingPermitValidationError):
    pass


class TemporaryVehicleValidationError(ParkingPermitValidationError):
    pass


class DeletionNotAllowedError(ParkingPermitValidationError):
    pass


class CustomerCannotBeAnonymizedError(ParkingPermitBaseError):
    pass
