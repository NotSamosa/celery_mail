# Django Celery Email Service with Redis & Celery Beat

A production-ready asynchronous task processing system built with **Django 6**, **Celery 5**, **Redis**, and **Celery Beat**. This service handles background email dispatching, batch bulk sending, HTML templates, file attachments, and periodic task execution with comprehensive admin monitoring.

---

## 🌟 Key Features

1. **Celery & Redis Integration**:
   - Redis as message broker (`redis://127.0.0.1:6379/0`).
   - `django-celery-results` for task result persistence.
   - Task error handling with exponential backoff and automatic retry policies.
2. **Email Capabilities**:
   - Gmail SMTP integration with app-specific password support.
   - Single email task (`send_email_task`) with error logging.
   - Bulk email task (`send_bulk_email_task`) using shared SMTP connection pooling and isolated failure handling.
   - Responsive HTML templates (`base_email.html`, `welcome.html`, `notification.html`).
   - Attachment support (text, binary, or Base64).
3. **REST API & Interactive UI**:
   - `POST /api/send-email/`: Asynchronously triggers email sending and returns `task_id`.
   - `GET /api/email-status/<task_id>/`: Real-time task execution polling.
   - Interactive testing UI at `/` with live polling status bars and JSON inspector.
4. **Periodic Tasks & Scheduling**:
   - Celery Beat database scheduler (`django-celery-beat`).
   - Crontab schedules with timezone support (`Asia/Kolkata`).
   - Dynamic schedule management via management command and Django Admin.
5. **Monitoring & Management**:
   - `EmailLog` database tracking with color-coded status badges in Django Admin.
   - One-click admin retry action for failed emails.

---

## 📁 Project Architecture

```
celery_email_service/
├── celery_email_service/
│   ├── __init__.py          # Celery app export
│   ├── celery.py            # Celery instance configuration & autodiscovery
│   ├── settings.py          # Django, SMTP, Celery, and Beat settings
│   ├── urls.py              # Root routing
│   └── wsgi.py
├── mailer/
│   ├── admin.py             # EmailLog admin with status badges & retry action
│   ├── models.py            # EmailLog tracking model
│   ├── serializers.py       # DRF serializers for email validation
│   ├── tasks.py             # Asynchronous and periodic Celery tasks
│   ├── urls.py              # API and UI routing
│   ├── views.py             # SendEmailAPIView & EmailStatusAPIView
│   ├── management/commands/
│   │   └── setup_periodic_tasks.py  # Dynamic scheduler setup command
│   └── tests.py             # Comprehensive test suite (9 test cases)
├── templates/
│   ├── emails/              # HTML email templates
│   │   ├── base_email.html
│   │   ├── welcome.html
│   │   └── notification.html
│   └── mailer/
│       └── index.html       # Interactive web UI tester
├── .env.example             # Configuration template
├── manage.py
└── requirements.txt
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
Ensure **Redis** is installed and running:
```bash
redis-cli ping
# Expected output: PONG
```

### 2. Environment Configuration
Create `.env` file based on `.env.example`:
```bash
cp .env.example .env
```
Edit `.env` to configure your Gmail SMTP credentials:
```ini
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_16_digit_gmail_app_password
DEFAULT_FROM_EMAIL=your_email@gmail.com
```

### 3. Run Migrations & Setup Periodic Tasks
```bash
# Run database migrations
./venv/bin/python manage.py migrate

# Seed Celery Beat periodic tasks into the database
./venv/bin/python manage.py setup_periodic_tasks
```

Default admin credentials created:
- **Username**: `admin`
- **Password**: `admin123`
- **Admin URL**: `http://127.0.0.1:8000/admin/`

---

## 🏃 Running the Application Services

Open three terminal tabs to run the services:

### Terminal 1: Django Web Server
```bash
./venv/bin/python manage.py runserver
```

### Terminal 2: Celery Worker
```bash
./venv/bin/celery -A celery_email_service worker -l info
```

### Terminal 3: Celery Beat Scheduler
```bash
./venv/bin/celery -A celery_email_service beat -l info -S django_celery_beat.schedulers:DatabaseScheduler
```

---

## 📡 API Reference & Examples

### 1. Send Single Email (with HTML Template)
**Endpoint**: `POST /api/send-email/`

```bash
curl -X POST http://127.0.0.1:8000/api/send-email/ \
  -H "Content-Type: application/json" \
  -d '{
    "recipient": "user@example.com",
    "subject": "Welcome to our Service",
    "template": "welcome",
    "context": {
      "name": "Jane Doe",
      "action_url": "https://example.com/start"
    }
  }'
```

**Response (HTTP 202 Accepted)**:
```json
{
  "status": "QUEUED",
  "message": "Email task has been successfully queued for asynchronous processing.",
  "task_id": "893c5d7a-d021-4d3f-9ec6-8964722881bb",
  "mode": "single",
  "recipients": "user@example.com",
  "status_url": "/api/email-status/893c5d7a-d021-4d3f-9ec6-8964722881bb/"
}
```

---

### 2. Send Bulk Email
**Endpoint**: `POST /api/send-email/`

```bash
curl -X POST http://127.0.0.1:8000/api/send-email/ \
  -H "Content-Type: application/json" \
  -d '{
    "recipients": ["client1@example.com", "client2@example.com"],
    "subject": "Scheduled Maintenance Notice",
    "template": "notification",
    "context": {
      "recipient_name": "Valued Customer",
      "details": {
        "Window": "Saturday 02:00 - 04:00 AM",
        "Impact": "Minimal disruption expected"
      }
    }
  }'
```

---

### 3. Send Email with Attachment
**Endpoint**: `POST /api/send-email/`

```bash
curl -X POST http://127.0.0.1:8000/api/send-email/ \
  -H "Content-Type: application/json" \
  -d '{
    "recipient": "audit@example.com",
    "subject": "System Report",
    "message": "Attached is the requested system report.",
    "attachments": [
      {
        "filename": "report.txt",
        "content": "Report metrics: 100% operational.",
        "mimetype": "text/plain"
      }
    ]
  }'
```

---

### 4. Check Task Status
**Endpoint**: `GET /api/email-status/<task_id>/`

```bash
curl http://127.0.0.1:8000/api/email-status/893c5d7a-d021-4d3f-9ec6-8964722881bb/
```

**Response (In-Progress)**:
```json
{
  "task_id": "893c5d7a-d021-4d3f-9ec6-8964722881bb",
  "status": "PENDING",
  "ready": false,
  "successful": false,
  "result": null,
  "error": null
}
```

**Response (Completed)**:
```json
{
  "task_id": "893c5d7a-d021-4d3f-9ec6-8964722881bb",
  "status": "SUCCESS",
  "ready": true,
  "successful": true,
  "result": {
    "status": "SUCCESS",
    "task_id": "893c5d7a-d021-4d3f-9ec6-8964722881bb",
    "recipient": "user@example.com",
    "subject": "Welcome to our Service",
    "sent_count": 1
  },
  "error": null
}
```

---

## ⏰ Celery Beat Periodic Scheduling

The project is configured with both static settings schedules and database-backed dynamic schedules:

| Task Name | Schedule | Timezone | Description |
|-----------|----------|----------|-------------|
| `Daily Morning System Digest` | Crontab: `0 9 * * *` (09:00 AM) | `Asia/Kolkata` | Sends automated system digest emails |
| `Weekly Results Maintenance` | Crontab: `0 2 * * 0` (Sunday 02:00 AM) | `Asia/Kolkata` | Purges expired task records and logs older than 7 days |
| `Hourly Task Results Health Check` | Interval: Every 1 hour | System default | Periodic health verification (toggleable in admin) |

Schedules can be modified dynamically at runtime without server restarts in the Django Admin interface under **Periodic Tasks** (`/admin/django_celery_beat/periodictask/`).

---

## 🧪 Running Automated Tests

Run the full test suite verifying single tasks, bulk dispatching, template rendering, attachments, API endpoints, and periodic tasks:

```bash
./venv/bin/python manage.py test mailer
```

**Result**:
```
Found 9 test(s).
Creating test database for alias 'default'...
System check identified no issues (0 silenced).
.........
----------------------------------------------------------------------
Ran 9 tests in 0.035s

OK
Destroying test database for alias 'default'...
```

