# vim: set sw=4 et:
from .common import *  # noqa
import os, pwd

SECRET_KEY = os.environ['DJANGO_SECRET_KEY']
SUBMISSION_KEY = os.environ['LUNCHCLUB_SUBMISSION_KEY'].encode('ascii')
DEBUG = False

ADMINS = (
    ('Mathias Rav', 'rav@cs.au.dk'),
)

# Update database configuration with $DATABASE_URL.
import dj_database_url
db_from_env = dj_database_url.config(conn_max_age=500)
DATABASES['default'].update(db_from_env)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': ('[%(asctime)s %(name)s %(levelname)s] ' +
                       '%(message)s'),
        },
    },
    'handlers': {
        'file': {
            'class': 'logging.handlers.WatchedFileHandler',
            'filename': os.path.join(BASE_DIR,
                                     'django-%s.log' % pwd.getpwuid(os.geteuid()).pw_name),
            'formatter': 'simple',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'mail_admins'],
            'level': 'INFO',
        },
    },
}

STATIC_ROOT = os.path.join(BASE_DIR, "static")
STATIC_URL = "/lunchclub/static/"

ALLOWED_HOSTS = ['127.0.0.1']

EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = '/home/rav/django-email'

SERVER_EMAIL = 'courses@apps-server.cs.au.dk'

SEND_EMAIL_VIA_MAILTO = True

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "asgi_redis.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("localhost", 6379)],
        },
        "ROUTING": "lunchclub.routing.channel_routing",
    },
}
