import re
import random
import string
import decimal
import datetime
import collections

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum, Q, Max
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings
from django.core.urlresolvers import reverse
from lunchclub.fields import AmountField


def username_validate(v):
    if not re.match(r'^[a-z]*$', v):
        raise ValidationError('Username must consist of only a-z')


class Person(models.Model):
    user = models.ForeignKey(User, null=True, blank=True)
    username = models.CharField(max_length=30, unique=True,
                                validators=[username_validate])
    display_name = models.CharField(max_length=100)
    balance = AmountField()
    created_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.display_name

    class Meta:
        ordering = ['username']

    @classmethod
    def get_or_create(cls, username):
        try:
            return Person.objects.get(username=username)
        except Person.DoesNotExist:
            p = Person(username=username, balance=0)
            p.clean()
            p.save()
            return p

    def get_or_create_user(self):
        if self.user is not None:
            return self.user
        user = User(username=self.username)
        user.save()
        self.user = user  # Set self.user_id
        self.save()
        return self.user

    @classmethod
    def annotate_active(cls, expense=True, attendance=True):
        qs = Person.objects.all()
        if expense:
            qs = qs.annotate(last_expense=Max('expense__date'))
        if attendance:
            qs = qs.annotate(last_attendance=Max('attendance__date'))
        return qs

    @classmethod
    def last_attendance_order(cls):
        qs = cls.annotate_active(expense=False, attendance=True)
        return qs.order_by('-last_attendance', 'username')

    @classmethod
    def filter_active(cls, inactive_months=6, today=None):
        if today is None:
            today = timezone.now().date()
        ym = 12*today.year + today.month
        earliest_ym = ym - inactive_months + 1
        earliest_y, earliest_m = divmod(earliest_ym, 12)
        earliest_date = datetime.date(earliest_y, earliest_m, 1)

        qs = cls.annotate_active()
        qs = qs.filter(
            Q(last_expense__gte=earliest_date) |
            Q(last_attendance__gte=earliest_date))
        return qs

    def clean(self):
        if not self.display_name:
            self.display_name = self.username


class Attendance(models.Model):
    date = models.DateField()
    person = models.ForeignKey(Person)
    created_by = models.ForeignKey(Person, related_name='+')
    created_time = models.DateTimeField(auto_now_add=True)

    @classmethod
    def from_tuple(cls, t):
        # Ensure that t has both a uname and a creator.
        if not hasattr(t, 'uname') or not hasattr(t, 'creator'):
            raise TypeError(type(t).__name__)
        result = cls()
        result.source_tuple = t
        return result

    def resolve(self, get_date, username_map):
        if self.date is None:
            self.date = get_date(self.source_tuple)
        # Use getattr() since self.person would raise AttributeError when None.
        if getattr(self, 'person', None) is None:
            self.person = username_map[self.source_tuple.uname]
        if getattr(self, 'created_by', None) is None:
            self.created_by = username_map[self.source_tuple.creator]

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

    @classmethod
    def from_tuple(cls, t):
        # Ensure that t has a uname but no creator.
        if not hasattr(t, 'uname') or hasattr(t, 'creator'):
            raise TypeError(type(t).__name__)
        result = cls()
        result.source_tuple = t
        result.amount = decimal.Decimal(t.amount)
        return result

    def resolve(self, get_date, username_map):
        if self.date is None:
            self.date = get_date(self.source_tuple)
        # Use getattr() since self.person would raise AttributeError when None.
        if getattr(self, 'person', None) is None:
            self.person = username_map[self.source_tuple.uname]
        if getattr(self, 'created_by', None) is None:
            self.created_by = username_map[self.source_tuple.uname]

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
    def get_or_create(cls, person):
        qs = AccessToken.objects.filter(person=person)
        qs = qs.order_by('-created_time')
        try:
            return qs[0]
        except IndexError:
            r = cls.fresh(person)
            r.save()
            return r

    def login_url(self):
        if not self.token:
            return ''
        return (settings.SITE_PREFIX + reverse('login') +
                '?token=' + self.token)

    @classmethod
    def all_as_dict(self):
        token_qs = AccessToken.objects.all()
        tokens = {}
        for t in token_qs:
            ex = tokens.setdefault(t.person, t)
            if ex.created_time < t.created_time:
                # Retain token with latest created_time
                tokens[t.person] = t
        return tokens

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
    # Count attendances using a set in order to remove duplicate
    # (date,person)-pairs.
    months = collections.defaultdict(lambda: ([], set()))
    for o in expense_qs:
        months[o.month][0].append(o)
    for o in attendance_qs:
        months[o.month][1].add((o.date, o.person))
    return {month: safediv(sum(e.amount for e in expenses),
                           decimal.Decimal(len(attendances)))
            for month, (expenses, attendances) in months.items()}


def compute_month_balances(expense_qs, attendance_qs, meal_prices=None):
    if meal_prices is None:
        meal_prices = compute_meal_prices(expense_qs, attendance_qs)
    # balances[p][m] == b means person p has balance b in month m
    # Note that we mutate p.balance, so we must have only one instance
    # of each Person.
    balances = collections.defaultdict(
        lambda: collections.defaultdict(decimal.Decimal))
    attendances = set((a.person, a.month, a.date) for a in attendance_qs)
    for person, month, date in attendances:
        balances[person][month] -= meal_prices[month]
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
    # If a Person has no attendance/expenses, they aren't in "balances".
    # Set their balance to 0 in this case.
    Person.objects.all().update(balance=0)
    for p, a in balances.items():
        p.balance = sum(a.values())
        p.save()


def get_average_meal_price():
    expense_qs = Expense.objects.all()
    attendance_qs = Attendance.objects.all()
    expense_sum = expense_qs.aggregate(s=Sum('amount'))['s']
    attendance_count = attendance_qs.count()
    return expense_sum / attendance_count if attendance_count else 0


class ShoppingListItem(models.Model):
    created_by = models.ForeignKey(Person, on_delete=models.SET_NULL,
                                   blank=True, null=True, related_name='+')
    created_time = models.DateTimeField(auto_now_add=True)
    deleted_by = models.ForeignKey(Person, on_delete=models.SET_NULL,
                                   blank=True, null=True, related_name='+')
    deleted_time = models.DateTimeField(blank=True, null=True)
    name = models.CharField(max_length=100)


class Announce(models.Model):
    WHO = 'who'
    WHO_LABEL = 'Initiate protocol!'
    WAY = 'way'
    WAY_LABEL = 'Tell all someone is getting food'
    NOW = 'now'
    NOW_LABEL = 'Tell all there\'s lunch now'

    KIND = [
        (WHO, WHO_LABEL),
        (WAY, WAY_LABEL),
        (NOW, NOW_LABEL),
    ]

    NOTIFICATION = {
        WHO: ('Lunch?', '%s asks: Do you want lunch?'),
        WAY: ('Lunch soon', '%s: Someone is getting food'),
        NOW: ('Food!', '%s says: There\'s food now!'),
    }

    created_time = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Person, on_delete=models.CASCADE)
    kind = models.CharField(max_length=10, choices=KIND)

    def notification(self):
        title, body = self.NOTIFICATION[self.kind]
        return dict(title=title, body=body % str(self.created_by),
                    created_time_epoch_ms=dt_to_epoch_ms(self.created_time))

    @classmethod
    def current_notification_for_date(cls, today):
        today_dt = datetime.datetime.combine(today, datetime.time())
        tomorrow_date = today + datetime.timedelta(1)
        tomorrow_dt = datetime.datetime.combine(tomorrow_date, datetime.time())
        qs = cls.objects.filter(created_time__gte=today_dt,
                                created_time__lt=tomorrow_dt)
        qs = qs.order_by('-created_time')
        try:
            o = qs[0]
        except IndexError:
            return None
        return o.notification()

    @classmethod
    def create(cls, time, person, kind):
        if kind not in (k for k, l in cls.KIND):
            raise ValueError(kind)
        o = cls.objects.create(created_time=time, created_by=person, kind=kind)
        # Delay import to avoid import cycle
        import lunchclub.today
        lunchclub.today.send_notification(o)


def dt_to_epoch_ms(dt: datetime.datetime):
    epoch = dt.timestamp()
    return int(epoch * 1e3)


class Rsvp(models.Model):
    YES = 'yes'
    YES_LABEL = 'I want lunchclub lunch'
    OWN = 'own'
    OWN_LABEL = 'I bring my own lunch'
    NO = 'no'
    NO_LABEL = 'I have other plans'

    STATUS = [
        (YES, YES_LABEL),
        (OWN, OWN_LABEL),
        (NO, NO_LABEL),
    ]
    date = models.DateField()
    created_time = models.DateTimeField(auto_now_add=True)
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS)

    class Meta:
        unique_together = [('date', 'person')]

    @classmethod
    def data_for_date(cls, date):
        qs = cls.objects.filter(date=date).select_related()
        return [{'username': o.person.username,
                 'display_name': o.person.display_name,
                 'status': o.status,
                 'created_time_epoch_ms': dt_to_epoch_ms(o.created_time)}
                for o in qs]

    @classmethod
    def set_rsvp(cls, date, person, status):
        if status not in (k for k, l in cls.STATUS):
            raise ValueError(status)
        try:
            o = cls.objects.get(date=date, person=person)
        except cls.DoesNotExist:
            o = cls(date=date, person=person)
        o.status = status
        o.save()
        # Delay import to avoid import cycle
        import lunchclub.today
        lunchclub.today.send_current_rsvp()
