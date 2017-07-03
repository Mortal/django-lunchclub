# From http://masnun.rocks/2016/09/25/introduction-to-django-channels/
import os
from channels.asgi import get_channel_layer

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lunchclub.settings")

channel_layer = get_channel_layer()
