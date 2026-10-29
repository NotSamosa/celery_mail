import logging
from celery.result import AsyncResult
from django.shortcuts import render
from django.views import View
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django_celery_results.models import TaskResult

from .serializers import SendEmailSerializer
from .tasks import send_email_task, send_bulk_email_task

logger = logging.getLogger('mailer')


class SendEmailAPIView(APIView):
    """
    POST /api/send-email/
    Triggers asynchronous email delivery in the background via Celery.
    Accepts single recipient or list of recipients, plain text or HTML templates, and optional attachments.
    """

    def post(self, request, *args, **kwargs):
        serializer = SendEmailSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": "ERROR", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data
        subject = data['subject']
        message = data.get('message', '')
        html_message = data.get('html_message')
        template_name = data.get('template_name')
        context = data.get('context', {})
        attachments = data.get('attachments', [])

        recipients = data.get('recipients')
        single_recipient = data.get('recipient')

        # Determine single vs bulk dispatch
        if recipients and len(recipients) > 1:
            task = send_bulk_email_task.delay(
                recipient_list=recipients,
                subject=subject,
                message=message,
                html_message=html_message,
                template_name=template_name,
                context=context,
                attachments=attachments,
            )
            mode = "bulk"
            recipient_info = recipients
        else:
            target_recipient = single_recipient or recipients[0]
            task = send_email_task.delay(
                recipient_email=target_recipient,
                subject=subject,
                message=message,
                html_message=html_message,
                template_name=template_name,
                context=context,
                attachments=attachments,
            )
            mode = "single"
            recipient_info = target_recipient

        logger.info("Queued Celery email task [%s] (mode=%s)", task.id, mode)

        return Response(
            {
                "status": "QUEUED",
                "message": "Email task has been successfully queued for asynchronous processing.",
                "task_id": task.id,
                "mode": mode,
                "recipients": recipient_info,
                "status_url": f"/api/email-status/{task.id}/"
            },
            status=status.HTTP_202_ACCEPTED
        )


class EmailStatusAPIView(APIView):
    """
    GET /api/email-status/<task_id>/
    Queries Celery result backend for the live status of an asynchronous email task.
    """

    def get(self, request, task_id, *args, **kwargs):
        result = AsyncResult(task_id)

        response_payload = {
            "task_id": task_id,
            "status": result.status,
            "ready": result.ready(),
            "successful": False,
            "result": None,
            "error": None,
        }

        if result.ready():
            if result.successful():
                response_payload["successful"] = True
                response_payload["result"] = result.result
            else:
                response_payload["error"] = str(result.result)
        else:
            # Check if recorded in django-celery-results database
            try:
                task_record = TaskResult.objects.filter(task_id=task_id).first()
                if task_record:
                    response_payload["status"] = task_record.status
                    if task_record.status == 'SUCCESS':
                        response_payload["ready"] = True
                        response_payload["successful"] = True
                        response_payload["result"] = task_record.result
                    elif task_record.status == 'FAILURE':
                        response_payload["ready"] = True
                        response_payload["error"] = task_record.traceback or "Task failed"
            except Exception as e:
                logger.debug("Database check for task %s exception: %s", task_id, e)

        return Response(response_payload, status=status.HTTP_200_OK)


class EmailDemoUIView(View):
    """
    Interactive web UI to test and demonstrate asynchronous email sending with live status polling.
    """

    def get(self, request, *args, **kwargs):
        return render(request, 'mailer/index.html')
