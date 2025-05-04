def booking(request):
    """View for displaying and handling the passenger booking form"""
    # Get upcoming schedules for the dropdown
    schedules = Schedule.objects.filter(
        departure_datetime__gt=timezone.now(),
        status='scheduled'
    ).order_by('departure_datetime')

    # Check if a specific schedule was selected
    selected_schedule = None
    if request.GET.get('schedule'):
        try:
            selected_schedule = Schedule.objects.get(id=request.GET.get('schedule'))
            # Pre-calculate the fare rates for JavaScript
            adult_fare = selected_schedule.adult_fare
            child_fare = selected_schedule.child_fare
        except Schedule.DoesNotExist:
            messages.error(request, "The selected schedule does not exist.")
            return redirect('booking')

    context = {
        'schedules': schedules,
        'selected_schedule': selected_schedule,
    }

    return render(request, 'booking.html', context)

def vehicle_booking(request):
    """View for displaying and handling the vehicle booking form"""
    # Get upcoming schedules for the dropdown
    schedules = Schedule.objects.filter(
        departure_datetime__gt=timezone.now(),
        status='scheduled'
    ).order_by('departure_datetime')

    # Get all vehicle types for the vehicle booking form
    vehicle_types = VehicleType.objects.all()

    # Check if a specific schedule was selected
    selected_schedule = None
    if request.GET.get('schedule'):
        try:
            selected_schedule = Schedule.objects.get(id=request.GET.get('schedule'))
        except Schedule.DoesNotExist:
            messages.error(request, "The selected schedule does not exist.")
            return redirect('vehicle_booking')

    context = {
        'schedules': schedules,
        'vehicle_types': vehicle_types,
        'selected_schedule': selected_schedule,
    }

    return render(request, 'vehicle_booking.html', context)
