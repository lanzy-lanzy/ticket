from django.http import JsonResponse
from django.db.models import Q
from .models import Booking, Passenger

def get_passenger_names(request):
    """API endpoint to fetch passenger names for autofill"""
    try:
        # Get the current user if authenticated
        if request.user.is_authenticated:
            user_full_name = f"{request.user.first_name} {request.user.last_name}".strip()
            
            # Get unique passenger names from previous bookings
            # First, get bookings made by this user (based on email or full name)
            user_bookings = Booking.objects.filter(
                Q(email=request.user.email) | Q(full_name=user_full_name)
            )
            
            # Then get passengers from these bookings
            passengers = Passenger.objects.filter(
                booking__in=user_bookings
            ).values_list('full_name', flat=True).distinct()
            
            # Return the passenger names as JSON
            return JsonResponse({
                'success': True,
                'passenger_names': list(passengers)
            })
        else:
            # If not authenticated, return empty list
            return JsonResponse({
                'success': True,
                'passenger_names': []
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
