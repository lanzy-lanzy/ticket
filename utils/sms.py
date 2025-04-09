import logging
from twilio.rest import Client
from django.conf import settings

# Configure logger
logger = logging.getLogger(__name__)

def send_payment_confirmation_sms(booking, payment):
    """Send payment confirmation SMS using Twilio"""
    logger.info(f"Attempting to send payment confirmation SMS for booking: {booking.booking_reference}")
    
    try:
        logger.debug(f"SMS Details - Contact Number: {booking.contact_number}, "
                    f"Amount: ₱{payment.amount_paid}, "
                    f"Payment Ref: {payment.payment_reference}")
        
        # Initialize Twilio client
        logger.debug("Initializing Twilio client...")
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        # Prepare message body
        message_body = f"""Payment Confirmation
Thank you for your payment!

Booking Reference: {booking.booking_reference}
Amount Paid: ₱{payment.amount_paid}
Payment Reference: {payment.payment_reference}
Date: {payment.payment_date.strftime('%B %d, %Y %H:%M')}

Your ticket has been confirmed. Please show this message upon check-in."""

        logger.debug(f"Prepared SMS content: {message_body}")
        
        # Send message
        logger.info("Sending SMS via Twilio...")
        message = client.messages.create(
            body=message_body,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=booking.contact_number
        )
        
        logger.info(f"SMS sent successfully! Message SID: {message.sid}")
        return message.sid
        
    except Exception as e:
        logger.error(f"Failed to send payment confirmation SMS: {str(e)}", exc_info=True)
        logger.error(f"Booking details - Reference: {booking.booking_reference}, "
                    f"Contact: {booking.contact_number}")
        return None
