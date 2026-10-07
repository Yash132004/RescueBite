import json

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import IntegrityError, models, transaction
from django.db.models import Q

from .forms import VolunteerForm, NGOForm, DonorForm, FoodDonationForm
from .models import Donor, Food, NGO, Volunteer
from .services.matching import calculate_distance

# -------------------- SHARED HELPERS --------------------


def start_of_current_month():
    """First instant of the current month, used by the impact counters."""
    now = timezone.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def donation_stats(queryset):
    """Return ``(total_donations, donations_this_month)`` for a Food queryset."""
    start_of_month = start_of_current_month()
    total = queryset.count()
    monthly = queryset.filter(created_at__gte=start_of_month).count()
    return total, monthly


def donor_dashboard_context(donor):
    """Build the donor dashboard's history, open count, and impact figures."""
    my_foods = Food.objects.filter(donor=donor).select_related(
        'assigned_ngo'
    ).order_by('-created_at')
    open_food_count = Food.objects.filter(
        donor=donor,
        status__in=["AVAILABLE", "PENDING"],
    ).count()

    for food in my_foods:
        pickup_latitude = (
            food.pickup_latitude
            if food.pickup_latitude is not None
            else food.donor.latitude
        )
        pickup_longitude = (
            food.pickup_longitude
            if food.pickup_longitude is not None
            else food.donor.longitude
        )
        food.closest_distance_km = round(
            calculate_distance(
                pickup_latitude,
                pickup_longitude,
                food.assigned_ngo.latitude,
                food.assigned_ngo.longitude,
            ), 2,
        ) if food.assigned_ngo else None

    total_donations, monthly_donations = donation_stats(Food.objects.filter(donor=donor))
    return {
        'donor': donor,
        'my_foods': my_foods,
        'open_food_count': open_food_count,
        'total_donations': total_donations,
        'monthly_donations': monthly_donations,
    }


def food_from_json_body(request):
    """Return the Food referenced by ``{"food_id": ...}`` in a JSON POST body.

    Used by both AJAX endpoints so they resolve the donation identically.
    An empty body is treated as an empty object, which makes the lookup below
    raise the usual 404 instead of crashing on invalid JSON.
    """
    data = json.loads(request.body or b'{}')
    return get_object_or_404(Food, id=data.get('food_id'))


def registration_role_for(user):
    """Return a role only when the account has exactly one role profile."""
    profiles = (
        ('volunteer', Volunteer),
        ('ngo', NGO),
        ('donor', Donor),
    )
    roles = [role for role, profile_model in profiles
             if profile_model.objects.filter(user_id=user.pk).exists()]
    return roles[0] if len(roles) == 1 else None


def dashboard_for_role(role):
    return {
        'volunteer': 'volunteer_dashboard',
        'ngo': 'receiver_dashboard',
        'donor': 'donor_dashboard',
    }.get(role)


# -------------------- HOME --------------------

def home(request):
    # All three registration forms render on one page, so each needs its own
    # `id` namespace. `auto_id` scopes the generated id/for attributes only --
    # the POST field `name` attributes are unchanged, so the submission
    # contract below is identical to before.
    vol_form = VolunteerForm(auto_id='volunteer_%s')
    ngo_form = NGOForm(auto_id='ngo_%s')
    donor_form = DonorForm(auto_id='donor_%s')

    # Impact stats shown on the landing page
    total_donations, monthly_donations = donation_stats(Food.objects.all())

    form = None
    form_key = None
    role = None

    if request.method == "POST":
        # Determine which form was submitted
        if 'volunteer_submit' in request.POST:
            form = VolunteerForm(request.POST, request.FILES, auto_id='volunteer_%s')
            form_key, role = 'vol_form', 'volunteer'
        elif 'ngo_submit' in request.POST:
            form = NGOForm(request.POST, request.FILES, auto_id='ngo_%s')
            form_key, role = 'ngo_form', 'ngo'
        elif 'donor_submit' in request.POST:
            form = DonorForm(request.POST, request.FILES, auto_id='donor_%s')
            form_key, role = 'donor_form', 'donor'

        if form and form.is_valid():
            email = form.cleaned_data.get('email', '').strip().lower()
            password = form.cleaned_data.get('password')

            # User email is not unique in Django's default User model, so check
            # both account identifiers before creating a registration.
            duplicate_account = User.objects.filter(
                Q(username__iexact=email) | Q(email__iexact=email)
            ).exists()
            duplicate_profile = any(
                profile_model.objects.filter(email__iexact=email).exists()
                for profile_model in (Volunteer, NGO, Donor)
            )
            if duplicate_account or duplicate_profile:
                form.add_error('email', "This email is already registered. Please log in.")
            else:
                form.cleaned_data['email'] = email
                form.instance.email = email
                try:
                    # Keep the auth account and its role profile all-or-nothing.
                    with transaction.atomic():
                        new_user = User.objects.create_user(
                            username=email,
                            email=email,
                            password=password,
                        )
                        profile = form.save(commit=False)
                        profile.user = new_user
                        profile.save()
                except IntegrityError:
                    # Covers a duplicate created concurrently after validation.
                    form.add_error(
                        'email',
                        "This email or username is already registered. Please log in.",
                    )
                else:
                    # The chosen submit button selects the concrete ModelForm,
                    # so saving it above creates exactly that role's profile.
                    login(request, new_user)

                    # Retained for compatibility with any existing session code;
                    # login routing itself is based on the persisted profile.
                    request.session['role'] = role
                    request.session['user_id'] = profile.pk

                    messages.success(request, f"Registered and logged in as {role}!")
                    return redirect(dashboard_for_role(role))

    # Pass the counts to the template
    context = {
        'vol_form': vol_form,
        'ngo_form': ngo_form,
        'donor_form': donor_form,
        'total_donations': total_donations,
        'monthly_donations': monthly_donations,
    }

    # Re-bind the submitted form so its existing validation errors are shown on
    # the matching tab, instead of silently rendering a blank form again.
    if form is not None and form_key and form.is_bound:
        context[form_key] = form
        context['submitted_form'] = form_key

    return render(request, 'main/home.html', context)


# -------------------- CREATE FOOD DONATION (DONOR) --------------------

@login_required(login_url='login')
def create_food_donation(request):
    # Check if the logged-in user is actually a donor
    donor = getattr(request.user, 'donor', None)  # The OneToOne link directly
    if donor is None:
        messages.error(request, "Access Denied: You are not a Donor.")
        return redirect('home')

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

    context = donor_dashboard_context(donor)
    context['form'] = form
    return render(request, 'main/donor.html', context)


# -------------------- NGO DASHBOARD --------------------

@login_required(login_url='login')
def donation_page(request):
    ngo = getattr(request.user, 'ngo', None)
    if ngo is None:
        messages.error(request, "You are not an NGO.")
        return redirect('login')

    now = timezone.now()

    foods = Food.objects.filter(
        status__in=["AVAILABLE", "PENDING"]
    ).filter(
        models.Q(priority_expires_at__isnull=True) |   # allow new donations
        models.Q(priority_expires_at__lte=now) |
        models.Q(assigned_ngo=ngo)
    )
    claimed_foods = Food.objects.filter(
        assigned_ngo=ngo,
    ).select_related('donor').order_by('-updated_at')

    return render(request, 'main/receiver.html', {
        'foods': foods,
        'claimed_foods': claimed_foods,
        'ngo': ngo
    })


# -------------------- ACCEPT DONATION --------------------

@require_POST
@login_required
def accept_donation(request):

    # Proper role check
    ngo = getattr(request.user, 'ngo', None)
    if ngo is None:
        return JsonResponse({
            'success': False,
            'error': 'Only NGOs can claim donations'
        }, status=403)

    food = food_from_json_body(request)

    if food.status not in ["AVAILABLE", "PENDING"]:
        return JsonResponse({'success': False, 'error': 'Already taken'}, status=400)

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
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password")
        candidates = User.objects.filter(
            Q(username__iexact=email) | Q(email__iexact=email)
        ).order_by('pk')
        user = next((
            authenticated
            for candidate in candidates
            if (authenticated := authenticate(
                request, username=candidate.username, password=password
            )) is not None
        ), None)

        if user is None:
            messages.error(request, "Invalid email or password.")
        else:
            role = registration_role_for(user)
            destination = dashboard_for_role(role)
            if destination is None:
                messages.error(
                    request,
                    "This account does not have exactly one RescueBite role profile. Contact support.",
                )
                return redirect('login')

            login(request, user)
            return redirect(destination)

    return render(request, "main/login.html")


# -------------------- LOGOUT --------------------

def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('login')


# -------------------- VOLUNTEER DASHBOARD --------------------

@login_required(login_url='login')
def volunteer_dashboard(request):
    volunteer = getattr(request.user, 'volunteer', None)
    if volunteer is None:
        messages.error(request, "You are not a Volunteer.")
        return redirect('login')

    # Only assigned deliveries with coordinates
    assigned_tasks = list(Food.objects.filter(
        status="ASSIGNED",
        assigned_ngo__isnull=False
    ).select_related('donor', 'assigned_ngo'))

    # Read-only counters for the dashboard summary. The task list itself is
    # unchanged; these are derived from the rows already fetched above so the
    # page costs a single query.
    summary = {
        'active': len(assigned_tasks),
        'stops': len(assigned_tasks) * 2,
        'donors': len({t.donor_id for t in assigned_tasks}),
        'ngos': len({t.assigned_ngo_id for t in assigned_tasks if t.assigned_ngo_id}),
        'expiring': sum(1 for t in assigned_tasks if t.is_expired()),
    }

    return render(request, 'main/volunteer.html', {
        'volunteer': volunteer,
        'assigned_tasks': assigned_tasks,   #  IMPORTANT: name must match template
        'summary': summary,
    })


# -------------------- DONOR DASHBOARD --------------------

@login_required(login_url='login')
def donor_dashboard(request):
    donor = getattr(request.user, 'donor', None)
    if donor is None:
        messages.error(request, "You are not a Donor.")
        return redirect('login')

    return render(request, 'main/donor.html', donor_dashboard_context(donor))


# -------------------- VOLUNTEER ACCEPT DELIVERY --------------------

@require_POST
@login_required
def volunteer_accept_delivery(request):
    if getattr(request.user, 'volunteer', None) is None:
        return JsonResponse({
            'success': False,
            'error': 'Only volunteers can accept deliveries'
        }, status=403)

    food = food_from_json_body(request)

    # Only allow accepting if currently assigned to an NGO
    if food.status != "ASSIGNED":
        return JsonResponse({
            'success': False,
            'error': 'This delivery is not available for pickup'
        }, status=400)

    # Move the donation to in-transit
    food.status = "IN_TRANSIT"
    food.save()

    return JsonResponse({
        'success': True,
        'message': 'Delivery accepted by volunteer'
    })
