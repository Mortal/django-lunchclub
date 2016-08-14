from collections import namedtuple
from decimal import Decimal

from lunchclub import models


class YearMonth(namedtuple('YearMonth', 'year month')):
    @property
    def ym(self):
        return self


class YearMonthDay(namedtuple('YearMonthDay', 'year month day')):
    @property
    def ym(self):
        return YearMonth(self.year, self.month)

    @property
    def ymd(self):
        return self


class DateMixin:
    @property
    def ym(self):
        return YearMonth(self.year, self.month)

    @property
    def ymd(self):
        return YearMonthDay(self.year, self.month, self.day)


class Attend(namedtuple('Attend', 'year month day creator uname'), DateMixin):
    pass


class Expense(namedtuple('Expense', 'year month day uname amount'), DateMixin):
    pass


def parse_attenddb(s):
    for line in s.splitlines():
        if not line.strip():
            continue
        year, month, day, creator, uname = line.split()
        yield Attend(int(year), int(month), int(day),
                     creator=creator, uname=uname)


def get_attenddb_from_model():
    qs = models.Attendance.objects.all().select_related()
    return (Attend(a.date.year, a.date.month, a.date.day,
                   a.created_by.username, a.person.username)
            for a in qs)


def parse_expensedb(s):
    for line in s.splitlines():
        if not line.strip():
            continue
        year, month, day, amount, uname = line.split()
        yield Expense(int(year), int(month), int(day),
                      amount=Decimal(amount), uname=uname)


def get_expensedb_from_model():
    qs = models.Expense.objects.all().select_related()
    return (Expense(e.date.year, e.date.month, e.date.day,
                    e.created_by.username, e.amount)
            for e in qs)


def import_attendance(s):
    input_attendance = frozenset(parse_attenddb(s))
    existing_attendance = frozenset(get_attenddb_from_model())
    new_attendance = input_attendance - existing_attendance
    usernames = frozenset(u for a in new_attendance
                          for u in (a.creator, a.uname))
    username_qs = models.Person.objects.filter(username__in=usernames)
    username_map = {p.username: p for p in username_qs}
    new_users = []
    for username in usernames - frozenset(username_map):
        p = models.Person(username=username
    for line in s.splitlines():
