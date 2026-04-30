import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import Andromeda.services.status_service as svc
from Andromeda.services.status_service import _worst_status, invalidate_cache, get_status
from Andromeda.models.status import ServiceStatus


class TestWorstStatus:
    def test_single_operational(self):
        assert _worst_status([ServiceStatus.operational]) == ServiceStatus.operational

    def test_single_major_outage(self):
        assert _worst_status([ServiceStatus.major_outage]) == ServiceStatus.major_outage

    def test_priority_major_outage_wins(self):
        statuses = [ServiceStatus.operational, ServiceStatus.degraded, ServiceStatus.major_outage]
        assert _worst_status(statuses) == ServiceStatus.major_outage

    def test_priority_partial_outage_over_degraded(self):
        statuses = [ServiceStatus.degraded, ServiceStatus.partial_outage]
        assert _worst_status(statuses) == ServiceStatus.partial_outage

    def test_priority_degraded_over_operational(self):
        statuses = [ServiceStatus.operational, ServiceStatus.degraded]
        assert _worst_status(statuses) == ServiceStatus.degraded

    def test_empty_list_returns_operational(self):
        assert _worst_status([]) == ServiceStatus.operational

    def test_all_statuses_present(self):
        statuses = [
            ServiceStatus.operational,
            ServiceStatus.degraded,
            ServiceStatus.partial_outage,
            ServiceStatus.major_outage,
        ]
        assert _worst_status(statuses) == ServiceStatus.major_outage


class TestInvalidateCache:
    def setup_method(self):
        svc._cache = None

    def test_clears_populated_cache(self):
        svc._cache = svc._StatusCache(
            response=MagicMock(),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        invalidate_cache()
        assert svc._cache is None

    def test_noop_when_already_empty(self):
        invalidate_cache()
        assert svc._cache is None


class TestGetStatus:
    def setup_method(self):
        svc._cache = None

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self):
        fake_response = MagicMock()
        svc._cache = svc._StatusCache(
            response=fake_response,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        session = AsyncMock()
        result = await get_status(session)
        assert result is fake_response
        session.exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_populates_cache(self):
        fake_response = MagicMock()
        session = AsyncMock()
        with patch.object(svc, "_fetch_status", new=AsyncMock(return_value=fake_response)):
            result = await get_status(session)
        assert result is fake_response
        assert svc._cache is not None
        assert svc._cache.response is fake_response

    @pytest.mark.asyncio
    async def test_expired_cache_refetches(self):
        fake_new = MagicMock()
        svc._cache = svc._StatusCache(
            response=MagicMock(),
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        session = AsyncMock()
        with patch.object(svc, "_fetch_status", new=AsyncMock(return_value=fake_new)):
            result = await get_status(session)
        assert result is fake_new

    @pytest.mark.asyncio
    async def test_invalidate_then_get_refetches(self):
        fake_new = MagicMock()
        svc._cache = svc._StatusCache(
            response=MagicMock(),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        invalidate_cache()
        session = AsyncMock()
        with patch.object(svc, "_fetch_status", new=AsyncMock(return_value=fake_new)):
            result = await get_status(session)
        assert result is fake_new

    @pytest.mark.asyncio
    async def test_concurrent_requests_fetch_once(self):
        fake_response = MagicMock()
        fetch_count = 0

        async def counted_fetch(session):
            nonlocal fetch_count
            fetch_count += 1
            await asyncio.sleep(0)
            return fake_response

        session = AsyncMock()
        with patch.object(svc, "_fetch_status", new=counted_fetch):
            results = await asyncio.gather(
                get_status(session),
                get_status(session),
                get_status(session),
            )

        assert all(r is fake_response for r in results)
        assert fetch_count == 1
