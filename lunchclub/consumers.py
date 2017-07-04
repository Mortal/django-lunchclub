import json
# from django.http import HttpResponse
from channels import Group
# from channels.handler import AsgiRequest, AsgiHandler
from channels.auth import http_session_user
from lunchclub.views import (
    TodayActions, send_status, send_event, send_event_json,
)


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

    msg = 'Do you want lunch today?'
    options = [
        (f.__name__, f.label)
        for f in TodayActions.actions
    ]
    option_dicts = [
        {'key': key, 'text': text}
        for key, text in options
    ]
    data = {'msg': msg, 'options': option_dicts}

    send_status(message.reply_channel, 200)
    send_event_json(message.reply_channel, 'query', data)

    Group('today_events').add(message.reply_channel)
    Group('today_events_%s' % message.user.username).add(message.reply_channel)
