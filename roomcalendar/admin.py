from django.contrib import admin
from roomcalendar.models import (
    Calendar, CalendarItem,
)


@admin.register(Calendar)
class PersonAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(CalendarItem)
class PersonAdmin(admin.ModelAdmin):
    list_display = ('subject', 'calendar', 'date', 'start_time', 'end_time')
