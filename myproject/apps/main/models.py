from datetime import timedelta

from django.db import models
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.contrib.auth.models import User


def hash_password_once(password):
    """Hash a plaintext password, leaving an already-hashed value untouched.

    Shared by the two models that store a hashed password on the profile
    instead of relying on the auth User.
    """
    if password.startswith('pbkdf2_'):
        return password
    return make_password(password)


# ---------------- VOLUNTEER ----------------
class Volunteer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    username = models.CharField(max_length=100, unique=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15)

    password = models.CharField(max_length=128)

    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.password = hash_password_once(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username


# ---------------- DONOR ----------------
class Donor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    organization_name = models.CharField(max_length=150)
    contact = models.CharField(max_length=15)
    email = models.EmailField(unique=True)

    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.organization_name


# ---------------- RECEIVER (NGO) ----------------
class NGO(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    organization_name = models.CharField(max_length=150)
    contact = models.CharField(max_length=15)
    email = models.EmailField(unique=True)

    password = models.CharField(max_length=128)

    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.password = hash_password_once(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.organization_name


# ---------------- FOOD DONATION ----------------
class Food(models.Model):
    donor = models.ForeignKey(
        'Donor',
        on_delete=models.CASCADE,
        related_name='donated_foods'
    )
    name = models.CharField(max_length=255)
    food_quantity = models.CharField(
        max_length=255,
        help_text="Example: 50 plates, 10 kg rice, 20 boxes of biryani..."
    )

    description = models.TextField(
        blank=True,
        help_text="Additional details (veg/non-veg, allergens, etc.)"
    )

    expiry_hours = models.PositiveIntegerField(
        default=24,
        help_text="Hours until this food expires"
    )

    image = models.ImageField(
        upload_to='food_donations/%Y/%m/%d/',
        blank=True,
        null=True
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ("AVAILABLE", "Available for pickup"),
            ("PENDING", "Pickup requested"),
            ("ASSIGNED", "Assigned to NGO/Volunteer"),
            # Set by main.views.volunteer_accept_delivery when a volunteer
            # takes the delivery. It was already being written by the app
            # (and already present in the database) but was missing here, so
            # the admin/form choices did not list it.
            ("IN_TRANSIT", "Picked up by volunteer - in transit"),
            ("RECEIVED", "Successfully received"),
            ("EXPIRED", "Expired - not collected"),
            ("CANCELLED", "Cancelled by donor"),
        ],
        default="AVAILABLE"
    )

    assigned_ngo = models.ForeignKey(
        'NGO',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_foods'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Optional: different pickup location
    pickup_latitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True
    )
    pickup_longitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True
    )
    closest_distance_km = models.FloatField(null=True, blank=True)

    priority_expires_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Time until only closest NGO can see this donation"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Food Donation"
        verbose_name_plural = "Food Donations"

    def __str__(self):
        return f"{self.donor.organization_name} - {self.food_quantity} ({self.status})"

    def is_expired(self):
        expiry_time = self.created_at + timedelta(hours=self.expiry_hours)
        return timezone.now() > expiry_time