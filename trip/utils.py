import uuid
from datetime import datetime

def generate_booking_reference():
    """Generate a unique booking reference"""
    timestamp = datetime.now().strftime('%Y%m%d')
    unique_id = str(uuid.uuid4()).split('-')[0].upper()
    return f'BK{timestamp}{unique_id}'