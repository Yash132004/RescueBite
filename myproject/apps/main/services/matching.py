"""Geo-matching helpers shared by the views.

The implementation of :func:`calculate_distance` was previously inlined in
``apps.main.views``. It lives here so that distance maths has a single home;
the formula and its inputs/outputs are unchanged.
"""
import math

from ..models import NGO

EARTH_RADIUS_KM = 6371.0


def calculate_distance(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two points.

    Arguments are coerced with ``float()`` so that ``Decimal`` model fields and
    string query values are both accepted. Returns a float.
    """
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))

    a = math.sin(dphi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(dlambda / 2.0) ** 2

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def haversine(lat1, lon1, lat2, lon2):
    """Backward-compatible name for the great-circle distance helper."""
    return calculate_distance(lat1, lon1, lat2, lon2)


def find_nearest_receiver(donor):
    """Return the nearest NGO and its distance from a donor.

    The NGO claim workflow remains manual; this helper is kept for existing
    callers that use the matching service directly.
    """
    nearest = None
    minimum_distance = float('inf')

    for receiver in NGO.objects.all():
        distance = calculate_distance(
            donor.latitude,
            donor.longitude,
            receiver.latitude,
            receiver.longitude,
        )
        if distance < minimum_distance:
            nearest = receiver
            minimum_distance = distance

    return nearest, minimum_distance
