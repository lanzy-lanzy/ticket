from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.files.base import ContentFile
from django.utils import timezone
import qrcode
import io
import uuid
from decimal import Decimal
# --------------------------------
# 1. VESSEL & SCHEDULE MANAGEMENT
# --------------------------------

class Vessel(models.Model):
    name = models.CharField(max_length=100)
    capacity_passengers = models.PositiveIntegerField()
    capacity_cargo = models.FloatField(help_text="Capacity in metric tons")
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

# --------------------------------
# 1.1 ROUTE MANAGEMENT
# --------------------------------

class Route(models.Model):
    name = models.CharField(max_length=100)
    origin = models.CharField(max_length=100)
    destination = models.CharField(max_length=100)
    distance = models.FloatField(
        help_text="Distance in nautical miles",
        validators=[MinValueValidator(0.1)]
    )
    estimated_duration = models.DurationField(
        help_text="Estimated travel duration (HH:MM:SS)"
    )
    active = models.BooleanField(default=True)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_routes'
    )
    def __str__(self):
        return f"{self.origin} to {self.destination}"

class Schedule(models.Model):
    vessel = models.ForeignKey(Vessel, on_delete=models.CASCADE)
    route = models.ForeignKey(Route, on_delete=models.CASCADE)
    departure_datetime = models.DateTimeField()
    arrival_datetime = models.DateTimeField()
    available_seats = models.PositiveIntegerField()
    available_cargo_space = models.FloatField()
    # Add fare fields
    adult_fare = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Adult passenger fare rate"
    )
    child_fare = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Child passenger fare rate (ages 3-11)"
    )

    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('canceled', 'Canceled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    notes = models.TextField(blank=True, null=True)

    def get_available_seats(self):
        """Calculate remaining passenger seats"""
        # Get total passenger capacity from vessel
        total_capacity = self.vessel.capacity_passengers

        # Get total booked passengers for this schedule
        booked_passengers = Booking.objects.filter(
            schedule=self,
            booking_type='passenger'
        ).aggregate(
            total=models.Sum(
                models.F('adult_passengers') + models.F('child_passengers'),
                output_field=models.IntegerField()
            )
        )['total'] or 0

        return total_capacity - booked_passengers

    def get_available_cargo_space(self):
        """Calculate remaining cargo space"""
        # Get total cargo capacity from vessel
        total_capacity = self.vessel.capacity_cargo

        # Get total booked cargo for this schedule
        booked_cargo = Booking.objects.filter(
            schedule=self,
            booking_type='cargo'
        ).aggregate(
            total=models.Sum(
                models.F('cargo_weight'),
                output_field=models.FloatField()
            )
        )['total'] or 0

        return total_capacity - booked_cargo

    def __str__(self):
        return f"{self.vessel.name} - {self.route.name} - {self.departure_datetime.strftime('%Y-%m-%d %H:%M')}"

# --------------------------------
# 2. OPTIONAL VEHICLE SUPPORT
# --------------------------------

class VehicleType(models.Model):
    name = models.CharField(max_length=50)
    max_occupants = models.PositiveIntegerField(
        default=1,
        help_text="Maximum number of people allowed (including driver)."
    )
    max_cargo_weight = models.FloatField(
        default=0.0,
        help_text="Max cargo weight in metric tons."
    )
    base_fare = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    def __str__(self):
        return self.name

# --------------------------------
# 3. BOOKING & QR CODE GENERATION
# --------------------------------

class Passenger(models.Model):
    """Model to store individual passenger information"""
    PASSENGER_TYPE_CHOICES = [
        ('adult', 'Adult'),
        ('child', 'Child'),
    ]

    full_name = models.CharField(max_length=200)
    passenger_type = models.CharField(
        max_length=10,
        choices=PASSENGER_TYPE_CHOICES,
        default='adult'
    )
    booking = models.ForeignKey('Booking', on_delete=models.CASCADE, related_name='passengers')

    def __str__(self):
        return f"{self.full_name} ({self.get_passenger_type_display()})"

class Booking(models.Model):
    # Add these status choices at the top of the model
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed')
    ]

    booking_reference = models.CharField(max_length=10, unique=True)
    BOOKING_TYPE_CHOICES = [
        ('passenger', 'Passenger'),
        ('vehicle', 'Vehicle'),
    ]
    booking_type = models.CharField(
        max_length=10,
        choices=BOOKING_TYPE_CHOICES,
        default='passenger'
    )

    # Common fields
    full_name = models.CharField(max_length=200)
    contact_number = models.CharField(max_length=15)
    email = models.EmailField()
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE)
    is_paid = models.BooleanField(default=False)
    booking_reference = models.CharField(max_length=20, unique=True, blank=True)
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Passenger-only
    number_of_passengers = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)]
    )

    # Vehicle-specific
    vehicle_type = models.ForeignKey(
        VehicleType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    plate_number = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )
    occupant_count = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)]
    )

    # Cargo
    cargo_weight = models.FloatField(
        default=0.0,
        help_text="Total cargo weight in metric tons."
    )

    # Add passenger type counts and fares
    adult_passengers = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)]
    )
    child_passengers = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)]
    )
    adult_fare_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    child_fare_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    total_fare = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )



    def calculate_total_fare(self):
        # For vehicle bookings, fare calculation is not applicable.
        if self.booking_type == 'vehicle':
            return Decimal('0.00')

        adult_rate = self.adult_fare_rate if self.adult_fare_rate is not None else Decimal('0.00')
        child_rate = self.child_fare_rate if self.child_fare_rate is not None else Decimal('0.00')
        adult_total = self.adult_passengers * adult_rate
        child_total = self.child_passengers * child_rate
        return adult_total + child_total

    def __str__(self):
        return f"{self.get_booking_type_display()} Booking {self.booking_reference} - {self.full_name}"

    def save(self, *args, **kwargs):
        self.total_fare = self.calculate_total_fare()
        super().save(*args, **kwargs)

        if not self.qr_code:
            self.qr_code = self.generate_qr_code()
            super().save(update_fields=['qr_code'])

    def generate_booking_reference(self):
        return str(uuid.uuid4()).split('-')[0].upper()

    def generate_qr_code(self):
    # Create a QR code image
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(self.booking_reference)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        # Create a file-like object to save the image to
        from io import BytesIO
        from django.core.files.uploadedfile import InMemoryUploadedFile
        import sys

        # Save image to buffer
        buffer = BytesIO()
        img.save(buffer, format='PNG')

        # Create a Django file from the buffer
        file_name = f"{self.booking_reference}.png"
        file_size = buffer.tell()
        buffer.seek(0)

        # Create a Django file object and return it
        return InMemoryUploadedFile(
            buffer,
            None,
            file_name,
            'image/png',
            file_size,
            None
        )
    @property
    def total_amount(self):
        if self.booking_type == 'passenger':
            return (self.adult_passengers * self.adult_fare_rate) + (self.child_passengers * self.child_fare_rate)
        elif self.booking_type == 'vehicle':
            # Only return the base fare for vehicles
            return self.vehicle_type.base_fare if self.vehicle_type else Decimal('0.00')
        return Decimal('0.00')

# --------------------------------
# 4. PAYMENT
# --------------------------------

class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('gcash', 'GCash'),

    ]

    booking = models.ForeignKey('Booking', on_delete=models.CASCADE)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    amount_received = models.DecimalField(max_digits=10, decimal_places=2)
    change_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(
        max_length=50,
        choices=PAYMENT_METHOD_CHOICES,
        default='cash'
    )
    payment_date = models.DateTimeField(auto_now_add=True)
    payment_reference = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f"Payment {self.payment_reference} - {self.get_payment_method_display()}"

# --------------------------------
# 5. REPORTING
# --------------------------------

class Report(models.Model):
    REPORT_TYPE_CHOICES = [
        ('passenger', 'Passenger Report'),
        ('cargo', 'Cargo Report'),
        ('sales', 'Sales Report'),
    ]
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    generated_at = models.DateTimeField(auto_now_add=True)
    details = models.TextField()

    def __str__(self):
        return f"{self.get_report_type_display()} - {self.generated_at.strftime('%Y-%m-%d %H:%M')}"

# --------------------------------
# 6. RATINGS & FEEDBACK
# --------------------------------

class Rating(models.Model):
    vessel = models.ForeignKey(Vessel, on_delete=models.CASCADE)
    rating = models.IntegerField(choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5')])
    comment = models.TextField(blank=True, null=True)
    full_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=False)  # Add this field for moderation
    user = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)  # Add this field to track user ratings

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.full_name}'s {self.rating}-star rating for {self.vessel.name}"

# --------------------------------
# 7. TEMPLATE-BASED NOTIFICATIONS
# --------------------------------

class Notification(models.Model):
    """
    A template-based notification that can be displayed as a 'card' in your frontend.
    The `template` field determines which card layout to use in your templates.
    `context` holds dynamic data (JSON) you can display in the card.
    """
    NOTIFICATION_TEMPLATES = [
        ('booking_confirm', 'Booking Confirmation'),
        ('payment_received', 'Payment Received'),
        ('trip_canceled', 'Trip Canceled'),
        ('general_alert', 'General Alert'),
    ]
    template = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TEMPLATES
    )
    context = models.TextField(
        blank=True,
        null=True,
        help_text="Dynamic data to display in the card template (JSON string)"
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_template_display()} - {self.created_at}"

# --------------------------------
# 8. TRAVEL GUIDELINES
# --------------------------------

class TravelGuideline(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    effective_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Message from {self.name} ({self.created_at.strftime('%Y-%m-%d')})"
