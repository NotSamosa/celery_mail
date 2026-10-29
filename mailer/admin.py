from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import EmailLog
from .tasks import send_email_task


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'subject', 'status_badge', 'short_task_id', 'created_at', 'sent_at')
    list_filter = ('status', 'created_at')
    search_fields = ('recipient', 'subject', 'task_id', 'error_message')
    readonly_fields = ('task_id', 'recipient', 'subject', 'body_snippet', 'status', 'error_message', 'created_at', 'sent_at')
    actions = ['retry_failed_emails']

    def status_badge(self, obj):
        colors = {
            'SUCCESS': '#10b981',  # green
            'FAILED': '#ef4444',   # red
            'PENDING': '#f59e0b',  # amber
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 12px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.status
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'

    def short_task_id(self, obj):
        if not obj.task_id:
            return '-'
        return format_html('<code title="{}">{}...</code>', obj.task_id, obj.task_id[:8])
    short_task_id.short_description = 'Task ID'

    @admin.action(description="Retry selected failed emails via Celery background task")
    def retry_failed_emails(self, request, queryset):
        retried_count = 0
        for log_entry in queryset.filter(status='FAILED'):
            task = send_email_task.delay(
                recipient_email=log_entry.recipient,
                subject=log_entry.subject,
                message=log_entry.body_snippet or "Retried from Django admin"
            )
            log_entry.task_id = task.id
            log_entry.status = 'PENDING'
            log_entry.error_message = None
            log_entry.save(update_fields=['task_id', 'status', 'error_message'])
            retried_count += 1

        self.message_user(request, f"Successfully queued {retried_count} failed email(s) for background retry.")
