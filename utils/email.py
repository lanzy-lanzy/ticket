import logging
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

def send_booking_confirmation_email(booking):
    """Send booking confirmation email"""
    try:
        logger.info(f"Starting email send process to {booking.email}")
        logger.info(f"Using email configuration: HOST={settings.EMAIL_HOST}, PORT={settings.EMAIL_PORT}")
        
        subject = f'Booking Confirmation - {booking.booking_reference}'
        html_content = render_to_string('emails/booking_confirmation.html', {
            'booking': booking,
            'EMAIL_HOST_USER': settings.EMAIL_HOST_USER
        })
        
        send_mail(
            subject=subject,
            message='',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.email],
            html_message=html_content,
            fail_silently=False,
        )
        
        logger.info(f"Email sent successfully to {booking.email}")
        return True
            
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}", exc_info=True)
        logger.error(f"Email settings used: HOST={settings.EMAIL_HOST}, USER={settings.EMAIL_HOST_USER}")
        return False
