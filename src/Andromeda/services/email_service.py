import secrets
import resend

from datetime import datetime, timezone

from Andromeda.config import settings


VERIFICATION_TOKEN_TTL = 900


def _redis_key(token: str) -> str:
    return f"email_verify:{token}"


async def send_verification_email(user_id: str, email: str, redis_client) -> None:
    token = secrets.token_urlsafe(32)
    await redis_client.setex(_redis_key(token), VERIFICATION_TOKEN_TTL, user_id)

    verify_url = f"{settings.frontend_url}/verify-email?token={token}"

    html = f"""<!DOCTYPE html>
        <html lang="en">
        <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        </head>
        <body style="margin:0;padding:0;background-color:#f4f4f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f5;padding:40px 0;">
            <tr>
            <td align="center">
                <table width="480" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
                <!-- Header -->
                <tr>
                    <td style="background-color:#000000;padding:32px 40px;text-align:center;">
                    <img src="https://cdn.galacti.org/design/logos/classic/galacti.svg" alt="Galacti" height="64" style="display:block;margin:0 auto;" />
                    </td>
                </tr>
                <!-- Body -->
                <tr>
                    <td style="padding:40px 40px 32px;">
                    <h1 style="margin:0 0 12px;font-size:20px;font-weight:600;color:#000000;">Verify your email address</h1>
                    <p style="margin:0 0 24px;font-size:15px;line-height:1.6;color:#52525b;">
                        Thanks for signing up. Click the button below to confirm your email address.
                        This link expires in <strong>15 minutes</strong>.
                    </p>
                    <a href="{verify_url}"
                        style="display:inline-block;background-color:#000000;color:#ffffff;text-decoration:none;font-size:15px;font-weight:500;padding:12px 28px;border-radius:8px;">
                        Verify email
                    </a>
                    </td>
                </tr>
                <!-- Divider -->
                <tr>
                    <td style="padding:0 40px;">
                    <hr style="border:none;border-top:1px solid #e4e4e7;margin:0;" />
                    </td>
                </tr>
                <!-- Footer -->
                <tr>
                    <td style="padding:24px 40px 32px;">
                    <p style="margin:0 0 8px;font-size:13px;color:#a1a1aa;">
                        If the button doesn't work, paste this link into your browser:
                    </p>
                    <p style="margin:0;font-size:13px;color:#a1a1aa;word-break:break-all;">
                        <a href="{verify_url}" style="color:#71717a;">{verify_url}</a>
                    </p>
                    <p style="margin:16px 0 0;font-size:13px;color:#a1a1aa;">
                        If you didn't create an account, you can safely ignore this email.
                    </p>
                    </td>
                </tr>
                </table>
                <table width="480" cellpadding="0" cellspacing="0" style="margin-top:24px;">
                    <tr>
                    <td align="center" style="padding:0 40px;">
                        <p style="margin:0;font-size:12px;line-height:1.6;color:#a1a1aa;">
                        &copy; {datetime.now(timezone.utc).year} Galacti. All rights reserved.
                        </p>
                    </td>
                    </tr>
                </table>
            </td>
            </tr>
        </table>
        </body>
        </html>"""

    resend.api_key = settings.resend_api_key
    resend.Emails.send({
        "from": settings.resend_from_email,
        "to": email,
        "subject": "Verify your email address",
        "html": html,
    })


async def consume_verification_token(token: str, redis_client) -> str | None:
    key = _redis_key(token)
    user_id = await redis_client.get(key)
    if user_id:
        await redis_client.delete(key)
    return user_id
