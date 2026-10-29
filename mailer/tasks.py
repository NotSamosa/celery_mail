import logging
import base64
from typing import List, Dict, Any, Optional
from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils import timezone
from smtplib import SMTPException

from .models import EmailLog

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

    if attachments:
        for item in attachments:
            filename = item.get('filename', 'attachment')
            raw_content = item.get('content', '')
            mimetype = item.get('mimetype', 'application/octet-stream')

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
    Asynchronous task to send an email to a single recipient with retries, database logging, and error tracking.
    """
    task_id = self.request.id or 'sync-call'
    logger.info("[%s] Initiating email task to: %s with subject: '%s'", task_id, recipient_email, subject)

    # Record initial pending log in database
    log_entry, _ = EmailLog.objects.get_or_create(
        task_id=task_id,
        recipient=recipient_email,
        defaults={'subject': subject, 'body_snippet': message[:200], 'status': 'PENDING'}
    )

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
            log_entry.status = 'SUCCESS'
            log_entry.sent_at = timezone.now()
            log_entry.error_message = None
            log_entry.save(update_fields=['status', 'sent_at', 'error_message'])

            return {
                "status": "SUCCESS",
                "task_id": task_id,
                "recipient": recipient_email,
                "subject": subject,
                "sent_count": sent_count,
            }
        else:
            err_msg = "Email backend returned 0 dispatched messages"
            logger.warning("[%s] %s for %s", task_id, err_msg, recipient_email)
            log_entry.status = 'FAILED'
            log_entry.error_message = err_msg
            log_entry.save(update_fields=['status', 'error_message'])

            return {
                "status": "FAILED",
                "task_id": task_id,
                "recipient": recipient_email,
                "error": err_msg,
            }

    except Exception as exc:
        logger.error("[%s] Error sending email to %s: %s (attempt %d/%d)",
                     task_id, recipient_email, exc, self.request.retries + 1, self.max_retries)
        log_entry.status = 'FAILED'
        log_entry.error_message = str(exc)
        log_entry.save(update_fields=['status', 'error_message'])

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
    task_id = self.request.id or 'sync-bulk'
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

        for recipient in recipient_list:
            log_entry = EmailLog.objects.create(
                task_id=task_id,
                recipient=recipient,
                subject=subject,
                body_snippet=message[:200],
                status='PENDING'
            )
            try:
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
                msg.send(fail_silently=False)
                successful.append(recipient)
                log_entry.status = 'SUCCESS'
                log_entry.sent_at = timezone.now()
                log_entry.save(update_fields=['status', 'sent_at'])
            except Exception as single_err:
                logger.error("[%s] Bulk task: Failed for recipient %s: %s", task_id, recipient, single_err)
                failed.append({"recipient": recipient, "error": str(single_err)})
                log_entry.status = 'FAILED'
                log_entry.error_message = str(single_err)
                log_entry.save(update_fields=['status', 'error_message'])

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


# ==============================================================================
# Periodic Tasks (Celery Beat)
# ==============================================================================

@shared_task(name="mailer.tasks.send_periodic_digest_task")
def send_periodic_digest_task(recipient_email: Optional[str] = None) -> Dict[str, Any]:
    """
    Scheduled periodic task: Dispatches automated system digest emails based on crontab schedules.
    """
    target = recipient_email or settings.DEFAULT_FROM_EMAIL
    current_time_str = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M:%S %Z')
    subject = f"Periodic System Digest - {current_time_str}"
    message = (
        f"Automated digest report executed by Celery Beat scheduler.\n"
        f"Server Timestamp: {current_time_str}\n"
        f"Timezone: {settings.TIME_ZONE}\n"
        f"System Status: All Celery workers operational."
    )
    context = {
        "recipient_name": target.split('@')[0],
        "subject": subject,
        "message": message,
        "details": {
            "Execution Time": current_time_str,
            "Scheduler": "Celery Beat (DatabaseScheduler)",
            "Timezone": settings.TIME_ZONE,
            "Total Emails Sent Today": EmailLog.objects.filter(
                created_at__date=timezone.localdate()
            ).count()
        }
    }

    return send_email_task(
        recipient_email=target,
        subject=subject,
        message=message,
        template_name="emails/notification.html",
        context=context
    )


@shared_task(name="mailer.tasks.cleanup_old_task_results_task")
def cleanup_old_task_results_task(days: int = 7) -> Dict[str, Any]:
    """
    Periodic maintenance task: Cleans up TaskResult records older than specified days.
    """
    cutoff = timezone.now() - timedelta(days=days)
    try:
        from django_celery_results.models import TaskResult
        deleted_results, _ = TaskResult.objects.filter(date_done__lt=cutoff).delete()
    except Exception as e:
        deleted_results = 0
        logger.warning("Could not delete from TaskResult: %s", e)

    deleted_logs, _ = EmailLog.objects.filter(created_at__lt=cutoff).delete()
    logger.info("Maintenance cleanup finished: %d old task results and %d email logs removed",
                deleted_results, deleted_logs)

    return {
        "status": "SUCCESS",
        "deleted_task_results": deleted_results,
        "deleted_email_logs": deleted_logs,
        "cutoff": cutoff.isoformat(),
    }
