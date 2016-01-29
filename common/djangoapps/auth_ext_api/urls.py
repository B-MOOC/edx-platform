"""Url configuration for the auth ext API module."""

from django.conf.urls import include, patterns, url


urlpatterns = patterns(
    '',
    url(r'^auth-ext-api/login/$', 'auth_ext_api.views.login'),
    url(r'^auth-ext-api/login/post/$', 'auth_ext_api.views.post'),
)
