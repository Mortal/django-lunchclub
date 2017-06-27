import logging
import datetime

from django.shortcuts import redirect
from django.views.generic import TemplateView, FormView, View, ListView
from django.db.models import Q, Max, F
from django.contrib.auth import authenticate, login
from django.http import HttpResponse

from lunchclub.forms import DatabaseBulkEditForm, AccessTokenForm, SearchForm
from lunchclub.models import Person, Expense, Attendance, AccessToken
from lunchclub.models import get_average_meal_price, compute_month_balances
from lunchclub.parser import get_attenddb_from_model, get_expensedb_from_model


logger = logging.getLogger(__name__)


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
        person_qs = Person.objects.all()
        person_qs = person_qs.annotate(last_active=Max('expense__date'))
        if not search_data['show_all']:
            person_qs = person_qs.filter(last_active__gte=earliest_date)
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


class DatabaseBulkEdit(FormView):
    form_class = DatabaseBulkEditForm
    template_name = 'lunchclub/database_bulk_edit.html'

    def get_form_kwargs(self, **kwargs):
        form_kwargs = super().get_form_kwargs(**kwargs)
        form_kwargs['attenddb'] = get_attenddb_from_model()
        form_kwargs['expensedb'] = get_expensedb_from_model()
        return form_kwargs

    def post(self, request, *args, **kwargs):
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
        logger.info("Logout %s", request.user, token.pk)
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
            return self.render_to_response(dict(error='Invalid token specified'))
        if request.user == user:
            return redirect('home')
        self.kwargs['user'] = kwargs['user'] = user
        self.kwargs['token'] = kwargs['token'] = token
        return super(Login, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        data = super(Login, self).get_context_data(**kwargs)
        data['user'] = self.kwargs['user']
        return data

    def post(self, request, user, token):
        logger.info("Login %s with token %s", user, token[20:])
        qs = AccessToken.objects.filter(token=token)
        qs.update(use_count=F('use_count') + 1)
        login(request, user)
        return redirect('home')


class AccessTokenList(ListView):
    queryset = AccessToken.objects.all()
    template_name = 'lunchclub/accesstoken_list.html'


class AccessTokenCreate(FormView):
    form_class = AccessTokenForm
    template_name = 'lunchclub/accesstoken_create.html'

    def form_valid(self, form):
        token = AccessToken.fresh(form.cleaned_data['person'])
        token.save()
        return redirect('accesstoken_list')
