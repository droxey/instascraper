from django.conf.urls import url
from django.conf.urls import patterns
from django.contrib.auth.decorators import login_required
from .views import *

urlpatterns = patterns('instascraper.views',
    (r"^$", 'user_content_front', {}, 'usercontent'),
    (r"^(?P<id>\d+)/$", 'social_post_detail', {}, "user_post" ),
    (r"^(?P<id>\d+)/single/$", 'social_post_detail_single', {}, "user_post_single" ),

    # Used by HashtagQueryAdmin
    url(r"^(?P<query>\w+)/stop/$", scraper_stop_search, name="scraper_stop_search"),
    url(r"^(?P<query>\w+)/fetch/$", scraper_fetch_more, name="scraper_fetch_more"),
)
