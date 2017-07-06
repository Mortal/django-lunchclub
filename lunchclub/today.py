from django.utils import timezone
from channels import Group
from lunchclub.sse import send_event, send_event_json
from lunchclub.models import Rsvp, Announce


def send_keepalive():
    send_event(Group('today_events'), 'ping', '')


def send_current_rsvp(channel=None):
    if channel is None:
        channel = Group('today_events')

    msg = 'Do you want lunch today?'
    rsvp_options = [
        {'key': key, 'label': label}
        for key, label in Rsvp.STATUS
    ]
    announce = [
        {'key': key, 'label': label}
        for key, label in Announce.KIND
    ]
    today = timezone.now().date()
    data = {'msg': msg, 'rsvp_options': rsvp_options, 'announce': announce,
            'announcement': Announce.current_notification_for_date(today),
            'rsvps': Rsvp.data_for_date(today)}

    send_event_json(channel, 'query', data)


def send_notification(announce: 'Announce', channel=None):
    if channel is None:
        channel = Group('today_events')

    send_event_json(channel, 'notification', announce.notification())
