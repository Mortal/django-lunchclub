import logging

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone, dateparse
from django.core.exceptions import ValidationError


logger = logging.getLogger('lunchclub')


class Calendar(models.Model):
    name = models.CharField(max_length=200)
    created_time = models.DateTimeField()

    def __str__(self):
        return self.name

    def today_items(self):
        return CalendarItem.existing_for_date(calendar=self,
                                              date=timezone.now().date())

    @classmethod
    def get_or_create(cls, name):
        try:
            return cls.objects.get(name=name)
        except cls.DoesNotExist:
            return cls.objects.create(name=name,
                                      created_time=timezone.now())


class CalendarItem(models.Model):
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE)
    subject = models.CharField(max_length=200)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    date = models.DateField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL,
                                   null=True, blank=True)
    created_time = models.DateTimeField()

    def __str__(self):
        return '%s-%s %s' % (
            self.start_time.strftime('%H:%M'),
            self.end_time.strftime('%H:%M'),
            self.subject,
        )

    @classmethod
    def existing_for_date(cls, calendar, date):
        return list(cls.objects.filter(calendar=calendar, date=date))

    @classmethod
    def update_for_date(cls, calendar, items, date, created_by):
        delete = []
        existing = {}
        for o in cls.existing_for_date(calendar, date):
            ex = existing.setdefault((o.subject, o.start_time, o.end_time), o)
            if o is not ex:
                # Duplicate
                delete.append(o)
        new = []
        now = timezone.now()
        for item in items:
            try:
                subject = item['subject']
                start_str = item['start']
                end_str = item['end']
            except KeyError as exn:
                raise ValidationError('Missing key %s' % exn)
            start = dateparse.parse_datetime(start_str)
            if not start:
                raise ValidationError(start_str)
            end = dateparse.parse_datetime(end_str)
            if not end:
                raise ValidationError(end_str)
            o = cls(calendar=calendar,
                    subject=subject, start_time=start, end_time=end,
                    date=date, created_by=created_by, created_time=now)
            o.clean()
            ex = existing.setdefault((subject, start, end), o)
            if ex is o:
                new.append(o)
        for o in delete:
            logger.info('%s: Delete %r', created_by, o)
            o.delete()
        for o in new:
            o.save()
            logger.info('%s: Create %r', created_by, o)
