# from django.http import HttpResponse
from channels import Group
# from channels.handler import AsgiRequest, AsgiHandler
from channels.auth import http_session_user
from lunchclub.sse import send_status, send_event
from lunchclub.today import send_current_rsvp


@http_session_user
def chat_stream(message):
    group_name = 'chat_stream'
    send_status(message.reply_channel, 200)
    send_event(message.reply_channel, 'chat_message',
               'Hello, %s!' % message.user)
    Group(group_name).add(message.reply_channel)


@http_session_user
def today_events(message):
    if not message.user.is_authenticated():
        send_status(message.reply_channel, 400)
        send_event(message.reply_channel, 'error', 'Not authenticated', False)
        return

    send_status(message.reply_channel, 200)
    send_current_rsvp(message.reply_channel)

    Group('today_events').add(message.reply_channel)
    Group('today_events_%s' % message.user.username).add(message.reply_channel)
