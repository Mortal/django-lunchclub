import random
import string
import decimal
import collections

from django.db import models
from django.db.models import Sum
from django.contrib.auth.models import User
from lunchclub.fields import AmountField


class Person(models.Model):
    user = models.ForeignKey(User, null=True, blank=True)
    username = models.CharField(max_length=30, unique=True)
    balance = AmountField()
    created_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.username

    class Meta:
        ordering = ['username']


class Attendance(models.Model):
    date = models.DateField()
    person = models.ForeignKey(Person)
    created_by = models.ForeignKey(Person, related_name='+')
    created_time = models.DateTimeField(auto_now_add=True)

    @property
    def month(self):
        return (self.date.year, self.date.month)

    class Meta:
        ordering = ['date', 'person']


class Expense(models.Model):
    date = models.DateField()
    person = models.ForeignKey(Person)
    created_by = models.ForeignKey(Person, related_name='+')
    created_time = models.DateTimeField(auto_now_add=True)
    amount = AmountField()

    @property
    def month(self):
        return (self.date.year, self.date.month)

    class Meta:
        ordering = ['date', 'person']


class AccessToken(models.Model):
    person = models.ForeignKey(Person)
    token = models.CharField(max_length=200)
    created_time = models.DateTimeField(auto_now_add=True)
    use_count = models.IntegerField(default=0)

    @classmethod
    def fresh(cls, person):
        rng = random.SystemRandom()
        N = cls._meta.get_field('token').max_length
        chars = string.ascii_letters + string.digits
        token = ''.join(rng.choice(chars) for _ in range(N))
        return cls(person=person, token=token)


def safediv(x, y):
    return float('inf') if y == 0 else x / y


def compute_meal_prices(expense_qs, attendance_qs):
    months = collections.defaultdict(lambda: ([], []))
    for o in expense_qs:
        months[o.month][0].append(o)
    for o in attendance_qs:
        months[o.month][1].append(o)
    return {month: safediv(sum(e.amount for e in expenses), len(attendances))
            for month, (expenses, attendances) in months.items()}


def compute_month_balances(expense_qs, attendance_qs, meal_prices=None):
    if meal_prices is None:
        meal_prices = compute_meal_prices(expense_qs, attendance_qs)
    # balances[p][m] == b means person p has balance b in month m
    # Note that we mutate p.balance, so we must have only one instance
    # of each Person.
    balances = collections.defaultdict(
        lambda: collections.defaultdict(decimal.Decimal))
    for a in attendance_qs:
        balances[a.person][a.month] -= meal_prices[a.month]
    for e in expense_qs:
        balances[e.person][e.month] += e.amount
    return meal_prices, balances


def compute_all_meal_prices():
    return compute_meal_prices(Expense.objects.all(), Attendance.objects.all())


def recompute_balances():
    expense_qs = Expense.objects.all()
    attendance_qs = Attendance.objects.all()
    meal_prices, balances = compute_month_balances(expense_qs,
                                                   attendance_qs)
    for p, a in balances.items():
        p.balance = sum(a.values())
        p.save()


def get_average_meal_price():
    expense_qs = Expense.objects.all()
    attendance_qs = Attendance.objects.all()
    expense_sum = expense_qs.aggregate(s=Sum('amount'))['s']
    attendance_count = attendance_qs.count()
    return expense_sum / attendance_count if attendance_count else 0
