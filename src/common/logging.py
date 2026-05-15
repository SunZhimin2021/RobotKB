from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pythonjsonlogger import json as jsonlogger
from pydantic import BaseModel, Field


def _build_json_handler() -> logging.StreamHandler:
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)
    return handler


_root_logger = logging.getLogger("robotkb")
if not _root_logger.handlers:
    _root_logger.addHandler(_build_json_handler())
    _root_logger.setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class AuditRecord(BaseModel):
    operator: str
    action: str
    object_type: str
    object_id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def audit_log(
    operator: str,
    action: str,
    object_type: str,
    object_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    rec = AuditRecord(
        operator=operator,
        action=action,
        object_type=object_type,
        object_id=object_id,
        before=before,
        after=after,
    )
    log = get_logger("robotkb.audit")
    log.info(
        rec.model_dump_json(),
        extra={
            "operator": rec.operator,
            "action": rec.action,
            "object_type": rec.object_type,
            "object_id": rec.object_id,
        },
    )
