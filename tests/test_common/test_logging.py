import json
import logging
import io
import pytest
from common.logging import get_logger, audit_log, AuditRecord


def capture_json_log(logger_name: str, level=logging.DEBUG):
    """Return (logger, stream) with JSON formatter — read stream.getvalue() after logging."""
    from pythonjsonlogger import json as jsonlogger
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(jsonlogger.JsonFormatter("%(message)s"))
    log = logging.getLogger(logger_name)
    log.handlers.clear()
    log.propagate = False
    log.addHandler(handler)
    log.setLevel(level)
    return log, stream


def test_get_logger_returns_logger():
    log = get_logger("test.module")
    assert isinstance(log, logging.Logger)
    assert log.name == "test.module"


def test_logger_emits_json(monkeypatch):
    log, stream = capture_json_log("robotkb.test_json")
    monkeypatch.setattr("common.logging._root_logger", log)
    get_logger("robotkb.test_json").info("hello world")
    output = stream.getvalue().strip()
    # Should be parseable JSON
    data = json.loads(output)
    assert data.get("message") == "hello world" or "hello world" in str(data)


def test_audit_record_fields():
    rec = AuditRecord(
        operator="test_admin",
        action="delete",
        object_type="document",
        object_id="doc-123",
        before={"status": "published"},
        after=None,
    )
    assert rec.operator == "test_admin"
    assert rec.action == "delete"
    assert rec.object_id == "doc-123"
    assert rec.timestamp is not None


def test_audit_record_timestamp_auto():
    rec = AuditRecord(
        operator="user",
        action="publish",
        object_type="document",
        object_id="doc-456",
    )
    assert rec.timestamp is not None
    assert len(rec.timestamp) > 0


def test_audit_log_produces_structured_output(caplog):
    with caplog.at_level(logging.INFO, logger="robotkb.audit"):
        audit_log(
            operator="test_reviewer",
            action="rollback",
            object_type="document",
            object_id="doc-789",
            before={"version": "v1.2"},
            after={"version": "v1.1"},
        )
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.INFO
    assert "rollback" in record.getMessage() or hasattr(record, "action")


def test_audit_record_serializable():
    rec = AuditRecord(
        operator="admin",
        action="permission_change",
        object_type="user",
        object_id="user-001",
        before={"role": "viewer"},
        after={"role": "reviewer"},
    )
    data = rec.model_dump()
    assert data["operator"] == "admin"
    assert data["before"]["role"] == "viewer"
    assert data["after"]["role"] == "reviewer"
    # Must be JSON-serializable
    json.dumps(data)


def test_get_logger_same_name_returns_same_instance():
    l1 = get_logger("robotkb.shared")
    l2 = get_logger("robotkb.shared")
    assert l1 is l2
