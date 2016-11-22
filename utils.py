import datetime
from celery import Celery
from os.path import basename
import urllib2
from boto.s3.key import Key
from sherri_extra.models import s3_connect
from django.conf import settings
import logging
logger = logging.getLogger('instagram')

def send_ig_img_to_s3(remote_path):
    conn = s3_connect()
    bucket = conn.get_bucket(settings.AWS_BUCKET_NAME)
    s3_filepath = 'media/instagram/%s' % basename(remote_path)
    remote_img = urllib2.urlopen(remote_path)
    k = Key(bucket)
    k.key = s3_filepath
    s3_url = None
    saved = None
    exists_in_s3 = bucket.get_key(s3_filepath)
    if not exists_in_s3:
        try: saved = k.set_contents_from_string(remote_img.read())
        except:
            logger.debug('Could not save %s to s3!' % basename(remote_path))
            return None
    elif exists_in_s3 or saved:
        try: s3_url = k.generate_url(expires_in=0, query_auth=False)
        except: logger.debug('Could not generate url for %s in s3!' % basename(remote_path))
    if not s3_url:
        return None
    else:
        return s3_url

app = Celery('instascraper.tasks', broker=settings.BROKER_URL)

QUERY_STATE_COMPLETED = 2

def kickoff_instagram_search(hashtag, start_id=None):
    task_args=[hashtag]
    if start_id:
        task_args.append(start_id)

    hashtag.status = QUERY_STATE_COMPLETED
    hashtag.processing_completed_on = None
    hashtag.task_id = app.send_task('init_instagram_search', args=task_args, kwargs={})
    hashtag.save()
