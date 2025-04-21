# Simple script to test settings
import os
import sys

# Add the current directory to the Python path
sys.path.insert(0, os.getcwd())

# Import settings
from booking.settings import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    EMAIL_HOST_USER,
    EMAIL_HOST_PASSWORD
)

# Print settings
print(f'Twilio SID: {TWILIO_ACCOUNT_SID}')
print(f'Twilio Auth Token: {TWILIO_AUTH_TOKEN}')
print(f'Twilio Phone Number: {TWILIO_PHONE_NUMBER}')
print(f'Email Host User: {EMAIL_HOST_USER}')
print(f'Email Host Password: {EMAIL_HOST_PASSWORD}')
