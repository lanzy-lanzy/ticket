from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.db import models
from django.http import JsonResponse, HttpResponse, QueryDict
from .models import Booking, Vessel, Schedule, Payment, VehicleType, Vehicle, Rating, Route, ContactMessage, TravelGuideline, Passenger
from django.urls import reverse
from .forms import BookingForm, RouteForm, UserRegistrationForm
from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.template.loader import render_to_string
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from decimal import Decimal
from django.db.models import Sum, Avg # Add this import
from datetime import timedelta
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods
from utils.email import send_booking_confirmation_email
  # Consolidated database imports# Add this import
# Ln view
def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {username}!")

                # Redirect based on user role
                if user.is_staff:
                    return redirect('dashboard')  # Admin/staff go to dashboard
                else:
                    return redirect('home')  # Regular users go to home page
            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form})

# Registration view
def register_view(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')

            # Store contact number and emergency contact info in session for later use
            contact_number = form.cleaned_data.get('contact_number')
            emergency_contact_name = form.cleaned_data.get('emergency_contact_name')
            emergency_contact_number = form.cleaned_data.get('emergency_contact_number')
            emergency_contact_relationship = form.cleaned_data.get('emergency_contact_relationship')

            if contact_number:
                request.session['user_contact_number'] = contact_number
            if emergency_contact_name:
                request.session['emergency_contact_name'] = emergency_contact_name
            if emergency_contact_number:
                request.session['emergency_contact_number'] = emergency_contact_number
            if emergency_contact_relationship:
                request.session['emergency_contact_relationship'] = emergency_contact_relationship

            messages.success(request, f"Account created for {username}! You can now log in.")
            return redirect('login')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = UserRegistrationForm()
    return render(request, 'register.html', {'form': form})

# Logout view
def logout_view(request):
    logout(request)
    messages.success(request, "You have been successfully logged out.")
    return redirect('home')

@login_required
@staff_member_required
def ratings_dashboard(request):
    # Get filter parameters
    status = request.GET.get('status', 'all')
    rating_filter = request.GET.get('rating', 'all')

    # Base queryset with related fields
    ratings = Rating.objects.select_related('vessel', 'user').order_by('-created_at')

    # Apply filters
    if status == 'pending':
        ratings = ratings.filter(is_approved=False)
    elif status == 'approved':
        ratings = ratings.filter(is_approved=True)

    if rating_filter != 'all':
        ratings = ratings.filter(rating=int(rating_filter))

    # Calculate average rating
    avg_rating = ratings.aggregate(avg=Avg('rating'))['avg'] or 0

    # Pagination
    page = request.GET.get('page', 1)
    paginator = Paginator(ratings, 10)  # 10 ratings per page

    try:
        ratings = paginator.page(page)
    except PageNotAnInteger:
        ratings = paginator.page(1)
    except EmptyPage:
        ratings = paginator.page(paginator.num_pages)

    context = {
        'ratings': ratings,
        'avg_rating': round(avg_rating, 1),
        'status': status,
        'rating_filter': rating_filter,
    }

    return render(request, 'dashboard/ratings.html', context)

@login_required
@staff_member_required
def approve_rating(request, rating_id):
    if request.method == 'POST':
        rating = get_object_or_404(Rating, id=rating_id)
        rating.is_approved = True
        rating.save()
        messages.success(request, 'Rating approved successfully.')
    return redirect('ratings_dashboard')

@login_required
@staff_member_required
def delete_rating(request, rating_id):
    if request.method == 'POST':
        rating = get_object_or_404(Rating, id=rating_id)
        rating.delete()
        messages.success(request, 'Rating deleted successfully.')
    return redirect('ratings_dashboard')
@login_required
@staff_member_required
@login_required
@staff_member_required
def dashboard_home(request):
    today = timezone.now().date()
    current_date = timezone.now()
    thirty_days_ago = current_date - timezone.timedelta(days=30)

    # Calculate booking growth
    previous_month_bookings = Booking.objects.filter(
        created_at__lt=thirty_days_ago
    ).count()
    current_month_bookings = Booking.objects.filter(
        created_at__gte=thirty_days_ago
    ).count()
    booking_growth = (
        ((current_month_bookings - previous_month_bookings) / previous_month_bookings * 100)
        if previous_month_bookings > 0 else 0
    )

    # Calculate revenue growth
    previous_month_revenue = Payment.objects.filter(
        payment_date__lt=thirty_days_ago
    ).aggregate(total=models.Sum('amount_paid'))['total'] or 0
    current_month_revenue = Payment.objects.filter(
        payment_date__gte=thirty_days_ago
    ).aggregate(total=models.Sum('amount_paid'))['total'] or 0
    revenue_growth = (
        ((current_month_revenue - previous_month_revenue) / previous_month_revenue * 100)
        if previous_month_revenue > 0 else 0
    )

    # Get active routes with additional data needed for the template
    active_routes_list = Route.objects.filter(
        active=True
    ).annotate(
        schedule_count=models.Count('schedule')
    ).order_by('-schedule_count')[:4]

    # Get upcoming schedules with all related data needed for the template
    upcoming_schedules = Schedule.objects.select_related(
        'vessel',
        'route'
    ).filter(
        departure_datetime__gte=timezone.now(),
        status='scheduled'
    ).order_by('departure_datetime')[:6]

    # Calculate available seats and cargo space for each schedule
    for schedule in upcoming_schedules:
        schedule.available_seats = schedule.get_available_seats()
        schedule.available_cargo_space = schedule.get_available_cargo_space()

    # Get recent bookings with related schedule and route information
    recent_bookings = Booking.objects.select_related(
        'schedule',
        'schedule__route'
    ).order_by('-created_at')[:5]

    # Calculate total revenue
    total_revenue = Payment.objects.aggregate(
        total=models.Sum('amount_paid')
    )['total'] or 0

    context = {
        # Card metrics
        'total_bookings': Booking.objects.count(),
        'booking_growth': booking_growth,
        'total_revenue': total_revenue,
        'revenue_growth': revenue_growth,
        'active_vessels': Vessel.objects.filter(active=True).count(),
        'todays_schedules': Schedule.objects.filter(
            departure_datetime__date=today,
            status='scheduled'
        ).count(),

        # Recent bookings table
        'recent_bookings': recent_bookings,

        # Upcoming schedules section
        'upcoming_schedules': upcoming_schedules,

        # Active routes section
        'active_routes_list': active_routes_list,

        # Quick actions section
        'vehicle_types': VehicleType.objects.all(),
    }

    return render(request, 'dashboard/home.html', context)
def home(request):
    # Get only approved testimonials
    testimonials = Rating.objects.filter(
        is_approved=True  # Only get approved ratings
    ).select_related(
        'vessel',
        'user'
    ).order_by('-created_at')[:6]  # Get latest 6 approved testimonials

    # Calculate average rating from approved ratings only
    avg_rating = Rating.objects.filter(
        is_approved=True  # Only include approved ratings in average
    ).aggregate(
        avg=Avg('rating')
    )['avg'] or 0

    # Get active vessels for the rating form
    vessels = Vessel.objects.filter(active=True).order_by('name')

    context = {
        'testimonials': testimonials,
        'avg_rating': round(avg_rating, 1),
        'vessels': vessels,
    }

    return render(request, 'home.html', context)

def get_payment_details(request, booking_reference):
    booking = get_object_or_404(Booking, booking_reference=booking_reference)

    # Calculate payment amount
    if booking.booking_type == 'passenger':
        adult_passengers = int(booking.adult_passengers or 0)
        child_passengers = int(booking.child_passengers or 0)
        adult_fare = booking.adult_fare_rate or Decimal('0.00')
        child_fare = booking.child_fare_rate or Decimal('0.00')
        payment_amount = (adult_passengers * adult_fare) + (child_passengers * child_fare)

    return HttpResponse(f'₱{payment_amount}')

def booking(request):
    """View for displaying and handling the booking form"""
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
            # Pre-calculate the fare rates for JavaScript
            adult_fare = selected_schedule.adult_fare
            child_fare = selected_schedule.child_fare
        except Schedule.DoesNotExist:
            messages.error(request, "The selected schedule does not exist.")
            return redirect('booking')

    # Get user information if authenticated
    user_info = {}
    if request.user.is_authenticated:
        user_full_name = f"{request.user.first_name} {request.user.last_name}".strip()

        # Get contact number from session if available
        contact_number = request.session.get('user_contact_number', '')

        # If not in session, try to get from recent bookings
        if not contact_number:
            try:
                recent_booking = Booking.objects.filter(
                    email=request.user.email
                ).order_by('-created_at').first()

                if recent_booking:
                    contact_number = recent_booking.contact_number
            except Exception as e:
                print(f"Error getting contact number: {str(e)}")

        user_info = {
            'full_name': user_full_name,
            'email': request.user.email,
            'contact_number': contact_number
        }

    context = {
        'schedules': schedules,
        'vehicle_types': vehicle_types,
        'selected_schedule': selected_schedule,
        'user_info': user_info,
    }

    return render(request, 'booking.html', context)


def guidelines_view(request):
    """View for displaying travel guidelines"""
    # Get all guidelines ordered by effective date (newest first)
    guidelines = TravelGuideline.objects.all().order_by('-effective_date')

    context = {
        'guidelines': guidelines,
    }

    return render(request, 'guidelines.html', context)
def get_schedule(request, pk):
    """
    API endpoint to get schedule details by ID
    """
    try:
        schedule = get_object_or_404(Schedule, pk=pk)

        # Format the data for the response
        schedule_data = {
            'id': schedule.id,
            'vessel': {
                'id': schedule.vessel.id,
                'name': schedule.vessel.name,
                'capacity': schedule.vessel.passenger_capacity,
                'cargo_capacity': schedule.vessel.cargo_capacity
            },
            'route': {
                'id': schedule.route.id,
                'name': schedule.route.name,
                'origin': schedule.route.origin,
                'destination': schedule.route.destination,
                'distance': schedule.route.distance,
                'duration': str(schedule.route.estimated_duration)
            },
            'departure_datetime': schedule.departure_datetime.isoformat(),
            'arrival_datetime': schedule.arrival_datetime.isoformat(),
            'available_seats': schedule.available_seats,
            'available_cargo_space': schedule.available_cargo_space,
            'status': schedule.status,
            'notes': schedule.notes if hasattr(schedule, 'notes') else ''
        }

        return JsonResponse({'success': True, 'schedule': schedule_data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def get_vessel_capacity(request, vessel_id):
    """
    API endpoint to get vessel capacity information
    """
    try:
        vessel = get_object_or_404(Vessel, id=vessel_id)

        # Return vessel capacity data
        capacity_data = {
            'id': vessel.id,
            'name': vessel.name,
            'capacity_passengers': vessel.capacity_passengers,
            'capacity_cargo': vessel.capacity_cargo
        }

        return JsonResponse({'success': True, 'capacity': capacity_data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def mark_payment_complete(request, booking_reference):
    """
    Mark a booking as paid after GCash payment
    """
    if request.method == 'POST':
        try:
            booking = get_object_or_404(Booking, booking_reference=booking_reference)
            payment_method = request.POST.get('payment_method', 'gcash')

            print(f"Processing payment completion for booking: {booking_reference}")
            print(f"Booking type: {booking.booking_type}")
            print(f"Payment method: {payment_method}")

            # Use the total_fare that was already calculated and stored in the booking
            if hasattr(booking, 'total_fare') and booking.total_fare:
                payment_amount = booking.total_fare
                print(f"Using stored total_fare: {payment_amount}")
            else:
                # Calculate payment amount based on booking type as fallback
                if booking.booking_type == 'passenger':
                    adult_passengers = int(booking.adult_passengers or 0)
                    child_passengers = int(booking.child_passengers or 0)
                    student_passengers = int(booking.student_passengers or 0)
                    senior_passengers = int(booking.senior_passengers or 0)

                    adult_fare = booking.schedule.adult_fare or Decimal('0.00')
                    child_fare = booking.schedule.child_fare or Decimal('0.00')
                    student_fare = booking.schedule.student_fare or adult_fare
                    senior_fare = booking.schedule.senior_fare or adult_fare

                    payment_amount = (adult_passengers * adult_fare) + (child_passengers * child_fare) + \
                                    (student_passengers * student_fare) + (senior_passengers * senior_fare)
                    print(f"Calculated passenger fare: {payment_amount}")
                elif booking.booking_type == 'vehicle':
                    # Use the base_fare from vehicle_type
                    if booking.vehicle_type:
                        payment_amount = booking.vehicle_type.base_fare
                        print(f"Using vehicle base fare: {payment_amount}")
                    else:
                        payment_amount = Decimal('0.00')
                        print("Warning: Vehicle booking without vehicle type")

            # Create payment record with all required fields
            payment = Payment.objects.create(
                booking=booking,
                amount_paid=payment_amount,
                amount_received=payment_amount,  # For GCash, received amount equals paid amount
                change_amount=Decimal('0.00'),   # No change for GCash payments
                payment_method=payment_method,
                payment_date=timezone.now(),
                payment_reference=f"PAY-{timezone.now().strftime('%Y%m%d')}-{booking_reference[-6:]}"
            )
            print(f"Created payment record: {payment.id}")

            # Update booking status
            booking.is_paid = True
            booking.save()
            print(f"Marked booking as paid: {booking.is_paid}")

            messages.success(request, "Payment successful! Your booking is confirmed.")
            print(f"Redirecting to booking confirmation: {booking_reference}")
            return redirect('booking_confirmation', booking_reference=booking.booking_reference)

        except Booking.DoesNotExist:
            print(f"Booking not found: {booking_reference}")
            messages.error(request, "Invalid booking reference.")
            return redirect('home')
        except Exception as e:
            print(f"Error processing payment: {str(e)}")
            messages.error(request, f"Error processing payment: {str(e)}")
            return redirect('payment', booking_reference=booking_reference)

    # If not POST, redirect to payment page
    return redirect('payment', booking_reference=booking_reference)
import qrcode
from django.http import HttpResponse
from io import BytesIO

def get_schedule_fares(request, schedule_id):
    """API endpoint to get fare information for a specific schedule"""
    schedule = get_object_or_404(Schedule, id=schedule_id)
    return JsonResponse({
        'adult_fare': str(schedule.adult_fare),
        'child_fare': str(schedule.child_fare),
        'student_fare': str(schedule.student_fare) if schedule.student_fare else str(schedule.adult_fare),
        'senior_fare': str(schedule.senior_fare) if schedule.senior_fare else str(schedule.adult_fare)
    })

def get_booking_details(request, booking_reference):
    try:
        booking = get_object_or_404(Booking, booking_reference=booking_reference)
        total_amount = calculate_booking_payment(booking)

        booking_data = {
            'success': True,
            'booking_type': booking.get_booking_type_display(),
            'passenger_name': booking.full_name,
            'contact_number': booking.contact_number,
            'email': booking.email,
            'schedule': str(booking.schedule),
            'total_amount': float(total_amount),
            'departure_datetime': booking.schedule.departure_datetime.strftime('%B %d, %Y %I:%M %p'),
            'is_paid': booking.is_paid,
            'created_at': booking.created_at.strftime('%B %d, %Y %I:%M %p'),
        }

        if booking.booking_type == 'passenger':
            booking_data.update({
                'number_of_passengers': booking.number_of_passengers,
                'cargo_weight': float(booking.cargo_weight or 0)
            })
        elif booking.booking_type == 'vehicle':
            booking_data.update({
                'vehicle_type': booking.vehicle_type.name if booking.vehicle_type else 'Standard',
                'plate_number': booking.plate_number or 'N/A',
                'occupant_count': booking.occupant_count,
                'cargo_weight': float(booking.cargo_weight or 0)
            })

        return JsonResponse(booking_data)
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Booking not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def generate_qr_code(request, booking_reference):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(booking_reference)  # Just the reference, no extra formatting
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    return HttpResponse(buffer, content_type='image/png')


# Add these new HTMX-friendly views
import logging
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .models import Booking, Payment
from utils.sms import send_payment_confirmation_sms
from utils.email import send_booking_confirmation_email
# Configure logger
logger = logging.getLogger(__name__)

@require_http_methods(["POST"])
def process_payment_htmx(request):
    booking_reference = request.POST.get('booking_reference')
    logger.info(f"Processing payment for booking: {booking_reference}")

    try:
        total_amount = Decimal(request.POST.get('total_amount', '0'))
        amount_received = Decimal(request.POST.get('amount_received', '0'))

        logger.debug(f"Payment details - Total: ₱{total_amount}, Received: ₱{amount_received}")

        booking = get_object_or_404(Booking, booking_reference=booking_reference)
        logger.debug(f"Found booking - Customer: {booking.full_name}, Contact: {booking.contact_number}")
        logger.debug(f"Booking type: {booking.booking_type}")

        if booking.booking_type == 'vehicle' and booking.vehicle_type:
            logger.debug(f"Vehicle type: {booking.vehicle_type.name}, Base fare: {booking.vehicle_type.base_fare}")

        if amount_received < total_amount:
            logger.warning(f"Insufficient payment - Expected: ₱{total_amount}, Received: ₱{amount_received}")
            return HttpResponseBadRequest("Amount received is less than total amount")

        # Create payment record
        payment = Payment.objects.create(
            booking=booking,
            amount_paid=total_amount,
            amount_received=amount_received,
            change_amount=amount_received - total_amount,
            payment_method='cash',
            payment_date=timezone.now(),
            payment_reference=f"PAY-{timezone.now().strftime('%Y%m%d')}-{booking_reference[-6:]}"
        )
        logger.info(f"Payment record created - Reference: {payment.payment_reference}")

        # Update booking status
        booking.is_paid = True
        booking.save()
        logger.info("Booking marked as paid")

        # Send confirmation email after payment is recorded
        try:
            email_sent = send_booking_confirmation_email(booking)
            if email_sent:
                logger.info("Confirmation email sent successfully")
            else:
                logger.warning("Failed to send confirmation email")
        except Exception as email_error:
            logger.error(f"Email sending error: {str(email_error)}", exc_info=True)
            # Continue processing even if email fails

        # Return JSON response for AJAX request
        if 'X-Requested-With' in request.headers:
            return JsonResponse({
                'success': True,
                'booking_reference': booking_reference,
                'customer_name': booking.full_name,
                'total_amount': float(total_amount),
                'payment_reference': payment.payment_reference,
                'message': 'Payment processed successfully'
            })
        else:
            # For non-AJAX requests, redirect to print ticket page
            return HttpResponseRedirect(reverse('print_ticket', args=[booking_reference]))

    except Exception as e:
        logger.error(f"Payment processing error: {str(e)}", exc_info=True)
        # Return JSON error for AJAX request
        if 'X-Requested-With' in request.headers:
            return JsonResponse({
                'success': False,
                'error': f"Error processing payment: {str(e)}"
            }, status=400)
        else:
            return HttpResponseBadRequest(f"Error processing payment: {str(e)}")
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.template.response import TemplateResponse
from .models import Booking

def booking_detail(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    return TemplateResponse(request, 'dashboard/partials/booking_details.html', {
        'booking': booking
    })

def booking_delete(request, booking_id):
    if request.method == 'DELETE':
        booking = get_object_or_404(Booking, id=booking_id)
        booking.delete()
        return HttpResponse(status=200)
    return HttpResponse(status=405)

def booking(request):
    """View for displaying and handling the booking form"""
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
            # Pre-calculate the fare rates for JavaScript
            adult_fare = selected_schedule.adult_fare
            child_fare = selected_schedule.child_fare
        except Schedule.DoesNotExist:
            messages.error(request, "The selected schedule does not exist.")
            return redirect('booking')

    context = {
        'schedules': schedules,
        'vehicle_types': vehicle_types,
        'selected_schedule': selected_schedule,
    }

    return render(request, 'booking.html', context)

def schedules_view(request):
    """View for displaying ferry schedules"""
    # Get upcoming schedules
    schedules = Schedule.objects.filter(
        departure_datetime__gt=timezone.now(),
        status='scheduled'
    ).order_by('departure_datetime')

    # Get filter parameters
    route = request.GET.get('route', '')
    date = request.GET.get('date', '')

    # Apply filters if provided
    if route:
        schedules = schedules.filter(route__name__icontains=route)

    if date:
        try:
            search_date = timezone.datetime.strptime(date, '%Y-%m-%d').date()
            schedules = schedules.filter(departure_datetime__date=search_date)
        except ValueError:
            pass

    context = {
        'schedules': schedules,
        'selected_route': route,
        'selected_date': date,
    }

    return render(request, 'schedules.html', context)
from django.http import JsonResponse
from .models import Vessel

def get_vessels(request):
    try:
        vessels = Vessel.objects.all().values('id', 'name', 'capacity_passengers', 'capacity_cargo')
        return JsonResponse({
            'success': True,
            'vessels': list(vessels)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })



def get_schedule_fares(request, schedule_id):
    """API endpoint to get fare information for a specific schedule"""
    schedule = get_object_or_404(Schedule, id=schedule_id)
    return JsonResponse({
        'adult_fare': str(schedule.adult_fare),
        'child_fare': str(schedule.child_fare)
    })


def get_schedule_fares(request, schedule_id):
    """API endpoint to get fare information for a specific schedule"""
    try:
        schedule = get_object_or_404(Schedule, id=schedule_id)
        return JsonResponse({
            'success': True,
            'adult_fare': str(schedule.adult_fare),
            'child_fare': str(schedule.child_fare)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)

def calculate_fare(request):
    """HTMX endpoint for calculating fares"""
    try:
        schedule_id = request.GET.get('schedule')
        adult_count = int(request.GET.get('adult_passengers', 0))
        child_count = int(request.GET.get('child_passengers', 0))

        schedule = Schedule.objects.get(id=schedule_id)
        adult_total = schedule.adult_fare * adult_count
        child_total = schedule.child_fare * child_count
        total = adult_total + child_total

        return render(request, 'partials/fare_summary.html', {
            'adult_total': adult_total,
            'child_total': child_total,
            'total': total
        })
    except Exception as e:
        return HttpResponse(f"Error calculating fare: {str(e)}")


def payment_view(request, booking_reference):
    try:
        booking = Booking.objects.get(booking_reference=booking_reference)
        payment_amount = Decimal('0.00')

        if booking.booking_type == 'passenger':
            # Ensure we have valid numbers for calculation
            adult_passengers = int(booking.adult_passengers or 0)
            child_passengers = int(booking.child_passengers or 0)
            adult_fare = booking.schedule.adult_fare or Decimal('0.00')
            child_fare = booking.schedule.child_fare or Decimal('0.00')

            payment_amount = (adult_passengers * adult_fare) + (child_passengers * child_fare)

        elif booking.booking_type == 'vehicle':
            # Only use the base fare for vehicle bookings
            payment_amount = booking.vehicle_type.base_fare if booking.vehicle_type else Decimal('0.00')

        return render(request, 'payment.html', {
            'booking': booking,
            'payment_amount': payment_amount
        })

    except Booking.DoesNotExist:
        messages.error(request, "Invalid booking reference.")
        return redirect('booking')
    except Exception as e:
        messages.error(request, f"Error processing payment: {str(e)}")
        return redirect('booking')

def booking_confirmation(request, booking_reference):
    """
    Display booking confirmation details after successful payment
    """
    try:
        booking = get_object_or_404(Booking, booking_reference=booking_reference)

        # Get the associated payment if it exists
        try:
            payment = Payment.objects.get(booking=booking)
        except Payment.DoesNotExist:
            payment = None

        context = {
            'booking': booking,
            'payment': payment,
            'schedule': booking.schedule,
        }

        return render(request, 'booking_confirmation.html', context)

    except Exception as e:
        messages.error(request, f"Error retrieving booking: {str(e)}")
        return redirect('home')

from django.shortcuts import render
from decimal import Decimal
def print_ticket(request, booking_reference):
    """View for generating a printable ticket"""
    booking = get_object_or_404(Booking, booking_reference=booking_reference)
    return render(request, 'tickets/print_ticket.html', {
        'booking': booking
    })

def calculate_change(request):
    """Calculate change amount for cash payments via HTMX"""
    try:
        amount_received = Decimal(request.GET.get('amount_received', 0))
        total_amount = Decimal(request.GET.get('total_amount', 0))
        change = amount_received - total_amount if amount_received > total_amount else Decimal('0.00')

        return render(request, 'dashboard/partials/change_display.html', {
            'change': change,
            'is_sufficient': amount_received >= total_amount
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def routes_view(request):
    """Public view for displaying available routes"""
    routes = Route.objects.filter(active=True).order_by('name')

    # Get upcoming schedules for each route
    for route in routes:
        route.upcoming_schedules = Schedule.objects.filter(
            route=route,
            departure_datetime__gte=timezone.now(),
            status='scheduled'
        ).order_by('departure_datetime')[:3]

    return render(request, 'routes.html', {'routes': routes})

@login_required
@staff_member_required
def payment_list(request):
    """
    Display a list of all payments for admin dashboard
    """
    payments = Payment.objects.all().order_by('-payment_date')

    # Get filter parameters
    booking_ref = request.GET.get('booking_ref', '')
    payment_method = request.GET.get('payment_method', '')

    # Apply filters if provided
    if booking_ref:
        payments = payments.filter(booking__booking_reference__icontains=booking_ref)

    if payment_method:
        payments = payments.filter(payment_method=payment_method)

    # Calculate total revenue
    total_revenue = payments.aggregate(total=models.Sum('amount_paid'))['total'] or 0

    context = {
        'payments': payments,
        'total_revenue': total_revenue,
        'payment_methods': Payment.PAYMENT_METHOD_CHOICES,
        'selected_method': payment_method,
        'booking_ref': booking_ref
    }

    return render(request, 'dashboard/payments.html', context)

@login_required
@staff_member_required
def process_specific_payment(request, booking_reference):
    """View for processing payment for a specific booking"""
    try:
        booking = get_object_or_404(Booking, booking_reference=booking_reference)

        # Calculate payment amount based on booking type
        if booking.booking_type == 'passenger':
            adult_total = booking.adult_passengers * booking.schedule.adult_fare
            child_total = booking.child_passengers * booking.schedule.child_fare

            # Calculate student and senior fare totals
            student_fare = booking.schedule.student_fare if booking.schedule.student_fare is not None else booking.schedule.adult_fare
            senior_fare = booking.schedule.senior_fare if booking.schedule.senior_fare is not None else booking.schedule.adult_fare
            student_total = booking.student_passengers * student_fare
            senior_total = booking.senior_passengers * senior_fare

            total_amount = adult_total + child_total + student_total + senior_total

            # Store these values for display in the template
            booking.adult_fare_total = adult_total
            booking.child_fare_total = child_total
            booking.student_fare_total = student_total
            booking.senior_fare_total = senior_total
        elif booking.booking_type == 'vehicle' and booking.vehicle_type:
            total_amount = booking.vehicle_type.base_fare
        else:
            total_amount = Decimal('0.00')

        context = {
            'booking': booking,
            'total_amount': total_amount,
        }

        return render(request, 'dashboard/process_payment.html', context)
    except Exception as e:
        messages.error(request, f"Error processing payment: {str(e)}")
        return redirect('payments')



@staff_member_required
def add_rating(request):
    """
    Add a new rating/testimonial from the admin dashboard
    """
    if request.method == 'POST':
        try:
            vessel_id = request.POST.get('vessel')
            vessel = get_object_or_404(Vessel, id=vessel_id)

            # Create new rating
            rating = Rating.objects.create(
                vessel=vessel,
                rating=int(request.POST.get('rating')),
                comment=request.POST.get('comment', ''),
                full_name=request.POST.get('full_name'),
                email=request.POST.get('email', '')
            )

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    # GET requests should redirect to ratings list
    return redirect('dashboard_ratings')

def ratings(request):
    """
    Public view for displaying and submitting ratings/testimonials
    """
    # Get all approved ratings ordered by creation date (newest first)
    # You might want to add an 'approved' field to your Rating model if you want to moderate reviews
    ratings_list = Rating.objects.all().order_by('-created_at')

    # Calculate average rating
    avg_rating = ratings_list.aggregate(avg=models.Avg('rating'))['avg'] or 0
    avg_rating = round(avg_rating, 1)

    # Get rating distribution
    rating_distribution = []
    for i in range(1, 6):
        count = ratings_list.filter(rating=i).count()
        percentage = (count / ratings_list.count() * 100) if ratings_list.count() > 0 else 0
        rating_distribution.append({
            'stars': i,
            'count': count,
            'percentage': round(percentage, 1)
        })

    # Get all active vessels for the rating form
    vessels = Vessel.objects.filter(active=True).order_by('name')

    # Handle form submission
    if request.method == 'POST':
        try:
            vessel_id = request.POST.get('vessel')
            vessel = get_object_or_404(Vessel, id=vessel_id)

            # Create new rating
            rating = Rating.objects.create(
                vessel=vessel,
                rating=int(request.POST.get('rating')),
                comment=request.POST.get('comment', ''),
                full_name=request.POST.get('full_name'),
                email=request.POST.get('email', '')
            )

            messages.success(request, "Thank you for your feedback! Your rating has been submitted.")
            return redirect('ratings')
        except Exception as e:
            messages.error(request, f"Error submitting rating: {str(e)}")

    context = {
        'ratings': ratings_list,
        'avg_rating': avg_rating,
        'rating_distribution': rating_distribution,
        'vessels': vessels
    }

    return render(request, 'ratings.html', context)

def get_schedule(request, pk):
    """
    API endpoint to get schedule details by ID
    """
    try:
        schedule = get_object_or_404(Schedule, pk=pk)

        # Format the data for the response
        schedule_data = {
            'id': schedule.id,
            'vessel': {
                'id': schedule.vessel.id,
                'name': schedule.vessel.name,
                'capacity': schedule.vessel.passenger_capacity,
                'cargo_capacity': schedule.vessel.cargo_capacity
            },
            'route': {
                'id': schedule.route.id,
                'name': schedule.route.name,
                'origin': schedule.route.origin,
                'destination': schedule.route.destination,
                'distance': schedule.route.distance,
                'duration': str(schedule.route.estimated_duration)
            },
            'departure_datetime': schedule.departure_datetime.isoformat(),
            'arrival_datetime': schedule.arrival_datetime.isoformat(),
            'available_seats': schedule.available_seats,
            'available_cargo_space': schedule.available_cargo_space,
            'status': schedule.status,
            'notes': schedule.notes if hasattr(schedule, 'notes') else ''
        }

        return JsonResponse({'success': True, 'schedule': schedule_data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def get_vessel_capacity(request, vessel_id):
    """
    API endpoint to get vessel capacity information
    """
    try:
        vessel = get_object_or_404(Vessel, id=vessel_id)

        # Return vessel capacity data
        capacity_data = {
            'id': vessel.id,
            'name': vessel.name,
            'capacity_passengers': vessel.capacity_passengers,
            'capacity_cargo': vessel.capacity_cargo
        }

        return JsonResponse({'success': True, 'capacity': capacity_data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# This function has been moved to the main mark_payment_complete function at the top of the file
import qrcode
from django.http import HttpResponse
from io import BytesIO

def get_schedule_fares(request, schedule_id):
    """API endpoint to get fare information for a specific schedule"""
    schedule = get_object_or_404(Schedule, id=schedule_id)
    return JsonResponse({
        'adult_fare': str(schedule.adult_fare),
        'child_fare': str(schedule.child_fare)
    })

from decimal import Decimal

def calculate_total_fare(self):
    # If booking type is 'vehicle', skip fare calculations
    if self.booking_type == 'vehicle':
        return Decimal('0.00')

    adult_rate = self.adult_fare_rate if self.adult_fare_rate is not None else Decimal('0.00')
    child_rate = self.child_fare_rate if self.child_fare_rate is not None else Decimal('0.00')
    adult_total = self.adult_passengers * adult_rate
    child_total = self.child_passengers * child_rate
    return adult_total + child_total
def calculate_booking_payment(booking):
    if booking.booking_type == 'passenger':
        base_fare = 50
        cargo_fee = 30 * (booking.cargo_weight or 0)
        return base_fare * (booking.number_of_passengers or 0) + cargo_fee
    elif booking.booking_type == 'vehicle':
        # Use 0 as fallback if booking.vehicle_type.max_cargo_weight is None
        base_price = ((booking.vehicle_type.max_cargo_weight or 0) * 50
                      if booking.vehicle_type else 100)
        occupant_fee = 20 * (booking.occupant_count or 0)
        cargo_fee = 30 * (booking.cargo_weight or 0)
        return base_price + occupant_fee + cargo_fee
    return 0

def get_booking_details(request, booking_reference):
    try:
        booking = get_object_or_404(Booking, booking_reference=booking_reference)
        total_amount = calculate_booking_payment(booking)

        booking_data = {
            'success': True,
            'booking_type': booking.get_booking_type_display(),
            'passenger_name': booking.full_name,
            'contact_number': booking.contact_number,
            'email': booking.email,
            'schedule': str(booking.schedule),
            'total_amount': float(total_amount),
            'departure_datetime': booking.schedule.departure_datetime.strftime('%B %d, %Y %I:%M %p'),
            'is_paid': booking.is_paid,
            'created_at': booking.created_at.strftime('%B %d, %Y %I:%M %p'),
        }

        if booking.booking_type == 'passenger':
            booking_data.update({
                'number_of_passengers': booking.number_of_passengers,
                'cargo_weight': float(booking.cargo_weight or 0)
            })
        elif booking.booking_type == 'vehicle':
            booking_data.update({
                'vehicle_type': booking.vehicle_type.name if booking.vehicle_type else 'Standard',
                'plate_number': booking.plate_number or 'N/A',
                'occupant_count': booking.occupant_count,
                'cargo_weight': float(booking.cargo_weight or 0)
            })

        return JsonResponse(booking_data)
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Booking not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def generate_qr_code(request, booking_reference):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(booking_reference)  # Just the reference, no extra formatting
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    return HttpResponse(buffer, content_type='image/png')





# Add these imports if they're not already present
from django.template.loader import render_to_string
from django.http import HttpResponse

# Add these new HTMX-friendly views
@staff_member_required
def booking_details_html(request):
    reference = request.GET.get('payment-reference')
    if not reference:
        return HttpResponse('')

    try:
        booking = Booking.objects.select_related(
            'schedule',
            'schedule__route',
            'schedule__vessel',
            'vehicle_type'
        ).get(booking_reference=reference)

        # Calculate fares based on booking type
        if booking.booking_type == 'passenger':
            adult_fare = booking.schedule.adult_fare or Decimal('0')
            child_fare = booking.schedule.child_fare or Decimal('0')

            # Calculate student and senior fare totals
            student_fare = booking.schedule.student_fare if booking.schedule.student_fare is not None else adult_fare
            senior_fare = booking.schedule.senior_fare if booking.schedule.senior_fare is not None else adult_fare

            booking.adult_fare_total = adult_fare * booking.adult_passengers
            booking.child_fare_total = child_fare * booking.child_passengers
            booking.student_fare_total = student_fare * booking.student_passengers
            booking.senior_fare_total = senior_fare * booking.senior_passengers

            total_amount = booking.adult_fare_total + booking.child_fare_total + booking.student_fare_total + booking.senior_fare_total
        else:  # vehicle booking
            if booking.vehicle_type:
                # Calculate vehicle fare including base fare and additional charges
                base_fare = booking.vehicle_type.base_fare
                # Add vehicle fare to booking object for template access
                booking.vehicle_fare_total = base_fare
                total_amount = base_fare
            else:
                booking.vehicle_fare_total = Decimal('0')
                total_amount = Decimal('0')

        return render(request, 'dashboard/partials/booking_details.html', {
            'booking': booking,
            'total_amount': total_amount
        })

    except Booking.DoesNotExist:
        return render(request, 'dashboard/partials/booking_details.html', {
            'booking': None
        })
from django.http import HttpResponseBadRequest


from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.template.response import TemplateResponse
from .models import Booking


from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Rating, Vessel

@login_required
def submit_rating(request):
    if request.method == 'POST':
        try:
            vessel_id = request.POST.get('vessel')
            rating = request.POST.get('rating')
            comment = request.POST.get('comment')

            # Create new rating (initially not approved)
            new_rating = Rating.objects.create(
                user=request.user,
                vessel_id=vessel_id,
                rating=rating,
                comment=comment,
                is_approved=False,  # Set to false by default
                full_name=request.user.get_full_name() or request.user.username
            )

            return JsonResponse({
                'success': True,
                'message': 'Thank you! Your review will be visible after approval.'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

    return JsonResponse({
        'success': False,
        'error': 'Invalid request method'
    })

def ratings(request):
    """
    Public view for displaying and submitting ratings/testimonials
    """
    # Get all approved ratings ordered by creation date
    ratings_list = Rating.objects.filter(is_approved=True).order_by('-created_at')

    # Calculate average rating
    avg_rating = ratings_list.aggregate(avg=models.Avg('rating'))['avg'] or 0
    avg_rating = round(avg_rating, 1)

    # Get rating distribution
    rating_distribution = []
    for i in range(1, 6):
        count = ratings_list.filter(rating=i).count()
        percentage = (count / ratings_list.count() * 100) if ratings_list.count() > 0 else 0
        rating_distribution.append({
            'stars': i,
            'count': count,
            'percentage': round(percentage, 1)
        })

    # Get all active vessels for the rating form
    vessels = Vessel.objects.filter(active=True).order_by('name')

    # Get user's existing ratings if authenticated
    user_ratings = {}
    if request.user.is_authenticated:
        user_ratings = {
            rating.vessel_id: rating
            for rating in Rating.objects.filter(user=request.user)
        }

    context = {
        'ratings': ratings_list,
        'avg_rating': avg_rating,
        'rating_distribution': rating_distribution,
        'vessels': vessels,
        'user_ratings': user_ratings
    }

    return render(request, 'ratings.html', context)



def booking_detail(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)

    # Calculate total amount based on booking type
    if booking.booking_type == 'passenger':
        adult_total = booking.adult_passengers * booking.schedule.adult_fare
        child_total = booking.child_passengers * booking.schedule.child_fare

        # Calculate student and senior fare totals
        student_fare = booking.schedule.student_fare if booking.schedule.student_fare is not None else booking.schedule.adult_fare
        senior_fare = booking.schedule.senior_fare if booking.schedule.senior_fare is not None else booking.schedule.adult_fare
        student_total = booking.student_passengers * student_fare
        senior_total = booking.senior_passengers * senior_fare

        total_amount = adult_total + child_total + student_total + senior_total

        # Store these values for display in the template
        booking.adult_fare_total = adult_total
        booking.child_fare_total = child_total
        booking.student_fare_total = student_total
        booking.senior_fare_total = senior_total
    elif booking.booking_type == 'vehicle' and booking.vehicle_type:
        total_amount = booking.vehicle_type.base_fare
        # Store the vehicle fare for display in the template
        booking.vehicle_fare_total = total_amount
    else:
        total_amount = 0

    return TemplateResponse(request, 'dashboard/partials/booking_details.html', {
        'booking': booking,
        'total_amount': total_amount
    })

def booking_delete(request, booking_id):
    if request.method == 'DELETE':
        booking = get_object_or_404(Booking, id=booking_id)
        booking.delete()
        return HttpResponse(status=200)
    return HttpResponse(status=405)

def booking(request):
    """View for displaying and handling the booking form"""
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
            # Pre-calculate the fare rates for JavaScript
            adult_fare = selected_schedule.adult_fare
            child_fare = selected_schedule.child_fare
        except Schedule.DoesNotExist:
            messages.error(request, "The selected schedule does not exist.")
            return redirect('booking')

    # Get user information if authenticated
    user_info = {}
    if request.user.is_authenticated:
        # Get the user's full name and contact information
        user_full_name = f"{request.user.first_name} {request.user.last_name}".strip()

        # Try to get the most recent booking for this user to get their contact number
        contact_number = ""
        try:
            # Use OR condition to find bookings by this user's email or full name
            recent_booking = Booking.objects.filter(
                email=request.user.email
            ).order_by('-created_at').first()

            if not recent_booking:
                # Try by full name if no booking found by email
                recent_booking = Booking.objects.filter(
                    full_name=user_full_name
                ).order_by('-created_at').first()

            if recent_booking:
                contact_number = recent_booking.contact_number
        except Exception as e:
            # If there's an error, just continue without the contact number
            print(f"Error getting contact number: {str(e)}")

        # Get emergency contact info from session if available
        emergency_contact_name = request.session.get('emergency_contact_name', '')
        emergency_contact_number = request.session.get('emergency_contact_number', '')
        emergency_contact_relationship = request.session.get('emergency_contact_relationship', '')

        user_info = {
            'full_name': user_full_name,
            'email': request.user.email,
            'contact_number': contact_number,
            'emergency_contact_name': emergency_contact_name,
            'emergency_contact_number': emergency_contact_number,
            'emergency_contact_relationship': emergency_contact_relationship
        }

    context = {
        'schedules': schedules,
        'vehicle_types': vehicle_types,
        'selected_schedule': selected_schedule,
        'user_info': user_info
    }

    return render(request, 'booking.html', context)




def get_schedule_fares(request, schedule_id):
    """API endpoint to get fare information for a specific schedule"""
    schedule = get_object_or_404(Schedule, id=schedule_id)
    return JsonResponse({
        'adult_fare': str(schedule.adult_fare),
        'child_fare': str(schedule.child_fare)
    })


def get_schedule_fares(request, schedule_id):
    """API endpoint to get fare information for a specific schedule"""
    try:
        schedule = get_object_or_404(Schedule, id=schedule_id)
        return JsonResponse({
            'success': True,
            'adult_fare': str(schedule.adult_fare),
            'child_fare': str(schedule.child_fare)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)

def calculate_fare(request):
    """HTMX endpoint for calculating fares"""
    try:
        schedule_id = request.GET.get('schedule')
        adult_count = int(request.GET.get('adult_passengers', 0))
        child_count = int(request.GET.get('child_passengers', 0))

        schedule = Schedule.objects.get(id=schedule_id)
        adult_total = schedule.adult_fare * adult_count
        child_total = schedule.child_fare * child_count
        total = adult_total + child_total

        return render(request, 'partials/fare_summary.html', {
            'adult_total': adult_total,
            'child_total': child_total,
            'total': total
        })
    except Exception as e:
        return HttpResponse(f"Error calculating fare: {str(e)}")


def payment_view(request, booking_reference):
    try:
        booking = Booking.objects.get(booking_reference=booking_reference)
        payment_amount = Decimal('0.00')

        if booking.booking_type == 'vehicle':
            # Add logging to track the amount
            base_fare = booking.vehicle_type.base_fare if booking.vehicle_type else Decimal('0.00')
            print(f"Vehicle base fare: {base_fare}")  # Debug log
            payment_amount = base_fare

            # Store the payment amount in the booking for later reference
            booking.total_fare = payment_amount
            booking.save(update_fields=['total_fare'])

        elif booking.booking_type == 'passenger':
            adult_passengers = int(booking.adult_passengers or 0)
            child_passengers = int(booking.child_passengers or 0)
            adult_fare = booking.schedule.adult_fare or Decimal('0.00')
            child_fare = booking.schedule.child_fare or Decimal('0.00')
            payment_amount = (adult_passengers * adult_fare) + (child_passengers * child_fare)

            # Store the payment amount in the booking for later reference
            booking.total_fare = payment_amount
            booking.save(update_fields=['total_fare'])

        print(f"Final payment amount: {payment_amount}")  # Debug log

        return render(request, 'payment.html', {
            'booking': booking,
            'payment_amount': payment_amount
        })

    except Booking.DoesNotExist:
        messages.error(request, "Invalid booking reference.")
        return redirect('booking')
    except Exception as e:
        messages.error(request, f"Error processing payment: {str(e)}")
        return redirect('booking')

def booking_confirmation(request, booking_reference):
    """
    Display booking confirmation details after successful payment
    """
    try:
        booking = get_object_or_404(Booking, booking_reference=booking_reference)

        # Get the associated payment if it exists
        try:
            payment = Payment.objects.get(booking=booking)
        except Payment.DoesNotExist:
            payment = None

        context = {
            'booking': booking,
            'payment': payment,
            'schedule': booking.schedule,
        }

        return render(request, 'booking_confirmation.html', context)

    except Exception as e:
        messages.error(request, f"Error retrieving booking: {str(e)}")
        return redirect('home')

from django.db.models import Count, Sum, F, Case, When, DecimalField, Value
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone

from django.db.models import Count, Sum, F, Case, When, DecimalField, Value, IntegerField
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone

def reports_view(request):
    # Get filter parameters with defaults
    month = int(request.GET.get('month', timezone.now().month))
    year = int(request.GET.get('year', timezone.now().year))
    selected_route = request.GET.get('route', '')
    selected_vessel = request.GET.get('vessel', '')

    # Get passenger boarding list specific filters
    departure_date = request.GET.get('departure_date', '')
    departure_time = request.GET.get('departure_time', '')
    selected_schedule = request.GET.get('schedule', '')
    selected_passenger_type = request.GET.get('passenger_type', '')
    passenger_name = request.GET.get('passenger_name', '')

    # Get vehicle list specific filters
    vehicle_departure_date = request.GET.get('vehicle_departure_date', '')
    selected_vehicle_schedule = request.GET.get('vehicle_schedule', '')
    selected_vehicle_type = request.GET.get('vehicle_type', '')
    vehicle_plate = request.GET.get('vehicle_plate', '')

    # Get revenue report specific filters
    selected_payment_method = request.GET.get('payment_method', '')
    selected_booking_type = request.GET.get('booking_type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    routes = Route.objects.filter(active=True)
    vessels = Vessel.objects.filter(active=True)

    # Get upcoming schedules for the boarding list filter dropdown
    schedules = Schedule.objects.select_related('route', 'vessel').filter(
        departure_datetime__gte=timezone.now()
    ).order_by('departure_datetime')[:30]  # Limit to next 30 schedules

    # Get all vehicle types for the filter dropdown
    vehicle_types = VehicleType.objects.all().order_by('name')

    # Base queryset for the selected month
    bookings = Booking.objects.filter(
        schedule__departure_datetime__year=year,
        schedule__departure_datetime__month=month,
        is_paid=True
    )

    # Apply route and vessel filters if selected
    if selected_route:
        bookings = bookings.filter(schedule__route_id=selected_route)
    if selected_vessel:
        bookings = bookings.filter(schedule__vessel_id=selected_vessel)

    # Apply revenue report specific filters
    if selected_booking_type:
        bookings = bookings.filter(booking_type=selected_booking_type)

    # Date range filters for revenue report
    if date_from:
        try:
            date_from_obj = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
            bookings = bookings.filter(created_at__date__gte=date_from_obj)
        except ValueError:
            # Invalid date format, ignore filter
            pass

    if date_to:
        try:
            date_to_obj = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
            bookings = bookings.filter(created_at__date__lte=date_to_obj)
        except ValueError:
            # Invalid date format, ignore filter
            pass

    # Calculate monthly metrics
    monthly_bookings_count = bookings.count()
    monthly_revenue = bookings.aggregate(
        total=Coalesce(Sum('total_fare'), Value(0, output_field=DecimalField()))
    )['total']

    # Calculate previous month's metrics
    prev_month = timezone.datetime(year, month, 1) - timezone.timedelta(days=1)
    prev_bookings = Booking.objects.filter(
        schedule__departure_datetime__year=prev_month.year,
        schedule__departure_datetime__month=prev_month.month,
        is_paid=True
    )

    prev_bookings_count = prev_bookings.count()
    prev_revenue = prev_bookings.aggregate(
        total=Coalesce(Sum('total_fare'), Value(0, output_field=DecimalField()))
    )['total']

    # Calculate growth percentages
    booking_growth = ((monthly_bookings_count - prev_bookings_count) / (prev_bookings_count or 1)) * 100 if prev_bookings_count else 0
    revenue_growth = ((monthly_revenue - prev_revenue) / (prev_revenue or 1)) * 100 if prev_revenue else 0

    # Calculate average booking value
    avg_booking_value = monthly_revenue / monthly_bookings_count if monthly_bookings_count > 0 else 0

    # Calculate occupancy metrics
    total_capacity = Schedule.objects.filter(
        departure_datetime__year=year,
        departure_datetime__month=month
    ).aggregate(
        total_capacity=Coalesce(Sum('vessel__capacity_passengers'), Value(0))
    )['total_capacity']

    occupancy_rate = (monthly_bookings_count / (total_capacity or 1)) * 100 if total_capacity else 0

    # Calculate route performance
    route_performance = []
    for route in routes:
        route_bookings = bookings.filter(schedule__route=route)
        route_revenue = route_bookings.aggregate(
            total=Coalesce(Sum('total_fare'), Value(0, output_field=DecimalField()))
        )['total']

        # Calculate total capacity for this route's schedules
        route_capacity = Schedule.objects.filter(
            route=route,
            departure_datetime__year=year,
            departure_datetime__month=month
        ).aggregate(
            total_capacity=Coalesce(Sum('vessel__capacity_passengers'), Value(0))
        )['total_capacity']

        # Calculate occupancy rate for this route
        route_occupancy = (route_bookings.count() / (route_capacity or 1)) * 100 if route_capacity else 0

        route_performance.append({
            'route': route,
            'total_bookings': route_bookings.count(),
            'revenue': route_revenue,
            'occupancy_rate': route_occupancy
        })

    # Sort route performance by revenue
    route_performance.sort(key=lambda x: x['revenue'], reverse=True)

    # Generate revenue data for chart
    revenue_data = []
    revenue_labels = []

    # Get data for the last 12 months
    for i in range(11, -1, -1):
        date = timezone.now() - timezone.timedelta(days=i*30)
        month_revenue = Booking.objects.filter(
            schedule__departure_datetime__year=date.year,
            schedule__departure_datetime__month=date.month,
            is_paid=True
        ).aggregate(
            total=Coalesce(Sum('total_fare'), Value(0, output_field=DecimalField()))
        )['total']

        revenue_data.append(float(month_revenue))
        revenue_labels.append(date.strftime('%b %Y'))

    # Get passenger boarding list data
    passenger_list_query = Passenger.objects.select_related(
        'booking',
        'booking__schedule',
        'booking__schedule__route',
        'booking__schedule__vessel'
    ).filter(
        booking__is_paid=True
    )

    # Apply boarding list specific filters
    if departure_date:
        try:
            departure_date_obj = timezone.datetime.strptime(departure_date, '%Y-%m-%d').date()
            passenger_list_query = passenger_list_query.filter(
                booking__schedule__departure_datetime__date=departure_date_obj
            )

            # Apply time filter if both date and time are provided
            if departure_time:
                try:
                    # Parse the time string into a time object
                    departure_time_obj = timezone.datetime.strptime(departure_time, '%H:%M').time()

                    # Filter by time - using __time to extract time part from datetime field
                    passenger_list_query = passenger_list_query.filter(
                        booking__schedule__departure_datetime__time=departure_time_obj
                    )
                except ValueError:
                    # Invalid time format, ignore time filter
                    pass
        except ValueError:
            # Invalid date format, ignore filter
            pass

    if selected_schedule:
        passenger_list_query = passenger_list_query.filter(
            booking__schedule_id=selected_schedule
        )

    if selected_passenger_type:
        passenger_list_query = passenger_list_query.filter(
            passenger_type=selected_passenger_type
        )

    # Apply passenger name filter if provided
    if passenger_name:
        passenger_list_query = passenger_list_query.filter(
            full_name__icontains=passenger_name
        )

    # Apply the same route and vessel filters as the main report
    if selected_route:
        passenger_list_query = passenger_list_query.filter(
            booking__schedule__route_id=selected_route
        )

    if selected_vessel:
        passenger_list_query = passenger_list_query.filter(
            booking__schedule__vessel_id=selected_vessel
        )



    # Order by departure date and passenger name
    passenger_list = passenger_list_query.order_by(
        'booking__schedule__departure_datetime',
        'full_name'
    )

    # Get vehicle bookings list data
    vehicle_list_query = Booking.objects.filter(
        booking_type='vehicle',
        is_paid=True
    ).select_related(
        'schedule',
        'schedule__route',
        'schedule__vessel',
        'vehicle_type'
    )

    # Apply vehicle list specific filters
    if vehicle_departure_date:
        try:
            vehicle_date_obj = timezone.datetime.strptime(vehicle_departure_date, '%Y-%m-%d').date()
            vehicle_list_query = vehicle_list_query.filter(
                schedule__departure_datetime__date=vehicle_date_obj
            )
        except ValueError:
            # Invalid date format, ignore filter
            pass

    if selected_vehicle_schedule:
        vehicle_list_query = vehicle_list_query.filter(
            schedule_id=selected_vehicle_schedule
        )

    if selected_vehicle_type:
        vehicle_list_query = vehicle_list_query.filter(
            vehicle_type_id=selected_vehicle_type
        )

    # Apply plate number filter if provided
    if vehicle_plate:
        vehicle_list_query = vehicle_list_query.filter(
            plate_number__icontains=vehicle_plate
        )

    # Apply the same route and vessel filters as the main report
    if selected_route:
        vehicle_list_query = vehicle_list_query.filter(
            schedule__route_id=selected_route
        )

    if selected_vessel:
        vehicle_list_query = vehicle_list_query.filter(
            schedule__vessel_id=selected_vessel
        )

    # Order by departure date and customer name
    vehicle_list = vehicle_list_query.order_by(
        'schedule__departure_datetime',
        'full_name'
    )

    # Get all vehicle types for the filter dropdown
    vehicle_types = VehicleType.objects.all().order_by('name')

    # Get revenue breakdown data

    # 1. Revenue by booking type
    passenger_revenue = bookings.filter(booking_type='passenger').aggregate(
        total=Coalesce(Sum('total_fare'), Value(0, output_field=DecimalField()))
    )['total']

    vehicle_revenue = bookings.filter(booking_type='vehicle').aggregate(
        total=Coalesce(Sum('total_fare'), Value(0, output_field=DecimalField()))
    )['total']

    cargo_revenue = bookings.filter(booking_type='cargo').aggregate(
        total=Coalesce(Sum('total_fare'), Value(0, output_field=DecimalField()))
    )['total']

    # Calculate percentages
    total_revenue = passenger_revenue + vehicle_revenue + cargo_revenue
    passenger_revenue_percent = round((passenger_revenue / total_revenue) * 100) if total_revenue > 0 else 0
    vehicle_revenue_percent = round((vehicle_revenue / total_revenue) * 100) if total_revenue > 0 else 0
    cargo_revenue_percent = round((cargo_revenue / total_revenue) * 100) if total_revenue > 0 else 0

    # 2. Revenue by payment method
    payments = Payment.objects.filter(
        booking__in=bookings
    )

    # Apply payment method filter if selected
    if selected_payment_method:
        payments = payments.filter(payment_method=selected_payment_method)

    cash_payments = payments.filter(payment_method='cash')
    gcash_payments = payments.filter(payment_method='gcash')

    cash_payment_count = cash_payments.count()
    gcash_payment_count = gcash_payments.count()

    cash_revenue = cash_payments.aggregate(
        total=Coalesce(Sum('amount_paid'), Value(0, output_field=DecimalField()))
    )['total']

    gcash_revenue = gcash_payments.aggregate(
        total=Coalesce(Sum('amount_paid'), Value(0, output_field=DecimalField()))
    )['total']

    # Calculate percentages
    payment_total = cash_revenue + gcash_revenue
    cash_revenue_percent = round((cash_revenue / payment_total) * 100) if payment_total > 0 else 0
    gcash_revenue_percent = round((gcash_revenue / payment_total) * 100) if payment_total > 0 else 0

    # 3. Revenue by passenger type
    # Get all passengers from the filtered bookings
    passengers = Passenger.objects.filter(booking__in=bookings)

    # Count by passenger type
    adult_count = passengers.filter(passenger_type='adult').count()
    child_count = passengers.filter(passenger_type='child').count()
    student_count = passengers.filter(passenger_type='student').count()
    senior_count = passengers.filter(passenger_type='senior').count()

    # Calculate revenue by passenger type
    # This is an approximation based on the fare rates and passenger counts
    adult_revenue = Decimal('0.00')
    child_revenue = Decimal('0.00')
    student_revenue = Decimal('0.00')
    senior_revenue = Decimal('0.00')

    for booking in bookings.filter(booking_type='passenger'):
        # Get passengers for this booking
        booking_passengers = Passenger.objects.filter(booking=booking)

        # Count by type
        booking_adult_count = booking_passengers.filter(passenger_type='adult').count()
        booking_child_count = booking_passengers.filter(passenger_type='child').count()
        booking_student_count = booking_passengers.filter(passenger_type='student').count()
        booking_senior_count = booking_passengers.filter(passenger_type='senior').count()

        # Get fare rates
        adult_rate = booking.adult_fare_rate or Decimal('0.00')
        child_rate = booking.child_fare_rate or Decimal('0.00')
        student_rate = booking.student_fare_rate or Decimal('0.00')
        senior_rate = booking.senior_fare_rate or Decimal('0.00')

        # Calculate revenue by type
        adult_revenue += booking_adult_count * adult_rate
        child_revenue += booking_child_count * child_rate
        student_revenue += booking_student_count * student_rate
        senior_revenue += booking_senior_count * senior_rate

    context = {
        'month': month,
        'year': year,
        'routes': routes,
        'vessels': vessels,
        'schedules': schedules,
        'selected_route': selected_route,
        'selected_vessel': selected_vessel,
        'selected_schedule': selected_schedule,
        'selected_passenger_type': selected_passenger_type,
        'departure_date': departure_date,
        'departure_time': departure_time,
        'passenger_name': passenger_name,
        'vehicle_plate': vehicle_plate,
        'vehicle_departure_date': vehicle_departure_date,
        'selected_vehicle_type': selected_vehicle_type,
        'selected_payment_method': selected_payment_method,
        'selected_booking_type': selected_booking_type,
        'date_from': date_from,
        'date_to': date_to,
        'monthly_bookings_count': monthly_bookings_count,
        'monthly_revenue': monthly_revenue,
        'booking_growth': booking_growth,
        'revenue_growth': revenue_growth,
        'avg_booking_value': avg_booking_value,
        'occupancy_rate': occupancy_rate,
        'route_performance': route_performance,
        'revenue_data': revenue_data,
        'revenue_labels': revenue_labels,
        'passenger_list': passenger_list,

        # Revenue breakdown data
        'passenger_revenue': passenger_revenue,
        'vehicle_revenue': vehicle_revenue,
        'passenger_revenue_percent': passenger_revenue_percent,
        'vehicle_revenue_percent': vehicle_revenue_percent,

        # Payment method data
        'cash_payment_count': cash_payment_count,
        'gcash_payment_count': gcash_payment_count,
        'cash_revenue': cash_revenue,
        'gcash_revenue': gcash_revenue,
        'cash_revenue_percent': cash_revenue_percent,
        'gcash_revenue_percent': gcash_revenue_percent,

        # Passenger type data
        'adult_count': adult_count,
        'child_count': child_count,
        'student_count': student_count,
        'senior_count': senior_count,
        'adult_revenue': adult_revenue,
        'child_revenue': child_revenue,
        'student_revenue': student_revenue,
        'senior_revenue': senior_revenue,

        # Vehicle data
        'vehicle_list': vehicle_list,
        'vehicle_types': vehicle_types,
        'selected_vehicle_schedule': selected_vehicle_schedule,
        'vehicle_departure_date': vehicle_departure_date
    }

    return render(request, 'dashboard/reports.html', context)
def routes_view(request):
    """Public view for displaying available routes"""
    routes = Route.objects.filter(active=True).order_by('name')

    # Get upcoming schedules for each route
    for route in routes:
        route.upcoming_schedules = Schedule.objects.filter(
            route=route,
            departure_datetime__gte=timezone.now(),
            status='scheduled'
        ).order_by('departure_datetime')[:3]

    return render(request, 'routes.html', {'routes': routes})

@login_required
@staff_member_required
def payment_list(request):
    """
    Display a list of all payments for admin dashboard
    """
    payments = Payment.objects.all().order_by('-payment_date')

    # Get filter parameters
    booking_ref = request.GET.get('booking_ref', '')
    payment_method = request.GET.get('payment_method', '')

    # Apply filters if provided
    if booking_ref:
        payments = payments.filter(booking__booking_reference__icontains=booking_ref)

    if payment_method:
        payments = payments.filter(payment_method=payment_method)

    # Calculate total revenue
    total_revenue = payments.aggregate(total=models.Sum('amount_paid'))['total'] or 0

    context = {
        'payments': payments,
        'total_revenue': total_revenue,
        'payment_methods': Payment.PAYMENT_METHOD_CHOICES,
        'selected_method': payment_method,
        'booking_ref': booking_ref
    }

    return render(request, 'dashboard/payments.html', context)

@login_required
@staff_member_required
def dashboard_ratings(request):
    """
    Display and manage ratings/testimonials in the admin dashboard
    """
    # Get all ratings ordered by creation date (newest first)
    ratings = Rating.objects.all().order_by('-created_at')

    # Get filter parameters
    min_rating = request.GET.get('min_rating', '')
    vessel_id = request.GET.get('vessel', '')

    # Apply filters if provided
    if min_rating and min_rating.isdigit():
        ratings = ratings.filter(rating__gte=int(min_rating))

    if vessel_id and vessel_id.isdigit():
        ratings = ratings.filter(vessel_id=int(vessel_id))

    # Calculate average rating
    avg_rating = ratings.aggregate(avg=models.Avg('rating'))['avg'] or 0
    avg_rating = round(avg_rating, 1)

    # Get rating distribution
    rating_distribution = []
    for i in range(1, 6):
        count = ratings.filter(rating=i).count()
        percentage = (count / ratings.count() * 100) if ratings.count() > 0 else 0
        rating_distribution.append({
            'stars': i,
            'count': count,
            'percentage': round(percentage, 1)
        })

    # Get all vessels for the filter dropdown
    vessels = Vessel.objects.filter(active=True).order_by('name')

    context = {
        'ratings': ratings,
        'avg_rating': avg_rating,
        'rating_distribution': rating_distribution,
        'vessels': vessels,
        'min_rating': min_rating,
        'selected_vessel': vessel_id
    }

    return render(request, 'dashboard/ratings.html', context)

@staff_member_required
def add_rating(request):
    """
    Add a new rating/testimonial from the admin dashboard
    """
    if request.method == 'POST':
        try:
            vessel_id = request.POST.get('vessel')
            vessel = get_object_or_404(Vessel, id=vessel_id)

            # Create new rating
            rating = Rating.objects.create(
                vessel=vessel,
                rating=int(request.POST.get('rating')),
                comment=request.POST.get('comment', ''),
                full_name=request.POST.get('full_name'),
                email=request.POST.get('email', '')
            )

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    # GET requests should redirect to ratings list
    return redirect('dashboard_ratings')

def ratings(request):
    """
    Public view for displaying and submitting ratings/testimonials
    """
    # Get all approved ratings ordered by creation date (newest first)
    # You might want to add an 'approved' field to your Rating model if you want to moderate reviews
    ratings_list = Rating.objects.all().order_by('-created_at')

    # Calculate average rating
    avg_rating = ratings_list.aggregate(avg=models.Avg('rating'))['avg'] or 0
    avg_rating = round(avg_rating, 1)

    # Get rating distribution
    rating_distribution = []
    for i in range(1, 6):
        count = ratings_list.filter(rating=i).count()
        percentage = (count / ratings_list.count() * 100) if ratings_list.count() > 0 else 0
        rating_distribution.append({
            'stars': i,
            'count': count,
            'percentage': round(percentage, 1)
        })

    # Get all active vessels for the rating form
    vessels = Vessel.objects.filter(active=True).order_by('name')

    # Handle form submission
    if request.method == 'POST':
        try:
            vessel_id = request.POST.get('vessel')
            vessel = get_object_or_404(Vessel, id=vessel_id)

            # Create new rating
            rating = Rating.objects.create(
                vessel=vessel,
                rating=int(request.POST.get('rating')),
                comment=request.POST.get('comment', ''),
                full_name=request.POST.get('full_name'),
                email=request.POST.get('email', '')
            )

            messages.success(request, "Thank you for your feedback! Your rating has been submitted.")
            return redirect('ratings')
        except Exception as e:
            messages.error(request, f"Error submitting rating: {str(e)}")

    context = {
        'ratings': ratings_list,
        'avg_rating': avg_rating,
        'rating_distribution': rating_distribution,
        'vessels': vessels
    }

    return render(request, 'ratings.html', context)

@login_required
@staff_member_required
def get_schedule(request, schedule_id):
    """API endpoint for getting schedule details"""
    try:
        schedule = get_object_or_404(Schedule, pk=schedule_id)

        return JsonResponse({
            'success': True,
            'schedule': {
                'id': schedule.id,
                'vessel_id': schedule.vessel.id,
                'route_id': schedule.route.id,
                'departure_datetime': schedule.departure_datetime.isoformat(),
                'arrival_datetime': schedule.arrival_datetime.isoformat(),
                'available_seats': schedule.available_seats,
                'available_cargo_space': schedule.available_cargo_space,
                'adult_fare': str(schedule.adult_fare),
                'child_fare': str(schedule.child_fare),
                'student_fare': str(schedule.student_fare) if schedule.student_fare else '',
                'senior_fare': str(schedule.senior_fare) if schedule.senior_fare else '',
                'status': schedule.status,
                'notes': schedule.notes
            }
        })
    except Schedule.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Schedule not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse
import logging

logger = logging.getLogger(__name__)

@staff_member_required
def rating_details(request, rating_id):
    logger.debug(f"Rating details requested for ID: {rating_id}")
    logger.debug(f"Headers: {request.headers}")

    rating = get_object_or_404(Rating.objects.select_related('vessel'), id=rating_id)

    if 'HX-Request' in request.headers:
        logger.debug("HTMX request detected, rendering partial template")
        return render(request, 'dashboard/partials/rating_details.html', {
            'rating': rating
        })

    logger.debug("Non-HTMX request detected")
    return JsonResponse({'error': 'HTMX request required'}, status=400)



def get_vessel_capacity(request, vessel_id):
    """
    API endpoint to get vessel capacity information
    """
    try:
        vessel = get_object_or_404(Vessel, id=vessel_id)

        # Return vessel capacity data
        capacity_data = {
            'id': vessel.id,
            'name': vessel.name,
            'capacity_passengers': vessel.capacity_passengers,
            'capacity_cargo': vessel.capacity_cargo
        }

        return JsonResponse({'success': True, 'capacity': capacity_data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# This function has been consolidated with the main mark_payment_complete function

import qrcode
from django.http import HttpResponse
from io import BytesIO

def get_schedule_fares(request, schedule_id):
    """API endpoint to get fare information for a specific schedule"""
    schedule = get_object_or_404(Schedule, id=schedule_id)
    return JsonResponse({
        'adult_fare': str(schedule.adult_fare),
        'child_fare': str(schedule.child_fare)
    })



def get_booking_details(request, booking_reference):
    try:
        booking = get_object_or_404(Booking, booking_reference=booking_reference)
        total_amount = calculate_booking_payment(booking)

        booking_data = {
            'success': True,
            'booking_type': booking.get_booking_type_display(),
            'passenger_name': booking.full_name,
            'contact_number': booking.contact_number,
            'email': booking.email,
            'schedule': str(booking.schedule),
            'total_amount': float(total_amount),
            'departure_datetime': booking.schedule.departure_datetime.strftime('%B %d, %Y %I:%M %p'),
            'is_paid': booking.is_paid,
            'created_at': booking.created_at.strftime('%B %d, %Y %I:%M %p'),
        }

        if booking.booking_type == 'passenger':
            booking_data.update({
                'number_of_passengers': booking.number_of_passengers,
                'cargo_weight': float(booking.cargo_weight or 0)
            })
        elif booking.booking_type == 'vehicle':
            booking_data.update({
                'vehicle_type': booking.vehicle_type.name if booking.vehicle_type else 'Standard',
                'plate_number': booking.plate_number or 'N/A',
                'occupant_count': booking.occupant_count,
                'cargo_weight': float(booking.cargo_weight or 0)
            })

        return JsonResponse(booking_data)
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Booking not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def generate_qr_code(request, booking_reference):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(booking_reference)  # Just the reference, no extra formatting
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    return HttpResponse(buffer, content_type='image/png')


# Add these imports if they're not already present
from django.template.loader import render_to_string
from django.http import HttpResponse
from decimal import Decimal
from django.shortcuts import render
from django.http import HttpResponse
from .models import Booking
# Add these new HTMX-friendly views
from django.views.decorators.http import require_http_methods


@staff_member_required
@staff_member_required

def booking_detail(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)

    # Calculate total amount based on booking type
    if booking.booking_type == 'passenger':
        adult_total = booking.adult_passengers * booking.schedule.adult_fare
        child_total = booking.child_passengers * booking.schedule.child_fare
        total_amount = adult_total + child_total

        # Store these values for display in the template
        booking.adult_fare_total = adult_total
        booking.child_fare_total = child_total
    elif booking.booking_type == 'vehicle' and booking.vehicle_type:
        total_amount = booking.vehicle_type.base_fare
        # Store the vehicle fare for display in the template
        booking.vehicle_fare_total = total_amount
    else:
        total_amount = 0

    return TemplateResponse(request, 'dashboard/partials/booking_details.html', {
        'booking': booking,
        'total_amount': total_amount
    })

def booking_delete(request, booking_id):
    if request.method == 'DELETE':
        booking = get_object_or_404(Booking, id=booking_id)
        booking.delete()
        return HttpResponse(status=200)
    return HttpResponse(status=405)

@staff_member_required
def vessels_view(request):
    vessels = Vessel.objects.all()
    return render(request, 'dashboard/vessels.html', {'vessels': vessels})

def schedule_view(request):
    schedules = Schedule.objects.all()


    return render(request, 'dashboard/schedules.html', {'schedules': schedules})

def routes_view(request):
    routes = Route.objects.all()

    return render(request, 'dashboard/routes.html', {'routes': routes})
def booking(request):
    """View for displaying and handling the booking form"""
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
            # Pre-calculate the fare rates for JavaScript
            adult_fare = selected_schedule.adult_fare
            child_fare = selected_schedule.child_fare
        except Schedule.DoesNotExist:
            messages.error(request, "The selected schedule does not exist.")
            return redirect('booking')

    context = {
        'schedules': schedules,
        'vehicle_types': vehicle_types,
        'selected_schedule': selected_schedule,
    }

    return render(request, 'booking.html', context)


from .utils import generate_booking_reference
from decimal import Decimal
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from .models import Schedule, Booking, VehicleType
from .utils import generate_booking_reference  # Assuming your utility function is in utils.py

def create_booking(request):
    """Process the booking form submission"""
    if request.method != 'POST':
        return redirect('booking')

    try:
        # Get selected schedule
        schedule_id = request.POST.get('schedule')
        print(f"Received schedule_id: {schedule_id}")

        if not schedule_id:
            messages.error(request, "No schedule selected.")
            return redirect('booking')

        schedule = get_object_or_404(Schedule, id=schedule_id)
        print(f"Found schedule: {schedule}")

        # Get common booking data
        booking_type = request.POST.get('booking_type', 'passenger')
        print(f"Booking type: {booking_type}")

        # Create new booking with common fields
        booking = Booking(
            schedule=schedule,
            booking_type=booking_type,
            booking_reference=generate_booking_reference(),
            full_name=request.POST.get('full_name'),
            contact_number=request.POST.get('contact_number'),
            email=request.POST.get('email'),
            emergency_contact_name=request.POST.get('emergency_contact_name'),
            emergency_contact_number=request.POST.get('emergency_contact_number'),
            emergency_contact_relationship=request.POST.get('emergency_contact_relationship'),
            is_paid=False
        )

        # Set type-specific fields
        if booking_type == 'passenger':
            booking.adult_passengers = int(request.POST.get('adult_passengers', 0) or 0)
            booking.child_passengers = int(request.POST.get('child_passengers', 0) or 0)
            booking.student_passengers = int(request.POST.get('student_passengers', 0) or 0)
            booking.senior_passengers = int(request.POST.get('senior_passengers', 0) or 0)

            booking.number_of_passengers = (
                booking.adult_passengers +
                booking.child_passengers +
                booking.student_passengers +
                booking.senior_passengers
            )

            booking.adult_fare_rate = schedule.adult_fare
            booking.child_fare_rate = schedule.child_fare
            booking.student_fare_rate = schedule.student_fare
            booking.senior_fare_rate = schedule.senior_fare

            print(f"Passenger booking - Adults: {booking.adult_passengers}, Children: {booking.child_passengers}, Students: {booking.student_passengers}, Seniors: {booking.senior_passengers}")
            print(f"Adult fare: {booking.adult_fare_rate}, Child fare: {booking.child_fare_rate}, Student fare: {booking.student_fare_rate}, Senior fare: {booking.senior_fare_rate}")

        else:  # vehicle booking
            vehicle_type_id = request.POST.get('vehicle_type')
            print(f"Vehicle type ID: {vehicle_type_id}")

            if not vehicle_type_id:
                messages.error(request, "Please select a vehicle type.")
                return redirect('booking')

            try:
                vehicle_type = get_object_or_404(VehicleType, id=vehicle_type_id)
                print(f"Found vehicle type: {vehicle_type.name}, base fare: {vehicle_type.base_fare}")

                booking.vehicle_type = vehicle_type
                booking.plate_number = request.POST.get('plate_number', '')
                booking.occupant_count = int(request.POST.get('occupant_count', 1) or 1)
                booking.cargo_weight = Decimal(request.POST.get('cargo_weight', 0) or 0)

                print(f"Vehicle details - Plate: {booking.plate_number}, Occupants: {booking.occupant_count}, Cargo: {booking.cargo_weight}")

                # Set fare rates to 0 for vehicle bookings to satisfy NOT NULL constraint
                booking.adult_fare_rate = Decimal('0.00')
                booking.child_fare_rate = Decimal('0.00')

                # Set total_fare to vehicle_type.base_fare
                booking.total_fare = vehicle_type.base_fare
                print(f"Setting total fare to: {booking.total_fare}")

                # Set number_of_passengers to occupant_count for vehicle bookings
                booking.number_of_passengers = booking.occupant_count

            except VehicleType.DoesNotExist:
                print(f"Vehicle type not found: {vehicle_type_id}")
                messages.error(request, "Selected vehicle type does not exist.")
                return redirect('booking')

        # Save the booking
        booking.save()
        print(f"Booking saved with ID: {booking.id}")

        # Save individual passenger information if it's a passenger booking
        if booking_type == 'passenger':
            # Process adult passengers
            for i in range(1, booking.adult_passengers + 1):
                passenger_name = request.POST.get(f'adult_passenger_name_{i}')
                if passenger_name:
                    Passenger.objects.create(
                        booking=booking,
                        full_name=passenger_name,
                        passenger_type='adult'
                    )

            # Process child passengers
            for i in range(1, booking.child_passengers + 1):
                passenger_name = request.POST.get(f'child_passenger_name_{i}')
                if passenger_name:
                    Passenger.objects.create(
                        booking=booking,
                        full_name=passenger_name,
                        passenger_type='child'
                    )

            # Process student passengers
            for i in range(1, booking.student_passengers + 1):
                passenger_name = request.POST.get(f'student_passenger_name_{i}')
                if passenger_name:
                    Passenger.objects.create(
                        booking=booking,
                        full_name=passenger_name,
                        passenger_type='student'
                    )

            # Process senior passengers
            for i in range(1, booking.senior_passengers + 1):
                passenger_name = request.POST.get(f'senior_passenger_name_{i}')
                if passenger_name:
                    Passenger.objects.create(
                        booking=booking,
                        full_name=passenger_name,
                        passenger_type='senior'
                    )

        # Log the booking details for debugging
        print(f"Created booking: {booking.booking_reference}, Type: {booking.booking_type}")
        if booking_type == 'vehicle':
            print(f"Vehicle Type: {booking.vehicle_type.name if booking.vehicle_type else 'None'}")
            print(f"Plate Number: {booking.plate_number}")
            print(f"Occupants: {booking.occupant_count}")
            print(f"Cargo Weight: {booking.cargo_weight}")

        # Redirect to payment
        messages.success(request, "Booking created successfully. Please complete your payment.")
        return redirect('payment', booking_reference=booking.booking_reference)

    except Exception as e:
        print(f"Error creating booking: {str(e)}")
        messages.error(request, f"Error creating booking: {str(e)}")
        return redirect('booking')

def get_schedule_fares(request, schedule_id):
    """API endpoint to get fare information for a specific schedule"""
    try:
        # Check if schedule_id is valid
        if not schedule_id or schedule_id == '0':
            return JsonResponse({
                'success': False,
                'error': 'Please select a valid schedule'
            }, status=400)

        schedule = get_object_or_404(Schedule, id=schedule_id)
        return JsonResponse({
            'success': True,
            'adult_fare': str(schedule.adult_fare),
            'child_fare': str(schedule.child_fare)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)

def calculate_fare(request):
    """HTMX endpoint for calculating fares"""
    try:
        schedule_id = request.GET.get('schedule')

        # Check if schedule_id is empty or None
        if not schedule_id or schedule_id == '0':
            return HttpResponse("Please select a schedule first")

        adult_count = int(request.GET.get('adult_passengers', 0))
        child_count = int(request.GET.get('child_passengers', 0))
        student_count = int(request.GET.get('student_passengers', 0))
        senior_count = int(request.GET.get('senior_passengers', 0))

        try:
            schedule = Schedule.objects.get(id=schedule_id)
            adult_total = schedule.adult_fare * adult_count
            child_total = schedule.child_fare * child_count

            # Handle student and senior fares, using adult fare as fallback if not set
            student_fare = schedule.student_fare if schedule.student_fare is not None else schedule.adult_fare
            senior_fare = schedule.senior_fare if schedule.senior_fare is not None else schedule.adult_fare

            student_total = student_fare * student_count
            senior_total = senior_fare * senior_count

            total = adult_total + child_total + student_total + senior_total

            return render(request, 'partials/fare_summary.html', {
                'adult_total': adult_total,
                'child_total': child_total,
                'student_total': student_total,
                'senior_total': senior_total,
                'total': total,
                'adult_fare': schedule.adult_fare,
                'child_fare': schedule.child_fare,
                'student_fare': student_fare,
                'senior_fare': senior_fare
            })
        except Schedule.DoesNotExist:
            return HttpResponse("Selected schedule not found")
    except Exception as e:
        return HttpResponse(f"Error calculating fare: {str(e)}")

def calculate_vehicle_fare(request):
    """HTMX endpoint for calculating vehicle fares"""
    try:
        vehicle_type_id = request.GET.get('vehicle_type')
        if not vehicle_type_id:
            return HttpResponse("Please select a vehicle type")

        # Log the request for debugging
        print(f"Calculating vehicle fare for vehicle type ID: {vehicle_type_id}")

        vehicle_type = get_object_or_404(VehicleType, id=vehicle_type_id)
        print(f"Found vehicle type: {vehicle_type.name}, base fare: {vehicle_type.base_fare}")

        # Get base fare for the vehicle type
        base_fare = vehicle_type.base_fare

        # You can add additional calculations here based on your business logic
        # For example, adding surcharges based on occupants, cargo weight, etc.

        context = {
            'vehicle_type': vehicle_type.name,
            'base_fare': base_fare,
            'total_fare': base_fare  # Modify this if you add surcharges
        }

        print(f"Rendering vehicle fare summary with context: {context}")
        return render(request, 'partials/vehicle_fare_summary.html', context)
    except VehicleType.DoesNotExist:
        print(f"Vehicle type not found: {vehicle_type_id}")
        return HttpResponse(f"Vehicle type not found. Please select a valid vehicle type.")
    except Exception as e:
        print(f"Error calculating vehicle fare: {str(e)}")
        return HttpResponse(f"Error calculating vehicle fare: {str(e)}")


def payment_view(request, booking_reference):
    try:
        booking = Booking.objects.get(booking_reference=booking_reference)
        payment_amount = Decimal('0.00')

        print(f"Processing payment for booking: {booking_reference}, type: {booking.booking_type}")

        if booking.booking_type == 'passenger':
            # Ensure we have valid numbers for calculation
            adult_passengers = int(booking.adult_passengers or 0)
            child_passengers = int(booking.child_passengers or 0)
            student_passengers = int(booking.student_passengers or 0)
            senior_passengers = int(booking.senior_passengers or 0)

            adult_fare = booking.schedule.adult_fare or Decimal('0.00')
            child_fare = booking.schedule.child_fare or Decimal('0.00')
            student_fare = booking.schedule.student_fare or adult_fare
            senior_fare = booking.schedule.senior_fare or adult_fare

            adult_total = adult_passengers * adult_fare
            child_total = child_passengers * child_fare
            student_total = student_passengers * student_fare
            senior_total = senior_passengers * senior_fare

            payment_amount = adult_total + child_total + student_total + senior_total

            print(f"Passenger booking - Adults: {adult_passengers} x ₱{adult_fare} = ₱{adult_total}")
            print(f"Passenger booking - Children: {child_passengers} x ₱{child_fare} = ₱{child_total}")
            print(f"Passenger booking - Students: {student_passengers} x ₱{student_fare} = ₱{student_total}")
            print(f"Passenger booking - Seniors: {senior_passengers} x ₱{senior_fare} = ₱{senior_total}")
            print(f"Total payment amount: ₱{payment_amount}")

        elif booking.booking_type == 'vehicle':
            # Calculate vehicle fare
            if booking.vehicle_type:
                base_price = booking.vehicle_type.base_fare
                print(f"Vehicle booking - Type: {booking.vehicle_type.name}, Base fare: ₱{base_price}")
                payment_amount = base_price
            else:
                print("Warning: Vehicle booking without vehicle type")
                payment_amount = Decimal('0.00')

            print(f"Total payment amount: ₱{payment_amount}")

        # Store the payment amount in the booking for later reference
        booking.total_fare = payment_amount
        booking.save(update_fields=['total_fare'])

        return render(request, 'payment.html', {
            'booking': booking,
            'payment_amount': payment_amount
        })

    except Booking.DoesNotExist:
        print(f"Booking not found: {booking_reference}")
        messages.error(request, "Invalid booking reference.")
        return redirect('booking')
    except Exception as e:
        print(f"Error processing payment: {str(e)}")
        messages.error(request, f"Error processing payment: {str(e)}")
        return redirect('booking')

def booking_confirmation(request, booking_reference):
    """
    Display booking confirmation details after successful payment
    """
    try:
        booking = get_object_or_404(Booking, booking_reference=booking_reference)

        # Get the associated payment if it exists
        try:
            payment = Payment.objects.get(booking=booking)
        except Payment.DoesNotExist:
            payment = None

        context = {
            'booking': booking,
            'payment': payment,
            'schedule': booking.schedule,
        }

        return render(request, 'booking_confirmation.html', context)

    except Exception as e:
        messages.error(request, f"Error retrieving booking: {str(e)}")
        return redirect('home')





def contact_view(request):
    """View for handling contact form"""
    if request.method == 'POST':
        # Handle form submission
        name = request.POST.get('name')
        email = request.POST.get('email')
        message = request.POST.get('message')

        try:
            # Create contact message record
            ContactMessage.objects.create(
                name=name,
                email=email,
                message=message
            )

            messages.success(request, "Your message has been sent successfully. We'll get back to you soon.")
            return redirect('contact')

        except Exception as e:
            messages.error(request, "There was an error sending your message. Please try again.")

    # For GET requests, just display the contact form
    return render(request, 'contact.html')



@login_required
@staff_member_required
def vessel_list(request):
    """View for displaying and managing vessels in the dashboard"""
    # Get all vessels with their related schedules
    vessels = Vessel.objects.all().prefetch_related('schedule_set')

    # Handle search
    search_query = request.GET.get('search', '')
    if search_query:
        vessels = vessels.filter(
            Q(name__icontains=search_query) |
            Q(capacity__icontains=search_query) |
            Q(vessel_type__icontains=search_query)
        )

    # Pagination
    page = request.GET.get('page', 1)
    paginator = Paginator(vessels, 10)  # Show 10 vessels per page

    try:
        vessels = paginator.page(page)
    except PageNotAnInteger:
        vessels = paginator.page(1)
    except EmptyPage:
        vessels = paginator.page(paginator.num_pages)

    context = {
        'vessels': vessels,
        'search_query': search_query,
        'active_tab': 'vessels'
    }


    return render(request, 'dashboard/vessels.html', context)




@login_required
@staff_member_required
def schedule_list(request):
    """View for displaying and managing schedules in the dashboard"""
    # Get all schedules with related vessels and routes
    schedules = Schedule.objects.select_related('vessel', 'route').order_by('departure_datetime')

    # Handle search and filtering
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    date_filter = request.GET.get('date', '')

    if search_query:
        schedules = schedules.filter(
            Q(vessel__name__icontains=search_query) |
            Q(route__name__icontains=search_query)
        )

    if status_filter:
        schedules = schedules.filter(status=status_filter)

    if date_filter:
        try:
            filter_date = timezone.datetime.strptime(date_filter, '%Y-%m-%d').date()
            schedules = schedules.filter(departure_datetime__date=filter_date)
        except ValueError:
            pass

    # Pagination
    paginator = Paginator(schedules, 15)  # Show 15 schedules per page
    page = request.GET.get('page', 1)

    try:
        schedules = paginator.page(page)
    except PageNotAnInteger:
        schedules = paginator.page(1)
    except EmptyPage:
        schedules = paginator.page(paginator.num_pages)

    context = {
        'schedules': schedules,
        'search_query': search_query,
        'status_filter': status_filter,
        'date_filter': date_filter,
        'active_tab': 'schedules',
        'status_choices': Schedule.STATUS_CHOICES,
    }


    return render(request, 'dashboard/schedules.html', context)



@login_required
@staff_member_required
def booking_list(request):
    """View for displaying and managing bookings in the dashboard"""
    # Get all bookings with related schedules and payments
    bookings = Booking.objects.select_related(
        'schedule__vessel',
        'schedule__route',
        'vehicle_type'  # Add this line to include vehicle_type
    ).prefetch_related(
        'payment_set'
    ).order_by('-created_at')

    # Handle search and filtering
    search_query = request.GET.get('search', '')
    booking_type = request.GET.get('booking_type', '')
    payment_status = request.GET.get('payment_status', '')
    vehicle_type = request.GET.get('vehicle_type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if search_query:
        bookings = bookings.filter(
            Q(booking_reference__icontains=search_query) |
            Q(full_name__icontains=search_query) |
            Q(contact_number__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    if booking_type:
        bookings = bookings.filter(booking_type=booking_type)

    if payment_status:
        bookings = bookings.filter(payment_status=payment_status)

    if vehicle_type and booking_type == 'vehicle':
        bookings = bookings.filter(vehicle_type_id=vehicle_type)

    if date_from:
        bookings = bookings.filter(created_at__date__gte=date_from)

    if date_to:
        bookings = bookings.filter(created_at__date__lte=date_to)

    # Pagination
    paginator = Paginator(bookings, 20)  # Show 20 bookings per page
    page = request.GET.get('page', 1)

    try:
        bookings = paginator.page(page)
    except PageNotAnInteger:
        bookings = paginator.page(1)
    except EmptyPage:
        bookings = paginator.page(paginator.num_pages)

    context = {
        'bookings': bookings,
        'search_query': search_query,
        'booking_type': booking_type,
        'payment_status': payment_status,
        'vehicle_type': vehicle_type,
        'date_from': date_from,
        'date_to': date_to,
        'active_tab': 'bookings',
        'vehicle_types': VehicleType.objects.all(),
    }

    return render(request, 'dashboard/bookings.html', context)

def get_vessel_capacity(request, vessel_id):
    """
    API endpoint to get vessel capacity
    """
    try:
        vessel = get_object_or_404(Vessel, id=vessel_id)
        return JsonResponse({
            'success': True,
            'capacity_passengers': vessel.capacity_passengers,
            'capacity_cargo': vessel.capacity_cargo
        })
    except Vessel.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Vessel not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@staff_member_required
def booking_create(request):
    """View for creating bookings from the dashboard"""
    if request.method == 'POST':
        try:
            # Get schedule
            schedule_id = request.POST.get('schedule')
            schedule = get_object_or_404(Schedule, id=schedule_id)

            # Create booking
            booking = Booking.objects.create(
                schedule=schedule,
                booking_type=request.POST.get('booking_type'),
                full_name=request.POST.get('full_name'),
                contact_number=request.POST.get('contact_number'),
                email=request.POST.get('email'),
                adult_passengers=request.POST.get('adult_passengers', 0),
                child_passengers=request.POST.get('child_passengers', 0),
                vehicle_type_id=request.POST.get('vehicle_type') if request.POST.get('booking_type') == 'vehicle' else None,
                status='pending',
                booking_reference=generate_booking_reference(),
                created_by=request.user
            )

            messages.success(request, f'Booking {booking.booking_reference} created successfully')

            if request.htmx:
                return render(request, 'dashboard/partials/booking_success.html', {'booking': booking})
            return redirect('booking_view', pk=booking.id)

        except Exception as e:
            messages.error(request, f'Error creating booking: {str(e)}')
            if request.htmx:
                return HttpResponse(
                    '<div class="alert alert-danger">Error creating booking</div>',
                    status=400
                )
            return redirect('booking_create')

    # For GET requests
    context = {
        'schedules': Schedule.objects.filter(
            departure_datetime__gt=timezone.now(),
            status='scheduled'
        ).select_related('vessel', 'route'),
        'vehicle_types': VehicleType.objects.all(),
        'active_tab': 'bookings'
    }

    if request.htmx:
        return render(request, 'dashboard/partials/booking_form.html', context)
    return render(request, 'dashboard/booking_create.html', context)

@login_required
@staff_member_required
def route_list(request):
    """View for displaying and managing routes in the dashboard"""
    # Get all routes with related schedules
    routes = Route.objects.prefetch_related(
        'schedule_set'
    ).order_by('name')

    # Handle search and filtering
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('active', '')

    if search_query:
        routes = routes.filter(
            Q(name__icontains=search_query) |
            Q(origin__icontains=search_query) |
            Q(destination__icontains=search_query)
        )

    if status_filter:
        routes = routes.filter(active=status_filter == 'true')

    # Add schedule count and latest schedule for each route
    for route in routes:
        route.schedule_count = route.schedule_set.count()
        route.latest_schedule = route.schedule_set.filter(
            departure_datetime__gt=timezone.now()
        ).order_by('departure_datetime').first()

    # Pagination
    paginator = Paginator(routes, 15)  # Show 15 routes per page
    page = request.GET.get('page', 1)

    try:
        routes = paginator.page(page)
    except PageNotAnInteger:
        routes = paginator.page(1)
    except EmptyPage:
        routes = paginator.page(paginator.num_pages)

    context = {
        'routes': routes,
        'search_query': search_query,
        'status_filter': status_filter,
        'active_tab': 'routes'
    }


    return render(request, 'dashboard/routes.html', context)
@login_required
@staff_member_required

def add_route(request):
    """View for adding new routes"""
    if request.method == 'POST':
        try:
            # Convert HH:MM string to timedelta
            duration_str = request.POST.get('estimated_duration')
            hours, minutes = map(int, duration_str.split(':'))
            duration = timedelta(hours=hours, minutes=minutes)

            # Create new route
            route = Route.objects.create(
                name=request.POST.get('name'),
                origin=request.POST.get('origin'),
                destination=request.POST.get('destination'),
                distance=request.POST.get('distance'),
                estimated_duration=duration,  # Use the converted duration
                active=request.POST.get('active') == 'on',  # Fix for checkbox handling
                description=request.POST.get('description', ''),
                created_by=request.user
            )

            messages.success(request, f'Route "{route.name}" created successfully')
            return redirect('route_list')

        except Exception as e:
            messages.error(request, f'Error creating route: {str(e)}')

@login_required
@staff_member_required
@require_http_methods(["GET"])
def get_routes(request):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            routes = Route.objects.all()
            routes_data = [{
                'id': route.id,
                'origin': route.origin,
                'destination': route.destination,
                'estimated_duration': str(route.estimated_duration)
            } for route in routes]
            return JsonResponse({'success': True, 'routes': routes_data})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required

def edit_schedule(request, schedule_id):
    """API endpoint for editing a schedule"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        schedule = get_object_or_404(Schedule, pk=schedule_id)

        # Update schedule fields
        schedule.vessel_id = request.POST.get('vessel')
        schedule.route_id = request.POST.get('route')

        # Parse datetime strings from the form
        departure_datetime = request.POST.get('departure_datetime')
        arrival_datetime = request.POST.get('arrival_datetime')

        # Assign the datetime values directly
        schedule.departure_datetime = departure_datetime
        schedule.arrival_datetime = arrival_datetime

        schedule.available_seats = request.POST.get('available_seats')
        schedule.available_cargo_space = request.POST.get('available_cargo_space')
        schedule.adult_fare = request.POST.get('adult_fare')
        schedule.child_fare = request.POST.get('child_fare')

        # Handle optional fare fields
        student_fare = request.POST.get('student_fare')
        senior_fare = request.POST.get('senior_fare')
        if student_fare:
            schedule.student_fare = student_fare
        if senior_fare:
            schedule.senior_fare = senior_fare

        schedule.status = request.POST.get('status')
        schedule.notes = request.POST.get('notes')

        schedule.save()

        return JsonResponse({
            'success': True,
            'message': 'Schedule updated successfully'
        })
    except Schedule.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Schedule not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
@login_required
@staff_member_required
def get_route(request, pk):
    """API endpoint for getting route details"""
    route = get_object_or_404(Route, pk=pk)
    return JsonResponse({
        'id': route.id,
        'name': route.name,
        'origin': route.origin,
        'destination': route.destination,
        'distance': route.distance,
        'estimated_duration': str(route.estimated_duration).split('.')[0],  # Remove microseconds
        'description': route.description or '',
        'active': route.active
    })

@login_required
@staff_member_required
def edit_route(request, pk):
    """View for editing existing routes"""
    route = get_object_or_404(Route, pk=pk)

    if request.method == 'POST':
        try:
            # Convert HH:MM string to timedelta
            duration_str = request.POST.get('estimated_duration')
            hours, minutes = map(int, duration_str.split(':'))
            duration = timedelta(hours=hours, minutes=minutes)

            # Update route
            route.name = request.POST.get('name')
            route.origin = request.POST.get('origin')
            route.destination = request.POST.get('destination')
            route.distance = request.POST.get('distance')
            route.estimated_duration = duration
            route.active = request.POST.get('active') == 'on'
            route.description = request.POST.get('description', '')
            route.save()

            return JsonResponse({
                'success': True,
                'message': f'Route "{route.name}" updated successfully'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

    return JsonResponse({
        'success': False,
        'error': 'Invalid request method'
    })

@login_required
@staff_member_required
@require_http_methods(["DELETE"])
def delete_route(request, pk):
    """View for deleting routes"""
    try:
        route = get_object_or_404(Route, pk=pk)
        route.delete()
        return JsonResponse({
            'success': True,
            'message': 'Route deleted successfully'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
@login_required
@staff_member_required
def booking_view(request, pk):
    booking = get_object_or_404(Booking, pk=pk)

    # Calculate total fare based on booking type
    if booking.booking_type == 'vehicle' and booking.vehicle_type:
        total_fare = booking.vehicle_type.base_fare
        # Store the vehicle fare for display in the template
        booking.vehicle_fare_total = total_fare
    else:
        total_fare = (
            booking.adult_passengers * booking.schedule.adult_fare +
            booking.child_passengers * booking.schedule.child_fare
        )
        # Store these values for display in the template
        booking.adult_fare_total = booking.adult_passengers * booking.schedule.adult_fare
        booking.child_fare_total = booking.child_passengers * booking.schedule.child_fare

    context = {
        'booking': booking,
        'active_tab': 'bookings',
        'total_fare': total_fare,
        'payment': booking.payment_set.first(),
    }

    return render(request, 'dashboard/booking_view.html', context)

@login_required
@staff_member_required
def booking_mark_paid(request, pk):
    """View for marking a booking as paid from the dashboard"""
    if request.method != 'POST':
        return HttpResponse(status=405)  # Method Not Allowed

    booking = get_object_or_404(Booking, pk=pk)

    try:
        if booking.is_paid:
            messages.warning(request, 'This booking is already marked as paid.')
            if request.htmx:
                return HttpResponse(
                    '<div class="bg-yellow-100 text-yellow-700 p-4 rounded">'
                    'This booking is already marked as paid'
                    '</div>'
                )
            return redirect('booking_view', pk=pk)

        # Calculate payment amount
        if booking.booking_type == 'vehicle' and booking.vehicle_type:
            payment_amount = booking.vehicle_type.base_fare
        else:
            payment_amount = (
                booking.adult_passengers * booking.schedule.adult_fare +
                booking.child_passengers * booking.schedule.child_fare
            )

        # Create payment record
        Payment.objects.create(
            booking=booking,
            amount_paid=payment_amount,
            payment_method=request.POST.get('payment_method', 'cash'),
            payment_date=timezone.now(),
            processed_by=request.user
        )

        # Update booking status
        booking.is_paid = True
        booking.save()

        messages.success(request, f'Booking #{booking.booking_reference} has been marked as paid.')

        if request.htmx:
            return render(request, 'dashboard/partials/booking_payment_success.html', {
                'booking': booking,
                'payment_amount': payment_amount
            })
        return redirect('booking_view', pk=pk)

    except Exception as e:
        messages.error(request, f'Error processing payment: {str(e)}')
        if request.htmx:
            return HttpResponse(
                '<div class="bg-red-100 text-red-700 p-4 rounded">'
                f'Error processing payment: {str(e)}'
                '</div>',
                status=400
            )
        return redirect('booking_view', pk=pk)
@login_required
@staff_member_required
def booking_print(request, pk):
    """View for generating printable booking details"""
    booking = get_object_or_404(Booking, pk=pk)

    # Calculate total fare
    if booking.booking_type == 'vehicle' and booking.vehicle_type:
        total_fare = booking.vehicle_type.base_fare
    else:
        total_fare = (
            booking.adult_passengers * booking.schedule.adult_fare +
            booking.child_passengers * booking.schedule.child_fare
        )

    context = {
        'booking': booking,
        'total_fare': total_fare,
        'payment': booking.payment_set.first(),
        'company_name': 'Your Company Name',  # Customize as needed
        'company_address': 'Your Company Address',  # Customize as needed
        'company_contact': 'Your Company Contact',  # Customize as needed
        'print_date': timezone.now(),
    }

    # Use a print-specific template
    response = render(request, 'dashboard/print/booking_print.html', context)

    # Set print-friendly headers
    response['Content-Type'] = 'text/html'
    response['Content-Disposition'] = f'inline; filename="booking-{booking.booking_reference}.html"'

    return response
@login_required
@staff_member_required
def add_vessel(request):
    """View for adding a new vessel"""
    if request.method == 'POST':
        try:
            vessel = Vessel.objects.create(
                name=request.POST.get('name'),
                capacity_passengers=request.POST.get('capacity_passengers'),
                capacity_cargo=request.POST.get('capacity_cargo'),
                active=request.POST.get('active') == 'on'
            )

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Vessel added successfully'
                })

            messages.success(request, 'Vessel added successfully')
            return redirect('vessel_list')

        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                })

            messages.error(request, f'Error adding vessel: {str(e)}')
            return redirect('vessel_list')

    # This view doesn't need a GET handler as it uses a modal form in vessels.html
    return redirect('vessel_list')


@login_required
@staff_member_required
def edit_vessel(request, vessel_id):
    """View for editing an existing vessel"""
    vessel = get_object_or_404(Vessel, id=vessel_id)

    if request.method == 'POST':
        try:
            # Update vessel fields from form data
            vessel.name = request.POST.get('name')
            vessel.capacity_passengers = request.POST.get('capacity_passengers')
            vessel.capacity_cargo = request.POST.get('capacity_cargo')
            vessel.active = request.POST.get('active') == 'on'
            vessel.save()

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Vessel updated successfully'
                })

            messages.success(request, 'Vessel updated successfully')
            return redirect('vessel_list')

        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                })

            messages.error(request, f'Error updating vessel: {str(e)}')
            return redirect('vessel_list')

    # This view doesn't need a GET handler as it uses a modal form
    return redirect('vessel_list')
@login_required
@staff_member_required
def delete_vessel(request, vessel_id):
    """View for deleting a vessel"""
    vessel = get_object_or_404(Vessel, id=vessel_id)

    try:
        vessel_name = vessel.name
        vessel.delete()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': f'Vessel "{vessel_name}" deleted successfully'
            })

        messages.success(request, f'Vessel "{vessel_name}" deleted successfully')

    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

        messages.error(request, f'Error deleting vessel: {str(e)}')

    return redirect('vessel_list')
@login_required
@staff_member_required
def toggle_vessel_status(request, vessel_id):
    """View for toggling vessel active status"""
    if request.method == 'POST':
        try:
            vessel = get_object_or_404(Vessel, id=vessel_id)
            vessel.active = not vessel.active
            vessel.save()

            return JsonResponse({
                'success': True,
                'active': vessel.active,
                'message': f'Vessel status updated to {"active" if vessel.active else "inactive"}'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

    return JsonResponse({
        'success': False,
        'error': 'Invalid request method'
    })



@login_required
@staff_member_required
def add_schedule(request):
    """API endpoint for adding a new schedule"""
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Method not allowed'
        }, status=405)

    try:
        # Extract data from request
        data = request.POST
        vessel_id = data.get('vessel')
        route_id = data.get('route')
        departure_datetime = data.get('departure_datetime')
        arrival_datetime = data.get('arrival_datetime')
        available_seats = data.get('available_seats')
        available_cargo_space = data.get('available_cargo_space')
        adult_fare = data.get('adult_fare')
        child_fare = data.get('child_fare')
        student_fare = data.get('student_fare')
        senior_fare = data.get('senior_fare')
        status = data.get('status', 'scheduled')
        notes = data.get('notes', '')

        # Validate required fields
        if not all([vessel_id, route_id, departure_datetime, arrival_datetime,
                   available_seats, available_cargo_space]):
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields'
            }, status=400)

        # Convert string values to appropriate types
        try:
            vessel = Vessel.objects.get(id=vessel_id)
            route = Route.objects.get(id=route_id)
            departure_datetime = parse_datetime(departure_datetime)
            arrival_datetime = parse_datetime(arrival_datetime)
            available_seats = int(available_seats)
            available_cargo_space = float(available_cargo_space)
            adult_fare = Decimal(adult_fare) if adult_fare else None
            child_fare = Decimal(child_fare) if child_fare else None
            student_fare = Decimal(student_fare) if student_fare else None
            senior_fare = Decimal(senior_fare) if senior_fare else None
        except (Vessel.DoesNotExist, Route.DoesNotExist):
            return JsonResponse({
                'success': False,
                'error': 'Invalid vessel or route'
            }, status=400)
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid data format'
            }, status=400)

        # Create new schedule
        schedule = Schedule.objects.create(
            vessel=vessel,
            route=route,
            departure_datetime=departure_datetime,
            arrival_datetime=arrival_datetime,
            available_seats=available_seats,
            available_cargo_space=available_cargo_space,
            adult_fare=adult_fare,
            child_fare=child_fare,
            student_fare=student_fare,
            senior_fare=senior_fare,
            status=status,
            notes=notes
        )

        return JsonResponse({
            'success': True,
            'message': 'Schedule created successfully',
            'schedule': {
                'id': schedule.id,
                'vessel_name': schedule.vessel.name,
                'route_name': schedule.route.name,
                'departure_datetime': schedule.departure_datetime.isoformat(),
                'arrival_datetime': schedule.arrival_datetime.isoformat(),
                'available_seats': schedule.available_seats,
                'available_cargo_space': schedule.available_cargo_space,
                'adult_fare': str(schedule.adult_fare),
                'child_fare': str(schedule.child_fare),
                'student_fare': str(schedule.student_fare) if schedule.student_fare else '',
                'senior_fare': str(schedule.senior_fare) if schedule.senior_fare else '',
                'status': schedule.status
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from django.utils import timezone
import csv

@login_required
@staff_member_required
def export_report(request):
    # Get filter parameters
    export_format = request.GET.get('format', 'pdf')
    report_type = request.GET.get('report_type', 'financial')
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))
    selected_route = request.GET.get('route', '')
    selected_vessel = request.GET.get('vessel', '')

    # Get passenger boarding list specific filters
    departure_date = request.GET.get('departure_date', '')
    departure_time = request.GET.get('departure_time', '')
    selected_schedule = request.GET.get('schedule', '')
    selected_passenger_type = request.GET.get('passenger_type', '')
    passenger_name = request.GET.get('passenger_name', '')

    # Get cargo list specific filters
    cargo_departure_date = request.GET.get('cargo_departure_date', '')
    selected_cargo_schedule = request.GET.get('cargo_schedule', '')
    min_weight = request.GET.get('min_weight', '')
    max_weight = request.GET.get('max_weight', '')

    # Get vehicle list specific filters
    vehicle_departure_date = request.GET.get('vehicle_departure_date', '')
    selected_vehicle_schedule = request.GET.get('vehicle_schedule', '')
    selected_vehicle_type = request.GET.get('vehicle_type', '')
    vehicle_plate = request.GET.get('vehicle_plate', '')

    # Get revenue report specific filters
    selected_payment_method = request.GET.get('payment_method', '')
    selected_booking_type = request.GET.get('booking_type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if report_type == 'cargo':
        # Export cargo list
        # Base queryset for cargo bookings
        cargo_list_query = Booking.objects.filter(
            booking_type='cargo',
            is_paid=True
        ).select_related(
            'schedule',
            'schedule__route',
            'schedule__vessel'
        )

        # Apply cargo list specific filters
        if cargo_departure_date:
            try:
                cargo_date_obj = timezone.datetime.strptime(cargo_departure_date, '%Y-%m-%d').date()
                cargo_list_query = cargo_list_query.filter(
                    schedule__departure_datetime__date=cargo_date_obj
                )
            except ValueError:
                # Invalid date format, ignore filter
                pass

        if selected_cargo_schedule:
            cargo_list_query = cargo_list_query.filter(
                schedule_id=selected_cargo_schedule
            )

        if min_weight:
            try:
                min_weight_float = float(min_weight)
                cargo_list_query = cargo_list_query.filter(
                    cargo_weight__gte=min_weight_float
                )
            except ValueError:
                # Invalid format, ignore filter
                pass

        if max_weight:
            try:
                max_weight_float = float(max_weight)
                cargo_list_query = cargo_list_query.filter(
                    cargo_weight__lte=max_weight_float
                )
            except ValueError:
                # Invalid format, ignore filter
                pass

        # Apply the same route and vessel filters as the main report
        if selected_route:
            cargo_list_query = cargo_list_query.filter(
                schedule__route_id=selected_route
            )

        if selected_vessel:
            cargo_list_query = cargo_list_query.filter(
                schedule__vessel_id=selected_vessel
            )

        # Order by departure date and customer name
        cargo_list = cargo_list_query.order_by(
            'schedule__departure_datetime',
            'full_name'
        )

        # Prepare data for export
        data = {
            'title': 'Cargo Bookings List',
            'user': request.user,
            'generated_at': timezone.now(),
            'cargo_list': cargo_list,
            'cargo_count': cargo_list.count(),
        }

        if export_format == 'pdf':
            return export_cargo_pdf(data)
        elif export_format == 'excel':
            return export_cargo_excel(data)
        elif export_format == 'csv':
            return export_cargo_csv(data)
        else:
            return HttpResponse('Invalid export format', status=400)

    elif report_type == 'vehicle':
        # Export vehicle list
        # Base queryset for vehicle bookings
        vehicle_list_query = Booking.objects.filter(
            booking_type='vehicle',
            is_paid=True
        ).select_related(
            'schedule',
            'schedule__route',
            'schedule__vessel',
            'vehicle_type'
        )

        # Apply vehicle list specific filters
        if vehicle_departure_date:
            try:
                vehicle_date_obj = timezone.datetime.strptime(vehicle_departure_date, '%Y-%m-%d').date()
                vehicle_list_query = vehicle_list_query.filter(
                    schedule__departure_datetime__date=vehicle_date_obj
                )
            except ValueError:
                # Invalid date format, ignore filter
                pass

        if selected_vehicle_schedule:
            vehicle_list_query = vehicle_list_query.filter(
                schedule_id=selected_vehicle_schedule
            )

        if selected_vehicle_type:
            vehicle_list_query = vehicle_list_query.filter(
                vehicle_type_id=selected_vehicle_type
            )

        # Apply plate number filter if provided
        if vehicle_plate:
            vehicle_list_query = vehicle_list_query.filter(
                plate_number__icontains=vehicle_plate
            )

        # Apply the same route and vessel filters as the main report
        if selected_route:
            vehicle_list_query = vehicle_list_query.filter(
                schedule__route_id=selected_route
            )

        if selected_vessel:
            vehicle_list_query = vehicle_list_query.filter(
                schedule__vessel_id=selected_vessel
            )

        # Order by departure date and customer name
        vehicle_list = vehicle_list_query.order_by(
            'schedule__departure_datetime',
            'full_name'
        )

        # Prepare data for export
        data = {
            'title': 'Vehicle Bookings List',
            'user': request.user,
            'generated_at': timezone.now(),
            'vehicle_list': vehicle_list,
            'vehicle_count': vehicle_list.count(),
        }

        if export_format == 'pdf':
            return export_vehicle_pdf(data)
        elif export_format == 'excel':
            return export_vehicle_excel(data)
        elif export_format == 'csv':
            return export_vehicle_csv(data)
        else:
            return HttpResponse('Invalid export format', status=400)

    elif report_type == 'boarding':
        # Export passenger boarding list
        # Base queryset for passengers
        passenger_list_query = Passenger.objects.select_related(
            'booking',
            'booking__schedule',
            'booking__schedule__route',
            'booking__schedule__vessel'
        ).filter(
            booking__is_paid=True
        )

        # Apply boarding list specific filters
        if departure_date:
            try:
                departure_date_obj = timezone.datetime.strptime(departure_date, '%Y-%m-%d').date()
                passenger_list_query = passenger_list_query.filter(
                    booking__schedule__departure_datetime__date=departure_date_obj
                )

                # Apply time filter if both date and time are provided
                if departure_time:
                    try:
                        # Parse the time string into a time object
                        departure_time_obj = timezone.datetime.strptime(departure_time, '%H:%M').time()

                        # Filter by time - using __time to extract time part from datetime field
                        passenger_list_query = passenger_list_query.filter(
                            booking__schedule__departure_datetime__time=departure_time_obj
                        )
                    except ValueError:
                        # Invalid time format, ignore time filter
                        pass
            except ValueError:
                # Invalid date format, ignore filter
                pass

        if selected_schedule:
            passenger_list_query = passenger_list_query.filter(
                booking__schedule_id=selected_schedule
            )

        if selected_passenger_type:
            passenger_list_query = passenger_list_query.filter(
                passenger_type=selected_passenger_type
            )

        # Apply passenger name filter if provided
        if passenger_name:
            passenger_list_query = passenger_list_query.filter(
                full_name__icontains=passenger_name
            )

        # Apply the same route and vessel filters as the main report
        if selected_route:
            passenger_list_query = passenger_list_query.filter(
                booking__schedule__route_id=selected_route
            )

        if selected_vessel:
            passenger_list_query = passenger_list_query.filter(
                booking__schedule__vessel_id=selected_vessel
            )

        # Order by departure date and passenger name
        passenger_list = passenger_list_query.order_by(
            'booking__schedule__departure_datetime',
            'full_name'
        )

        # Prepare data for export
        data = {
            'title': 'Passenger Boarding List',
            'user': request.user,
            'generated_at': timezone.now(),
            'passenger_list': passenger_list,
            'passenger_count': passenger_list.count(),
        }

        if export_format == 'pdf':
            return export_boarding_pdf(data)
        elif export_format == 'excel':
            return export_boarding_excel(data)
        elif export_format == 'csv':
            return export_boarding_csv(data)
        else:
            return HttpResponse('Invalid export format', status=400)

    elif report_type == 'revenue':
        # Export comprehensive revenue report
        # Base queryset for bookings
        bookings = Booking.objects.filter(
            schedule__departure_datetime__year=year,
            schedule__departure_datetime__month=month,
            is_paid=True
        )

        # Apply filters
        if selected_route:
            bookings = bookings.filter(schedule__route_id=selected_route)
        if selected_vessel:
            bookings = bookings.filter(schedule__vessel_id=selected_vessel)
        if selected_booking_type:
            bookings = bookings.filter(booking_type=selected_booking_type)

        # Date range filters
        if date_from:
            try:
                date_from_obj = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
                bookings = bookings.filter(created_at__date__gte=date_from_obj)
            except ValueError:
                # Invalid date format, ignore filter
                pass

        if date_to:
            try:
                date_to_obj = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
                bookings = bookings.filter(created_at__date__lte=date_to_obj)
            except ValueError:
                # Invalid date format, ignore filter
                pass

        # Get revenue breakdown data
        # 1. Revenue by booking type
        passenger_revenue = bookings.filter(booking_type='passenger').aggregate(
            total=Coalesce(Sum('total_fare'), Value(0, output_field=DecimalField()))
        )['total']

        vehicle_revenue = bookings.filter(booking_type='vehicle').aggregate(
            total=Coalesce(Sum('total_fare'), Value(0, output_field=DecimalField()))
        )['total']

        cargo_revenue = bookings.filter(booking_type='cargo').aggregate(
            total=Coalesce(Sum('total_fare'), Value(0, output_field=DecimalField()))
        )['total']

        # 2. Revenue by payment method
        payments = Payment.objects.filter(
            booking__in=bookings
        )

        # Apply payment method filter if selected
        if selected_payment_method:
            payments = payments.filter(payment_method=selected_payment_method)

        cash_payments = payments.filter(payment_method='cash')
        gcash_payments = payments.filter(payment_method='gcash')

        cash_payment_count = cash_payments.count()
        gcash_payment_count = gcash_payments.count()

        cash_revenue = cash_payments.aggregate(
            total=Coalesce(Sum('amount_paid'), Value(0, output_field=DecimalField()))
        )['total']

        gcash_revenue = gcash_payments.aggregate(
            total=Coalesce(Sum('amount_paid'), Value(0, output_field=DecimalField()))
        )['total']

        # 3. Revenue by passenger type
        # Get all passengers from the filtered bookings
        passengers = Passenger.objects.filter(booking__in=bookings)

        # Count by passenger type
        adult_count = passengers.filter(passenger_type='adult').count()
        child_count = passengers.filter(passenger_type='child').count()
        student_count = passengers.filter(passenger_type='student').count()
        senior_count = passengers.filter(passenger_type='senior').count()

        # Calculate revenue by passenger type
        # This is an approximation based on the fare rates and passenger counts
        adult_revenue = Decimal('0.00')
        child_revenue = Decimal('0.00')
        student_revenue = Decimal('0.00')
        senior_revenue = Decimal('0.00')

        for booking in bookings.filter(booking_type='passenger'):
            # Get passengers for this booking
            booking_passengers = Passenger.objects.filter(booking=booking)

            # Count by type
            booking_adult_count = booking_passengers.filter(passenger_type='adult').count()
            booking_child_count = booking_passengers.filter(passenger_type='child').count()
            booking_student_count = booking_passengers.filter(passenger_type='student').count()
            booking_senior_count = booking_passengers.filter(passenger_type='senior').count()

            # Get fare rates
            adult_rate = booking.adult_fare_rate or Decimal('0.00')
            child_rate = booking.child_fare_rate or Decimal('0.00')
            student_rate = booking.student_fare_rate or Decimal('0.00')
            senior_rate = booking.senior_fare_rate or Decimal('0.00')

            # Calculate revenue by type
            adult_revenue += booking_adult_count * adult_rate
            child_revenue += booking_child_count * child_rate
            student_revenue += booking_student_count * student_rate
            senior_revenue += booking_senior_count * senior_rate

        # Prepare data for export
        data = {
            'title': 'Comprehensive Revenue Report',
            'month': timezone.datetime(year, month, 1).strftime('%B %Y'),
            'user': request.user,
            'generated_at': timezone.now(),
            'bookings': bookings,
            'booking_count': bookings.count(),
            'total_revenue': passenger_revenue + vehicle_revenue + cargo_revenue,

            # Revenue breakdown data
            'passenger_revenue': passenger_revenue,
            'vehicle_revenue': vehicle_revenue,
            'cargo_revenue': cargo_revenue,

            # Payment method data
            'cash_payment_count': cash_payment_count,
            'gcash_payment_count': gcash_payment_count,
            'cash_revenue': cash_revenue,
            'gcash_revenue': gcash_revenue,

            # Passenger type data
            'adult_count': adult_count,
            'child_count': child_count,
            'student_count': student_count,
            'senior_count': senior_count,
            'adult_revenue': adult_revenue,
            'child_revenue': child_revenue,
            'student_revenue': student_revenue,
            'senior_revenue': senior_revenue
        }

        if export_format == 'pdf':
            return export_revenue_pdf(data)
        elif export_format == 'excel':
            return export_revenue_excel(data)
        elif export_format == 'csv':
            return export_revenue_csv(data)
        else:
            return HttpResponse('Invalid export format', status=400)

    else:
        # Export financial report (default)
        # Base queryset for bookings
        bookings = Booking.objects.filter(
            created_at__year=year,
            created_at__month=month,
            is_paid=True
        )

        # Apply filters
        if selected_route:
            bookings = bookings.filter(schedule__route_id=selected_route)
        if selected_vessel:
            bookings = bookings.filter(schedule__vessel_id=selected_vessel)

        # Prepare data for export
        data = {
            'month': timezone.datetime(year, month, 1).strftime('%B %Y'),
            'user': request.user,
            'generated_at': timezone.now(),
            'bookings': bookings,
            'booking_count': bookings.count(),
            'total_revenue': bookings.aggregate(total=Sum('total_fare'))['total'] or 0,
        }

        if export_format == 'pdf':
            return export_pdf(data)
        elif export_format == 'excel':
            return export_excel(data)
        elif export_format == 'csv':
            return export_csv(data)
        else:
            return HttpResponse('Invalid export format', status=400)

def export_csv(data):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename=booking_report_{data["month"].replace(" ", "_")}.csv'

    writer = csv.writer(response)
    writer.writerow([
        'Booking Reference',
        'Date',
        'Full Name',
        'Contact',
        'Type',
        'Route',
        'Adult Passengers',
        'Child Passengers',
        'Status',
        'Total Fare'
    ])

    for booking in data['bookings']:
        writer.writerow([
            booking.booking_reference,
            booking.created_at.strftime('%Y-%m-%d'),
            booking.full_name,
            booking.contact_number,
            booking.get_booking_type_display(),
            booking.schedule.route.name if booking.schedule and booking.schedule.route else 'N/A',
            booking.adult_passengers,
            booking.child_passengers,
            'Paid' if booking.is_paid else 'Unpaid',
            f"₱{booking.total_fare:,.2f}"
        ])

    return response

def export_boarding_csv(data):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename=passenger_boarding_list_{timezone.now().strftime("%Y%m%d_%H%M")}.csv'

    writer = csv.writer(response)
    writer.writerow([
        'Booking Reference',
        'Passenger Name',
        'Passenger Type',
        'Route',
        'Departure Date/Time',
        'Vessel',
        'Status'
    ])

    for passenger in data['passenger_list']:
        writer.writerow([
            passenger.booking.booking_reference,
            passenger.full_name,
            passenger.get_passenger_type_display(),
            passenger.booking.schedule.route.name if passenger.booking.schedule and passenger.booking.schedule.route else 'N/A',
            passenger.booking.schedule.departure_datetime.strftime('%Y-%m-%d %H:%M') if passenger.booking.schedule else 'N/A',
            passenger.booking.schedule.vessel.name if passenger.booking.schedule and passenger.booking.schedule.vessel else 'N/A',
            'Confirmed' if passenger.booking.is_paid else 'Pending'
        ])

    return response

def export_cargo_csv(data):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename=cargo_list_{timezone.now().strftime("%Y%m%d_%H%M")}.csv'

    writer = csv.writer(response)
    writer.writerow([
        'Booking Reference',
        'Customer Name',
        'Weight (tons)',
        'Route',
        'Departure Date/Time',
        'Vessel',
        'Status'
    ])

    for cargo in data['cargo_list']:
        writer.writerow([
            cargo.booking_reference,
            cargo.full_name,
            f"{cargo.cargo_weight:.2f}",
            cargo.schedule.route.name if cargo.schedule and cargo.schedule.route else 'N/A',
            cargo.schedule.departure_datetime.strftime('%Y-%m-%d %H:%M') if cargo.schedule else 'N/A',
            cargo.schedule.vessel.name if cargo.schedule and cargo.schedule.vessel else 'N/A',
            'Confirmed' if cargo.is_paid else 'Pending'
        ])

    return response

def export_vehicle_csv(data):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename=vehicle_list_{timezone.now().strftime("%Y%m%d_%H%M")}.csv'

    writer = csv.writer(response)
    writer.writerow([
        'Booking Reference',
        'Customer Name',
        'Vehicle Type',
        'Plate Number',
        'Route',
        'Departure Date/Time',
        'Vessel',
        'Status'
    ])

    for vehicle in data['vehicle_list']:
        writer.writerow([
            vehicle.booking_reference,
            vehicle.full_name,
            vehicle.vehicle_type.name if vehicle.vehicle_type else 'N/A',
            vehicle.plate_number or 'N/A',
            vehicle.schedule.route.name if vehicle.schedule and vehicle.schedule.route else 'N/A',
            vehicle.schedule.departure_datetime.strftime('%Y-%m-%d %H:%M') if vehicle.schedule else 'N/A',
            vehicle.schedule.vessel.name if vehicle.schedule and vehicle.schedule.vessel else 'N/A',
            'Confirmed' if vehicle.is_paid else 'Pending'
        ])

    return response

def export_revenue_csv(data):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename=revenue_report_{data["month"].replace(" ", "_")}.csv'

    writer = csv.writer(response)

    # Write header
    writer.writerow(['Comprehensive Revenue Report'])
    writer.writerow([f'Period: {data["month"]}'])
    writer.writerow([f'Generated: {data["generated_at"].strftime("%Y-%m-%d %H:%M")}'])
    writer.writerow([f'Generated By: {data["user"].username}'])
    writer.writerow([])

    # Write summary section
    writer.writerow(['SUMMARY'])
    writer.writerow(['Total Bookings', data['booking_count']])
    writer.writerow(['Total Revenue', f'₱{data["total_revenue"]:,.2f}'])
    writer.writerow([])

    # Write revenue by booking type
    writer.writerow(['REVENUE BY BOOKING TYPE'])
    writer.writerow(['Passenger Bookings', f'₱{data["passenger_revenue"]:,.2f}'])
    writer.writerow(['Vehicle Bookings', f'₱{data["vehicle_revenue"]:,.2f}'])
    writer.writerow(['Cargo Bookings', f'₱{data["cargo_revenue"]:,.2f}'])
    writer.writerow([])

    # Write revenue by payment method
    writer.writerow(['REVENUE BY PAYMENT METHOD'])
    writer.writerow(['Cash Payments', data['cash_payment_count'], f'₱{data["cash_revenue"]:,.2f}'])
    writer.writerow(['GCash Payments', data['gcash_payment_count'], f'₱{data["gcash_revenue"]:,.2f}'])
    writer.writerow([])

    # Write revenue by passenger type
    writer.writerow(['REVENUE BY PASSENGER TYPE'])
    writer.writerow(['Regular Adult', data['adult_count'], f'₱{data["adult_revenue"]:,.2f}'])
    writer.writerow(['Child', data['child_count'], f'₱{data["child_revenue"]:,.2f}'])
    writer.writerow(['Student', data['student_count'], f'₱{data["student_revenue"]:,.2f}'])
    writer.writerow(['Senior Citizen', data['senior_count'], f'₱{data["senior_revenue"]:,.2f}'])
    writer.writerow([])

    # Write booking details
    writer.writerow(['BOOKING DETAILS'])
    writer.writerow([
        'Booking Reference',
        'Date',
        'Full Name',
        'Type',
        'Route',
        'Total Fare'
    ])

    for booking in data['bookings']:
        writer.writerow([
            booking.booking_reference,
            booking.created_at.strftime('%Y-%m-%d'),
            booking.full_name,
            booking.get_booking_type_display(),
            booking.schedule.route.name if booking.schedule and booking.schedule.route else 'N/A',
            f'₱{booking.total_fare:,.2f}'
        ])

    return response

def export_vehicle_pdf(data):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=vehicle_list_{timezone.now().strftime("%Y%m%d_%H%M")}.pdf'

    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(letter),
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    story = []
    styles = getSampleStyleSheet()

    # Add title and metadata
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=20
    )

    story.append(Paragraph(f"Vehicle Bookings List", title_style))
    story.append(Spacer(1, 10))

    # Add generation info
    info_style = ParagraphStyle(
        'Info',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=20
    )
    story.append(Paragraph(f"Generated: {data['generated_at'].strftime('%Y-%m-%d %H:%M')}", info_style))
    story.append(Paragraph(f"Generated By: {data['user'].username}", info_style))
    story.append(Spacer(1, 10))

    # Create the main table
    table_data = [[
        'Booking Ref',
        'Customer Name',
        'Vehicle Type',
        'Plate Number',
        'Route',
        'Departure',
        'Status'
    ]]

    for vehicle in data['vehicle_list']:
        table_data.append([
            vehicle.booking_reference,
            vehicle.full_name,
            vehicle.vehicle_type.name if vehicle.vehicle_type else 'N/A',
            vehicle.plate_number or 'N/A',
            vehicle.schedule.route.name if vehicle.schedule and vehicle.schedule.route else 'N/A',
            vehicle.schedule.departure_datetime.strftime('%Y-%m-%d %H:%M') if vehicle.schedule else 'N/A',
            'Confirmed' if vehicle.is_paid else 'Pending'
        ])

    # Create and style the table
    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    # Add conditional formatting for status column
    for i, row in enumerate(table_data):
        if i > 0:  # Skip header row
            status = row[-1]
            if status == 'Confirmed':
                table.setStyle(TableStyle([
                    ('BACKGROUND', (-1, i), (-1, i), colors.lightgreen),
                    ('TEXTCOLOR', (-1, i), (-1, i), colors.darkgreen),
                ]))
            else:
                table.setStyle(TableStyle([
                    ('BACKGROUND', (-1, i), (-1, i), colors.lightcoral),
                    ('TEXTCOLOR', (-1, i), (-1, i), colors.darkred),
                ]))

    story.append(table)
    story.append(Spacer(1, 20))

    # Add summary
    summary_style = ParagraphStyle(
        'Summary',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=6
    )
    story.append(Paragraph(f"Total Vehicle Bookings: {data['vehicle_count']}", summary_style))

    doc.build(story)
    return response

def export_boarding_pdf(data):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=passenger_boarding_list_{timezone.now().strftime("%Y%m%d_%H%M")}.pdf'

    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(letter),
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    story = []
    styles = getSampleStyleSheet()

    # Add title and metadata
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=20
    )

    story.append(Paragraph(f"Passenger Boarding List", title_style))
    story.append(Spacer(1, 10))

    # Add generation info
    info_style = ParagraphStyle(
        'Info',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=20
    )
    story.append(Paragraph(f"Generated: {data['generated_at'].strftime('%Y-%m-%d %H:%M')}", info_style))
    story.append(Paragraph(f"Generated By: {data['user'].username}", info_style))
    story.append(Spacer(1, 10))

    # Create the main table
    table_data = [[
        'Booking Ref',
        'Passenger Name',
        'Type',
        'Route',
        'Departure',
        'Vessel',
        'Status'
    ]]

    for passenger in data['passenger_list']:
        table_data.append([
            passenger.booking.booking_reference,
            passenger.full_name,
            passenger.get_passenger_type_display(),
            passenger.booking.schedule.route.name if passenger.booking.schedule and passenger.booking.schedule.route else 'N/A',
            passenger.booking.schedule.departure_datetime.strftime('%Y-%m-%d %H:%M') if passenger.booking.schedule else 'N/A',
            passenger.booking.schedule.vessel.name if passenger.booking.schedule and passenger.booking.schedule.vessel else 'N/A',
            'Confirmed' if passenger.booking.is_paid else 'Pending'
        ])

    # Create and style the table
    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    # Add conditional formatting for status column
    for i, row in enumerate(table_data):
        if i > 0:  # Skip header row
            status = row[-1]
            if status == 'Confirmed':
                table.setStyle(TableStyle([
                    ('BACKGROUND', (-1, i), (-1, i), colors.lightgreen),
                    ('TEXTCOLOR', (-1, i), (-1, i), colors.darkgreen),
                ]))
            else:
                table.setStyle(TableStyle([
                    ('BACKGROUND', (-1, i), (-1, i), colors.lightcoral),
                    ('TEXTCOLOR', (-1, i), (-1, i), colors.darkred),
                ]))

    story.append(table)
    story.append(Spacer(1, 20))

    # Add summary
    summary_style = ParagraphStyle(
        'Summary',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=6
    )
    story.append(Paragraph(f"Total Passengers: {data['passenger_count']}", summary_style))

    doc.build(story)
    return response

def export_revenue_pdf(data):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=revenue_report_{data["month"].replace(" ", "_")}.pdf'

    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(letter),  # Use landscape orientation for more width
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    story = []
    styles = getSampleStyleSheet()

    # Add title and metadata
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=10,
        alignment=1  # Center alignment
    )

    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=5,
        alignment=1,  # Center alignment
        textColor=colors.gray
    )

    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=15,
        spaceAfter=10,
        backColor=colors.lightgrey,
        borderPadding=5
    )

    story.append(Paragraph("Comprehensive Revenue Report", title_style))
    story.append(Paragraph(f"Period: {data['month']}", subtitle_style))
    story.append(Paragraph(f"Generated: {data['generated_at'].strftime('%Y-%m-%d %H:%M')}", subtitle_style))
    story.append(Paragraph(f"Generated By: {data['user'].username}", subtitle_style))
    story.append(Spacer(1, 20))

    # Summary Section
    story.append(Paragraph("SUMMARY", section_style))

    summary_data = [
        ['Total Bookings:', f"{data['booking_count']}"],
        ['Total Revenue:', f"₱{data['total_revenue']:,.2f}"]
    ]

    summary_table = Table(summary_data, colWidths=[150, 150])
    summary_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))

    story.append(summary_table)
    story.append(Spacer(1, 10))

    # Revenue by Booking Type
    story.append(Paragraph("REVENUE BY BOOKING TYPE", section_style))

    # Calculate percentages
    total_revenue = float(data['passenger_revenue'] + data['vehicle_revenue'])
    passenger_percent = (float(data['passenger_revenue']) / total_revenue * 100) if total_revenue > 0 else 0
    vehicle_percent = (float(data['vehicle_revenue']) / total_revenue * 100) if total_revenue > 0 else 0

    booking_type_data = [
        ['Booking Type', 'Revenue', 'Percentage'],
        ['Passenger Bookings', f"₱{data['passenger_revenue']:,.2f}", f"{passenger_percent:.1f}%"],
        ['Vehicle Bookings', f"₱{data['vehicle_revenue']:,.2f}", f"{vehicle_percent:.1f}%"]
    ]

    booking_type_table = Table(booking_type_data, colWidths=[150, 150, 100])
    booking_type_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
    ]))

    story.append(booking_type_table)
    story.append(Spacer(1, 10))

    # Revenue by Payment Method
    story.append(Paragraph("REVENUE BY PAYMENT METHOD", section_style))

    # Calculate percentages
    payment_total = float(data['cash_revenue'] + data['gcash_revenue'])
    cash_percent = (float(data['cash_revenue']) / payment_total * 100) if payment_total > 0 else 0
    gcash_percent = (float(data['gcash_revenue']) / payment_total * 100) if payment_total > 0 else 0

    payment_method_data = [
        ['Payment Method', 'Transactions', 'Revenue', 'Percentage'],
        ['Cash', data['cash_payment_count'], f"₱{data['cash_revenue']:,.2f}", f"{cash_percent:.1f}%"],
        ['GCash', data['gcash_payment_count'], f"₱{data['gcash_revenue']:,.2f}", f"{gcash_percent:.1f}%"]
    ]

    payment_method_table = Table(payment_method_data, colWidths=[100, 100, 150, 100])
    payment_method_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (3, -1), 'RIGHT'),
    ]))

    story.append(payment_method_table)
    story.append(Spacer(1, 10))

    # Revenue by Passenger Type
    story.append(Paragraph("REVENUE BY PASSENGER TYPE", section_style))

    passenger_type_data = [
        ['Passenger Type', 'Count', 'Revenue'],
        ['Regular Adult', data['adult_count'], f"₱{data['adult_revenue']:,.2f}"],
        ['Child', data['child_count'], f"₱{data['child_revenue']:,.2f}"],
        ['Student', data['student_count'], f"₱{data['student_revenue']:,.2f}"],
        ['Senior Citizen', data['senior_count'], f"₱{data['senior_revenue']:,.2f}"]
    ]

    passenger_type_table = Table(passenger_type_data, colWidths=[150, 100, 150])
    passenger_type_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
    ]))

    story.append(passenger_type_table)
    story.append(Spacer(1, 10))

    # Booking Details
    story.append(Paragraph("BOOKING DETAILS", section_style))

    # Create the booking details table with a more descriptive header
    booking_details_data = [
        ['Booking Reference', 'Date', 'Full Name', 'Type', 'Total Fare']
    ]

    # Add up to 20 bookings to avoid making the PDF too large
    for booking in list(data['bookings'])[:20]:
        # Format the booking reference to ensure it's clearly visible
        booking_details_data.append([
            Paragraph(booking.booking_reference, ParagraphStyle('BookingRef', fontSize=7, fontName='Helvetica')),
            booking.created_at.strftime('%Y-%m-%d'),
            booking.full_name,
            booking.get_booking_type_display(),
            f"₱{booking.total_fare:,.2f}"
        ])

    # Add a note if there are more bookings
    if data['bookings'].count() > 20:
        booking_details_data.append(['', '', f"... and {data['bookings'].count() - 20} more bookings", '', ''])

    # Adjust column widths to better fit the content in landscape mode
    booking_details_table = Table(booking_details_data, colWidths=[140, 80, 200, 100, 100])
    booking_details_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),  # Header font size
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),  # Add padding to header
        ('TOPPADDING', (0, 0), (-1, 0), 6),  # Add padding to header
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),  # Left align booking reference
        ('ALIGN', (4, 0), (4, -1), 'RIGHT'),  # Right align fare
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),  # Vertically center all content
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),  # Alternate row colors
    ]))

    story.append(booking_details_table)

    doc.build(story)
    return response

def export_excel(data):
    import xlsxwriter
    from io import BytesIO

    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()

    # Add headers
    headers = [
        'Booking Reference',
        'Date',
        'Full Name',
        'Contact',
        'Type',
        'Route',
        'Adult Passengers',
        'Child Passengers',
        'Status',
        'Total Fare'
    ]

    # Formats
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4B5563',
        'font_color': 'white',
        'border': 1
    })

    cell_format = workbook.add_format({
        'border': 1
    })

    money_format = workbook.add_format({
        'border': 1,
        'num_format': '₱#,##0.00'
    })

    # Write headers
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)

    # Write data
    for row, booking in enumerate(data['bookings'], start=1):
        worksheet.write(row, 0, booking.booking_reference, cell_format)
        worksheet.write(row, 1, booking.created_at.strftime('%Y-%m-%d'), cell_format)
        worksheet.write(row, 2, booking.full_name, cell_format)
        worksheet.write(row, 3, booking.contact_number, cell_format)
        worksheet.write(row, 4, booking.get_booking_type_display(), cell_format)
        worksheet.write(row, 5,
            booking.schedule.route.name if booking.schedule and booking.schedule.route else 'N/A',
            cell_format)
        worksheet.write(row, 6, booking.adult_passengers, cell_format)
        worksheet.write(row, 7, booking.child_passengers, cell_format)
        worksheet.write(row, 8, 'Paid' if booking.is_paid else 'Unpaid', cell_format)
        worksheet.write(row, 9, float(booking.total_fare), money_format)

    # Add summary
    summary_row = len(data['bookings']) + 2
    worksheet.write(summary_row, 0, 'Summary', header_format)
    worksheet.write(summary_row, 1, f"Total Bookings: {data['booking_count']}", cell_format)
    worksheet.write(summary_row, 2, f"Total Revenue: ₱{data['total_revenue']:,.2f}", money_format)

    # Adjust column widths
    worksheet.set_column('A:A', 15)  # Reference
    worksheet.set_column('B:B', 12)  # Date
    worksheet.set_column('C:C', 25)  # Full Name
    worksheet.set_column('D:D', 15)  # Contact
    worksheet.set_column('E:E', 12)  # Type
    worksheet.set_column('F:F', 20)  # Route
    worksheet.set_column('G:H', 10)  # Passengers
    worksheet.set_column('I:I', 10)  # Status
    worksheet.set_column('J:J', 15)  # Total Fare

    workbook.close()
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=booking_report_{data["month"].replace(" ", "_")}.xlsx'
    return response

def export_vehicle_excel(data):
    import xlsxwriter
    from io import BytesIO

    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet('Vehicle List')

    # Define styles
    title_format = workbook.add_format({
        'bold': True,
        'font_size': 16,
        'align': 'center',
        'valign': 'vcenter'
    })

    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'color': 'white',
        'align': 'center',
        'valign': 'vcenter',
        'border': 1
    })

    cell_format = workbook.add_format({
        'align': 'left',
        'valign': 'vcenter',
        'border': 1
    })

    confirmed_format = workbook.add_format({
        'align': 'center',
        'valign': 'vcenter',
        'bg_color': '#C6EFCE',
        'color': '#006100',
        'border': 1
    })

    pending_format = workbook.add_format({
        'align': 'center',
        'valign': 'vcenter',
        'bg_color': '#FFC7CE',
        'color': '#9C0006',
        'border': 1
    })

    # Set column widths
    worksheet.set_column('A:A', 15)  # Booking Reference
    worksheet.set_column('B:B', 25)  # Customer Name
    worksheet.set_column('C:C', 20)  # Vehicle Type
    worksheet.set_column('D:D', 15)  # Plate Number
    worksheet.set_column('E:E', 20)  # Route
    worksheet.set_column('F:F', 20)  # Departure
    worksheet.set_column('G:G', 15)  # Status

    # Write title
    worksheet.merge_range('A1:G1', 'Vehicle Bookings List', title_format)
    worksheet.merge_range('A2:G2', f'Generated: {data["generated_at"].strftime("%Y-%m-%d %H:%M")}', cell_format)
    worksheet.merge_range('A3:G3', f'Generated By: {data["user"].username}', cell_format)

    # Write headers
    headers = ['Booking Ref', 'Customer Name', 'Vehicle Type', 'Plate Number', 'Route', 'Departure', 'Status']
    for col, header in enumerate(headers):
        worksheet.write(4, col, header, header_format)

    # Write data
    row = 5
    for vehicle in data['vehicle_list']:
        worksheet.write(row, 0, vehicle.booking_reference, cell_format)
        worksheet.write(row, 1, vehicle.full_name, cell_format)
        worksheet.write(row, 2, vehicle.vehicle_type.name if vehicle.vehicle_type else 'N/A', cell_format)
        worksheet.write(row, 3, vehicle.plate_number or 'N/A', cell_format)
        worksheet.write(row, 4, vehicle.schedule.route.name if vehicle.schedule and vehicle.schedule.route else 'N/A', cell_format)
        worksheet.write(row, 5, vehicle.schedule.departure_datetime.strftime('%Y-%m-%d %H:%M') if vehicle.schedule else 'N/A', cell_format)

        # Use conditional formatting for status
        status = 'Confirmed' if vehicle.is_paid else 'Pending'
        status_format = confirmed_format if vehicle.is_paid else pending_format
        worksheet.write(row, 6, status, status_format)

        row += 1

    # Write summary
    summary_row = row + 2
    worksheet.merge_range(f'A{summary_row}:B{summary_row}', f'Total Vehicle Bookings: {data["vehicle_count"]}', title_format)

    workbook.close()
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=vehicle_list_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx'
    return response

def export_boarding_excel(data):
    import xlsxwriter
    from io import BytesIO

    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet('Passenger Boarding List')

    # Add headers
    headers = [
        'Booking Reference',
        'Passenger Name',
        'Passenger Type',
        'Route',
        'Departure Date/Time',
        'Vessel',
        'Status'
    ]

    # Formats
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4B5563',
        'font_color': 'white',
        'border': 1
    })

    cell_format = workbook.add_format({
        'border': 1
    })

    date_format = workbook.add_format({
        'border': 1,
        'num_format': 'yyyy-mm-dd hh:mm'
    })

    confirmed_format = workbook.add_format({
        'border': 1,
        'bg_color': '#D1FAE5',
        'font_color': '#065F46'
    })

    pending_format = workbook.add_format({
        'border': 1,
        'bg_color': '#FEE2E2',
        'font_color': '#991B1B'
    })

    # Write headers
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)

    # Write data
    for row, passenger in enumerate(data['passenger_list'], start=1):
        worksheet.write(row, 0, passenger.booking.booking_reference, cell_format)
        worksheet.write(row, 1, passenger.full_name, cell_format)
        worksheet.write(row, 2, passenger.get_passenger_type_display(), cell_format)
        worksheet.write(row, 3, passenger.booking.schedule.route.name if passenger.booking.schedule and passenger.booking.schedule.route else 'N/A', cell_format)

        # Format departure datetime
        if passenger.booking.schedule and passenger.booking.schedule.departure_datetime:
            worksheet.write(row, 4, passenger.booking.schedule.departure_datetime.strftime('%Y-%m-%d %H:%M'), date_format)
        else:
            worksheet.write(row, 4, 'N/A', cell_format)

        worksheet.write(row, 5, passenger.booking.schedule.vessel.name if passenger.booking.schedule and passenger.booking.schedule.vessel else 'N/A', cell_format)

        # Format status with color
        status_format = confirmed_format if passenger.booking.is_paid else pending_format
        status_text = 'Confirmed' if passenger.booking.is_paid else 'Pending'
        worksheet.write(row, 6, status_text, status_format)

    # Add summary
    summary_row = len(data['passenger_list']) + 2
    worksheet.write(summary_row, 0, 'Summary', header_format)
    worksheet.write(summary_row, 1, f"Total Passengers: {data['passenger_count']}", cell_format)
    worksheet.write(summary_row, 2, f"Generated: {data['generated_at'].strftime('%Y-%m-%d %H:%M')}", cell_format)

    # Adjust column widths
    worksheet.set_column('A:A', 15)  # Reference
    worksheet.set_column('B:B', 25)  # Passenger Name
    worksheet.set_column('C:C', 15)  # Passenger Type
    worksheet.set_column('D:D', 25)  # Route
    worksheet.set_column('E:E', 20)  # Departure Date/Time
    worksheet.set_column('F:F', 20)  # Vessel
    worksheet.set_column('G:G', 10)  # Status

    workbook.close()
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=passenger_boarding_list_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx'

    return response

def export_revenue_excel(data):
    import xlsxwriter
    from io import BytesIO

    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet('Revenue Report')

    # Formats
    title_format = workbook.add_format({
        'bold': True,
        'font_size': 16,
        'align': 'center',
        'valign': 'vcenter'
    })

    subtitle_format = workbook.add_format({
        'italic': True,
        'align': 'center'
    })

    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4B5563',
        'font_color': 'white',
        'border': 1
    })

    section_format = workbook.add_format({
        'bold': True,
        'bg_color': '#E5E7EB',
        'border': 1
    })

    cell_format = workbook.add_format({
        'border': 1
    })

    money_format = workbook.add_format({
        'border': 1,
        'num_format': '₱#,##0.00'
    })

    percent_format = workbook.add_format({
        'border': 1,
        'num_format': '0.0%'
    })

    date_format = workbook.add_format({
        'border': 1,
        'num_format': 'yyyy-mm-dd'
    })

    # Write title and metadata
    worksheet.merge_range('A1:G1', 'Comprehensive Revenue Report', title_format)
    worksheet.merge_range('A2:G2', f'Period: {data["month"]}', subtitle_format)
    worksheet.merge_range('A3:G3', f'Generated: {data["generated_at"].strftime("%Y-%m-%d %H:%M")}', subtitle_format)
    worksheet.merge_range('A4:G4', f'Generated By: {data["user"].username}', subtitle_format)

    # Write summary section
    row = 5
    worksheet.merge_range(row, 0, row, 6, 'SUMMARY', section_format)
    row += 1

    worksheet.write(row, 0, 'Total Bookings', cell_format)
    worksheet.write(row, 1, data['booking_count'], cell_format)
    row += 1

    worksheet.write(row, 0, 'Total Revenue', cell_format)
    worksheet.write(row, 1, float(data['total_revenue']), money_format)
    row += 2

    # Write revenue by booking type
    worksheet.merge_range(row, 0, row, 6, 'REVENUE BY BOOKING TYPE', section_format)
    row += 1

    worksheet.write(row, 0, 'Booking Type', header_format)
    worksheet.write(row, 1, 'Revenue', header_format)
    worksheet.write(row, 2, 'Percentage', header_format)
    row += 1

    # Calculate percentages
    total_revenue = float(data['passenger_revenue'] + data['vehicle_revenue'])
    passenger_percent = float(data['passenger_revenue']) / total_revenue if total_revenue > 0 else 0
    vehicle_percent = float(data['vehicle_revenue']) / total_revenue if total_revenue > 0 else 0

    worksheet.write(row, 0, 'Passenger Bookings', cell_format)
    worksheet.write(row, 1, float(data['passenger_revenue']), money_format)
    worksheet.write(row, 2, passenger_percent, percent_format)
    row += 1

    worksheet.write(row, 0, 'Vehicle Bookings', cell_format)
    worksheet.write(row, 1, float(data['vehicle_revenue']), money_format)
    worksheet.write(row, 2, vehicle_percent, percent_format)
    row += 2

    # Write revenue by payment method
    worksheet.merge_range(row, 0, row, 6, 'REVENUE BY PAYMENT METHOD', section_format)
    row += 1

    worksheet.write(row, 0, 'Payment Method', header_format)
    worksheet.write(row, 1, 'Transactions', header_format)
    worksheet.write(row, 2, 'Revenue', header_format)
    worksheet.write(row, 3, 'Percentage', header_format)
    row += 1

    # Calculate percentages
    payment_total = float(data['cash_revenue'] + data['gcash_revenue'])
    cash_percent = float(data['cash_revenue']) / payment_total if payment_total > 0 else 0
    gcash_percent = float(data['gcash_revenue']) / payment_total if payment_total > 0 else 0

    worksheet.write(row, 0, 'Cash', cell_format)
    worksheet.write(row, 1, data['cash_payment_count'], cell_format)
    worksheet.write(row, 2, float(data['cash_revenue']), money_format)
    worksheet.write(row, 3, cash_percent, percent_format)
    row += 1

    worksheet.write(row, 0, 'GCash', cell_format)
    worksheet.write(row, 1, data['gcash_payment_count'], cell_format)
    worksheet.write(row, 2, float(data['gcash_revenue']), money_format)
    worksheet.write(row, 3, gcash_percent, percent_format)
    row += 2

    # Write revenue by passenger type
    worksheet.merge_range(row, 0, row, 6, 'REVENUE BY PASSENGER TYPE', section_format)
    row += 1

    worksheet.write(row, 0, 'Passenger Type', header_format)
    worksheet.write(row, 1, 'Count', header_format)
    worksheet.write(row, 2, 'Revenue', header_format)
    row += 1

    worksheet.write(row, 0, 'Regular Adult', cell_format)
    worksheet.write(row, 1, data['adult_count'], cell_format)
    worksheet.write(row, 2, float(data['adult_revenue']), money_format)
    row += 1

    worksheet.write(row, 0, 'Child', cell_format)
    worksheet.write(row, 1, data['child_count'], cell_format)
    worksheet.write(row, 2, float(data['child_revenue']), money_format)
    row += 1

    worksheet.write(row, 0, 'Student', cell_format)
    worksheet.write(row, 1, data['student_count'], cell_format)
    worksheet.write(row, 2, float(data['student_revenue']), money_format)
    row += 1

    worksheet.write(row, 0, 'Senior Citizen', cell_format)
    worksheet.write(row, 1, data['senior_count'], cell_format)
    worksheet.write(row, 2, float(data['senior_revenue']), money_format)
    row += 2

    # Write booking details
    worksheet.merge_range(row, 0, row, 6, 'BOOKING DETAILS', section_format)
    row += 1

    worksheet.write(row, 0, 'Booking Reference', header_format)
    worksheet.write(row, 1, 'Date', header_format)
    worksheet.write(row, 2, 'Full Name', header_format)
    worksheet.write(row, 3, 'Type', header_format)
    worksheet.write(row, 4, 'Route', header_format)
    worksheet.write(row, 5, 'Total Fare', header_format)
    row += 1

    for booking in data['bookings']:
        worksheet.write(row, 0, booking.booking_reference, cell_format)
        worksheet.write(row, 1, booking.created_at.strftime('%Y-%m-%d'), date_format)
        worksheet.write(row, 2, booking.full_name, cell_format)
        worksheet.write(row, 3, booking.get_booking_type_display(), cell_format)
        worksheet.write(row, 4, booking.schedule.route.name if booking.schedule and booking.schedule.route else 'N/A', cell_format)
        worksheet.write(row, 5, float(booking.total_fare), money_format)
        row += 1

    # Adjust column widths
    worksheet.set_column('A:A', 20)  # Reference/Type
    worksheet.set_column('B:B', 15)  # Date/Count
    worksheet.set_column('C:C', 25)  # Name/Revenue
    worksheet.set_column('D:D', 15)  # Type/Percentage
    worksheet.set_column('E:E', 25)  # Route
    worksheet.set_column('F:F', 15)  # Fare

    workbook.close()
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=revenue_report_{data["month"].replace(" ", "_")}.xlsx'

    return response

def export_pdf(data):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=booking_report_{data["month"].replace(" ", "_")}.pdf'

    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(letter),
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )

    story = []
    styles = getSampleStyleSheet()

    # Add title and metadata
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30
    )

    story.append(Paragraph(f"Booking Report - {data['month']}", title_style))
    story.append(Spacer(1, 20))

    # Create the main table
    table_data = [[
        'Reference',
        'Date',
        'Full Name',
        'Contact',
        'Type',
        'Route',
        'Passengers',
        'Status',
        'Total Fare'
    ]]

    for booking in data['bookings']:
        passengers = f"A:{booking.adult_passengers} C:{booking.child_passengers}"
        route_name = booking.schedule.route.name if booking.schedule and booking.schedule.route else 'N/A'

        table_data.append([
            booking.booking_reference,
            booking.created_at.strftime('%Y-%m-%d'),
            booking.full_name,
            booking.contact_number,
            booking.get_booking_type_display(),
            route_name,
            passengers,
            'Paid' if booking.is_paid else 'Unpaid',
            f"₱{booking.total_fare:,.2f}"
        ])

    # Create and style the table
    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    story.append(table)
    story.append(Spacer(1, 20))

    # Add summary
    summary_style = ParagraphStyle(
        'Summary',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=6
    )
    story.append(Paragraph(f"Total Bookings: {data['booking_count']}", summary_style))
    story.append(Paragraph(f"Total Revenue: ₱{data['total_revenue']:,.2f}", summary_style))

    doc.build(story)
    return response


from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.views.decorators.http import require_http_methods
from .models import VehicleType


def vehicle_types_view(request):
    vehicle_types = VehicleType.objects.all().order_by('name')
    return render(request, 'dashboard/vehicle_type_item.html', {
        'vehicle_types': vehicle_types
    })

@login_required
@staff_member_required
def vehicle_list(request):
    """View for displaying and managing vehicles in the dashboard"""
    # Get all vehicles with their related vehicle types
    vehicles = Vehicle.objects.all().select_related('vehicle_type').order_by('name')

    # Handle search
    search_query = request.GET.get('search', '')
    if search_query:
        vehicles = vehicles.filter(
            Q(name__icontains=search_query) |
            Q(plate_number__icontains=search_query) |
            Q(vehicle_type__name__icontains=search_query)
        )

    # Get all vehicle types for the add vehicle form
    vehicle_types = VehicleType.objects.all().order_by('name')

    context = {
        'vehicles': vehicles,
        'vehicle_types': vehicle_types,
    }

    return render(request, 'dashboard/vehicles.html', context)

@login_required
@staff_member_required
def add_vehicle(request):
    """View for adding a new vehicle"""
    if request.method == 'POST':
        try:
            vehicle = Vehicle.objects.create(
                name=request.POST.get('name'),
                plate_number=request.POST.get('plate_number'),
                description=request.POST.get('description', ''),
                capacity=request.POST.get('capacity'),
                active=request.POST.get('active') == 'on',
                vehicle_type_id=request.POST.get('vehicle_type')
            )

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Vehicle added successfully'
                })

            messages.success(request, 'Vehicle added successfully')
            return redirect('vehicle_list')

        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                })

            messages.error(request, f'Error adding vehicle: {str(e)}')
            return redirect('vehicle_list')

    # This view doesn't need a GET handler as it uses a modal form in vehicles.html
    return redirect('vehicle_list')

@login_required
@staff_member_required
def edit_vehicle(request, vehicle_id):
    """View for editing an existing vehicle"""
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)

    if request.method == 'POST':
        try:
            vehicle.name = request.POST.get('name')
            vehicle.plate_number = request.POST.get('plate_number')
            vehicle.description = request.POST.get('description', '')
            vehicle.capacity = request.POST.get('capacity')
            vehicle.active = request.POST.get('active') == 'on'
            vehicle.vehicle_type_id = request.POST.get('vehicle_type')
            vehicle.save()

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Vehicle updated successfully'
                })

            messages.success(request, 'Vehicle updated successfully')
            return redirect('vehicle_list')

        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                })

            messages.error(request, f'Error updating vehicle: {str(e)}')
            return redirect('vehicle_list')

    # This view doesn't need a GET handler as it uses a modal form
    return redirect('vehicle_list')

@login_required
@staff_member_required
def delete_vehicle(request, vehicle_id):
    """View for deleting a vehicle"""
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)

    try:
        vehicle_name = vehicle.name
        vehicle.delete()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': f'Vehicle "{vehicle_name}" deleted successfully'
            })

        messages.success(request, f'Vehicle "{vehicle_name}" deleted successfully')

    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

        messages.error(request, f'Error deleting vehicle: {str(e)}')

    return redirect('vehicle_list')
@require_http_methods(["POST"])
def add_vehicle_type(request):
    vehicle_type = VehicleType.objects.create(
        name=request.POST['name'],
        max_occupants=request.POST['max_occupants'],
        max_cargo_weight=request.POST['max_cargo_weight'],
        base_fare=request.POST['base_fare']
    )
    vehicle_types = VehicleType.objects.all().order_by('name')
    return render(request, 'dashboard/vehicle_type_item.html', {
        'vehicle_type': vehicle_type,
        'vehicle_types': vehicle_types,
    })
def get_vehicle_types(request):
    vehicle_types = VehicleType.objects.all().order_by('name')
    return render(request, 'dashboard/vehicle_type_list.html', {
        'vehicle_types': vehicle_types
    })

@require_http_methods(["PUT", "POST"])
def update_vehicle_type(request, id):
    try:
        vehicle_type = get_object_or_404(VehicleType, id=id)

        # Get data from request
        data = request.POST if request.method == "POST" else QueryDict(request.body)

        # Update fields
        vehicle_type.name = data.get('name', vehicle_type.name)
        vehicle_type.max_occupants = data.get('max_occupants', vehicle_type.max_occupants)
        vehicle_type.max_cargo_weight = data.get('max_cargo_weight', vehicle_type.max_cargo_weight)
        vehicle_type.base_fare = data.get('base_fare', vehicle_type.base_fare)
        vehicle_type.save()

        # Return the updated item HTML
        return render(request, 'dashboard/vehicle_type_item.html', {
            'vehicle_types': [vehicle_type]
        })
    except VehicleType.DoesNotExist:
        return HttpResponse(status=404)
    except Exception as e:
        return HttpResponse(str(e), status=400)

@require_http_methods(["GET"])
def get_vehicle_type(request, id):
    vehicle_type = get_object_or_404(VehicleType, id=id)
    return render(request, 'dashboard/vehicle_type_item.html', {
        'vehicle_types': [vehicle_type]
    })

@require_http_methods(["DELETE", "POST"])
def delete_vehicle_type(request, id):
    vehicle_type = get_object_or_404(VehicleType, id=id)
    vehicle_type.delete()
    return HttpResponse('')

def get_vehicle_types(request):
    """View for getting all vehicle types for HTMX"""
    vehicle_types = VehicleType.objects.all().order_by('name')
    return render(request, 'dashboard/vehicle_type_list.html', {
        'vehicle_types': vehicle_types
    })


from django.http import JsonResponse
from decimal import Decimal

def calculate_vehicle_fare(request):
    """Calculate fare for vehicle bookings"""
    try:
        vehicle_type_id = request.GET.get('vehicle_type')
        if not vehicle_type_id:
            return JsonResponse({'error': 'Vehicle type is required'}, status=400)

        vehicle_type = get_object_or_404(VehicleType, id=vehicle_type_id)

        # Get base fare for the vehicle type
        base_fare = vehicle_type.base_fare or Decimal('0.00')

        # You can add additional calculations here based on your business logic
        # For example, adding surcharges based on weight, size, etc.

        context = {
            'base_fare': float(base_fare),
            'vehicle_type': vehicle_type.name,
            'total_fare': float(base_fare)  # Modify this if you add surcharges
        }

        # Return HTML snippet for HTMX
        return render(request, 'partials/vehicle_fare_details.html', context)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

from django.template.response import TemplateResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
@login_required
def get_notifications(request):
    # Get all pending bookings, ordered by most recent
    pending_bookings = Booking.objects.filter(is_paid=False).order_by('-created_at')
    return TemplateResponse(request, 'dashboard/partials/notifications.html', {
        'pending_bookings': pending_bookings
    })

def get_notification_context(request):
    if request.user.is_authenticated:
        # Get total count of all pending bookings
        pending_payments_count = Booking.objects.filter(is_paid=False).count()
        return {
            'pending_payments_count': pending_payments_count
        }
    return {'pending_payments_count': 0}

@login_required
@staff_member_required
def get_schedule(request, schedule_id):
    """API endpoint for getting schedule details"""
    try:
        schedule = get_object_or_404(Schedule, pk=schedule_id)

        return JsonResponse({
            'success': True,
            'schedule': {
                'id': schedule.id,
                'vessel_id': schedule.vessel.id,
                'route_id': schedule.route.id,
                'departure_datetime': schedule.departure_datetime.isoformat(),
                'arrival_datetime': schedule.arrival_datetime.isoformat(),
                'available_seats': schedule.available_seats,
                'available_cargo_space': schedule.available_cargo_space,
                'adult_fare': str(schedule.adult_fare),
                'child_fare': str(schedule.child_fare),
                'student_fare': str(schedule.student_fare) if schedule.student_fare else '',
                'senior_fare': str(schedule.senior_fare) if schedule.senior_fare else '',
                'status': schedule.status,
                'notes': schedule.notes
            }
        })
    except Schedule.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Schedule not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)



@login_required
@staff_member_required
def schedule_delete(request, pk):
    """API endpoint for deleting a schedule"""
    try:
        schedule = get_object_or_404(Schedule, pk=pk)

        # Delete the schedule
        schedule.delete()

        return JsonResponse({
            'success': True,
            'message': 'Schedule deleted successfully'
        })

    except Schedule.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Schedule not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
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

    # Get user information if authenticated
    user_info = {}
    if request.user.is_authenticated:
        user_full_name = f"{request.user.first_name} {request.user.last_name}".strip()

        # Get contact number from session if available
        contact_number = request.session.get('user_contact_number', '')

        # If not in session, try to get from recent bookings
        if not contact_number:
            try:
                recent_booking = Booking.objects.filter(
                    email=request.user.email
                ).order_by('-created_at').first()

                if recent_booking:
                    contact_number = recent_booking.contact_number
            except Exception as e:
                print(f"Error getting contact number: {str(e)}")

        user_info = {
            'full_name': user_full_name,
            'email': request.user.email,
            'contact_number': contact_number
        }

    context = {
        'schedules': schedules,
        'vehicle_types': vehicle_types,
        'selected_schedule': selected_schedule,
        'user_info': user_info,
    }

    return render(request, 'vehicle_booking.html', context)
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

    # Get user information if authenticated
    user_info = {}
    if request.user.is_authenticated:
        user_full_name = f"{request.user.first_name} {request.user.last_name}".strip()

        # Get contact number from session if available
        contact_number = request.session.get('user_contact_number', '')

        # If not in session, try to get from recent bookings
        if not contact_number:
            try:
                recent_booking = Booking.objects.filter(
                    email=request.user.email
                ).order_by('-created_at').first()

                if recent_booking:
                    contact_number = recent_booking.contact_number
            except Exception as e:
                print(f"Error getting contact number: {str(e)}")

        user_info = {
            'full_name': user_full_name,
            'email': request.user.email,
            'contact_number': contact_number
        }

    context = {
        'schedules': schedules,
        'vehicle_types': vehicle_types,
        'selected_schedule': selected_schedule,
        'user_info': user_info
    }

    return render(request, 'vehicle_booking.html', context)
