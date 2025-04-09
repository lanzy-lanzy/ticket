from django.urls import path
from . import views

urlpatterns = [
    # Authentication URLs
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    # API endpoints
    path('api/schedules/<int:schedule_id>/fares/', views.get_schedule_fares, name='get_schedule_fares'),
    # Add this URL pattern
    path('tickets/generate/<str:booking_reference>/', views.print_ticket, name='print_ticket'),

    # Existing URL patterns
    path('', views.home, name='home'),
    path('booking/', views.booking, name='booking'),
    path('payment/complete/<str:booking_reference>/', views.mark_payment_complete, name='mark_payment_complete'),
    path('booking-confirmation/<str:booking_reference>/', views.booking_confirmation, name='booking_confirmation'),
    path('schedules/', views.schedules_view, name='schedules'),
    path('guidelines/', views.guidelines_view, name='guidelines'),
    path('contact/', views.contact_view, name='contact'),
    path('routes/', views.routes_view, name='routes'),
    # Add this to your urlpatterns
    # path('api/booking-details/<str:booking_reference>/', views.booking_details_api, name='booking_details_api'),
    path('dashboard/', views.dashboard_home, name='dashboard'),
    path('dashboard/vessels/', views.vessel_list, name='vessels'),
    path('dashboard/schedules/', views.schedule_list, name='dashboard_schedules'),
    path('dashboard/bookings/', views.booking_list, name='booking_list'),
    path('dashboard/bookings/create/', views.booking_create, name='booking_create'),
    path('dashboard/payments/', views.payment_list, name='payments'),
    path('dashboard/reports/', views.reports_view, name='reports'),
    path('dashboard/reports/export/', views.export_report, name='export_report'),
    path('dashboard/ratings/', views.ratings_dashboard, name='ratings_dashboard'),
    path('dashboard/ratings/approve/<int:rating_id>/', views.approve_rating, name='approve_rating'),
    path('ratings/<int:rating_id>/details/', views.rating_details, name='rating_details'),
    path('dashboard/ratings/add/', views.add_rating, name='add_rating'),
    path('dashboard/routes/', views.route_list, name='route_list'),
    path('dashboard/routes/add/', views.add_route, name='add_route'),
    path('dashboard/routes/edit/<int:pk>/', views.edit_route, name='edit_route'),
    path('dashboard/routes/delete/<int:pk>/', views.delete_route, name='delete_route'),
    path('ratings/', views.ratings, name='ratings'),
    path('dashboard/bookings/<int:pk>/view/', views.booking_view, name='booking_view'),
    path('dashboard/bookings/<int:pk>/mark-paid/', views.booking_mark_paid, name='booking_mark_paid'),
    path('dashboard/bookings/<int:pk>/print/', views.booking_print, name='booking_print'),
     path('vessels/get/', views.get_vessels, name='get_vessels'),
    path('routes/get/', views.get_routes, name='get_routes'),
    path('vessels/<int:vessel_id>/capacity/', views.get_vessel_capacity, name='get_vessel_capacity'),
    path('dashboard/schedules/<int:schedule_id>/get/', views.get_schedule, name='get_schedule'),
    path('dashboard/schedules/<int:schedule_id>/edit/', views.edit_schedule, name='edit_schedule'),
    # API endpoints
    path('api/add-vessel/', views.add_vessel, name='add_vessel'),
    path('api/add-schedule/', views.add_schedule, name='add_schedule'),

    path('api/delete-schedule/<int:pk>/', views.schedule_delete, name='delete_schedule'),
    # path('api/get-schedule/<int:pk>/', views.get_schedule, name='get_schedule'),
    path('api/get-vessel-capacity/<int:vessel_id>/', views.get_vessel_capacity, name='get_vessel_capacity'),

    path('generate-qr-code/<str:booking_reference>/', views.generate_qr_code, name='generate_qr_code'),
    path('api/booking-details/<str:booking_reference>/', views.get_booking_details, name='get_booking_details'),
    # path('process-payment/', views.process_payment, name='process_payment'),
    path('booking/create/', views.create_booking, name='create_booking'),
    path('payment/<str:booking_reference>/', views.payment_view, name='payment'),
    path('api/booking-details-html/', views.booking_details_html, name='booking_details_html'),
    path('api/process-payment/', views.process_payment_htmx, name='process_payment_htmx'),
    path('dashboard/bookings/<int:booking_id>/detail/', views.booking_detail, name='booking_detail'),
    path('dashboard/bookings/<int:booking_id>/delete/', views.booking_delete, name='booking_delete'),
    path('api/schedules/<int:schedule_id>/fares/', views.get_schedule_fares, name='get_schedule_fares'),
     path('payment/details/<str:booking_reference>/', views.get_payment_details, name='get_payment_details'),
    path('calculate-fare/', views.calculate_fare, name='calculate_fare'),

    # Vessel management URLs
    path('dashboard/vessels/', views.vessel_list, name='vessel_list'),
    path('dashboard/vessels/add/', views.add_vessel, name='add_vessel'),
    path('vessels/<int:vessel_id>/edit/', views.edit_vessel, name='edit_vessel'),
    path('vessels/<int:vessel_id>/delete/', views.delete_vessel, name='delete_vessel'),
    path('dashboard/vessels/toggle-status/<int:vessel_id>/', views.toggle_vessel_status, name='toggle_vessel_status'),
    path('routes/get/', views.get_routes, name='get_routes'),
    path('dashboard/schedules/<int:schedule_id>/get/', views.get_schedule, name='get_schedule'),
    path('calculate-change/', views.calculate_change, name='calculate_change'),


    path('vehicle-types/add/', views.add_vehicle_type, name='add_vehicle_type'),
    path('vehicle-types/<int:id>/update/', views.update_vehicle_type, name='update_vehicle_type'),
    path('vehicle-types/<int:id>/delete/', views.delete_vehicle_type, name='delete_vehicle_type'),
    path('vehicle-types/<int:id>/', views.get_vehicle_type, name='get_vehicle_type'),

    path('vehicle-types/', views.vehicle_types_view, name='vehicle_types'),
    path('vehicle-types/get/', views.get_vehicle_types, name='get_vehicle_types'),

    path('calculate-vehicle-fare/', views.calculate_vehicle_fare, name='calculate_vehicle_fare'),
    path('calculate-fare/', views.calculate_fare, name='calculate_fare'),
    path('get-schedule-fares/<int:schedule_id>/', views.get_schedule_fares, name='get_schedule_fares'),
    path('notifications/', views.get_notifications, name='get_notifications'),
    path('dashboard/routes/<int:pk>/', views.get_route, name='get_route'),
    path('dashboard/routes/<int:pk>/edit/', views.edit_route, name='edit_route'),
    path('dashboard/routes/<int:pk>/delete/', views.delete_route, name='delete_route'),
 
    path('dashboard/schedules/<int:pk>/delete/', views.schedule_delete, name='schedule_delete'),
   
    path('dashboard/schedules/<int:schedule_id>/get/', views.get_schedule, name='get_schedule'),
    path('ratings/submit/', views.submit_rating, name='submit_rating'),
    path('ratings/<int:rating_id>/details/', views.rating_details, name='rating_details'),
]
