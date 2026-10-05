from django.contrib import admin
from .models import Volunteer, NGO, Donor, Food

admin.site.register(Donor)
admin.site.register(Volunteer)
admin.site.register(NGO)

@admin.register(Food)
class FoodAdmin(admin.ModelAdmin):
    list_display = ('donor', 'food_quantity', 'status', 'created_at', 'expiry_hours')
    list_filter = ('status', 'created_at')
    search_fields = ('donor__organization_name', 'food_quantity')
