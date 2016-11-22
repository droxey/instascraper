from __future__ import absolute_import
from celery import task
import datetime
import logging
import math
import urllib2
import json
import requests

from .utils import send_ig_img_to_s3
from celery import Celery
from django.conf import settings

from instagram.client import InstagramAPI
from instagram.bind import InstagramAPIError
from instagram.models import Media
from instagram import client, subscriptions

from . import app_settings
from .models import InstagramImage, HashtagQuery, QUERY_STATE_NEW, \
QUERY_STATE_PROCESSING, QUERY_STATE_COMPLETED, QUERY_STATE_CANCELLING, \
QUERY_STATE_TERMINATED, QUERY_STATE_NO_RESULTS, QUERY_STATE_END_OF_RESULTS

api = client.InstagramAPI(**app_settings.INSTAGRAM_OAUTH_CONFIG)
app = Celery('instascraper.tasks', broker=settings.BROKER_URL)
logger = logging.getLogger('instagram')


def print_api_exception(method_name, error):
    ''' Provides a DRY way to debug python-instagram API exceptions. '''
    logger.info('Error executing instascraper.tasks.%s: %s' % (method_name, error))
    logger.info("Remaining API Calls: %s/%s" % (api.x_ratelimit_remaining, api.x_ratelimit))


def end_query(hashtag, status=QUERY_STATE_COMPLETED):
    ''' Sets proper flags to notify UI that the query has ended,
    and optionally, in which state it ended.'''
    hashtag.processing_completed_on = datetime.datetime.now()
    hashtag.status = status
    hashtag.task_id = None
    hashtag.save()

def update_likes_for_image(img, media=None):
    ''' Takes in a like count and an optional instagram query result.
    If no Instagram media object exists, query API for the given image. '''
    try:
        likes_api = client.InstagramAPI(**app_settings.INSTAGRAM_LIKES_OAUTH_CONFIG)
        if not media:
            media = likes_api.media(img.instagram_id)
        img.likes = media.like_count
        img.save()
    except InstagramAPIError, e:
        print_api_exception('update_likes_for_image', e)


@app.task(name='get_image_by_shortcode')
def get_image_by_shortcode(img):
    ''' Given a shortcode, return and parse a single image result. '''
    # Remove dummy image entry that invokes this task.
    # A new image will be saved with all the correct data (DRY).
    code = img.shortcode
    try:
        hashtag = None
        result = api.media_shortcode(code)
        app.send_task('process_search_result', args=[hashtag, [result], code], kwargs={})
    except InstagramAPIError, e:
        print_api_exception('get_image_by_shortcode', e)


@app.task(name='init_instagram_search', ignore_result=True)
def init_instagram_search(hashtag, start_id=None):
    '''
    Kick off a search in the background. Process each result asyncronously,
    as popular hashtags will generate millions of results, and we don't
    want to force the user to wait too long while the system processes
    results.

    Fired via the HashtagQuery model's post_save signal, then populates the
    database with pre-existing search results, i.e. photos already posted
    to instagram.
    '''
    term = hashtag.api_query
    limit = hashtag.safe_limit
    max_tag = start_id
    counter = 0
    results = list()
    existing_images = InstagramImage.objects.filter(hashtag=hashtag).values('instagram_id')
    result_ids = [img.get('instagram_id') for img in existing_images]

    try:
        tagged, next = api.tag_recent_media(tag_name=term, count=limit, max_tag_id=None)
        for media in tagged:
            # Don't count videos or images we've seen before.
            if media.type is 'video': continue      # Only allow image types.
            if media.id in result_ids: continue     # Uniqueness check.
            results.append(media)
            result_ids.append(media.id)
            counter = counter + 1
            if counter > limit:
                break
        # Request the next page(s).
        # Workaround for Instagram omitted max_tag_id support added 04-04-2016.
        while next and counter < limit:
            r = requests.get(next).json()
            for result in r['data']:
                media = Media().object_from_dictionary(result)
                if media.type is 'video': continue      # Only allow image types.
                if media.id in result_ids: continue     # Uniqueness check.
                results.append(media)
                result_ids.append(media.id)
                counter = counter + 1
                if counter > limit:
                    next = None
                    break
            if 'next_url' in r['pagination']:
                next = r['pagination']['next_url']
            else: next = None
        # It's possible that we over-fetched results, so prune the extras.
        total_results = len(results)
        if total_results > 0 and total_results > limit:
            results = results[:limit]
        total_results = len(results)

        logger.info('Image results received: %s' % str(total_results))

        # If we returned results, parse them in new task.
        if total_results > 0:
            hashtag.state = QUERY_STATE_PROCESSING
            hashtag.task_id = app.send_task('process_search_result', args=[hashtag, results], kwargs={})
            hashtag.save()
        else:
            state = QUERY_STATE_END_OF_RESULTS if start_id else QUERY_STATE_NO_RESULTS
            end_query(hashtag, state)
    except InstagramAPIError, e:
        print_api_exception('init_instagram_search', e)


@app.task(name='process_search_result', ignore_result=True)
def process_search_result(hashtag, results, shortcode=None):
    for result in results:
        ok_to_save = True
        if result.type == 'image':
            try:
                if shortcode:
                    img = InstagramImage.objects.get(shortcode__iexact=shortcode)
                else:
                    img = InstagramImage.objects.get(instagram_id__iexact=result.id)
            except InstagramImage.DoesNotExist:
                img = InstagramImage(instagram_id=result.id)
            img.instagram_id = result.id
            img.thumb_url = result.get_thumbnail_url()
            img.user = result.user.username
            logger.debug(result.user.username)
            img.user_pic = None
            try: img.user_pic = send_ig_img_to_s3(result.user.profile_picture)
            except: ok_to_save = False
            img.url = result.get_standard_resolution_url()
            img.created_real = result.created_time
            img.hashtag = hashtag
            img.caption = ''
            img.post_url = result.link
            if result.caption:
                img.caption = result.caption.text
            update_likes_for_image(img, result)
            if ok_to_save:
                img.save()
    if hashtag:
        end_query(hashtag, QUERY_STATE_COMPLETED)


@task
def update_published_image_like_count():
    ''' Update the like counter for each published InstagramImage.
        Check app_settings.GET_LIKES_LATEST_COUNT to change how many images are
        updated on runtime. '''
    images = InstagramImage.objects.filter(published=True)
    count = images.count()
    limit = int(app_settings.GET_LIKES_LATEST_COUNT)
    if count > limit:
        images = images.order_by('-created_real')[:limit]
    for img in images:
        update_likes_for_image(img)
    return len(images)


@app.task(name='terminate_instagram_search', ignore_result=True)
def terminate_instagram_search(term):
    ''' Unsubscribe from Instagram real time update API. '''
    hashtag = HashtagQuery.objects.get(query__iexact=term)
    hashtag.state = QUERY_STATE_CANCELLING
    hashtag.save()
    if hashtag.task_id:
        try:
            task_id = hashtag.task_id
            end_query(hashtag, QUERY_STATE_TERMINATED)
            app.control.revoke(task_id, terminate=True)
        except:
            pass

@task
def verify_published_images_exist():
    ''' Check InstagramImage instances and make sure the URL is valid.
        If the image is no longer valid, set published=False so it no longer
        appears on the live website. '''
    published_images = InstagramImage.objects.filter(published=True)
    verified_count = 0
    deleted_count = 0
    passed = True
    for img in published_images:
        try:
            urllib2.urlopen(urllib2.Request(img.url))
        except:
            img.delete()
            passed = False
        finally:
            if passed:
                verified_count = verified_count + 1
            else:
                deleted_count = deleted_count + 1
    return verified_count, deleted_count
