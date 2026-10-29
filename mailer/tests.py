from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.core import mail

from mailer.tasks import send_email_task, send_bulk_email_task


class EmailTasksTestCase(TestCase):
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_email_task_success(self):
        """Test single email task using locmem backend."""
        result = send_email_task(
            recipient_email="user@test.com",
            subject="Test Subject",
            message="Test Message Content"
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Test Subject")
        self.assertEqual(mail.outbox[0].to, ["user@test.com"])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_email_task_with_template_and_attachments(self):
        """Test single email task with HTML template rendering and attachments."""
        result = send_email_task(
            recipient_email="welcome@test.com",
            subject="Welcome!",
            message="Welcome aboard",
            template_name="emails/welcome.html",
            context={"name": "Alice"},
            attachments=[{
                "filename": "hello.txt",
                "content": "Hello World Attachment",
                "mimetype": "text/plain"
            }]
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(len(sent.alternatives), 1)
        self.assertEqual(sent.alternatives[0][1], "text/html")
        self.assertIn("Hello Alice", sent.alternatives[0][0])
        self.assertEqual(len(sent.attachments), 1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_bulk_email_task_success(self):
        """Test bulk email task with multiple recipients."""
        recipients = ["one@test.com", "two@test.com", "three@test.com"]
        result = send_bulk_email_task(
            recipient_list=recipients,
            subject="Bulk Announcement",
            message="Message for everyone"
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["total_recipients"], 3)
        self.assertEqual(result["successful_count"], 3)
        self.assertEqual(len(mail.outbox), 3)


class EmailAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('mailer.views.send_email_task.delay')
    def test_send_single_email_api_success(self, mock_delay):
        mock_task = MagicMock()
        mock_task.id = 'task-uuid-1234'
        mock_delay.return_value = mock_task

        payload = {
            "recipient": "single@test.com",
            "subject": "Hello via API",
            "message": "Testing single API send",
            "template": "welcome"
        }

        response = self.client.post(reverse('send-email'), data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["status"], "QUEUED")
        self.assertEqual(response.data["task_id"], "task-uuid-1234")
        self.assertEqual(response.data["mode"], "single")
        mock_delay.assert_called_once()

    @patch('mailer.views.send_bulk_email_task.delay')
    def test_send_bulk_email_api_success(self, mock_delay):
        mock_task = MagicMock()
        mock_task.id = 'bulk-task-uuid-5678'
        mock_delay.return_value = mock_task

        payload = {
            "recipients": ["user1@test.com", "user2@test.com"],
            "subject": "Bulk API Notification",
            "message": "Testing bulk API send"
        }

        response = self.client.post(reverse('send-email'), data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["status"], "QUEUED")
        self.assertEqual(response.data["mode"], "bulk")
        mock_delay.assert_called_once()

    def test_send_email_api_validation_failure(self):
        # Missing recipient and recipients
        payload = {
            "subject": "No Recipient",
            "message": "Should fail validation"
        }
        response = self.client.post(reverse('send-email'), data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["status"], "ERROR")

    def test_get_email_status_endpoint(self):
        task_id = "test-task-999"
        url = reverse('email-status', kwargs={'task_id': task_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["task_id"], task_id)
        self.assertIn("status", response.data)
