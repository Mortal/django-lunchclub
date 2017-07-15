from django.contrib import admin
from lunchclub.models import (
    Person, Attendance, Expense, AccessToken,
)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ('username', 'balance', 'user', 'created_time')


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('person', 'date', 'created_by', 'created_time')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('person', 'amount', 'date', 'created_by', 'created_time')


@admin.register(AccessToken)
class AccessTokenAdmin(admin.ModelAdmin):
    list_display = ('person', 'created_time', 'use_count')
