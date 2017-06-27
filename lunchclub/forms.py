from django import forms

from lunchclub.models import recompute_balances, Person
from lunchclub.parser import (
    parse_attenddb, parse_expensedb,
    unparse_attenddb, unparse_expensedb,
    get_attenddb_from_model, get_expensedb_from_model,
    diff_attendance, diff_expense,
)
import json


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


class AccessTokenForm(forms.Form):
    person = forms.ModelChoiceField(Person.objects)


class SearchForm(forms.Form):
    months = forms.IntegerField(min_value=1, initial=10, required=False)
    show_all = forms.BooleanField(required=False)

    def clean_months(self):
        m = self.cleaned_data['months']
        if m is None:
            m = self.fields['months'].initial
        return m
