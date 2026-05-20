"""
Send transactional email via SendGrid using project templates.
"""
from __future__ import annotations

from django.conf import settings
from django.template.loader import render_to_string


def send_otp_email(
    *,
    to_email: str,
    otp: str,
    subject: str,
    intro: str,
    recipient_name: str = "",
    heading: str = "Email Verification",
    instruction: str = "Please use the OTP below to verify your email address:",
) -> None:
    if not settings.SENDGRID_API_KEY:
        return

    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    name = (recipient_name or "").strip() or (to_email.split("@", 1)[0] if "@" in to_email else "there")
    otp_minutes = max(1, int(getattr(settings, "OTP_TTL_SECONDS", 600)) // 60)
    site_url = settings.PUBLIC_SITE_URL

    context = {
        "otp": otp,
        "intro": intro,
        "recipient_name": name,
        "otp_minutes": otp_minutes,
        "site_url": site_url,
        "heading": heading,
        "instruction": instruction,
    }
    plain_text = render_to_string("users/emails/otp_email.txt", context)
    html_body = render_to_string("users/emails/otp_email.html", context)

    message = Mail(
        from_email=settings.DEFAULT_FROM_EMAIL,
        to_emails=to_email,
        subject=subject,
        plain_text_content=plain_text,
        html_content=html_body,
    )
    client = SendGridAPIClient(settings.SENDGRID_API_KEY)
    client.send(message)
