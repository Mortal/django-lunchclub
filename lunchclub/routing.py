# From http://masnun.rocks/2016/09/25/introduction-to-django-channels/
from channels.routing import route
from .consumers import websocket_receive

channel_routing = [
    route("websocket.receive", websocket_receive, path=r"^/chat/ws/"),
]
