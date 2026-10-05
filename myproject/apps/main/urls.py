
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    # Home & Registration (The 'Hub')
    path('', views.home, name='home'),

    # Authentication - Django built-in style
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Role-based Dashboards
    # Note: Changed 'donation_page' to 'donor_dashboard' for consistency
    path('donor/', views.donor_dashboard, name='donor_dashboard'),
    
    # NGO / Receiver View
    path('receiver/', views.donation_page, name='receiver_dashboard'),
    
    # Volunteer View
    path('volunteer/', views.volunteer_dashboard, name='volunteer_dashboard'),

    # Actions & AJAX
    path('donor/create-food/', views.create_food_donation, name='create_food_donation'),
    path('accept-donation/', views.accept_donation, name='accept_donation'),
    path('volunteer/accept-delivery/', views.volunteer_accept_delivery,    name='volunteer_accept_delivery'),
    
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)