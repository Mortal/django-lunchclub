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
            u = User(username=person.username)
            u.save()
            person.user = u
            person.save()
        return person.user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
