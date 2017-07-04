import json


def send_status(channel, status):
    # https://serverfault.com/a/801629
    headers = [
        ('Content-Type', 'text/event-stream'),
        ('Cache-Control', 'no-cache'),
        ('X-Accel-Buffering', 'no'),
    ]
    # https://github.com/flo-dhalluin/ssechannels/blob/master/ssechannels/sse.py
    reply = {
        'status': status,
        'headers': headers,
        'more_content': True,
    }
    channel.send(reply)


def send_event(channel, event, data, more_content=True):
    channel.send({
        'content':
        b'event:%s\ndata:%s\n\n' %
        (str(event).encode(),
         str(data).encode()),
        'more_content': more_content})


def send_event_json(channel, event, data, more_content=True):
    channel.send({
        'content':
        b'event:%s\ndata:%s\n\n' %
        (str(event).encode(),
         json.dumps(data).encode()),
        'more_content': more_content})
