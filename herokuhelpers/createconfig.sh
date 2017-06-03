#!/bin/sh
heroku config:set DJANGO_SETTINGS_MODULE=lunchclub.settings.heroku
heroku config:set DJANGO_SECRET_KEY=`pwgen -s 100 1`
