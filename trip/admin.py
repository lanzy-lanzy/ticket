from django.contrib import admin
from .models import Rating

@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ['user', 'vessel', 'rating', 'created_at', 'is_approved']
    list_filter = ['is_approved', 'rating', 'vessel']
    search_fields = ['user__username', 'user__email', 'vessel__name', 'comment']
    actions = ['approve_ratings', 'unapprove_ratings']
    
    def approve_ratings(self, request, queryset):
        queryset.update(is_approved=True)
    approve_ratings.short_description = "Approve selected ratings"
    
    def unapprove_ratings(self, request, queryset):
        queryset.update(is_approved=False)
    unapprove_ratings.short_description = "Unapprove selected ratings"
