import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
 
from Andromeda.services.status_service import _worst_status
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
        # No services in the database — treated as operational
        assert _worst_status([]) == ServiceStatus.operational
 
    def test_all_statuses_present(self):
        # Worst should always win regardless of list order
        statuses = [
            ServiceStatus.operational,
            ServiceStatus.degraded,
            ServiceStatus.partial_outage,
            ServiceStatus.major_outage,
        ]
        assert _worst_status(statuses) == ServiceStatus.major_outage
