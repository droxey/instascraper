from django import template
from django.template import loader, Context
from instascraper.models import InstagramImage
from django.shortcuts import get_object_or_404
from django.conf import settings
import math
from collections import deque
import json
register = template.Library()
import logging
logger = logging.getLogger('instagram')

@register.simple_tag
def get_insta_popup(pk, slides_list):
    as_list = list(slides_list)
    listpos = as_list.index(pk)
    logger.debug(as_list)
    t = loader.get_template("instascraper/popup.html")
    obj = None
    try: obj = InstagramImage.objects.get(pk=pk, published=True)
    except: pass
    c = Context({
        'obj': obj,
        'slides_list': slides_list
    })
    return t.render(c)

@register.simple_tag
def get_single_popup_slide(request, pk):
    t = loader.get_template("instascraper/popup_slide.html")
    obj = None
    try: obj = InstagramImage.objects.get(pk=pk, published=True)
    except: pass
    c = Context({
        'obj': obj,
        'request': request,
    })
    return t.render(c)

@register.filter(name='secure_instagram_img_fix')
def secure_instagram_img_fix(url):
    url = url.replace('http:', '')
    return url


@register.simple_tag
def homepage_posts(request):
    t = loader.get_template("instascraper/homepage_posts.html")
    images = []
    try: images =  InstagramImage.objects.filter(published=True).order_by("-created_real")[:12]
    except: return t.render({})
    imglist = []
    for i in images:
        imglist.append(i.id)
    slides_list = deque(imglist)
    slides_list.rotate(len(images)/2)
    slides_list = json.dumps(list(slides_list))

    c = Context({
        'objects': images,
        'request': request,
        'STATIC_URL' : settings.STATIC_URL,
        'slides_list': slides_list,
    })
    return t.render(c)

@register.simple_tag
def product_instagrams(request, product_id):
    t = loader.get_template("instascraper/product_instagrams.html")
    images = []
    try: images =  InstagramImage.objects.filter(published=True, product_id=product_id).order_by("-created_real")[:20]
    except: return t.render({})
    imglist = []
    for i in images:
        imglist.append(i.id)
    slides_list = deque(imglist)
    slides_list.rotate(len(images)/2)
    slides_list = json.dumps(list(slides_list))

    c = Context({
        'objects': images,
        'request': request,
        'STATIC_URL' : settings.STATIC_URL,
        'slides_list': slides_list,
    })
    return t.render(c)