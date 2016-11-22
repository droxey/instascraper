# Create your views here.

from .models import InstagramImage, InstagramAlbum, HashtagQuery
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _
from django.shortcuts import render
from . import app_settings
from .models import InstagramImage, HashtagQuery
from .tasks import terminate_instagram_search
from .utils import kickoff_instagram_search
from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms_foundation.layout import Layout, Button, Field, Fieldset, Hidden, ButtonHolderPanel, \
    SplitDateTimeField, Row, RowFluid, Column, Div, ButtonHolder, Submit, HTML, InlineSwitchField
from instagram import client
from django.shortcuts import render, get_object_or_404
from django.http import Http404, HttpResponseRedirect
from endless_pagination import utils
from django.conf import settings
from django.template import RequestContext
from django.shortcuts import render_to_response
import math
from collections import deque
import json
import logging

logger = logging.getLogger('instagram')
api = client.InstagramAPI(**app_settings.INSTAGRAM_OAUTH_CONFIG)

def user_content_front(request, template='instascraper/index.html', page_template='instascraper/index_page.html'):
    per_page = getattr(settings, 'CUSTOM_GRID_PAGINATION', 16)
    image_count = total_pages = 0
    hashtag_filter_title = 'SHERRIHILL'
    prev_page = next_page = None
    page_number = utils.get_page_number_from_request(request)
    trend_default = None
    queries_without_page = request.GET.copy()
    if queries_without_page.has_key('page'):
        del queries_without_page['page']

    try: trend_default = request.GET['trends']
    except:pass
    recent_default = 1 #if date sort not in url, force sort by newest
    try: recent_default = request.GET['recent']
    except: pass
    form = UserContentFilterForm(initial={
                'trends' : trend_default,
                'recent' : recent_default,
                })
    images = []
    try:
        if recent_default == '2': #sort by oldest first
            images =  InstagramImage.objects.filter(published=True).order_by("created_real")
        else: #sort by newest first
            images =  InstagramImage.objects.filter(published=True).order_by("-created_real")
    except:pass


    if trend_default and images:
        valid_hashtag = None
        try:  valid_hashtag = HashtagQuery.objects.get(pk=trend_default)
        except: pass
        if valid_hashtag:
            hashtag_filter_title = valid_hashtag.query
        images = images.filter(hashtag=trend_default)
    imglist = []
    for i in images:
        imglist.append(i.id)
    slides_list = deque(imglist)
    slides_list.rotate(len(images)/2)
    total_pages = math.ceil(float(len(images)) / float(per_page))
    paginator = Paginator(images, per_page)
    paged_images = paginator.page(page_number)
    if total_pages < 1:
        total_pages = 1
    paged_url = '/%s/?page=' % 'social'

    if page_number < total_pages:
        next_page = paged_url + str(page_number + 1)
    if page_number > 1:
        prev_page = paged_url + str(page_number -1)
    if page_number > total_pages:
        raise Http404
    slides_list = json.dumps(list(slides_list))
    context = {
        'bodyclass': 'user-content',
        'pagetitle': _('#SherriHill'),
        'objects' : images,
        'paged_objects': paged_images,
        'form' : form,
        'queries' : queries_without_page,
        'page_template':page_template,
        'current_page_number':page_number,
        'prev_page' : prev_page,
        'next_page' : next_page,
        'per_page' : per_page,
        'total_pages': total_pages,
        'slides_list': slides_list,
        'hashtag_filter_title' : hashtag_filter_title,
    }
    if request.is_ajax():
        template = page_template
    response = render_to_response(template, context_instance=RequestContext(request, context))
    return response

def social_post_detail(request, id):
    obj = get_object_or_404(InstagramImage, pk=id)
    slides_list = None
    if not obj:
        raise Http404
    context = {
        'obj': obj,
        'slides_list' : [],
    }
    if request.method == 'POST':
        try: slides_list = json.loads(request.POST['slides_list'])
        except: pass
        if slides_list:
            pos = slides_list.index(obj.id)
            shift = deque(slides_list)
            shift.rotate(-pos) #scoot the clicked image to the beginning of the slideshow
            context['slides_list'] = list(shift)

    return render(request, 'instascraper/popup.html', context)
def social_post_detail_single(request, id):
    obj = get_object_or_404(InstagramImage, pk=id)
    if not obj:
        raise Http404
    context = {
        'obj': obj,
    }

    return render(request, 'instascraper/popup_slide.html', context)
class UserContentFilterForm(forms.Form):
    trendsQ=list(HashtagQuery.objects.filter(active=True))
    trendsQ = sorted(trendsQ, key=lambda t: t.published_image_count)
    trendsQ.reverse()
    trends = forms.ChoiceField(
        choices=((t.id, t.query) for t in trendsQ),
    )
    RECENT_CHOICES = (
    (1, _("Most Recent")),
    (2, _("Oldest")),
)
    recent = forms.ChoiceField(choices=RECENT_CHOICES)
    def __init__(self, *args, **kwargs):
        super(UserContentFilterForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
                     Row(
                         Column('trends', css_class='small-6'),
                         Column('recent', css_class='small-6'),
                     ),
        )
        self.helper.form_id = 'id-socialFilter'
        self.helper.form_class = 'social-filter-form'
        self.helper.form_method = 'get'
        self.helper.form_action = '.'


def scraper_stop_search(request, query):
    ''' Cancel query and refresh the changelist page. '''
    terminate_instagram_search.delay(query)
    return HttpResponseRedirect(
        reverse('admin:instascraper_hashtagquery_changelist'))


def scraper_fetch_more(request, query):
    ''' Fetch more results and refresh the changelist page. '''
    hashtag = HashtagQuery.objects.get(query__iexact=query)
    try:
        start = InstagramImage.objects.filter(hashtag=hashtag).order_by('created_real')[0]
        kickoff_instagram_search(hashtag, start.instagram_id)
    except IndexError:
        kickoff_instagram_search(hashtag)
    return HttpResponseRedirect(
        reverse('admin:instascraper_hashtagquery_changelist'))
