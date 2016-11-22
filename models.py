import datetime

from django.core.validators import MaxValueValidator, MinValueValidator
from django.conf import settings
from django.db import models
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from product.modules.configurable.models import ConfigurableProduct

from . import app_settings
from .utils import kickoff_instagram_search


QUERY_STATE_NEW = 0
QUERY_STATE_PROCESSING = 1
QUERY_STATE_COMPLETED = 2
QUERY_STATE_CANCELLING = 3
QUERY_STATE_TERMINATED = 4
QUERY_STATE_NO_RESULTS = 5
QUERY_STATE_END_OF_RESULTS = 6

QUERY_PROCESSING_STATES = (
    (QUERY_STATE_NEW, 'New'),
    (QUERY_STATE_PROCESSING, 'Processing'),
    (QUERY_STATE_COMPLETED, 'Completed'),
    (QUERY_STATE_CANCELLING, 'Cancelling'),
    (QUERY_STATE_TERMINATED, 'Terminated'),
    (QUERY_STATE_NO_RESULTS, 'No Results Found'),
    (QUERY_STATE_END_OF_RESULTS, 'End of Results')
)


class TrackingFieldsMixin(models.Model):
    '''
    A simple, reusable audit trail.
    Administrators may view this info, but may not modify it.
    '''
    created = models.DateTimeField(auto_now_add=True, editable=False)
    modified = models.DateTimeField(auto_now=True, editable=False)
    deleted_on = models.DateTimeField(blank=True, null=True, editable=False)

    class Meta:
        abstract = True

    @property
    def is_active(self):
        return self.deleted_on is None



class HashtagQuery(TrackingFieldsMixin, models.Model):
    '''
    A representation of a query, used to search Instagram tags. Query text
    persists within the database in order to continue searching for results
    asyncronously after the user initiates a search.
    '''
    query = models.CharField(max_length=500, unique=True,
        help_text='Hashtag to Query WITHOUT the # (ex: sherrihill)')
    limit = models.PositiveIntegerField(default=200,
        validators=[
            MaxValueValidator(app_settings.MAX_INSTAGRAM_API_CALLS),
            MinValueValidator(10),
        ],
        help_text='Maximum total images to retreive from Instagram.')
    processing_completed_on = models.DateTimeField(editable=False, blank=True,
        null=True,
        help_text='When initial search results are all added to our database.')
    active=models.BooleanField(default=True,
        help_text='Is this query currently active?')
    task_id = models.CharField('Task ID', max_length=765, unique=True, blank=True,
                               null=True, editable=False)
    status = models.IntegerField('Status', default=QUERY_STATE_NEW, editable=False,
                                 choices=QUERY_PROCESSING_STATES)

    class Meta:
        verbose_name_plural = 'Hashtag Queries'

    def __unicode__(self):
        return self.query
    @property
    def image_count(self):
        return InstagramImage.objects.filter(hashtag=self).count()
    @property
    def published_image_count(self):
        return InstagramImage.objects.filter(hashtag=self, published=True).count()
    @property
    def api_query(self):
        '''
        For use with the Instagram API, which requires omitting the '#'
        character in method calls. If it's there, strip it, and return
        a clean term.
        '''
        if self.query.startswith('#'):
            return self.query[len('#'):]
        return self.query

    @property
    def processing_complete(self):
        ''' Bool. Returns True if initial data finished loading. '''
        return self.processing_completed_on is not None or self.status == QUERY_STATE_TERMINATED

    @property
    def safe_limit(self):
        ''' Returns an int, takes into account a max number of API calls.
            Always returns the lesser of the two. '''
        limit_max = app_settings.MAX_INSTAGRAM_API_CALLS
        return (self.limit if self.limit <= limit_max else limit_max)

from product.models import Product
class InstagramAlbum(TrackingFieldsMixin, models.Model):
    '''
    Contains one-to-many InstagramImage results, curated by the user.
    '''
    name = models.CharField(max_length=255, blank=False, null=True,
        help_text='An identifier for the collection of images.')
    product = models.ForeignKey(Product,
         blank=True, null=True,
         help_text='Optional. The product associated with this image.')
    def __unicode__(self):
        return self.name

    class Meta:
        verbose_name = 'Instagram Album'
        verbose_name_plural = 'Instagram Albums'


class InstagramImage(TrackingFieldsMixin, models.Model):
    '''
    Generated upon querying Instagram and selecting a desired
    image result.
    '''
    instagram_id = models.CharField(max_length=255, editable=False, unique=True,
        help_text='Uniquely identifies the image in the Instagram database.')
    product = models.ForeignKey(ConfigurableProduct,
         blank=True, null=True,
         help_text='Optional. The product associated with this image.')
    order = models.IntegerField(help_text='Defines image position within an album.', default=0)
    likes = models.IntegerField(default=0)
    album = models.ForeignKey('InstagramAlbum', blank=True, null=True,
        help_text='Optional. Associates the current image to the selected album.')
    url = models.URLField(editable=False,
        help_text='The direct link to the image, hosted on the Instagram server.')
    thumb_url = models.URLField(editable=True, blank=True, null=True,
        help_text='The direct link to the image thumbnail. \
            hosted on the Instagram server.')
    post_url = models.URLField(editable=True, blank=True, null=True,
        help_text='The direct link to the image post on external website.')
    user = models.CharField(max_length=255, null=True)
    user_pic = models.URLField(editable=True, blank=True, null=True,
        help_text='The direct link to the user avatar \
            hosted on the Instagram server.')
    published = models.BooleanField(default=False,
        help_text='Toggle visibility on the live website.')
    hashtag = models.ForeignKey(HashtagQuery, blank=True, null=True)
    shortcode = models.CharField(max_length=20, blank=True, null=True)
    created_real = models.DateTimeField("Original Post Date", default=datetime.datetime.now(),
        help_text="When the social media was originally posted.")
    caption = models.TextField('Caption', blank=True,null=True)
    is_favorite = models.BooleanField('Mark as Favorite', default=False,
        help_text='Mark as Favorite', blank=True,)
    is_staff_pick = models.BooleanField('Mark as Staff Pick', default=False, blank=True,
        help_text='Mark as Staff Pick')

    class Meta:
        verbose_name = 'Instagram Image'
        verbose_name_plural = 'Instagram Images'

    def __unicode__(self):
        return str(self.instagram_id)

    def get_absolute_url(self):
        return "/social/" + str(self.id)


'''
SIGNALS
'''

@receiver(post_save, sender=HashtagQuery)
def hashtag_query_post_save(sender, instance, created, **kwargs):
    ''' Executed when a HashtagQuery instance is created or modified. '''
    if created:
        kickoff_instagram_search(instance)
