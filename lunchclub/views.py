import logging
import datetime
import functools

from django.utils.decorators import method_decorator
from django.utils import timezone
from django.shortcuts import redirect
from django.views.generic import TemplateView, FormView, View
from django.http import HttpResponse
from django.views.defaults import permission_denied
from django.db.models import Q, F
from django.contrib.auth import authenticate, login, logout

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


logger = logging.getLogger(__name__)


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
        mailto_links = form.save()
        if mailto_links is not None:
            return self.render_to_response(self.get_context_data(
                form=form, mailto_links=mailto_links))
        return self.render_to_response(self.get_context_data(
            form=form, success=True))


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
        form.save()
        return redirect('home')

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        month_form = context_data['month_form'] = self.get_month_form()
        context_data['month'] = month_form.ym_name(month_form.initial_month)
        return context_data
