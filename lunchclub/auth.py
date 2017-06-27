from django.db.models import F
from django.contrib.auth.models import User
from lunchclub.models import AccessToken


class TokenBackend(object):
    def authenticate(self, token=None):
        try:
            token = AccessToken.objects.get(token=token)
        except AccessToken.DoesNotExist:
            return None
        return token.person.get_or_create_user()

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
