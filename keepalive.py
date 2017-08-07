import os
import time
import datetime
import subprocess


while True:
    subprocess.check_call(
        ('venv/bin/python', '-c', 'import django; django.setup(); ' +
         'import lunchclub.today; lunchclub.today.send_keepalive()'))
    print(datetime.datetime.now(), flush=True)
    time.sleep(30)
