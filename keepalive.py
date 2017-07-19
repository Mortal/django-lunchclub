import os
import time
import datetime
import subprocess


os.environ['DJANGO_SETTINGS_MODULE'] = 'lunchclub.settings'

while True:
    subprocess.check_call(
        ('venv/bin/python', '-c', 'import django; django.setup(); ' +
         'import lunchclub.today; lunchclub.today.send_keepalive()'))
    print(datetime.datetime.now())
    time.sleep(30)
