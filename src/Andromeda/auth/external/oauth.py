import secrets
from Andromeda.api.errors import AndromedaError


async def generate_oauth_state(redis_client) -> str:
    state = secrets.token_urlsafe(32)
    await redis_client.setex(f"oauth_state:{state}", 300, "1")
    return state


async def validate_oauth_state(state: str, redis_client) -> None:
    deleted = await redis_client.delete(f"oauth_state:{state}")
    if not deleted:
        raise AndromedaError(400, "bad_request", "Invalid or expired OAuth state")
