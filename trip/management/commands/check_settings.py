from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    help = 'Check the settings values'

    def handle(self, *args, **options):
        self.stdout.write(f'Twilio SID: {settings.TWILIO_ACCOUNT_SID}')
        self.stdout.write(f'Twilio Auth Token: {settings.TWILIO_AUTH_TOKEN}')
        self.stdout.write(f'Twilio Phone Number: {settings.TWILIO_PHONE_NUMBER}')
        self.stdout.write(f'Email Host User: {settings.EMAIL_HOST_USER}')
        self.stdout.write(f'Email Host Password: {settings.EMAIL_HOST_PASSWORD}')
