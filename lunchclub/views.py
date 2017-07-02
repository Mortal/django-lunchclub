import re
import hmac
import json
import base64
import decimal
import hashlib
import logging
import datetime
import functools

from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.shortcuts import redirect
from django.views.generic import TemplateView, FormView, View
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.defaults import permission_denied
from django.db.models import Q, F
from django.contrib.auth import authenticate, login, logout
from django.conf import settings

from lunchclub.forms import (
    DatabaseBulkEditForm, AccessTokenListForm, SearchForm, ExpenseCreateForm,
    AttendanceTodayForm, AttendanceCreateForm, MonthForm,
)
from lunchclub.models import Person, Expense, Attendance, AccessToken
from lunchclub.models import get_average_meal_price, compute_month_balances
from lunchclub.parser import (
    get_attenddb_from_model, get_expensedb_from_model,
    unparse_attenddb, unparse_expensedb,
)
import lunchclub.mail


logger = logging.getLogger('lunchclub')


def dispatch_superuser_required(function):
    @functools.wraps(function)
    def dispatch(request, *args, **kwargs):
        if not request.user.is_superuser:
            return permission_denied(request, exception=None)
        return function(request, *args, **kwargs)

    return dispatch


superuser_required = method_decorator(
    dispatch_superuser_required, name='dispatch')


def dispatch_person_required(function):
    @functools.wraps(function)
    def dispatch(request, *args, **kwargs):
        try:
            request.person = Person.objects.get(user=request.user)
        except Person.DoesNotExist:
            return permission_denied(request, exception=None)
        return function(request, *args, **kwargs)

    return dispatch


person_required = method_decorator(
    dispatch_person_required, name='dispatch')


def get_months(months):
    d = datetime.date.today()
    ym = d.year * 12 + d.month - 1
    yms = (divmod(ym - s, 12) for s in range(months))
    return [(y, m + 1) for y, m in yms]


class Home(TemplateView):
    template_name = 'lunchclub/home.html'

    def get_context_data(self, **kwargs):
        data = super(Home, self).get_context_data(**kwargs)

        data['search_form'] = search_form = SearchForm(
            data=self.request.GET or None)
        if search_form.is_valid():
            search_data = search_form.cleaned_data
        else:
            f = SearchForm(data={})
            if not f.is_valid():
                raise AssertionError('Blank SearchForm is not valid')
            search_data = f.cleaned_data
        months = get_months(search_data['months'])
        earliest_year, earliest_month = min(months)
        earliest_date = datetime.date(earliest_year, earliest_month, 1)
        date_filter = Q(date__gte=earliest_date)
        expense_qs = Expense.objects.filter(date_filter)
        attendance_qs = Attendance.objects.filter(date_filter)
        meal_prices, balances = compute_month_balances(expense_qs,
                                                       attendance_qs)
        month_data = []
        for (y, m) in months:
            name = '%04d-%02d' % (y, m)
            price = meal_prices.setdefault((y, m), 0)
            month_data.append(dict(name=name, price=price))
        data['total_price'] = get_average_meal_price()
        data['months'] = month_data

        person_data = []
        if search_data['show_all']:
            person_qs = Person.objects.all()
        else:
            person_qs = Person.filter_active()
        person_qs = person_qs.order_by('balance')
        for person in person_qs:
            person_months = []
            for (y, m) in months:
                person_months.append(dict(balance=balances[person][y, m]))
            person_data.append(dict(
                username=person.username, balance=person.balance,
                months=person_months))

        data['persons'] = person_data
        return data


class AttendanceExport(View):
    def get(self, request):
        return HttpResponse(
            unparse_attenddb(get_attenddb_from_model()),
            content_type='text/plain')


class ExpenseExport(View):
    def get(self, request):
        return HttpResponse(
            unparse_expensedb(get_expensedb_from_model()),
            content_type='text/plain')


class DatabaseBulkEdit(FormView):
    form_class = DatabaseBulkEditForm
    template_name = 'lunchclub/database_bulk_edit.html'

    def get_form_kwargs(self, **kwargs):
        form_kwargs = super().get_form_kwargs(**kwargs)
        form_kwargs['attenddb'] = get_attenddb_from_model()
        form_kwargs['expensedb'] = get_expensedb_from_model()
        return form_kwargs

    def post(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            return permission_denied(request, exception=None)
        if request.POST.get('preview'):
            return self.render_to_response(
                self.get_context_data(form=self.get_form(),
                                      preview=True))
        return super().post(request, *args, **kwargs)

    def get_context_data(self, preview=False, **kwargs):
        context_data = super().get_context_data(**kwargs)
        if preview:
            form = context_data['form']
            if form.is_valid():
                context_data['preview'] = list(form.iter_created_removed())
            else:
                context_data['preview_invalid'] = True
        return context_data

    def form_valid(self, form):
        for line in form.iter_created_removed():
            logger.info("%s: %s", self.request.user.username, line)
        form.save()
        return redirect('home')


class Logout(TemplateView):
    template_name = 'lunchclub/logout.html'

    def post(self, request):
        logger.info("Logout %s", request.user)
        logout(request)
        return redirect('home')


class Login(TemplateView):
    template_name = 'lunchclub/login.html'

    def dispatch(self, request, *args, **kwargs):
        token = request.GET.get('token')
        if not token:
            return self.render_to_response(dict(error='No token specified'))
        user = authenticate(token=token)
        if not user:
            return self.render_to_response(
                dict(error='Invalid token specified'))
        if request.user == user:
            # Already logged in!
            return redirect('home')
        # Not logged in, so present "bookmark this page"-form.
        self.kwargs['user'] = kwargs['user'] = user
        self.kwargs['token'] = kwargs['token'] = token
        return super(Login, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        data = super(Login, self).get_context_data(**kwargs)
        data['user'] = self.kwargs['user']
        return data

    def post(self, request, user, token):
        logger.info("Login %s with token %s", user, token[:20])
        qs = AccessToken.objects.filter(token=token)
        qs.update(use_count=F('use_count') + 1)
        login(request, user)
        return redirect('home')


@superuser_required
class AccessTokenList(FormView):
    form_class = AccessTokenListForm
    template_name = 'lunchclub/accesstokenlist.html'

    def get_form_kwargs(self, **kwargs):
        form_kwargs = super().get_form_kwargs(**kwargs)
        form_kwargs['queryset'] = Person.objects.all()
        return form_kwargs

    def form_valid(self, form):
        set_email, revoke_tokens, save_tokens, messages, save = form.actions()

        for user, email in set_email:
            logger.info("%s: Set email address of %s to %s",
                        self.request.user.username,
                        user.username, email)
        for token in save_tokens:
            logger.info("%s: Create %s token %s",
                        self.request.user.username, token.person.username,
                        token.token[:20])
        for token in revoke_tokens:
            logger.info("%s: Revoke %s token %s with %s use(s)",
                        self.request.user.username, token.person.username,
                        token.token[:20], token.use_count)

        save()

        fresh_kwargs = self.get_form_kwargs()
        fresh_kwargs.pop('data', None)
        fresh_kwargs.pop('files', None)
        fresh_form = self.form_class(**fresh_kwargs)
        assert not fresh_form.is_bound, fresh_kwargs

        if messages:
            if settings.SEND_EMAIL_VIA_MAILTO:
                mailto_links = lunchclub.mail.make_mailto_links(messages)
                return self.render_to_response(self.get_context_data(
                    form=fresh_form, mailto_links=mailto_links))
            else:
                recipients = [message.to[0] for message in messages]
                logger.info("%s: Send login emails to %s",
                            self.request.user.username,
                            recipients)
                lunchclub.mail.send_messages(messages)

        return self.render_to_response(self.get_context_data(
            form=fresh_form, success=True))


@person_required
class ExpenseCreate(FormView):
    form_class = ExpenseCreateForm
    template_name = 'lunchclub/expensecreate.html'

    def get_form_kwargs(self, **kwargs):
        form_kwargs = super().get_form_kwargs(**kwargs)
        form_kwargs['person'] = self.request.person
        form_kwargs['date'] = timezone.now().date()
        form_kwargs['queryset'] = Person.objects.all()
        return form_kwargs

    def form_valid(self, form):
        logger.info("%s: Create expense %s for %s",
                    self.request.user.username,
                    form.cleaned_data['person'], form.cleaned_data['expense'])
        form.save()
        return redirect('home')


@person_required
class AttendanceToday(FormView):
    form_class = AttendanceTodayForm
    template_name = 'lunchclub/attendancetoday.html'

    def get_form_kwargs(self, **kwargs):
        form_kwargs = super().get_form_kwargs(**kwargs)
        form_kwargs['person'] = self.request.person
        form_kwargs['date'] = timezone.now().date()
        form_kwargs['queryset'] = Person.last_attendance_order()
        return form_kwargs

    def form_valid(self, form):
        logger.info("%s: Today's attendance is %s",
                    self.request.user.username,
                    ', '.join(p.username for p in form.get_selected()))
        form.save()
        return redirect('attendance_today')


@person_required
class AttendanceCreate(FormView):
    form_class = AttendanceCreateForm
    template_name = 'lunchclub/attendancecreate.html'

    def get_month_range(self):
        now = timezone.now()
        earliest = (now.year - 2, now.month)
        current_month = (now.year, now.month)
        return earliest, current_month

    def iter_months(self):
        earliest, current_month = self.get_month_range()
        y, m = current_month
        while (y, m) >= earliest:
            yield (y, m)
            if m == 1:
                y -= 1
                m = 12
            else:
                m -= 1

    def get_month(self):
        form = self.get_month_form()
        return (form.cleaned_data['ym']
                if form.is_valid() else form.initial_month)

    def get_month_form(self):
        current_date = timezone.now().day
        choices = list(self.iter_months())
        initial_month = choices[0] if current_date >= 10 else choices[1]
        return MonthForm(choices=choices, initial_month=initial_month,
                         data=self.request.GET or None)

    def get_dates(self):
        dates = []
        y, m = self.get_month()
        for d in range(1, 32):
            try:
                dt = datetime.date(y, m, d)
            except ValueError:
                break
            dates.append(dt)
        return dates

    def get_form_kwargs(self, **kwargs):
        form_kwargs = super().get_form_kwargs(**kwargs)
        form_kwargs['person'] = self.request.person
        form_kwargs['dates'] = self.get_dates()
        form_kwargs['persons'] = Person.last_attendance_order()
        return form_kwargs

    def form_valid(self, form):
        by_person = {}
        for p, d in form.get_selected():
            by_person.setdefault(p.username, []).append(d.day)
        logger.info("%s: Attendance in %s: %r",
                    self.request.user.username,
                    self.get_month(), by_person)
        form.save()
        return redirect('home')

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        month_form = context_data['month_form'] = self.get_month_form()
        context_data['month'] = month_form.ym_name(self.get_month())
        return context_data


class Submit(View):
    def post(self, request):
        b64data = request.POST.get('payload')
        if b64data is None:
            return HttpResponseBadRequest('Missing "payload" parameter')
        try:
            data = base64.b64decode(b64data.encode('ascii'))
        except (ValueError, UnicodeEncodeError):
            return HttpResponseBadRequest('Invalid base64 data')
        input_mac = data[:64]
        payload = data[64:]
        save_payload = self.parse_payload(payload)
        if save_payload is None:
            print(payload)
            return HttpResponseBadRequest('Failed to parse payload')
        mac = hmac.new(settings.SUBMISSION_KEY,
                       payload,
                       hashlib.sha512).digest()
        if not constant_time_compare(input_mac, mac):
            print(payload, input_mac, mac)
            return HttpResponseBadRequest('MAC failed')

        result = save_payload()
        if isinstance(result, HttpResponse):
            return result
        elif result is None:
            # Return the message that lunchclub2015 expects
            return HttpResponse(json.dumps({'success': True}))
        else:
            return HttpResponseBadRequest(json.dumps({'error': result}))

    def parse_payload(self, payload):
        try:
            payload = payload.decode('ascii')
        except UnicodeDecodeError:
            return

        # Parse payload generated by lunchclub_backend in lunchclub2015
        expense_pattern = (r'^expense\s+(\d+)\s+(\d+)\s+(\d+)\s+' +
                           r'(\d+\.\d+)\s+([a-z0-9]+)$')
        mo = re.match(expense_pattern, payload)
        if mo:
            year, month, day = map(int, mo.group(1, 2, 3))
            date = datetime.date(year, month, day)
            amount = decimal.Decimal(mo.group(4))
            username = mo.group(5)

            def save():
                try:
                    person = Person.objects.get(username=username)
                except Person.DoesNotExist:
                    return '%r does not exist' % (username,)
                existing = Expense.objects.filter(
                    date=date, person=person, amount=amount)
                if existing.exists():
                    return 'Expense already registered'
                Expense.objects.create(
                    date=date, person=person, amount=amount,
                    created_by=person)

            return save

        attendance_pattern = (r'^attendance (\d+)\s+(\d+)\s+([a-z0-9]+)\s+' +
                              r'([a-z0-9]+)((?:\s+\d+)+)$')
        mo = re.match(attendance_pattern, payload)
        if mo:
            year, month = map(int, mo.group(1, 2))
            creator_name, person_name = mo.group(3, 4)
            days = list(map(int, mo.group(5).split()))

            def save():
                try:
                    person = Person.objects.get(username=person_name)
                except Person.DoesNotExist:
                    return '%r does not exist' % (person_name,)
                try:
                    created_by = Person.objects.get(username=creator_name)
                except Person.DoesNotExist:
                    return '%r does not exist' % (creator_name,)
                try:
                    dates = [datetime.date(year, month, d) for d in days]
                except ValueError:
                    return 'Invalid date'
                existing = Attendance.objects.filter(
                    person=person, date__in=dates)
                existing_dates = [e.date for e in existing]
                create = [Attendance(person=person, created_by=created_by,
                                     date=d)
                          for d in sorted(set(dates) - set(existing_dates))]
                Attendance.objects.bulk_create(create)

            return save

        token_pattern = r'^token (\d+)\s+(\d+)\s+(\d+)\s+([a-z0-9]+)$'
        mo = re.match(token_pattern, payload)
        if mo:
            year, month, day = map(int, mo.group(1, 2, 3))
            try:
                ymd = datetime.date(year, month, day)
            except ValueError:
                return 'Invalid date'
            if ymd != datetime.date.today():
                return 'Wrong date'
            username = mo.group(4)

            def save():
                person = Person.get_or_create(username)
                token = AccessToken.get_or_create(person)
                url = token.login_url()
                assert url
                return HttpResponse(json.dumps({'success': True,
                                                'return': url}))

            return save


submit_view = csrf_exempt(Submit.as_view())
