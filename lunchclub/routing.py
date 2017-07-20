# From http://masnun.rocks/2016/09/25/introduction-to-django-channels/
from channels.routing import route
from .consumers import chat_stream
from .consumers import today_events
from django.conf import settings as _s
_S = _s.CHANNEL_SUBPATH

channel_routing = [
    route("http.request", chat_stream, path='^' + _S + r"/chat/stream/$"),
    route("http.request", today_events, path='^' + _S + r"/today/events/$"),
]
