import secrets
import resend

from Andromeda.config import settings


VERIFICATION_TOKEN_TTL = 900


def _redis_key(token: str) -> str:
    return f"email_verify:{token}"


async def send_verification_email(user_id: str, email: str, redis_client) -> None:
    token = secrets.token_urlsafe(32)
    await redis_client.setex(_redis_key(token), VERIFICATION_TOKEN_TTL, user_id)

    verify_url = f"{settings.frontend_url}/verify-email?token={token}"

    resend.api_key = settings.resend_api_key
    resend.Emails.send({
        "from": settings.resend_from_email,
        "to": email,
        "subject": "Verify your email address",
        "html": (
            f"<p>Hi,</p>"
            f"<p>Click the link below to verify your email address. "
            f"This link expires in 15 minutes.</p>"
            f"<p><a href=\"{verify_url}\">{verify_url}</a></p>"
            f"<p>If you did not create an account, you can ignore this email.</p>"
        ),
    })


async def consume_verification_token(token: str, redis_client) -> str | None:
    key = _redis_key(token)
    user_id = await redis_client.get(key)
    if user_id:
        await redis_client.delete(key)
    return user_id
