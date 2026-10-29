import logging
import base64
from typing import List, Dict, Any, Optional
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from smtplib import SMTPException

logger = logging.getLogger('mailer')


def _prepare_email_message(
    subject: str,
    message: str,
    recipient_list: List[str],
    from_email: Optional[str] = None,
    html_message: Optional[str] = None,
    template_name: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    connection=None
) -> EmailMultiAlternatives:
    """
    Helper to construct an EmailMultiAlternatives instance with HTML support and attachments.
    """
    sender = from_email or settings.DEFAULT_FROM_EMAIL
    body = message or ""
    rendered_html = html_message

    # Render template if provided
    if template_name:
        ctx = context or {}
        ctx.setdefault('subject', subject)
        ctx.setdefault('message', body)
        rendered_html = render_to_string(template_name, ctx)

    email = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=sender,
        to=recipient_list,
        connection=connection
    )

    if rendered_html:
        email.attach_alternative(rendered_html, "text/html")

    # Handle attachments
    if attachments:
        for item in attachments:
            filename = item.get('filename', 'attachment')
            raw_content = item.get('content', '')
            mimetype = item.get('mimetype', 'application/octet-stream')

            # Decode base64 if marked as encoded
            if item.get('is_base64', False) and isinstance(raw_content, str):
                try:
                    content = base64.b64decode(raw_content)
                except Exception as decode_err:
                    logger.warning("Failed to decode base64 attachment %s: %s", filename, decode_err)
                    content = raw_content.encode('utf-8')
            elif isinstance(raw_content, str):
                content = raw_content.encode('utf-8')
            else:
                content = raw_content

            email.attach(filename, content, mimetype)

    return email


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(SMTPException, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
)
def send_email_task(
    self,
    recipient_email: str,
    subject: str,
    message: str,
    html_message: Optional[str] = None,
    template_name: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    from_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Asynchronous task to send an email to a single recipient with retries and logging.
    """
    task_id = self.request.id
    logger.info("[%s] Initiating email task to: %s with subject: '%s'", task_id, recipient_email, subject)

    try:
        email = _prepare_email_message(
            subject=subject,
            message=message,
            recipient_list=[recipient_email],
            from_email=from_email,
            html_message=html_message,
            template_name=template_name,
            context=context,
            attachments=attachments,
        )
        sent_count = email.send(fail_silently=False)

        if sent_count > 0:
            logger.info("[%s] Email successfully sent to %s", task_id, recipient_email)
            return {
                "status": "SUCCESS",
                "task_id": task_id,
                "recipient": recipient_email,
                "subject": subject,
                "sent_count": sent_count,
            }
        else:
            logger.warning("[%s] Email send returned 0 for %s", task_id, recipient_email)
            return {
                "status": "FAILED",
                "task_id": task_id,
                "recipient": recipient_email,
                "error": "Email was not dispatched by backend",
            }

    except Exception as exc:
        logger.error("[%s] Error sending email to %s: %s (attempt %d/%d)",
                     task_id, recipient_email, exc, self.request.retries + 1, self.max_retries)
        # Celery autoretry_for handles retries, but if retries exhausted:
        if self.request.retries >= self.max_retries:
            return {
                "status": "FAILED",
                "task_id": task_id,
                "recipient": recipient_email,
                "error": str(exc),
            }
        raise exc


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    autoretry_for=(SMTPException, ConnectionError, TimeoutError),
    retry_backoff=True,
)
def send_bulk_email_task(
    self,
    recipient_list: List[str],
    subject: str,
    message: str,
    html_message: Optional[str] = None,
    template_name: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    from_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Asynchronous task to send emails in bulk across a recipient list using a shared SMTP connection.
    """
    task_id = self.request.id
    total_recipients = len(recipient_list)
    logger.info("[%s] Initiating bulk email task for %d recipients. Subject: '%s'",
                task_id, total_recipients, subject)

    if not recipient_list:
        return {
            "status": "SUCCESS",
            "task_id": task_id,
            "total_recipients": 0,
            "successful_count": 0,
            "failed_recipients": [],
        }

    successful = []
    failed = []

    try:
        connection = get_connection(fail_silently=False)
        connection.open()

        messages_to_send = []
        for recipient in recipient_list:
            msg = _prepare_email_message(
                subject=subject,
                message=message,
                recipient_list=[recipient],
                from_email=from_email,
                html_message=html_message,
                template_name=template_name,
                context=context,
                attachments=attachments,
                connection=connection,
            )
            messages_to_send.append((recipient, msg))

        for recipient, msg in messages_to_send:
            try:
                msg.send(fail_silently=False)
                successful.append(recipient)
            except Exception as single_err:
                logger.error("[%s] Bulk task: Failed for recipient %s: %s", task_id, recipient, single_err)
                failed.append({"recipient": recipient, "error": str(single_err)})

        connection.close()

        logger.info("[%s] Bulk email task completed. Succeeded: %d, Failed: %d",
                    task_id, len(successful), len(failed))

        return {
            "status": "SUCCESS" if not failed else "PARTIAL_SUCCESS",
            "task_id": task_id,
            "total_recipients": total_recipients,
            "successful_count": len(successful),
            "failed_count": len(failed),
            "successful_recipients": successful,
            "failed_recipients": failed,
        }

    except Exception as exc:
        logger.error("[%s] Bulk email connection failure: %s", task_id, exc)
        if self.request.retries >= self.max_retries:
            return {
                "status": "FAILED",
                "task_id": task_id,
                "total_recipients": total_recipients,
                "error": str(exc),
            }
        raise exc


@shared_task(bind=True)
def send_periodic_digest_task(self, recipient_email: str) -> Dict[str, Any]:
    """
    Scheduled task example for Celery Beat: sends periodic system digests.
    """
    subject = "Scheduled System Digest & Task Summary"
    message = "This is an automated digest sent by Celery Beat periodic scheduler."
    context = {
        "recipient_name": recipient_email.split('@')[0],
        "subject": subject,
        "message": message,
        "details": {
            "Schedule Type": "Periodic (Celery Beat)",
            "Worker Status": "Healthy",
            "Broker": "Redis"
        }
    }
    return send_email_task(
        recipient_email=recipient_email,
        subject=subject,
        message=message,
        template_name="emails/notification.html",
        context=context
    )

