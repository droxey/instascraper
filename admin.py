import uuid
from django.contrib import admin
import django.forms as forms
from django.db import IntegrityError
from django.core.urlresolvers import reverse
from django.template import RequestContext
from django.shortcuts import render_to_response
from django.http import HttpResponse,HttpResponseRedirect
from django import forms
from string import Template
from django.utils.safestring import mark_safe
from .models import InstagramAlbum, InstagramImage, HashtagQuery
from .tasks import get_image_by_shortcode
from django.utils.translation import ugettext as _

class HashtagQueryAdmin(admin.ModelAdmin):
    list_display = ('query', 'active', 'created', 'modified', 'limit',
                    'total_count', 'total_published_count', 'processing_complete', 'status', 'fetch_more_link',
                    'stop_scraping_link', 'task_id')
    search_fields = ['query', ]
    list_filter = (
        ('created', admin.DateFieldListFilter),
        ('modified', admin.DateFieldListFilter),
    )

    def processing_complete(self, obj):
        return obj.processing_complete
    processing_complete.short_description = 'Done Importing'

    def limit(self, obj):
        return obj.limit
    limit.short_description = 'Import Limit'

    def total_count(self, obj):
        count = None
        try: count = InstagramImage.objects.filter(hashtag=obj).count()
        except: pass
        return '<a target="_blank" href="/admin/instascraper/instagramimage/?hashtag__id__exact=%s">%s</a>' % (obj.id, count)
    total_count.short_description = 'Total images'
    total_count.allow_tags = True

    def total_published_count(self, obj):
        count = None
        try: count = InstagramImage.objects.filter(hashtag=obj, published=True).count()
        except: pass
        return '<a target="_blank" href="/admin/instascraper/instagramimage/?published__exact=1&hashtag__id__exact=%s">%s</a>' % (obj.id, count)
    total_published_count.allow_tags = True
    total_published_count.short_description = 'Published images'

    def stop_scraping_link(self, obj):
        if not obj.processing_complete:
            return '<a href="%s" style="font-weight: bold;">Stop</a>' % reverse('scraper_stop_search', args=[obj.query])
        return ''
    stop_scraping_link.allow_tags = True
    stop_scraping_link.short_description = 'Stop Scraping?'

    def fetch_more_link(self, obj):
        return '<a href="%s" style="font-weight: bold;">Get %s More</a>' % (reverse('scraper_fetch_more', args=[obj.query]), str(obj.limit))
    fetch_more_link.allow_tags = True
    fetch_more_link.short_description = 'Fetch More?'


class AddToAlbumForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    queryset = InstagramAlbum.objects.all()
    album = forms.ModelChoiceField(queryset=queryset)
class InstagramImagePreviewWidget(forms.TextInput):
  def render(self, name, value, attrs=None):
    tpl = Template(u"""<img src='$url'/><br/>$url""")
    return mark_safe(tpl.substitute(url=value))

class InstagramImageInline(admin.TabularInline):
    model = InstagramImage
    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'thumb_url':
            kwargs['widget'] = InstagramImagePreviewWidget
        return super(InstagramImageInline,self).formfield_for_dbfield(db_field,**kwargs)
    extra = 0
class hasProductFilter(admin.SimpleListFilter):
    title = _('Has Product')
    parameter_name = 'description'
    def lookups(self, request, model_admin):
        return [
            ('has_product', _('Has products only')),
            ('missing_product', _('Missing products only')),
        ]
    def queryset(self, request, queryset):
        if self.value() == 'has_product':
            objects = []
            for i in InstagramImage.objects.all():
                if i.product_id:
                    objects.append(i.id)

            return queryset.filter(id__in=objects)
        elif self.value() == 'missing_product':
            objects = []
            for i in InstagramImage.objects.all():
                if not i.product_id:
                    objects.append(i.id)
            return queryset.filter(id__in=objects)


class InstagramUrlForm(forms.ModelForm):
    class Meta:
        model = InstagramImage
        fields = ('post_url',)

    def __init__(self, *args, **kwargs):
        super(InstagramUrlForm, self).__init__(*args, **kwargs)
        self.fields['post_url'].label = "Image URL"
        self.fields['post_url'].help_text = "The direct link to an Instagram image. Example: https://instagram.com/p/5Hvoilvt7F/"
        self.fields['post_url'].widget = forms.TextInput(attrs={
            'placeholder': 'Paste image link here...',
            'style': 'width: 100%'
        })

    def clean(self):
        cleaned = super(InstagramUrlForm, self).clean()
        url = cleaned.get('post_url', None)
        if url:
            if url.endswith('/'): url = url[:-1]
            shortcode = url.split('/')[-1]
            cleaned['shortcode'] = shortcode
            dupes = InstagramImage.objects.filter(post_url__iexact=cleaned['post_url'])
            if len(dupes) > 0:
                raise forms.ValidationError('An image with this shortcode already exists!')
        self.cleaned_data.update(cleaned)
        return self.cleaned_data

    def save(self, commit=True):
        instance = super(InstagramUrlForm, self).save(commit=False)
        instance.shortcode = self.cleaned_data['shortcode']
        temp_id = uuid.uuid4()
        instance.instagram_id = temp_id.hex
        instance.save()
        get_image_by_shortcode.apply_async([instance])
        return instance

class InstagramImageForm(forms.ModelForm):
    class Meta:
        model = InstagramImage


class InstagramImageAdmin(admin.ModelAdmin):
    class Media:
        js = ('/static/admin/js/instagram-image-admin.js', )

    search_fields = ['hashtag__query', 'caption']
    ordering = ('-created_real',)
    list_filter = (
        ('created', admin.DateFieldListFilter),
        ('modified', admin.DateFieldListFilter),
        ('published'),
        ('hashtag'),
        ('album'),
        hasProductFilter
    )
    def make_active(self, request, queryset):
        rows_updated = queryset.update(published=True)
        if rows_updated == 1:
            message_bit = _("1 image was")
        else:
            message_bit = "%s images were" % rows_updated
        self.message_user(request, "%s successfully published" % message_bit)
        return HttpResponseRedirect('')
    make_active.short_description = _("Publish")

    def make_inactive(self, request, queryset):
        rows_updated = queryset.update(published=False)
        if rows_updated == 1:
            message_bit = _("1 image was")
        else:
            message_bit = "%s images were" % rows_updated
        self.message_user(request, "%s successfully published" % message_bit)
        return HttpResponseRedirect('')
    make_inactive.short_description = _("Unpublish")

    def add_to_album(self, request, queryset):
        form = None
        if 'apply' in request.POST:
            form = AddToAlbumForm(request.POST)
            if form.is_valid():
                album = form.cleaned_data['album']
                count = 0
                for image in queryset:
                    image.album=album
                    image.save()
                    count += 1

                plural = ''
                if count != 1:
                    plural = 's'

                self.message_user(request, "Successfully added album %s to %d image%s." % (album.name, count, plural))
                return HttpResponseRedirect(request.get_full_path())


        if not form:
            form = AddToAlbumForm(initial={
                '_selected_action': request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
            })
        context = RequestContext(request, {
            'images': queryset,
            'tag_form': form,
            'action_field':"Selected album",
            'action_application':"add_to_album",
            'count':queryset.count(),
        })
        return render_to_response('admin/add_to_album.html',context, context_instance=RequestContext(request))
    add_to_album.short_description = "Add selected images to an album"
    actions = ('add_to_album','make_active', 'make_inactive',)
    def img_view(self, obj):
        return '<img height="100" src="%s"/>' % obj.url
    img_view.allow_tags = True
    def url_link(self, obj):
        return '<a href="%s" target="_blank">%s</a>' % (obj.url, obj.url)
    url_link.allow_tags = True

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'thumb_url':
            kwargs['widget'] = InstagramImagePreviewWidget
        return super(InstagramImageAdmin,self).formfield_for_dbfield(db_field,**kwargs)

    def thumbnail(self, obj):
        return '<a href="%s" target="_blank" title="Click to open in new tab"><img height="100" src="%s"/></a>' % (obj.url, obj.url)
    thumbnail.allow_tags = True
    actions = ('add_to_album','make_active', 'make_inactive',)
    list_display = ("user", "instagram_id", "thumbnail", "likes", "hashtag", "album", "product", "caption_admin", "created_real", "created", "published")
    def caption_admin(self, obj):
        return '<div class="instagram-admin-caption">%s</div>' % obj.caption
    caption_admin.allow_tags = True

    def get_form(self, request, obj=None, **kwargs):
        if request.GET.get('urlonly', False):
            return InstagramUrlForm
        else:
            return InstagramImageForm



class InstagramAlbumAdmin(admin.ModelAdmin):
    search_fields = ['name']
    list_display = ('name', 'count')
    def count(self, obj):
        album = InstagramAlbum.objects.get(pk=obj.id)
        count = album.instagramimage_set.all().count()
        return count
    count.short_description = "# Images"
    list_filter = (
        ('created', admin.DateFieldListFilter),
        ('modified', admin.DateFieldListFilter),
    )
    inlines = [InstagramImageInline]
    raw_id_fields = ('product',)
    autocomplete_lookup_fields = {
        'fk': ['product'],
    }
admin.site.register(InstagramAlbum, InstagramAlbumAdmin)
admin.site.register(InstagramImage, InstagramImageAdmin)
admin.site.register(HashtagQuery, HashtagQueryAdmin)
