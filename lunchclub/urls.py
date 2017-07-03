"""lunchclub URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls import url
from django.contrib import admin

from django.views.generic import TemplateView
from lunchclub.views import (
    Home, DatabaseBulkEdit, Login, Logout, AccessTokenList,
    ExpenseCreate, AttendanceToday, AttendanceCreate,
    AttendanceExport, ExpenseExport, submit_view,
    ShoppingList, chat_publish,
)

urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^$', Home.as_view(), name='home'),
    url(r'^edit/$', DatabaseBulkEdit.as_view(), name='edit'),
    url(r'^export/attenddb\.txt$', AttendanceExport.as_view(), name='attendance_export'),
    url(r'^export/expensedb\.txt$', ExpenseExport.as_view(), name='expense_export'),
    url(r'^export/expencedb\.txt$', ExpenseExport.as_view(), name='expense_export_sic'),
    url(r'^login/$', Login.as_view(), name='login'),
    url(r'^logout/$', Logout.as_view(), name='logout'),
    url(r'^token/$', AccessTokenList.as_view(), name='accesstoken_list'),
    url(r'^expense/$', ExpenseCreate.as_view(), name='expense_create'),
    url(r'^attendance/today/$', AttendanceToday.as_view(), name='attendance_today'),
    url(r'^attendance/$', AttendanceCreate.as_view(), name='attendance_create'),
    url(r'^clisubmit/$', submit_view),
    url(r'^shoppinglist/$', ShoppingList.as_view(), name='shopping_list'),
    url(r'^chat/$', TemplateView.as_view(template_name='chat.html')),
    url(r'^chat/publish/$', chat_publish),
]
