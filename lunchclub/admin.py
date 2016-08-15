from django.contrib import admin
from lunchclub.models import Person, Attendance, Expense, AccessToken


class PersonAdmin(admin.ModelAdmin):
    list_display = ('username', 'balance', 'user', 'created_time')


class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('person', 'date', 'created_by', 'created_time')


class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('person', 'amount', 'date', 'created_by', 'created_time')


class AccessTokenAdmin(admin.ModelAdmin):
    list_display = ('person', 'created_time', 'use_count')


admin.site.register(Person, PersonAdmin)
admin.site.register(Attendance, AttendanceAdmin)
admin.site.register(Expense, ExpenseAdmin)
admin.site.register(AccessToken, AccessTokenAdmin)
