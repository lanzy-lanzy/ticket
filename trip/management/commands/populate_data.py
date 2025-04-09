from django.core.management.base import BaseCommand
import random
from datetime import timedelta
from django.utils import timezone

from trip.models import Vessel, Schedule, VehicleType, Booking, Rating, Payment, Route

class Command(BaseCommand):
    help = 'Populates the database with sample data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before populating',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write(self.style.WARNING('Clearing existing data...'))
            # Clear in reverse order to avoid foreign key constraints
            Payment.objects.all().delete()
            Rating.objects.all().delete()
            Booking.objects.all().delete()
            Schedule.objects.all().delete()
            Route.objects.all().delete()
            VehicleType.objects.all().delete()
            Vessel.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Data cleared successfully!'))

        self.stdout.write(self.style.NOTICE('Starting database population...'))
        
        # Create base data
        vessels = self.create_vessels()
        vehicle_types = self.create_vehicle_types()
        routes = self.create_routes()
        
        # Create dependent data
        schedules = self.create_schedules(vessels, routes)
        bookings = self.create_bookings(schedules, vehicle_types)
        
        # Create additional data
        ratings = self.create_ratings(vessels)
        payments = self.create_payments(bookings)
        
        self.stdout.write(self.style.SUCCESS('\nDatabase population completed!'))
        self.stdout.write(f"Created {len(vessels)} vessels")
        self.stdout.write(f"Created {len(vehicle_types)} vehicle types")
        self.stdout.write(f"Created {len(routes)} routes")
        self.stdout.write(f"Created {len(schedules)} schedules")
        self.stdout.write(f"Created {len(bookings)} bookings")
        self.stdout.write(f"Created {len(ratings)} ratings")
        self.stdout.write(f"Created {len(payments)} payments")

    def create_vessels(self):
        """Create sample vessels"""
        self.stdout.write('Creating vessels...')
        vessels_data = [
            {
                'name': 'Ocean Explorer',
                'capacity_passengers': 250,
                'capacity_cargo': 50.0,
                'active': True
            },
            {
                'name': 'Island Hopper',
                'capacity_passengers': 150,
                'capacity_cargo': 30.0,
                'active': True
            },
            {
                'name': 'Coastal Voyager',
                'capacity_passengers': 200,
                'capacity_cargo': 40.0,
                'active': True
            },
            {
                'name': 'Sea Breeze',
                'capacity_passengers': 180,
                'capacity_cargo': 35.0,
                'active': True
            },
            {
                'name': 'Maritime Express',
                'capacity_passengers': 300,
                'capacity_cargo': 60.0,
                'active': False
            }
        ]
        
        created_vessels = []
        for data in vessels_data:
            vessel, created = Vessel.objects.get_or_create(
                name=data['name'],
                defaults={
                    'capacity_passengers': data['capacity_passengers'],
                    'capacity_cargo': data['capacity_cargo'],
                    'active': data['active']
                }
            )
            if created:
                self.stdout.write(f"  Created vessel: {vessel.name}")
            created_vessels.append(vessel)
        
        return created_vessels

    def create_vehicle_types(self):
        """Create sample vehicle types"""
        self.stdout.write('Creating vehicle types...')
        vehicle_types_data = [
            {
                'name': 'Motorcycle',
                'max_occupants': 2,
                'max_cargo_weight': 0.1
            },
            {
                'name': 'Sedan',
                'max_occupants': 5,
                'max_cargo_weight': 0.5
            },
            {
                'name': 'SUV',
                'max_occupants': 7,
                'max_cargo_weight': 1.0
            },
            {
                'name': 'Van',
                'max_occupants': 12,
                'max_cargo_weight': 1.5
            },
            {
                'name': 'Truck',
                'max_occupants': 3,
                'max_cargo_weight': 5.0
            }
        ]
        
        created_types = []
        for data in vehicle_types_data:
            vehicle_type, created = VehicleType.objects.get_or_create(
                name=data['name'],
                defaults={
                    'max_occupants': data['max_occupants'],
                    'max_cargo_weight': data['max_cargo_weight']
                }
            )
            if created:
                self.stdout.write(f"  Created vehicle type: {vehicle_type.name}")
            created_types.append(vehicle_type)
        
        return created_types

    def create_routes(self):
        """Create sample routes"""
        self.stdout.write('Creating routes...')
        routes_data = [
            {
                'name': 'Main Island to North Island',
                'origin': 'Main Island Port',
                'destination': 'North Island Harbor',
                'distance': 45.5,
                'estimated_duration': timedelta(hours=2, minutes=30),
                'active': True,
                'description': 'Regular route connecting the main island to the northern island.'
            },
            {
                'name': 'Main Island to South Island',
                'origin': 'Main Island Port',
                'destination': 'South Island Marina',
                'distance': 38.2,
                'estimated_duration': timedelta(hours=2, minutes=15),
                'active': True,
                'description': 'Popular route for tourists visiting the southern beaches.'
            },
            {
                'name': 'Main Island to East Island',
                'origin': 'Main Island Port',
                'destination': 'East Island Dock',
                'distance': 52.7,
                'estimated_duration': timedelta(hours=3),
                'active': True,
                'description': 'Scenic route with views of coral reefs and marine life.'
            },
            {
                'name': 'North Island to East Island',
                'origin': 'North Island Harbor',
                'destination': 'East Island Dock',
                'distance': 35.8,
                'estimated_duration': timedelta(hours=1, minutes=45),
                'active': True,
                'description': 'Direct connection between the northern and eastern islands.'
            },
            {
                'name': 'South Island to West Island',
                'origin': 'South Island Marina',
                'destination': 'West Island Port',
                'distance': 42.3,
                'estimated_duration': timedelta(hours=2, minutes=15),
                'active': False,
                'description': 'Seasonal route operating during summer months only.'
            }
        ]
        
        created_routes = []
        for data in routes_data:
            route, created = Route.objects.get_or_create(
                name=data['name'],
                defaults={
                    'origin': data['origin'],
                    'destination': data['destination'],
                    'distance': data['distance'],
                    'estimated_duration': data['estimated_duration'],
                    'active': data['active'],
                    'description': data['description']
                }
            )
            if created:
                self.stdout.write(f"  Created route: {route.name}")
            created_routes.append(route)
        
        return created_routes

    def create_schedules(self, vessels, routes):
        """Create sample schedules for the next 30 days"""
        self.stdout.write('Creating schedules...')
        now = timezone.now()
        schedules = []
        
        # Create 3 schedules per day for the next 30 days
        for day in range(30):
            for vessel in random.sample(vessels, min(3, len(vessels))):
                route = random.choice(routes)
                departure_time = now + timedelta(days=day, hours=random.randint(6, 18))
                # Use route's estimated duration to calculate arrival time
                arrival_time = departure_time + route.estimated_duration
                
                status = 'scheduled'
                if day < 5:  # Some past schedules
                    if random.random() < 0.3:
                        status = 'completed'
                    elif random.random() < 0.1:
                        status = 'canceled'
                
                schedule = Schedule.objects.create(
                    vessel=vessel,
                    route=route,
                    departure_datetime=departure_time,
                    arrival_datetime=arrival_time,
                    available_seats=int(vessel.capacity_passengers * 0.8),  # 80% of capacity
                    available_cargo_space=vessel.capacity_cargo * 0.8,  # 80% of capacity
                    status=status,
                    notes=f"Regular service from {route.origin} to {route.destination} on {departure_time.strftime('%Y-%m-%d')}"
                )
                
                schedules.append(schedule)
            
            if day % 5 == 0:
                self.stdout.write(f"  Created schedules for day {day+1}")
        
        return schedules

    def create_bookings(self, schedules, vehicle_types):
        """Create sample bookings"""
        self.stdout.write('Creating bookings...')
        first_names = ['John', 'Jane', 'Michael', 'Emily', 'David', 'Sarah', 'Robert', 'Lisa', 'William', 'Maria']
        last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
        domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'example.com']
        
        bookings = []
        
        # Create 50 random bookings
        for i in range(50):
            full_name = f"{random.choice(first_names)} {random.choice(last_names)}"
            email = f"{full_name.lower().replace(' ', '.')}{random.randint(1, 100)}@{random.choice(domains)}"
            contact_number = f"+1{random.randint(2000000000, 9999999999)}"
            
            # 70% passenger bookings, 30% vehicle bookings
            booking_type = 'passenger' if random.random() < 0.7 else 'vehicle'
            
            schedule = random.choice(schedules)
            
            booking_data = {
                'booking_type': booking_type,
                'full_name': full_name,
                'contact_number': contact_number,
                'email': email,
                'schedule': schedule,
                'is_paid': random.random() < 0.8,  # 80% are paid
                'number_of_passengers': random.randint(1, 5),
                'cargo_weight': round(random.uniform(0, 0.5), 2)
            }
            
            if booking_type == 'vehicle':
                vehicle_type = random.choice(vehicle_types)
                booking_data.update({
                    'vehicle_type': vehicle_type,
                    'plate_number': f"{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.randint(100, 999)}",
                    'occupant_count': random.randint(1, vehicle_type.max_occupants),
                    'cargo_weight': round(random.uniform(0, vehicle_type.max_cargo_weight), 2)
                })
            
            booking = Booking.objects.create(**booking_data)
            bookings.append(booking)
            
            if i % 10 == 0:
                self.stdout.write(f"  Created {i+1} bookings")
        
        return bookings

    def create_ratings(self, vessels):
        """Create sample ratings/testimonials"""
        self.stdout.write('Creating ratings...')
        comments = [
            "Great service! The staff was very friendly and helpful.",
            "The vessel was clean and comfortable. Will definitely travel again.",
            "On-time departure and arrival. Very professional crew.",
            "Excellent experience overall. Highly recommended.",
            "The journey was smooth and enjoyable.",
            "Good value for money. Satisfied with the service.",
            "The facilities on board were excellent.",
            "Very organized boarding process. No delays.",
            "The crew was attentive to passengers' needs.",
            "Comfortable seating and good amenities."
        ]
        
        first_names = ['Alex', 'Taylor', 'Jordan', 'Casey', 'Morgan', 'Riley', 'Jamie', 'Quinn', 'Avery', 'Cameron']
        last_names = ['Wilson', 'Thompson', 'Anderson', 'Thomas', 'Jackson', 'White', 'Harris', 'Martin', 'Clark', 'Lewis']
        
        ratings = []
        
        # Create 30 random ratings
        for i in range(30):
            full_name = f"{random.choice(first_names)} {random.choice(last_names)}"
            vessel = random.choice(vessels)
            rating_value = random.randint(3, 5)  # Mostly positive ratings (3-5 stars)
            comment = random.choice(comments)
            
            # Create rating with a date within the last 3 months
            created_date = timezone.now() - timedelta(days=random.randint(0, 90))
            
            rating = Rating.objects.create(
                full_name=full_name,
                vessel=vessel,
                rating=rating_value,
                comment=comment,
                created_at=created_date
            )
            
            ratings.append(rating)
            
            if i % 10 == 0:
                self.stdout.write(f"  Created {i+1} ratings")
        
        return ratings

    def create_payments(self, bookings):
        """Create sample payments for paid bookings"""
        self.stdout.write('Creating payments...')
        payment_methods = ['cash', 'credit_card', 'online']
        
        payments = []
        count = 0
        
        for booking in bookings:
            if booking.is_paid:
                # Calculate payment amount based on booking type
                if booking.booking_type == 'passenger':
                    amount = 50 * booking.number_of_passengers  # $50 per passenger
                else:  # vehicle
                    base_price = 100  # Base price for vehicle
                    amount = base_price + (20 * booking.occupant_count)  # $20 per occupant
                
                # Add random amount for cargo
                amount += booking.cargo_weight * 30  # $30 per ton
                
                payment = Payment.objects.create(
                    booking=booking,
                    amount_paid=round(amount, 2),
                    payment_method=random.choice(payment_methods)
                )
                
                payments.append(payment)
                count += 1
                
                if count % 10 == 0:
                    self.stdout.write(f"  Created {count} payments")
        
        return payments
