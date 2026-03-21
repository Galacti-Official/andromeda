from datetime import datetime, timedelta, timezone
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

fake_database_module = types.ModuleType("Andromeda.api.database.database")
setattr(fake_database_module, "engine", object())
sys.modules.setdefault("Andromeda.api.database.database", fake_database_module)

from Andromeda.models.status import Service, ServiceStatus
from Andromeda.services import health_service
from Andromeda.services.health_service import CheckResult, _update_service_status, write_daily_uptime


class FrozenDateTime(datetime):
    current = datetime(2026, 3, 21, 0, 2, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        value = cls.current
        if tz is not None:
            return value.astimezone(tz)
        return value.replace(tzinfo=None)


class ExecResult:
    def __init__(self, value):
        self._value = value

    def first(self):
        return self._value


class SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def make_service(status: ServiceStatus, degraded_since: datetime | None = None) -> Service:
    return Service(
        id="api",
        group_id="core",
        name="API",
        status=status,
        degraded_since=degraded_since,
    )


def make_result(healthy: bool) -> CheckResult:
    return CheckResult(
        service_id="api",
        healthy=healthy,
        response_time_ms=100.0,
        status_code=200 if healthy else 503,
        error=None if healthy else "bad gateway",
    )


@pytest.mark.asyncio
async def test_unhealthy_operational_service_becomes_degraded():
    session = MagicMock()
    service = make_service(ServiceStatus.operational)

    with patch.object(health_service, "datetime", FrozenDateTime):
        await _update_service_status(session, service, make_result(False))

    assert service.status == ServiceStatus.degraded
    assert service.degraded_since == FrozenDateTime.current
    session.add.assert_called_once_with(service)


@pytest.mark.asyncio
async def test_unhealthy_degraded_service_escalates_to_partial_outage_after_30_minutes():
    session = MagicMock()
    service = make_service(
        ServiceStatus.degraded,
        degraded_since=FrozenDateTime.current - timedelta(minutes=31),
    )

    with patch.object(health_service, "datetime", FrozenDateTime):
        await _update_service_status(session, service, make_result(False))

    assert service.status == ServiceStatus.partial_outage
    assert service.degraded_since == FrozenDateTime.current - timedelta(minutes=31)
    session.add.assert_called_once_with(service)


@pytest.mark.asyncio
async def test_healthy_service_recovers_to_operational():
    session = MagicMock()
    service = make_service(
        ServiceStatus.degraded,
        degraded_since=FrozenDateTime.current - timedelta(minutes=10),
    )

    with patch.object(health_service, "datetime", FrozenDateTime):
        await _update_service_status(session, service, make_result(True))

    assert service.status == ServiceStatus.operational
    assert service.degraded_since is None
    session.add.assert_called_once_with(service)


@pytest.mark.asyncio
async def test_write_daily_uptime_only_writes_yesterdays_bucket():
    yesterday = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)
    today = datetime(2026, 3, 21, 0, 0, tzinfo=timezone.utc)
    health_service._check_results.clear()
    health_service._check_results.update(
        {
            yesterday: {"api": [True, False]},
            today: {"api": [False]},
        }
    )

    session = MagicMock()
    session.exec = AsyncMock(return_value=ExecResult(None))
    session.commit = AsyncMock()

    with (
        patch.object(health_service, "datetime", FrozenDateTime),
        patch.object(health_service, "AsyncSession", return_value=SessionContext(session)),
    ):
        await write_daily_uptime()

    assert session.add.call_count == 1
    added_row = session.add.call_args.args[0]
    assert added_row.service_id == "api"
    assert added_row.date == yesterday
    assert added_row.uptime == 50.0
    assert yesterday not in health_service._check_results
    assert health_service._check_results[today]["api"] == [False]


@pytest.mark.asyncio
async def test_write_daily_uptime_noops_when_bucket_is_missing():
    health_service._check_results.clear()
    session = MagicMock()
    session.exec = AsyncMock()
    session.commit = AsyncMock()

    with (
        patch.object(health_service, "datetime", FrozenDateTime),
        patch.object(health_service, "AsyncSession", return_value=SessionContext(session)),
    ):
        await write_daily_uptime()

    session.exec.assert_not_called()
    session.commit.assert_not_called()
