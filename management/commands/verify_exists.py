import os
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from celery import Celery
app = Celery('instascraper.tasks', broker=settings.BROKER_URL)


class Command(BaseCommand):
    help = 'Fires the verify_published_images_exist celery task.'

    def handle(self, *args, **kwargs):
        app.send_task('instascraper.tasks.verify_published_images_exist', args=[], kwargs={})
        print 'instascraper.tasks.verify_published_images_exist fired!'
