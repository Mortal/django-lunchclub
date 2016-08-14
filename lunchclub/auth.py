from django.db.models import F
from django.contrib.auth.models import User
from lunchclub.models import AccessToken


class TokenBackend(object):
    def authenticate(self, token=None):
        try:
            token = AccessToken.objects.get(token=token)
        except AccessToken.DoesNotExist:
            return None
        person = token.person
        if person.user is None:
            person.user = User(username=person.username)
            person.user.save()
        qs = AccessToken.objects.filter(pk=token.pk)
        qs.update(use_count=F('use_count') + 1)
        return person.user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
