from django.db import models


class AmountField(models.DecimalField):
    def __init__(self, **kwargs):
        kwargs['max_digits'] = 19
        kwargs['decimal_places'] = 2
        kwargs['widget'] = models.NumberInput
        super(AmountField, self).__init__(**kwargs)
