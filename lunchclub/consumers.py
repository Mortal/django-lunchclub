from django.http import HttpResponse
from channels import Group
from channels.handler import AsgiRequest, AsgiHandler


def websocket_receive(message):
    text = message.content.get('text')
    if text:
        message.reply_channel.send({"text": "You said: {}".format(text)})


def chat_stream(message):
    group_name = 'chat_stream'

    # https://serverfault.com/a/801629
    headers = [
        ('Content-Type', 'text/event-stream'),
        ('Cache-Control', 'no-cache'),
        ('X-Accel-Buffering', 'no'),
    ]
    # https://github.com/flo-dhalluin/ssechannels/blob/master/ssechannels/sse.py
    reply = {
        'status': 200,
        'headers': headers,
        'more_content': True,
    }
    message.reply_channel.send(reply)
    Group(group_name).add(message.reply_channel)
