import json
import logging

from django import forms
from django.contrib.auth.models import User
from django.conf import settings

from lunchclub.models import (
    recompute_balances, AccessToken, Expense, Attendance,
    Person,
)
from lunchclub.parser import (
    parse_attenddb, parse_expensedb,
    unparse_attenddb, unparse_expensedb,
    get_attenddb_from_model, get_expensedb_from_model,
    diff_attendance, diff_expense,
)
import lunchclub.mail
import datetime
import re
import decimal


logger = logging.getLogger(__name__)


class DatabaseBulkEditForm(forms.Form):
    def __init__(self, **kwargs):
        self.attenddb = kwargs.pop('attenddb')
        self.expensedb = kwargs.pop('expensedb')
        super().__init__(**kwargs)
        self.fields['initial'].initial = json.dumps({
            'expense_pks': [o.pk for o in self.expensedb.values()],
            'attendance_pks': [o.pk for o in self.attenddb.values()],
        })
        self.fields['attendance'].initial = unparse_attenddb(self.attenddb)
        self.fields['expense'].initial = unparse_expensedb(self.expensedb)

    initial = forms.CharField(widget=forms.HiddenInput)
    attendance = forms.CharField(widget=forms.Textarea, required=False)
    expense = forms.CharField(widget=forms.Textarea, required=False)

    def clean_attendance(self):
        return parse_attenddb(self.cleaned_data['attendance'])

    def clean_expense(self):
        return parse_expensedb(self.cleaned_data['expense'])

    def clean_initial(self):
        try:
            o = json.loads(self.cleaned_data['initial'])
        except ValueError:
            raise forms.ValidationError('Invalid JSON in hidden initial field')
        if not isinstance(o, dict):
            raise forms.ValidationError(
                'Hidden initial field is not a JSON dict')
        return o

    def clean(self):
        if 'initial' in self.cleaned_data:
            apks = self.cleaned_data['initial'].get('attendance_pks')
            epks = self.cleaned_data['initial'].get('expense_pks')
            init = json.loads(self.fields['initial'].initial)
            if apks != init['attendance_pks'] or epks != init['expense_pks']:
                raise forms.ValidationError(
                    'Your form is expired as the database ' +
                    'has changed in the meantime.')
        if 'attendance' in self.cleaned_data:
            self.cleaned_data['diff_attendance'] = diff_attendance(
                get_attenddb_from_model(), self.cleaned_data['attendance'])
        if 'expense' in self.cleaned_data:
            self.cleaned_data['diff_expense'] = diff_expense(
                get_expensedb_from_model(), self.cleaned_data['expense'])

    def iter_created_removed(self):
        categories = [
            ('Create attendance', 'diff_attendance', 0),
            ('Remove attendance', 'diff_attendance', 1),
            ('Create expense', 'diff_expense', 0),
            ('Remove expense', 'diff_expense', 1),
        ]
        for label, field, index in categories:
            for o in self.cleaned_data[field][index]:
                yield '%s %s' % (label, o)

    def save(self):
        # Call save() functions on diff_{attendance,expense}.
        self.cleaned_data['diff_attendance'][2]()
        self.cleaned_data['diff_expense'][2]()
        recompute_balances()


class SearchForm(forms.Form):
    months = forms.IntegerField(min_value=1, initial=10, required=False)
    show_all = forms.BooleanField(required=False)

    def clean_months(self):
        m = self.cleaned_data['months']
        if m is None:
            m = self.fields['months'].initial
        return m


class AccessTokenListForm(forms.Form):
    def __init__(self, **kwargs):
        queryset = kwargs.pop('queryset')
        super().__init__(**kwargs)

        self.persons = []
        self.rows = []

        tokens = AccessToken.all_as_dict()

        for person in queryset.select_related():
            keys = {}
            entry = {'person': person, 'keys': keys}

            base = 'p%s_' % person.pk

            user = person.user or User()
            keys['email'] = k = base + 'email'
            entry['email'] = self.fields[k] = forms.EmailField(
                initial=user.email, required=False)

            for field in 'revoke generate send'.split():
                keys[field] = k = base + field
                entry[field] = self.fields[k] = forms.BooleanField(
                    required=False)

            entry['token'] = token = tokens.get(person, AccessToken())

            self.persons.append(entry)
            self.rows.append((
                person, token.login_url(),
                self[base + 'email'],
                self[base + 'revoke'],
                self[base + 'generate'],
                self[base + 'send'],
            ))

    def clean(self):
        data = self.cleaned_data
        for entry in self.persons:
            keys = entry['keys']
            if keys['email'] in data and not data[keys['email']]:
                # No email specified
                if data[keys['send']]:
                    # Wanted to send an email
                    self.add_error(keys['send'], 'Email address required')
            if data[keys['revoke']] and not entry['token']:
                self.add_error(keys['revoke'], 'No token to revoke!')
            already_has_token = (
                entry['token'].token and not data[keys['revoke']])
            if data[keys['generate']] and already_has_token:
                self.add_error(keys['generate'], 'Already has token!')

    def save(self):
        data = self.cleaned_data
        tokens = AccessToken.all_as_dict()

        set_email = []
        revoke_tokens = []
        save_tokens = []
        messages = []
        recipients = []

        for entry in self.persons:
            keys = entry['keys']
            email_changed = data[keys['email']] != entry['email'].initial
            if email_changed:
                set_email.append((entry['person'].get_or_create_user(),
                                  data[keys['email']]))
            if data[keys['revoke']]:
                revoke_tokens.append(tokens.pop(entry['person']))
            if data[keys['generate']]:
                token = AccessToken.fresh(entry['person'])
                save_tokens.append(token)
                tokens[entry['person']] = token
            if data[keys['send']]:
                link = tokens[entry['person']].login_url()
                recipient = data[keys['email']]
                assert recipient
                assert entry['person'].username
                assert link
                recipients.append(recipient)
                messages.append(lunchclub.mail.prepare_login_message(
                    name=entry['person'].username,
                    email=recipient,
                    link=link,
                ))

        for user, email in set_email:
            user.email = email
            user.save()
        for token in revoke_tokens:
            logger.info("Revoke %s token %s with %s use(s)",
                        user, token[:20], token.use_count)
            token.delete()
        for token in save_tokens:
            token.save()
        if messages:
            assert len(messages) == len(recipients)
            if settings.SEND_EMAIL_VIA_MAILTO:
                return lunchclub.mail.make_mailto_links(messages)
            else:
                logger.info("Send login emails to %s", recipients)
                lunchclub.mail.send_messages(messages)


class ExpenseCreateForm(forms.Form):
    myself = forms.BooleanField(widget=forms.HiddenInput, required=False)
    person = forms.ChoiceField(required=False)
    expense = forms.DecimalField(decimal_places=2,
                                 min_value=decimal.Decimal('0.01'),
                                 max_value=decimal.Decimal('400'))

    def __init__(self, **kwargs):
        self.person = kwargs.pop('person')
        self.queryset = kwargs.pop('queryset')
        self.date = kwargs.pop('date')
        if 'data' in kwargs and kwargs['data'].get('myself'):
            # If the form is invalid, we want to redisplay it with "myself"
            # as the chosen person.
            kwargs['data'] = kwargs['data'].copy()
            print(kwargs['data'])
            kwargs['data']['person'] = self.person.pk
        super().__init__(**kwargs)
        self.fields['person'].choices = [
            (person.pk, person.username)
            for person in self.queryset]
        self.fields['person'].initial = self.person

    def clean(self):
        data = self.cleaned_data
        if not data['myself'] and not data['person']:
            self.add_error('person', 'This field is required.')

        data['created_by'] = self.person

        if data['myself']:
            person = self.person
        else:
            try:
                person = self.queryset.get(pk=data['person'])
            except Person.DoesNotExist:
                raise forms.ValidationError('No Person with that ID')
        data['person'] = person
        return data

    def save(self):
        data = self.cleaned_data
        return Expense.objects.create(
            date=self.date,
            person=data['person'],
            created_by=data['created_by'],
            amount=data['expense'],
        )


class AttendanceTodayForm(forms.Form):
    def __init__(self, **kwargs):
        self.person = kwargs.pop('person')
        queryset = kwargs.pop('queryset')
        self.date = kwargs.pop('date')
        super().__init__(**kwargs)

        existing = {a.person: a
                    for a in Attendance.objects.filter(date=self.date)}

        self.rows = []
        self.persons = []
        for person in queryset:
            if person in existing:
                self.rows.append((person, True, ''))
                continue
            k = 'p%s' % person.pk
            self.fields[k] = forms.BooleanField(required=False)
            self.rows.append((person, False, self[k]))
            self.persons.append((person, k))

    def save(self):
        data = self.cleaned_data
        objects = [
            Attendance(date=self.date,
                       person=p,
                       created_by=self.person)
            for p, k in self.persons
            if data[k]
        ]
        Attendance.objects.bulk_create(objects)


class MonthForm(forms.Form):
    def __init__(self, **kwargs):
        self.month_choices = kwargs.pop('choices')
        self.initial_month = kwargs.pop('initial_month')
        super().__init__(**kwargs)

        self.fields['ym'] = forms.ChoiceField(
            choices=[(self.ym_key(ym), self.ym_name(ym))
                     for ym in self.month_choices],
            initial=self.ym_key(self.initial_month),
        )

    def ym_name(self, ym):
        y, m = ym
        return datetime.date(y, m, 1).strftime('%B %Y')

    def ym_key(self, ym):
        y, m = ym
        return '%04d%02d' % (y, m)

    def clean_ym(self):
        mo = re.match(r'^(\d{4})(\d{2})$', self.cleaned_data['ym'])
        if not mo:
            raise forms.ValidationError('Invalid month')
        y, m = map(int, mo.group(1, 2))
        if (y, m) not in self.month_choices:
            raise forms.ValidationError('Invalid month choice')
        return y, m


class AttendanceCreateForm(forms.Form):
    def __init__(self, **kwargs):
        self.person = kwargs.pop('person')
        persons = list(kwargs.pop('persons'))
        self.dates = kwargs.pop('dates')
        super().__init__(**kwargs)

        existing_qs = Attendance.objects.filter(date__in=self.dates,
                                                person__in=persons)
        existing = {(a.person, a.date): a for a in existing_qs}

        self.rows = []
        self.checkboxes = []
        for person in persons:
            row = []
            for date in self.dates:
                if (person, date) in existing:
                    row.append((True, ''))
                    continue
                k = 'p%s_%s' % (person.pk, date.strftime('%Y%m%d'))
                self.fields[k] = forms.BooleanField(required=False)
                self.checkboxes.append((person, date, k))
                row.append((False, self[k]))
            self.rows.append((person, row))

    def save(self):
        data = self.cleaned_data
        objects = [
            Attendance(date=d, person=p,
                       created_by=self.person)
            for p, d, k in self.checkboxes
            if data[k]
        ]
        Attendance.objects.bulk_create(objects)
