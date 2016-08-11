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
