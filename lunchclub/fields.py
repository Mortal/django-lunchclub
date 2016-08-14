from django.db import models
from django import forms


class AmountField(models.DecimalField):
    def __init__(self, **kwargs):
        kwargs['max_digits'] = 19
        kwargs['decimal_places'] = 2
        super(AmountField, self).__init__(**kwargs)

    def formfield(self, **kwargs):
        defaults = {'form_class': forms.NumberInput}
        defaults.update(kwargs)
        return super(AmountField, self).formfield(**defaults)
