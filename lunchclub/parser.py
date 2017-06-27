import collections
import datetime
import logging

from collections import namedtuple
from decimal import Decimal

from lunchclub import models


logger = logging.getLogger('lunchclub.parser')


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

    @property
    def date(self):
        return datetime.date(*self.ymd)


class Attend(namedtuple('Attend', 'year month day creator uname'), DateMixin):
    pass


class Expense(namedtuple('Expense', 'year month day uname amount'), DateMixin):
    pass


def iterparse_attenddb(s):
    '''
    >>> s = '2017 6 27 foo bar'
    >>> attend, = iterparse_attenddb(s)
    >>> print(attend)
    Attend(year=2017, month=6, day=27, creator='foo', uname='bar')
    '''
    for line in s.splitlines():
        if not line.strip():
            continue
        year, month, day, creator, uname = line.split()
        yield Attend(int(year), int(month), int(day),
                     creator=creator, uname=uname)


def parse_attenddb(s):
    '''
    >>> s = '2017 6 27 foo bar'
    >>> attenddb = parse_attenddb(s)
    >>> attend, = attenddb.values()
    >>> from lunchclub.models import Person
    >>> username_map = {u: Person(username=u) for u in 'foo bar'.split()}
    >>> get_date = date_cleaner(attenddb.keys())
    >>> attend.resolve(get_date, username_map)
    >>> attend.date
    datetime.date(2017, 6, 27)
    >>> print(attend.created_by)
    foo
    >>> print(attend.person)
    bar
    '''
    result = collections.OrderedDict()
    for a in iterparse_attenddb(s):
        if a in result:
            raise ValueError("Duplicate line: %r" % (a,))
        result[a] = models.Attendance.from_tuple(a)
    return result


def get_attenddb_from_model():
    qs = models.Attendance.objects.all().select_related()
    result = collections.OrderedDict()
    for attend in qs:
        a = Attend(a.date.year, a.date.month, a.date.day,
                   a.created_by.username, a.person.username)
        result[a] = attend
    return result


def iterparse_expensedb(s):
    '''
    >>> s = '2017 6 27 6.24 bar'
    >>> expense, = iterparse_expensedb(s)
    >>> print(expense)
    Expense(year=2017, month=6, day=27, uname='bar', amount=Decimal('6.24'))
    '''
    for line in s.splitlines():
        if not line.strip():
            continue
        year, month, day, amount, uname = line.split()
        yield Expense(int(year), int(month), int(day),
                      amount=Decimal(amount), uname=uname)


def parse_expensedb(s):
    '''
    >>> s = '2017 6 27 6.24 bar'
    >>> expensedb = parse_expensedb(s)
    >>> expense, = expensedb.values()
    >>> from lunchclub.models import Person
    >>> username_map = {'bar': Person(username='bar')}
    >>> get_date = date_cleaner(expensedb.keys())
    >>> expense.resolve(get_date, username_map)
    >>> expense.date
    datetime.date(2017, 6, 27)
    >>> print(expense.created_by)
    bar
    >>> print(expense.person)
    bar
    '''
    result = collections.OrderedDict()
    for e in iterparse_expensedb(s):
        if e in result:
            raise ValueError("Duplicate line: %r" % (e,))
        result[e] = models.Expense.from_tuple(e)
    return result


def get_expensedb_from_model():
    result = collections.OrderedDict()
    qs = models.Expense.objects.all().select_related()
    for expense in qs:
        e = Expense(e.date.year, e.date.month, e.date.day,
                    e.person.username, e.amount)
        result[e] = expense
    return result


def get_or_create_users(usernames):
    username_map = {username: models.Person(username=username, balance=0)
                    for username in usernames}

    def save():
        qs = models.Person.objects.filter(username__in=usernames)
        for u in qs:
            username_map.pop(u.username).pk = u.pk
        new_users = list(username_map.values())
        if username_map:
            logger.debug(
                "Create %s new users: %s",
                len(new_users), ', '.join(u.username for u in new_users))
            for u in new_users:
                u.save()

    return username_map, save


def date_cleaner(objects):
    days = {}
    for o in objects:
        days.setdefault((o.uname, o.ym), set()).add(o.day)

    def get_date(o):
        try:
            d = o.date
        except ValueError:
            # day out of range for month
            day = next(n for n in range(1, 31)
                       if n not in days[o.uname, o.ym])
            days[o.uname, o.ym].add(day)
            logger.debug("%s %s-%s-%s is invalid; use %s instead",
                         o.uname, o.year, o.month, o.day, day)
            d = datetime.date(o.year, o.month, day)
        return d

    return get_date


def import_attendance(s):
    input_attendance = frozenset(parse_attenddb(s))
    existing_attendance = frozenset(get_attenddb_from_model())
    get_date = date_cleaner(input_attendance | existing_attendance)
    new_attendance = input_attendance - existing_attendance
    usernames = frozenset(u for a in new_attendance
                          for u in (a.creator, a.uname))
    username_map, person_save = get_or_create_users(usernames)
    attendances = []
    for a in new_attendance:
        attendances.append(models.Attendance(
            date=get_date(a), person=username_map[a.uname],
            created_by=username_map[a.creator]))

    def save():
        person_save()
        for a in attendances:
            a.person = a.person  # Update person_id
            a.created_by = a.created_by  # Update created_by_id
        if attendances:
            logger.debug("Create %s new attendances", len(attendances))
            models.Attendance.objects.bulk_create(attendances)

    return attendances, save


def import_expenses(s):
    input_expenses = frozenset(parse_expensedb(s))
    existing_expenses = frozenset(get_expensedb_from_model())
    get_date = date_cleaner(input_expenses | existing_expenses)
    new_expenses = input_expenses - existing_expenses
    usernames = frozenset(e.uname for e in new_expenses)
    username_map, person_save = get_or_create_users(usernames)

    expenses = []
    for e in new_expenses:
        expenses.append(models.Expense(
            date=get_date(e), person=username_map[e.uname],
            created_by=username_map[e.uname], amount=e.amount))

    def save():
        person_save()
        for e in expenses:
            e.person = e.person  # Update person_id
            e.created_by = e.created_by  # Update created_by_id
        if expenses:
            logger.debug("Create %s new expenses", len(expenses))
            models.Expense.objects.bulk_create(expenses)

    return expenses, save
