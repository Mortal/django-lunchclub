"""
WSGI config for lunchclub project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.10/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lunchclub.settings")

application = get_wsgi_application()

if settings.RUNNING_IN_HEROKU:
    # For Heroku: Serve static files
    from whitenoise.django import DjangoWhiteNoise
    application = DjangoWhiteNoise(application)
