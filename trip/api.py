from django.http import JsonResponse
from .models import Passenger

def get_passenger_names(request):
    """API endpoint to fetch passenger names for autofill"""
    try:
        # Get the current user if authenticated
        if request.user.is_authenticated:
            user_full_name = f"{request.user.first_name} {request.user.last_name}".strip()

            # Get all passenger names from the database
            # This will fetch all passenger names for autofill
            passengers = Passenger.objects.values_list('full_name', flat=True).distinct()

            # Add the current user's name to the list if it's not already there
            if user_full_name and user_full_name not in passengers:
                passengers_list = list(passengers)
                passengers_list.append(user_full_name)
            else:
                passengers_list = list(passengers)

            # Return the passenger names as JSON
            return JsonResponse({
                'success': True,
                'passenger_names': passengers_list
            })
        else:
            # If not authenticated, still return all passenger names for autofill
            passengers = Passenger.objects.values_list('full_name', flat=True).distinct()

            return JsonResponse({
                'success': True,
                'passenger_names': list(passengers)
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
