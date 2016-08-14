from django import forms

from lunchclub.models import recompute_balances, Person
from lunchclub.parser import import_attendance, import_expenses


class ImportForm(forms.Form):
    attendance = forms.CharField(widget=forms.Textarea, required=False)
    expense = forms.CharField(widget=forms.Textarea, required=False)

    def clean_attendance(self):
        return import_attendance(self.cleaned_data['attendance'])

    def clean_expense(self):
        return import_expenses(self.cleaned_data['expense'])

    def save(self):
        self.cleaned_data['attendance'][1]()
        self.cleaned_data['expense'][1]()
        recompute_balances()


class AccessTokenForm(forms.Form):
    person = forms.ModelChoiceField(Person.objects)
