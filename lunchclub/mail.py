import textwrap
import urllib.parse
import django.core.mail
from django.utils.html import format_html
from django.core.mail import EmailMessage


def send_messages(messages):
    return django.core.mail.get_connection().send_messages(messages)


def make_mailto_link(message):
    link = 'mailto:{}?subject={}&body={}'.format(
        urllib.parse.quote(message.to[0]),
        urllib.parse.quote(message.subject),
        urllib.parse.quote(message.body),
    )
    return format_html('<a href="{}">{}</a>', link, message.subject)


def make_mailto_links(messages):
    return [make_mailto_link(message) for message in messages]


def prepare_login_message(name, email, link):
    text = textwrap.dedent('''
    Hi {name}

    Here is your personal lunchclub login link:

    {link}

    Don't share it with others, as that would allow others
    to enter data into the lunchclub on your behalf.

    You should bookmark the link in your browser for easy access in the future.

    Best regards,
    Your friendly lunchclub robot.
    '''.strip('\n')).format(name=name, link=link)

    return EmailMessage(
        subject='Link to lunchclub login for {}'.format(name),
        body=text,
        to=[email],
    )
