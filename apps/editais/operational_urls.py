"""Keep historical URL names, but retire generic CRUD in the operational application."""

from django.urls.resolvers import URLPattern

from .operational import retired_configuration
from .urls import urlpatterns as configuration_patterns

urlpatterns = [
    URLPattern(p.pattern, retired_configuration, p.default_args, p.name)
    for p in configuration_patterns
]
