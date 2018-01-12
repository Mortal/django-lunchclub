import re
import json
import decimal
import datetime
import collections

from django import forms
from django.contrib.auth.models import User

from lunchclub.models import (
    recompute_balances, AccessToken, Expense, Attendance,
    Person, ShoppingListItem,
)
from lunchclub.parser import (
    parse_attenddb, parse_expensedb,
    unparse_attenddb, unparse_expensedb,
    get_attenddb_from_model, get_expensedb_from_model,
    diff_attendance, diff_expense,
)
import lunchclub.mail


class DatabaseBulkEditForm(forms.Form):
    def __init__(self, **kwargs):
        self.attenddb = kwargs.pop('attenddb')
        self.expensedb = kwargs.pop('expensedb')
        super().__init__(**kwargs)
        self.fields['initial'].initial = json.dumps({
            'expense_pks': list(self.expensedb.values()),
            'attendance_pks': list(self.attenddb.values()),
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
        '''
        Compute diff between hidden initial data and textarea data.
        '''
        if 'initial' in self.cleaned_data:
            apks = sorted(
                self.cleaned_data['initial'].get('attendance_pks', []))
            epks = sorted(
                self.cleaned_data['initial'].get('expense_pks', []))
            init = json.loads(self.fields['initial'].initial)
            init_apks = sorted(init['attendance_pks'])
            init_epks = sorted(init['expense_pks'])
            if apks != init_apks or epks != init_epks:
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
        '''
        Return a generator over log lines that should be emitted when calling
        save(). This method is used both when previewing changes and when
        committing changes to this form.
        '''
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
    '''
    Search form used in Home view to specify what months to display.

    All fields have defaults, so the empty submission is valid:

    >>> form = SearchForm(data={})
    >>> form.is_valid()
    True

    This makes the search form usable with GET requests.
    '''
    months = forms.IntegerField(min_value=1, initial=10, required=False)
    show_all = forms.BooleanField(required=False)

    def clean_months(self):
        m = self.cleaned_data['months']
        if m is None:
            m = self.fields['months'].initial
        return m


class AccessTokenListForm(forms.Form):
    ChangesBase = collections.namedtuple(
        'Changes',
        'save_person set_name set_email revoke_tokens save_tokens set_hidden')

    default_email_domain = 'cs.au.dk'

    class Changes(ChangesBase):
        def log_entries(self):
            for person in self.save_person:
                yield ("Create %s", person.username)
            for person, name in self.set_name:
                yield ("Set name of %s to %s", person.username, name)
            for person, email in self.set_email:
                yield ("Set email address of %s to %s", person.username, email)
            for token in self.revoke_tokens:
                yield ("Revoke %s token %s with %s use(s)",
                       token.person.username,
                       token.token[:20], token.use_count)
            for token in self.save_tokens:
                yield ("Create %s token %s",
                       token.person.username,
                       token.token[:20])
            for person, b in self.set_hidden:
                yield ('%s %s', 'Hide' if b else 'Unhide', person.username)

        def save(self):
            for person in self.save_person:
                person.save()
            for person, name in self.set_name:
                person.display_name = name
                person.save()
            for person, email in self.set_email:
                user = person.get_or_create_user()
                user.email = email
                user.save()
            for token in self.revoke_tokens:
                token.delete()
            for token in self.save_tokens:
                token.person = token.person  # Update token_id
                token.save()
            for person, b in self.set_hidden:
                person.hidden = b
                person.save()

    def __init__(self, **kwargs):
        queryset = kwargs.pop('queryset')
        super().__init__(**kwargs)

        self.persons = []
        self.rows = []

        self.tokens = AccessToken.all_as_dict()

        for person in list(queryset.select_related()) + [Person()]:
            base = 'p_%s_' % person.username
            # The last person is a "new person" for which base == 'p__'.
            user = person.user or User()

            self.fields[base + 'name'] = forms.CharField(
                initial=person.display_name, required=False)
            self.fields[base + 'email'] = forms.CharField(
                initial=user.email, required=False)
            self.fields[base + 'revoke'] = forms.BooleanField(required=False)
            self.fields[base + 'generate'] = forms.BooleanField(required=False)
            self.fields[base + 'send'] = forms.BooleanField(required=False)
            self.fields[base + 'hidden'] = forms.BooleanField(
                initial=person.hidden, required=False)

            token = self.tokens.get(person.username) or AccessToken()

            if person.pk:
                person_cell = person.username
            else:
                self.fields[base + 'username'] = forms.CharField(
                    required=False, widget=forms.TextInput(
                        {'placeholder': 'New username'}))
                person_cell = self[base + 'username']

            self.persons.append(person)
            self.rows.append((
                person_cell,
                self[base + 'name'],
                token.login_url(),
                self[base + 'email'],
                self[base + 'revoke'],
                self[base + 'generate'],
                self[base + 'send'],
                self[base + 'hidden'],
            ))

    def clean(self):
        data = self.cleaned_data
        for person in self.persons:
            token = self.tokens.get(person.username) or AccessToken()
            base = 'p_%s_' % person.username
            if person.pk is None:
                # This is the row for creating a new person
                any_data = any([
                    data[base + 'username'],
                    data[base + 'name'],
                    data[base + 'email'],
                    data[base + 'revoke'],
                    data[base + 'generate'],
                    data[base + 'send'],
                    data[base + 'hidden'],
                ])
                if not any_data:
                    continue
                if not data.get(base + 'username'):
                    self.add_error(base + 'username', 'Username is required')
                else:
                    existing = Person.objects.filter(
                        username=data[base + 'username'])
                    if existing.exists():
                        self.add_error(base + 'username', 'Username is taken')

            if not data[base + 'name']:
                self.add_error(base + 'name', 'Display name is required')
            if data[base + 'email']:
                add_default = ('@' not in data[base + 'email'] and
                               self.default_email_domain)
                if add_default:
                    data[base + 'email'] += '@' + self.default_email_domain

                email = data[base + 'email']
                if not email.count('@') == email.strip('@').count('@') == 1:
                    self.add_error(base + 'email', 'Invalid email address')
            else:
                # No email specified
                if data[base + 'send']:
                    # Wanted to send an email
                    self.add_error(base + 'send', 'Email address required')
            if data[base + 'revoke'] and not token.token:
                self.add_error(base + 'revoke', 'No token to revoke!')
            already_has_token = (
                token.token and not data[base + 'revoke'])
            if data[base + 'generate'] and already_has_token:
                self.add_error(base + 'generate', 'Already has token!')

    def actions(self):
        data = self.cleaned_data

        save_person = []
        set_name = []
        set_email = []
        revoke_tokens = []
        save_tokens = []
        set_hidden = []
        messages = []
        recipients = []

        for person in self.persons:
            base = 'p_%s_' % person.username
            if person.pk is None:
                if data[base + 'username']:
                    person.username = data[base + 'username']
                    person.balance = 0
                    save_person.append(person)
                else:
                    continue
            name_changed = (data[base + 'name'] !=
                            self.fields[base + 'name'].initial)
            if name_changed:
                set_name.append((person, data[base + 'name']))
            email_changed = (data[base + 'email'] !=
                             self.fields[base + 'email'].initial)
            if email_changed:
                set_email.append((person, data[base + 'email']))
            if data[base + 'revoke']:
                revoke_tokens.append(self.tokens.pop(person.username))
            if data[base + 'generate']:
                token = AccessToken.fresh(person)
                save_tokens.append(token)
                self.tokens[person.username] = token
            if data[base + 'send']:
                link = self.tokens[person.username].login_url()
                recipient = data[base + 'email']
                assert recipient
                assert person.username
                assert link
                recipients.append(recipient)
                messages.append(lunchclub.mail.prepare_login_message(
                    name=person.username,
                    email=recipient,
                    link=link,
                ))
            if data[base + 'hidden'] != person.hidden:
                set_hidden.append((person, data[base + 'hidden']))

        return self.Changes(save_person, set_name, set_email,
                            revoke_tokens, save_tokens, set_hidden), messages


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
            k = person.username
            self.fields[k] = forms.BooleanField(required=False)
            self.rows.append((person, False, self[k]))
            self.persons.append((person, k))

    def get_selected(self):
        return [p for p, k in self.persons if self.cleaned_data[k]]

    def save(self):
        objects = [
            Attendance(date=self.date,
                       person=p,
                       created_by=self.person)
            for p in self.get_selected()
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
    lines = forms.CharField(widget=forms.Textarea, required=False)

    def __init__(self, **kwargs):
        self.person = kwargs.pop('person')
        self.persons = list(kwargs.pop('persons'))
        self.dates = kwargs.pop('dates')
        self.rsvps = kwargs.pop('rsvps')
        super().__init__(**kwargs)

        existing_qs = Attendance.objects.filter(date__in=self.dates,
                                                person__in=self.persons)
        existing = {(a.person, a.date): a for a in existing_qs}

        self.rows = []
        self.checkboxes = []
        for person in self.persons:
            row = []
            for date in self.dates:
                rsvp = self.rsvps.get((date, person.username))
                if (person, date) in existing:
                    row.append((True, rsvp, ''))
                    continue
                k = '%s_%s' % (person.username, date.strftime('%Y%m%d'))
                self.fields[k] = forms.BooleanField(required=False)
                self.checkboxes.append((person, date, k))
                row.append((False, rsvp, self[k]))
            self.rows.append((person, row))

    def clean_lines(self):
        s = self.cleaned_data['lines']
        result = []
        for line in s.splitlines():
            if not line.strip():
                continue
            name, *days = line.split()
            try:
                days = [int(d) for d in days]
            except ValueError as exn:
                raise forms.ValidationError(
                    'Invalid integer: %r' % (exn.args[0],))
            dmin = min(days)
            dmax = max(days)
            if dmin < 1:
                raise forms.ValidationError('Invalid day: %r' % (dmin,))
            if dmax > len(self.dates):
                raise forms.ValidationError('Invalid day: %r' % (dmax,))
            try:
                person = next(p for p in self.persons
                              if p.username == name)
            except StopIteration:
                raise forms.ValidationError(
                    'Unknown person: %r' % (name,))
            result.extend((person, self.dates[d-1]) for d in days)
        return result

    def get_checkbox_selected(self):
        return ((p, d) for p, d, k in self.checkboxes if self.cleaned_data[k])

    def get_selected(self):
        return sorted(set(self.get_checkbox_selected()) |
                      set(self.cleaned_data['lines']),
                      key=lambda x: (x[0].username, x[1]))

    def save(self):
        objects = [
            Attendance(date=d, person=p,
                       created_by=self.person)
            for p, d in self.get_selected()
        ]
        Attendance.objects.bulk_create(objects)


class ShoppingListForm(forms.Form):
    name = forms.CharField(required=False)
    create = forms.BooleanField(required=False)

    def __init__(self, **kwargs):
        self.queryset = kwargs.pop('queryset')
        super().__init__(**kwargs)

        self.shopping_list_items = []
        for o in self.queryset:
            k = 'i%s_delete' % o.pk
            self.fields[k] = forms.BooleanField(required=False)
            self.shopping_list_items.append((o, k))

    def clean(self):
        data = self.cleaned_data
        data['created'] = []
        if data.get('create'):
            try:
                data['created'].append(ShoppingListItem(name=data['name']))
            except KeyError:
                self.add_error('name', 'This field is required.')
        data['deleted'] = []
        for o, k in self.shopping_list_items:
            if data.get(k):
                data['deleted'].append(o)
