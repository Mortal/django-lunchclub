DJ_USER=`id -un`
DJ_PASS=`pwgen -s 20 1`
heroku run python manage.py shell -c \
	"from django.contrib.auth.models import User;\
	assert User.objects.count() == 0;\
	u = User(username='$DJ_USER', is_staff=True, is_superuser=True);\
	u.set_password('$DJ_PASS');\
	u.save()" && \
echo "$DJ_USER $DJ_PASS"
