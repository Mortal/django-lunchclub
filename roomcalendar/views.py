import json
import datetime

from django.views.generic import View
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseBadRequest
from django.core.exceptions import ValidationError

from lunchclub.auth import TokenBackend
from roomcalendar.models import Calendar, CalendarItem


class CalendarUpdate(View):
    @csrf_exempt
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        token = request.POST.get('token')
        user = TokenBackend().authenticate(token)
        if user is None:
            return HttpResponseBadRequest('Unauthorized')
        if not user.is_superuser:
            return HttpResponseBadRequest('Not superuser')
        payload_str = request.POST.get('payload') or ''
        try:
            payload = json.loads(payload_str)
        except ValueError as exn:
            return HttpResponseBadRequest(str(exn))
        try:
            date_str = payload.pop('date')
            calendars = payload.pop('calendars')
        except KeyError as exn:
            return HttpResponseBadRequest('Missing key %s' % exn)
        try:
            date = datetime.datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError as exn:
            return HttpResponseBadRequest('Invalid date: %r' % exn)
        try:
            for name, items in calendars.items():
                CalendarItem.update_for_date(
                    Calendar.get_or_create(name=name), items, date, user)
        except ValidationError as exn:
            return HttpResponseBadRequest(str(exn))
        return HttpResponse('OK')
