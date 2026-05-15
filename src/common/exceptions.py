class KBException(Exception):
    def __init__(self, message: str, code: int = 50000):
        super().__init__(message)
        self.code = code


class ConstraintExtractError(KBException):
    def __init__(self, message: str):
        super().__init__(message, code=40001)


class NoHitError(KBException):
    def __init__(self, message: str):
        super().__init__(message, code=40002)


class ConstraintConflictError(KBException):
    def __init__(self, message: str):
        super().__init__(message, code=40003)


class StorageUnavailable(KBException):
    def __init__(self, message: str):
        super().__init__(message, code=50001)


class InferenceUnavailable(KBException):
    def __init__(self, message: str):
        super().__init__(message, code=50002)
