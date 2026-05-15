import pytest
from common.exceptions import (
    KBException,
    ConstraintExtractError,
    NoHitError,
    ConstraintConflictError,
    StorageUnavailable,
    InferenceUnavailable,
)


def test_kb_exception_is_base():
    exc = KBException("something went wrong")
    assert isinstance(exc, Exception)
    assert exc.code == 50000
    assert "something went wrong" in str(exc)


def test_constraint_extract_error_code():
    exc = ConstraintExtractError("cannot extract chip")
    assert exc.code == 40001
    assert isinstance(exc, KBException)


def test_no_hit_error_code():
    exc = NoHitError("no documents matched")
    assert exc.code == 40002
    assert isinstance(exc, KBException)


def test_constraint_conflict_error_code():
    exc = ConstraintConflictError("chip conflict: Jetson vs RK3588")
    assert exc.code == 40003
    assert isinstance(exc, KBException)


def test_storage_unavailable_code():
    exc = StorageUnavailable("postgres is down")
    assert exc.code == 50001
    assert isinstance(exc, KBException)


def test_inference_unavailable_code():
    exc = InferenceUnavailable("embedding service unreachable")
    assert exc.code == 50002
    assert isinstance(exc, KBException)


def test_exceptions_are_catchable_as_kb_exception():
    for cls, code in [
        (ConstraintExtractError, 40001),
        (NoHitError, 40002),
        (ConstraintConflictError, 40003),
        (StorageUnavailable, 50001),
        (InferenceUnavailable, 50002),
    ]:
        with pytest.raises(KBException) as exc_info:
            raise cls("test message")
        assert exc_info.value.code == code


def test_exception_message_preserved():
    msg = "RK3588S chip constraint failed to parse"
    exc = ConstraintExtractError(msg)
    assert msg in str(exc)


def test_kb_exception_custom_code():
    exc = KBException("custom error", code=99999)
    assert exc.code == 99999
