from django.db import models


class EmailLog(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    ]

    task_id = models.CharField(max_length=255, db_index=True, help_text="Associated Celery task ID")
    recipient = models.EmailField(help_text="Recipient email address")
    subject = models.CharField(max_length=255)
    body_snippet = models.TextField(blank=True, default="", help_text="Snippet or content of the email")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Email Log'
        verbose_name_plural = 'Email Logs'

    def __str__(self):
        return f"[{self.status}] {self.recipient} - {self.subject} ({self.task_id[:8]}...)"
