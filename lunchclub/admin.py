from django.contrib import admin
from lunchclub.models import (
    Person, Attendance, Expense, AccessToken,
    ShoppingListItem, Announce, Rsvp,
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


@admin.register(ShoppingListItem)
class ShoppingListItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'created_time',
                    'deleted_by', 'deleted_time')


@admin.register(Announce)
class AnnounceAdmin(admin.ModelAdmin):
    list_display = ('kind', 'created_by', 'created_time')


@admin.register(Rsvp)
class RsvpAdmin(admin.ModelAdmin):
    list_display = ('status', 'person', 'date')
