import datetime

from django.shortcuts import redirect
from django.views.generic import TemplateView, FormView, View, ListView
from django.db.models import Q, Max
from django.contrib.auth import authenticate, login
from django.http import HttpResponse

from lunchclub.forms import ImportForm, AccessTokenForm
from lunchclub.models import Person, Expense, Attendance, AccessToken
from lunchclub.models import get_average_meal_price, compute_month_balances


def get_months():
    months = 10
    d = datetime.date.today()
    ym = d.year * 12 + d.month - 1
    yms = (divmod(ym - s, 12) for s in range(months))
    return [(y, m + 1) for y, m in yms]


class Home(TemplateView):
    template_name = 'lunchclub/home.html'

    def get_context_data(self, **kwargs):
        data = super(Home, self).get_context_data(**kwargs)
        months = get_months()
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
        person_qs = person_qs.filter(last_active__gte=earliest_date)
        person_qs = person_qs.prefetch_related('attendance_set', 'expense_set')
        person_qs = person_qs.order_by('balance')
        for person in person_qs:
            person_months = []
            for (y, m) in months:
                attendance_count = sum(1 for a in person.attendance_set.all()
                                       if a.month == (y, m))
                expense_sum = sum(e.amount for e in person.expense_set.all()
                                  if e.month == (y, m))
                month_balance = float(meal_prices[y, m] * attendance_count)
                month_balance -= float(expense_sum)
                person_months.append(dict(balance=month_balance))
            person_data.append(dict(
                username=person.username, balance=person.balance,
                months=person_months))

        data['persons'] = person_data
        return data


class Import(FormView):
    form_class = ImportForm
    template_name = 'lunchclub/import.html'

    def form_valid(self, form):
        form.save()
        return redirect('home')


class Login(View):
    def get(self, request):
        token = request.GET.get('token', '')
        user = authenticate(token=token)
        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            return HttpResponse('Invalid token')


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
