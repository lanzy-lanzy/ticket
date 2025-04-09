from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.db import models
from django.http import JsonResponse, HttpResponse
from .models import Booking, Vessel, Schedule, Payment, VehicleType, Rating, Route, ContactMessage, TravelGuideline, Passenger
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

    context = {
        'schedules': schedules,
        'vehicle_types': vehicle_types,
        'selected_schedule': selected_schedule,
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
            payment_method = request.POST.get('payment_method', 'online')

            # Calculate payment amount based on booking type
            payment_amount = 0
            if booking.booking_type == 'passenger':
                # Example: $50 per passenger
                payment_amount = 50 * booking.number_of_passengers
            elif booking.booking_type == 'vehicle':
                # Base price for vehicle + additional for passengers
                base_price = booking.vehicle_type.price if booking.vehicle_type else 100
                payment_amount = base_price + (20 * booking.occupant_count)

            # Create payment record
            payment = Payment.objects.create(
                booking=booking,
                amount_paid=payment_amount,
                payment_method=payment_method
            )

            # Update booking status
            booking.is_paid = True
            booking.save()

            messages.success(request, "Payment successful! Your booking is confirmed.")
            return redirect('booking_confirmation', booking_reference=booking.booking_reference)

        except Booking.DoesNotExist:
            messages.error(request, "Invalid booking reference.")
            return redirect('home')

    # If not POST, redirect to payment page
    return redirect('payment_view')
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
        booking.payment = payment
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

        return HttpResponseRedirect(reverse('print_ticket', args=[booking_reference]))

    except Exception as e:
        logger.error(f"Payment processing error: {str(e)}", exc_info=True)
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

def mark_payment_complete(request, booking_reference):
    """
    Mark a booking as paid after GCash payment
    """
    if request.method == 'POST':
        try:
            booking = get_object_or_404(Booking, booking_reference=booking_reference)
            payment_method = request.POST.get('payment_method', 'online')

            # Calculate payment amount based on booking type
            payment_amount = 0
            if booking.booking_type == 'passenger':
                # Example: $50 per passenger
                payment_amount = 50 * booking.number_of_passengers
            elif booking.booking_type == 'vehicle':
                # Base price for vehicle + additional for passengers
                base_price = booking.vehicle_type.price if booking.vehicle_type else 100
                payment_amount = base_price + (20 * booking.occupant_count)

            # Create payment record
            payment = Payment.objects.create(
                booking=booking,
                amount_paid=payment_amount,
                payment_method=payment_method
            )

            # Update booking status
            booking.is_paid = True
            booking.save()

            messages.success(request, "Payment successful! Your booking is confirmed.")
            return redirect('booking_confirmation', booking_reference=booking.booking_reference)

        except Booking.DoesNotExist:
            messages.error(request, "Invalid booking reference.")
            return redirect('home')

    # If not POST, redirect to payment page
    return redirect('payment_view')
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
            booking.adult_fare_total = adult_fare * booking.adult_passengers
            booking.child_fare_total = child_fare * booking.child_passengers
            total_amount = booking.adult_fare_total + booking.child_fare_total
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

        elif booking.booking_type == 'passenger':
            adult_passengers = int(booking.adult_passengers or 0)
            child_passengers = int(booking.child_passengers or 0)
            adult_fare = booking.schedule.adult_fare or Decimal('0.00')
            child_fare = booking.schedule.child_fare or Decimal('0.00')
            payment_amount = (adult_passengers * adult_fare) + (child_passengers * child_fare)

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

    routes = Route.objects.filter(active=True)
    vessels = Vessel.objects.filter(active=True)

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

    context = {
        'month': month,
        'year': year,
        'routes': routes,
        'vessels': vessels,
        'selected_route': selected_route,
        'selected_vessel': selected_vessel,
        'monthly_bookings_count': monthly_bookings_count,
        'monthly_revenue': monthly_revenue,
        'booking_growth': booking_growth,
        'revenue_growth': revenue_growth,
        'avg_booking_value': avg_booking_value,
        'occupancy_rate': occupancy_rate,
        'route_performance': route_performance,
        'revenue_data': revenue_data,
        'revenue_labels': revenue_labels
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

# Add this to your payment confirmation view
def mark_payment_complete(request, booking_reference):
    booking = get_object_or_404(Booking, booking_reference=booking_reference)

    # Create payment record with ACTUAL booking amount
    payment = Payment.objects.create(
        booking=booking,
        amount=booking.total_amount,  # Make sure you're using the actual booking amount
        payment_method='cash',
        payment_reference=f'PAY-{timezone.now().strftime("%Y%m%d")}-{booking_reference[-6:]}',
    )

    # Mark booking as paid
    booking.is_paid = True
    booking.save()

    return redirect('booking_confirmation', booking_reference=booking_reference)

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
        if not schedule_id:
            messages.error(request, "No schedule selected.")
            return redirect('booking')

        schedule = get_object_or_404(Schedule, id=schedule_id)

        # Get common booking data
        booking_type = request.POST.get('booking_type', 'passenger')

        # Create new booking with common fields
        booking = Booking(
            schedule=schedule,
            booking_type=booking_type,
            booking_reference=generate_booking_reference(),
            full_name=request.POST.get('full_name'),
            contact_number=request.POST.get('contact_number'),
            email=request.POST.get('email'),
            is_paid=False
        )

        # Set type-specific fields
        if booking_type == 'passenger':
            booking.adult_passengers = int(request.POST.get('adult_passengers', 0) or 0)
            booking.child_passengers = int(request.POST.get('child_passengers', 0) or 0)
            booking.number_of_passengers = booking.adult_passengers + booking.child_passengers
            booking.adult_fare_rate = schedule.adult_fare
            booking.child_fare_rate = schedule.child_fare
        else:  # vehicle booking
            vehicle_type_id = request.POST.get('vehicle_type')
            if vehicle_type_id:
                booking.vehicle_type = get_object_or_404(VehicleType, id=vehicle_type_id)

            booking.plate_number = request.POST.get('plate_number', '')
            booking.occupant_count = int(request.POST.get('occupant_count', 1) or 1)
            booking.cargo_weight = Decimal(request.POST.get('cargo_weight', 0) or 0)
            # Set fare rates to 0 for vehicle bookings to satisfy NOT NULL constraint
            booking.adult_fare_rate = Decimal('0.00')
            booking.child_fare_rate = Decimal('0.00')

        # Save the booking
        booking.save()

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

        # Redirect to payment
        messages.success(request, "Booking created successfully. Please complete your payment.")
        return redirect('payment', booking_reference=booking.booking_reference)

    except Exception as e:
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

        try:
            schedule = Schedule.objects.get(id=schedule_id)
            adult_total = schedule.adult_fare * adult_count
            child_total = schedule.child_fare * child_count
            total = adult_total + child_total

            return render(request, 'partials/fare_summary.html', {
                'adult_total': adult_total,
                'child_total': child_total,
                'total': total
            })
        except Schedule.DoesNotExist:
            return HttpResponse("Selected schedule not found")
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
            # Calculate vehicle fare
            base_price = Decimal(str(booking.vehicle_type.base_fare)) if booking.vehicle_type else Decimal('0.00')
            payment_amount = base_price
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
        schedule.departure_datetime = request.POST.get('departure_datetime')
        schedule.arrival_datetime = request.POST.get('arrival_datetime')
        schedule.available_seats = request.POST.get('available_seats')
        schedule.available_cargo_space = request.POST.get('available_cargo_space')
        schedule.adult_fare = request.POST.get('adult_fare')
        schedule.child_fare = request.POST.get('child_fare')
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
    if booking.booking_type == 'vehicle':
        total_fare = booking.vehicle_type.base_fare if booking.vehicle_type else 0
    else:
        total_fare = (
            booking.adult_passengers * booking.schedule.adult_fare +
            booking.child_passengers * booking.schedule.child_fare
        )

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
        payment_amount = (
            booking.adult_passengers * booking.schedule.adult_fare +
            booking.child_passengers * booking.schedule.child_fare +
            (booking.vehicle_type.fare if booking.vehicle_type else 0)
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
    total_fare = (
        booking.adult_passengers * booking.schedule.adult_fare +
        booking.child_passengers * booking.schedule.child_fare +
        (booking.vehicle_type.fare if booking.vehicle_type else 0)
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
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))
    selected_route = request.GET.get('route', '')
    selected_vessel = request.GET.get('vessel', '')

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
