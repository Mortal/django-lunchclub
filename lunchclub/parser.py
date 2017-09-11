import collections
import datetime
import logging

from collections import namedtuple
from decimal import Decimal

from lunchclub import models


logger = logging.getLogger('lunchclub')


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

    @property
    def day_invalid(self):
        try:
            self.date
            return False
        except ValueError:
            return True


class Attend(namedtuple('Attend', 'year month day creator uname'), DateMixin):
    def replace(self, day):
        return type(self)(year=self.year, month=self.month, day=day,
                          creator=self.creator, uname=self.uname)


class Expense(namedtuple('Expense', 'year month day uname amount'), DateMixin):
    def replace(self, day):
        return type(self)(year=self.year, month=self.month, day=day,
                          uname=self.uname, amount=self.amount)


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
        # Ignore any duplicates since they were silently discarded
        # in the old system.
        # if a in result:
        #     raise ValueError("Duplicate line: %r" % (a,))
        result[a] = models.Attendance.from_tuple(a)
    return result


def iter_unparse_attenddb(attendance):
    for a in attendance:
        yield ('%4d %2d %2d %s %s' %
               (a.year, a.month, a.day, a.creator, a.uname))


def unparse_attenddb(attendance):
    return '\n'.join(iter_unparse_attenddb(attendance))


def get_attenddb_from_model():
    qs = models.Attendance.objects.all().select_related()
    result = collections.OrderedDict()
    for attend in qs:
        a = Attend(attend.date.year, attend.date.month, attend.date.day,
                   attend.created_by.username, attend.person.username)
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


def iter_unparse_expensedb(expenses):
    for e in expenses:
        yield ('%04d %02d %02d %.2f %s ' %
               (e.year, e.month, e.day, e.amount, e.uname))


def unparse_expensedb(expenses):
    return '\n'.join(iter_unparse_expensedb(expenses))


def get_expensedb_from_model():
    result = collections.OrderedDict()
    qs = models.Expense.objects.all().select_related()
    for expense in qs:
        e = Expense(expense.date.year, expense.date.month, expense.date.day,
                    expense.person.username, expense.amount)
        result[e] = expense
    return result


def get_or_create_users(usernames):
    '''
    Return a dict mapping usernames to Person objects
    and a save() function to save new Persons.
    '''
    username_map = {p.username: p
                    for p in models.Person.objects.all()}
    for u in usernames:
        username_map.setdefault(u, models.Person(username=u, balance=0))

    def save():
        # Between the call to get_or_create_users() and the call to save(),
        # another save() function might have created Person objects.
        # We must avoid creating duplicate Person objects in that case.
        for p in models.Person.objects.all():
            # See if username_map contained a placeholder with this username.
            previous = username_map.get(p.username)
            if previous is not None and previous.pk is None:
                # Update old Person object with new pk
                # to avoid creating a duplicate.
                previous.pk = p.pk

        new_persons = []
        for p in username_map.values():
            if p.pk is None:
                p.clean()
                new_persons.append(p)

        if new_persons:
            logger.debug(
                "Create %s new Person objects: %s",
                len(new_persons), ', '.join(p.username for p in new_persons))
            for p in new_persons:
                p.save()

    return username_map, save


def date_cleaner(objects):
    '''
    Given a collection of namedtuples with "uname", "ym" and "day" fields,
    and "date" and "ymd" properties,
    return a function mapping a namedtuple to a valid date.

    If the "ym"-"day" fields don't correspond to a valid date,
    a free spare date for the user in the month is returned instead.

    The function ensures that no user has two distinct "ymd"-values map to
    the same datetime.date object. This is useful for attendance computation.
    '''
    days = {}
    for o in objects:
        days.setdefault((o.uname, o.ym), set()).add(o.day)

    # Maps invalid (uname, ymd) to a datetime.date object.
    dates = {}

    def get_date(o):
        if not o.day_invalid:
            return o.date

        # Try returning a cached replacement date.
        try:
            return dates[o.uname, o.ymd]
        except KeyError:
            pass

        # datetime.date() raised ValueError due to an invalid day in the
        # month. Pick another spare day in the month.
        day = next(n for n in range(1, 31)
                   if n not in days[o.uname, o.ym])
        days[o.uname, o.ym].add(day)
        logger.debug("%s %s-%s-%s is invalid; use %s instead",
                     o.uname, o.year, o.month, o.day, day)
        d = datetime.date(o.year, o.month, day)
        # Cache replacement date.
        dates[o.uname, o.ymd] = d
        return d

    return get_date


def match_invalid_days(old, new):
    only_old = old.keys() - new.keys()
    only_new = new.keys() - old.keys()

    old_map = {}
    for o in only_old:
        old_map.setdefault((o.uname, o.ym), []).append(o)
    new_keys = set(new.keys())
    replacements = []
    for key in only_new:
        if not key.day_invalid:
            continue
        olds = old_map.get((key.uname, key.ym), [])
        try:
            matching = next(a for a in olds if key.replace(day=a.day) == a)
        except StopIteration:
            continue
        olds.remove(matching)
        replacements.append((key, matching.day))
    for key, day in replacements:
        new_key = key.replace(day=day)
        if new_key in new:
            raise AssertionError()
        o = new.pop(key)
        new[new_key] = type(o).from_tuple(new_key)

    return new.keys() - old.keys(), old.keys() - new.keys()


def dbdiff(old, new, has_creator):
    for o in old.values():
        if o.pk is None:
            raise ValueError("Old item has no PK!")
    for o in new.values():
        if o.pk is not None:
            raise ValueError("New item has a PK!")
    remove = old.keys() - new.keys()
    create = new.keys() - old.keys()

    if any(o.day_invalid for o in create):
        create, remove = match_invalid_days(old, new)

    get_date = date_cleaner(old.keys() | new.keys())
    usernames = frozenset(a.uname for a in create)
    if has_creator:
        usernames |= frozenset(a.creator for a in create)
    username_map, person_save = get_or_create_users(usernames)
    for a in create:
        new[a].resolve(get_date, username_map)
        new[a].clean()

    def save():
        person_save()

        if remove:
            type_name = type(next(iter(remove))).__name__
            logger.debug("Delete %s %s", len(remove), type_name)
        for a in remove:
            old[a].delete()

        if create:
            type_name = type(next(iter(create))).__name__
            logger.debug("Save %s %s", len(create), type_name)
        for a in create:
            new[a].person = new[a].person  # Update person_id
            new[a].created_by = new[a].created_by  # Update created_by_id
            new[a].save()

    return create, remove, save


def diff_attendance(old, new):
    return dbdiff(old, new, has_creator=True)


def diff_expense(old, new):
    return dbdiff(old, new, has_creator=False)
