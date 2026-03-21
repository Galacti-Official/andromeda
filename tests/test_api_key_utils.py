import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from Andromeda.services.api_key_service import gen_kid, gen_secret, format_key

class TestAPIKeyUtils:
    def test_gen_kid(self):
        kid1 = gen_kid()
        kid2 = gen_kid()
        assert isinstance(kid1, str)
        assert isinstance(kid2, str)
        assert kid1 != kid2  # Should be unique
        assert len(kid1) == 22 # Expected length is 22 characters for 16 bytes of data when base64url encoded without padding
        assert len(kid2) == 22

    def test_gen_secret(self):
        secret1 = gen_secret()
        secret2 = gen_secret()
        assert isinstance(secret1, str)
        assert isinstance(secret2, str)
        assert secret1 != secret2  # Should be unique
        assert len(secret1) == 43 # Expected length is 43 characters for 32 bytes of data when base64url encoded without padding
        assert len(secret2) == 43

    def test_format_key(self):
        prefix = "sk"
        env = "test"
        kid = gen_kid()
        secret = gen_secret()
        formatted = format_key(prefix=prefix, env=env, kid=kid, secret=secret)
        assert formatted == f"{prefix}.{env}.{kid}.{secret}"
        parts = formatted.split(".")
        assert parts[0] == "sk"
        assert parts[1] == "test"
        assert parts[2] == kid
        assert parts[3] == secret
