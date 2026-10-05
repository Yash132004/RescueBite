import math
from datetime import timedelta
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import models

from .forms import VolunteerForm, NGOForm, DonorForm, FoodDonationForm
from .models import Donor, Volunteer, NGO, Food


# -------------------- DISTANCE FUNCTION --------------------

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))

    a = math.sin(dphi / 2.0)**2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(dlambda / 2.0)**2

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# -------------------- HOME --------------------

def home(request):
    vol_form = VolunteerForm()
    ngo_form = NGOForm()
    donor_form = DonorForm()

    # --- NEW: CALCULATE IMPACT STATS ---
    now = timezone.now()
    # Get the first day of the current month
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Count total donations vs donations this month
    total_donations = Food.objects.count()
    monthly_donations = Food.objects.filter(created_at__gte=start_of_month).count()

    if request.method == "POST":
        # Determine which form was submitted
        if 'volunteer_submit' in request.POST:
            form = VolunteerForm(request.POST, request.FILES)
            role = 'volunteer'
        elif 'ngo_submit' in request.POST:
            form = NGOForm(request.POST, request.FILES)
            role = 'ngo'
        elif 'donor_submit' in request.POST:
            form = DonorForm(request.POST, request.FILES)
            role = 'donor'
        else:
            form = None

        if form and form.is_valid():
            email = form.cleaned_data.get('email')
            password = form.cleaned_data.get('password')

            # Safety check: Prevent duplicate username error
            if User.objects.filter(username=email).exists():
                messages.error(request, "This email is already registered. Please login.")
                return redirect('login')
            
            # 1. Create the Auth User
            new_user = User.objects.create_user(username=email, email=email, password=password)
            
            # 2. Save the Profile
            profile = form.save(commit=False)
            profile.user = new_user
            profile.save()

            # 3. Log the user in automatically
            login(request, new_user)
            
            # Set session data
            request.session['role'] = role
            request.session['user_id'] = profile.id 

            messages.success(request, f"Registered and logged in as {role}!")
            
            # Redirect to the specific dashboard
            if role == 'volunteer':
                return redirect('volunteer_dashboard')
            elif role == 'ngo':
                return redirect('receiver_dashboard')
            else:
                return redirect('donor_dashboard')

    # Pass the counts to the template
    return render(request, 'home.html', {
        'vol_form': vol_form, 
        'ngo_form': ngo_form, 
        'donor_form': donor_form,
        'total_donations': total_donations,
        'monthly_donations': monthly_donations
    })

# -------------------- CREATE FOOD DONATION (DONOR) --------------------

@login_required(login_url='login')
def create_food_donation(request):
    # Check if the logged-in user is actually a donor
    if not hasattr(request.user, 'donor'):
        messages.error(request, "Access Denied: You are not a Donor.")
        return redirect('home')

    donor = request.user.donor # Using the OneToOne link directly

    if request.method == 'POST':
        form = FoodDonationForm(request.POST, request.FILES)
        if form.is_valid():
            food = form.save(commit=False)
            food.donor = donor
            food.status = "AVAILABLE"
            food.save()
            messages.success(request, "Food donation added successfully!")
            return redirect('donor_dashboard')
    else:
        form = FoodDonationForm()

    return render(request, 'donor.html', {'form': form, 'donor': donor})

# -------------------- NGO DASHBOARD --------------------
@login_required(login_url='login')
def donation_page(request):
    if not hasattr(request.user, 'ngo'):
        messages.error(request, "You are not an NGO.")
        return redirect('login')

    ngo = request.user.ngo
    now = timezone.now()

    foods = Food.objects.filter(
    status__in=["AVAILABLE", "PENDING"]
    ).filter(
    models.Q(priority_expires_at__isnull=True) |   # allow new donations
    models.Q(priority_expires_at__lte=now) |
    models.Q(assigned_ngo=ngo)
    )


    return render(request, 'receiver.html', {
        'foods': foods,
        'ngo': ngo
    })

# -------------------- ACCEPT DONATION --------------------

@require_POST
@login_required
def accept_donation(request):

    # Proper role check
    if not hasattr(request.user, 'ngo'):
        return JsonResponse({
            'success': False,
            'error': 'Only NGOs can claim donations'
        }, status=403)

    data = json.loads(request.body)
    food_id = data.get('food_id')

    food = get_object_or_404(Food, id=food_id)

    if food.status not in ["AVAILABLE", "PENDING"]:
        return JsonResponse({'success': False, 'error': 'Already taken'}, status=400)

    ngo = request.user.ngo

    # Priority window check
    if food.priority_expires_at and timezone.now() < food.priority_expires_at:
        if food.assigned_ngo != ngo:
            return JsonResponse({
                'success': False,
                'error': 'This donation is reserved for another NGO right now.'
            }, status=403)

    # Assign donation
    food.status = "ASSIGNED"
    food.assigned_ngo = ngo
    food.save()

    return JsonResponse({
        'success': True,
        'message': f'Donation assigned to {ngo.organization_name}'
    })



# -------------------- LOGIN --------------------

def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, username=email, password=password)

        if user is not None:
            login(request, user)

            if hasattr(user, 'volunteer'):
                return redirect('volunteer_dashboard')
            elif hasattr(user, 'donor'):
                return redirect('donor_dashboard')
            elif hasattr(user, 'ngo'):
                return redirect('receiver_dashboard')
            else:
                messages.error(request, "No role profile found for this user.")
                return redirect('login')
        else:
            messages.error(request, "Invalid email or password.")

    return render(request, "login.html")


# -------------------- LOGOUT --------------------

def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('login')


# -------------------- VOLUNTEER DASHBOARD --------------------
@login_required(login_url='login')
def volunteer_dashboard(request):
    if not hasattr(request.user, 'volunteer'):
        messages.error(request, "You are not a Volunteer.")
        return redirect('login')

    volunteer = request.user.volunteer

    #  NEW: Get only assigned deliveries with coordinates
    assigned_tasks = Food.objects.filter(
        status="ASSIGNED",
        assigned_ngo__isnull=False
    ).select_related('donor', 'assigned_ngo')

    return render(request, 'volunteer.html', {
        'volunteer': volunteer,
        'assigned_tasks': assigned_tasks,   #  IMPORTANT: name must match template
    })


# -------------------- DONOR DASHBOARD --------------------
@login_required(login_url='login')
def donor_dashboard(request):
    if not hasattr(request.user, 'donor'):
        messages.error(request, "You are not a Donor.")
        return redirect('login')

    donor = request.user.donor

    # Get all foods for this donor with specific statuses
    my_foods = Food.objects.filter(
        donor=donor,
        status__in=["AVAILABLE", "PENDING"]
    ).select_related('assigned_ngo').order_by('-created_at')

    # Calculate distance if NGO is assigned
    for food in my_foods:
        if food.assigned_ngo:
            food.closest_distance_km = round(
                calculate_distance(
                    food.donor.latitude,
                    food.donor.longitude,
                    food.assigned_ngo.latitude,
                    food.assigned_ngo.longitude
                ), 2
            )
        else:
            food.closest_distance_km = None

    # ------------------- NEW: Stats -------------------
    from django.utils import timezone
    now = timezone.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_donations = Food.objects.filter(donor=donor).count()
    monthly_donations = Food.objects.filter(donor=donor, created_at__gte=start_of_month).count()
    # ---------------------------------------------------

    return render(request, 'donor.html', {
        'donor': donor,
        'my_foods': my_foods,
        'total_donations': total_donations,
        'monthly_donations': monthly_donations
    })

@require_POST
@login_required
def volunteer_accept_delivery(request):
    if not hasattr(request.user, 'volunteer'):
        return JsonResponse({
            'success': False,
            'error': 'Only volunteers can accept deliveries'
        }, status=403)

    data = json.loads(request.body)
    food_id = data.get('food_id')

    food = get_object_or_404(Food, id=food_id)

    # Only allow accepting if currently assigned to an NGO
    if food.status != "ASSIGNED":
        return JsonResponse({
            'success': False,
            'error': 'This delivery is not available for pickup'
        }, status=400)

    #KEY CHANGE: Move to in-transit
    food.status = "IN_TRANSIT"
    food.save()

    return JsonResponse({
        'success': True,
        'message': 'Delivery accepted by volunteer'
    })
