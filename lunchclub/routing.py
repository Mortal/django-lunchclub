# From http://masnun.rocks/2016/09/25/introduction-to-django-channels/
from channels.routing import route
from .consumers import chat_stream

channel_routing = [
    route("http.request", chat_stream, path=r"^/chat/stream/$"),
]
