import json
from django.core.management.base import BaseCommand
from django.conf import settings
from django_celery_beat.models import PeriodicTask, CrontabSchedule, IntervalSchedule


class Command(BaseCommand):
    help = "Sets up default Celery Beat periodic tasks (Crontab & Interval schedules) in the database."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Configuring Celery Beat periodic schedules..."))

        # 1. Advanced Crontab Schedule: Every day at 09:00 AM with configured timezone
        crontab_9am, _ = CrontabSchedule.objects.get_or_create(
            minute='0',
            hour='9',
            day_of_week='*',
            day_of_month='*',
            month_of_year='*',
            timezone=settings.TIME_ZONE,
        )

        task_digest, created = PeriodicTask.objects.update_or_create(
            name="Daily Morning System Digest",
            defaults={
                "crontab": crontab_9am,
                "interval": None,
                "task": "mailer.tasks.send_periodic_digest_task",
                "args": json.dumps([settings.DEFAULT_FROM_EMAIL]),
                "enabled": True,
                "description": f"Dispatches a daily digest email every morning at 9:00 AM {settings.TIME_ZONE}.",
            }
        )
        action_digest = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action_digest} periodic task: '{task_digest.name}' (Crontab: 09:00 AM {settings.TIME_ZONE})"))

        # 2. Crontab Schedule: Weekly cleanup on Sunday at 02:00 AM
        crontab_weekly, _ = CrontabSchedule.objects.get_or_create(
            minute='0',
            hour='2',
            day_of_week='0',  # Sunday
            day_of_month='*',
            month_of_year='*',
            timezone=settings.TIME_ZONE,
        )

        task_cleanup, created = PeriodicTask.objects.update_or_create(
            name="Weekly Results Maintenance",
            defaults={
                "crontab": crontab_weekly,
                "interval": None,
                "task": "mailer.tasks.cleanup_old_task_results_task",
                "args": json.dumps([7]),  # Cleanup records older than 7 days
                "enabled": True,
                "description": "Weekly maintenance task to purge stale Celery task results and logs older than 7 days.",
            }
        )
        action_cleanup = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action_cleanup} periodic task: '{task_cleanup.name}' (Crontab: Sunday 02:00 AM)"))

        # 3. Dynamic Interval Schedule: Periodic heartbeat every 1 hour
        interval_1hr, _ = IntervalSchedule.objects.get_or_create(
            every=1,
            period=IntervalSchedule.HOURS
        )

        task_hourly, created = PeriodicTask.objects.update_or_create(
            name="Hourly Task Results Health Check",
            defaults={
                "interval": interval_1hr,
                "crontab": None,
                "task": "mailer.tasks.cleanup_old_task_results_task",
                "args": json.dumps([30]),
                "enabled": False,  # Disabled by default, can be toggled via admin
                "description": "Hourly check for long-term expired task data (toggleable in admin).",
            }
        )
        action_hourly = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action_hourly} periodic task: '{task_hourly.name}' (Interval: Every 1 hour)"))

        self.stdout.write(self.style.SUCCESS("All Celery Beat periodic schedules successfully configured."))

