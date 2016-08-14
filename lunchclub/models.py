import decimal
import collections

from django.db import models
from lunchclub.fields import AmountField


class Person(models.Model):
    username = models.CharField(max_length=30)
    balance = AmountField()
    created_time = models.DateTimeField(auto_now_add=True)


class Attendance(models.Model):
    date = models.DateField()
    person = models.ForeignKey(Person)
    created_by = models.ForeignKey(Person)
    created_time = models.DateTimeField(auto_now_add=True)

    @property
    def month(self):
        return (self.date.year, self.date.month)


class Expense(models.Model):
    date = models.DateField()
    person = models.ForeignKey(Person)
    created_by = models.ForeignKey(Person)
    created_time = models.DateTimeField(auto_now_add=True)
    amount = AmountField()

    @property
    def month(self):
        return (self.date.year, self.date.month)


def compute_meal_prices(expense_qs, attendance_qs):
    months = collections.defaultdict(lambda: ([], []))
    for o in expense_qs:
        months[o.month][0].append(o)
    for o in attendance_qs:
        months[o.month][1].append(o)
    return {month: sum(e.amount for e in expenses) / len(attendances)
            for month, (expenses, attendances) in months.items()}


def compute_all_meal_prices():
    return compute_meal_prices(Expense.objects.all(), Attendance.objects.all())


def recompute_balances():
    expense_qs = Expense.objects.all()
    attendance_qs = Attendance.objects.all()
    meal_prices = compute_meal_prices(expense_qs, attendance_qs)
    balances = collections.defaultdict(decimal.Decimal)
    for a in attendance_qs:
        balances[a.person] -= meal_prices[a.month]
    for e in expense_qs:
        balances[e.person] += e.amount
    for p, a in balances.items():
        p.balance = a
        p.save()
