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


class Attend(namedtuple('Attend', 'year month day uname'), DateMixin):
    pass


class Expense(namedtuple('Expense', 'year month day uname amount'), DateMixin):
    pass


def parse_attenddb(s):
    for line in s.splitlines():
        if not line.strip():
            continue
        year, month, day, _, uname = line.split()
        yield Attend(int(year), int(month), int(day),
                     uname=uname)


def parse_expensedb(s):
    for line in s.splitlines():
        if not line.strip():
            continue
        year, month, day, amount, uname = line.split()
        yield Expense(int(year), int(month), int(day),
                      amount=Decimal(amount), uname=uname)


def parse_attenddb(s):
    for line in s.splitlines():
