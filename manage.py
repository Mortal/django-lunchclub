#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    env_file = os.path.join(os.path.dirname(__file__), 'env.txt')
    if 'DJANGO_SETTINGS_MODULE' not in os.environ:
        if os.path.exists(env_file):
            with open(env_file) as fp:
                for line in fp:
                    k, v = line.split('=', 1)
                    if v.startswith('"'):
                        v = eval(v)
                    else:
                        v = v.strip('\n')
                    os.environ.setdefault(k, v)
        else:
            os.environ.setdefault("DJANGO_SETTINGS_MODULE",
                                  "lunchclub.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError:
        # The above import may fail for some other reason. Ensure that the
        # issue is really that Django is missing to avoid masking other
        # exceptions on Python 2.
        try:
            import django
        except ImportError:
            raise ImportError(
                "Couldn't import Django. Are you sure it's installed and "
                "available on your PYTHONPATH environment variable? Did you "
                "forget to activate a virtual environment?"
            )
        raise
    execute_from_command_line(sys.argv)
