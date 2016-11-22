import os
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from celery import Celery
app = Celery('instascraper.tasks', broker=settings.BROKER_URL)


class Command(BaseCommand):
    help = 'Fires the update_published_image_like_count celery task.'

    def handle(self, *args, **kwargs):
        app.send_task('instascraper.tasks.update_published_image_like_count',
                        args=[], kwargs={})
        print 'instascraper.tasks.update_published_image_like_count fired!'
