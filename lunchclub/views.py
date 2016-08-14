from django.shortcuts import redirect
from django.views.generic import TemplateView, FormView

from lunchclub.forms import ImportForm
from lunchclub.models import Person


class Home(TemplateView):
    template_name = 'lunchclub/home.html'

    def get_context_data(self, **kwargs):
        data = super(Home, self).get_context_data(**kwargs)
        data['persons'] = Person.objects.all()
        return data


class Import(FormView):
    form_class = ImportForm
    template_name = 'lunchclub/import.html'

    def form_valid(self, form):
        form.save()
        return redirect('home')
