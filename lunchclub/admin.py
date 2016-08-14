from django.contrib import admin
from lunchclub.models import Person, Attendance, Expense, AccessToken

admin.site.register(Person)
admin.site.register(Attendance)
admin.site.register(Expense)
admin.site.register(AccessToken)
