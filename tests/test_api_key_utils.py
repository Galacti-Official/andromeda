import pytest

from Andromeda.services.api_key_service import _gen_kid, _gen_secret, _format_key

class TestAPIKeyUtils:
    def test_gen_kid(self):
        kid1 = _gen_kid()
        kid2 = _gen_kid()
        assert isinstance(kid1, str)
        assert isinstance(kid2, str)
        assert kid1 != kid2  # Should be unique
        assert len(kid1) == 22 # Expected length is 22 characters for 16 bytes of data when base64url encoded without padding
        assert len(kid2) == 22

    def test_gen_secret(self):
        secret1 = _gen_secret()
        secret2 = _gen_secret()
        assert isinstance(secret1, str)
        assert isinstance(secret2, str)
        assert secret1 != secret2  # Should be unique
        assert len(secret1) == 43 # Expected length is 43 characters for 32 bytes of data when base64url encoded without padding
        assert len(secret2) == 43

    def test_format_key(self):
        prefix = "sk"
        env = "test"
        kid = _gen_kid()
        secret = _gen_secret()
        formatted = _format_key(prefix=prefix, env=env, kid=kid, secret=secret)
        assert formatted == f"{prefix}_{env}_{kid}_{secret}"
        parts = formatted.split("_")
        assert parts[0] == "sk"
        assert parts[1] == "test"
        assert parts[2] == kid
        assert parts[3] == secret
