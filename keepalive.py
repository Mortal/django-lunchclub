import time
import datetime
import subprocess

while True:
    subprocess.check_call(
        ('python', '-c', 'import lunchclub.today; lunchclub.today.send_keepalive()'))
    print(datetime.datetime.now())
    time.sleep(30)
