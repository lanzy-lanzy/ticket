import smtplib
import ssl

smtp_server = "smtp.gmail.com"
port = 587
sender_email = "bigbren480@gmail.com"
password = "vuhmpiryzbdezrmp"

try:
    # Create a secure SSL/TLS context
    context = ssl.create_default_context()

    # Try to connect to Gmail's SMTP server
    server = smtplib.SMTP(smtp_server, port)
    server.ehlo()
    server.starttls(context=context)
    server.ehlo()
    server.login(sender_email, password)
    print("Successfully connected to Gmail SMTP server!")
    server.quit()
except Exception as e:
    print(f"Connection failed: {str(e)}")