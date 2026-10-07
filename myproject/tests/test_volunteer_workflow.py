from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.main.models import Donor, Food, NGO, Volunteer


class VolunteerWorkflowTests(TestCase):
    def test_incomplete_legacy_pickup_coordinates_fall_back_as_a_pair(self):
        donor_user = User.objects.create_user(
            username='map-donor@example.test',
            email='map-donor@example.test',
            password='DonorPass!23456',
        )
        donor = Donor.objects.create(
            user=donor_user,
            organization_name='Map Donor',
            contact='1234567890',
            email='map-donor@example.test',
            latitude='19.000000',
            longitude='72.000000',
        )
        ngo_user = User.objects.create_user(
            username='map-ngo@example.test',
            email='map-ngo@example.test',
            password='NgoPass!234567',
        )
        ngo = NGO.objects.create(
            user=ngo_user,
            organization_name='Map NGO',
            contact='2345678901',
            email='map-ngo@example.test',
            password='NgoPass!234567',
            latitude='19.100000',
            longitude='72.100000',
        )
        volunteer_user = User.objects.create_user(
            username='map-volunteer@example.test',
            email='map-volunteer@example.test',
            password='VolunteerPass!234',
        )
        Volunteer.objects.create(
            user=volunteer_user,
            username='map-volunteer',
            email='map-volunteer@example.test',
            phone='3456789012',
            password='VolunteerPass!234',
            latitude='19.050000',
            longitude='72.050000',
        )
        Food.objects.create(
            donor=donor,
            assigned_ngo=ngo,
            name='Legacy-coordinate meal',
            food_quantity='2 boxes',
            expiry_hours=6,
            status='ASSIGNED',
            pickup_latitude='0.000000',
            pickup_longitude=None,
        )

        self.client.force_login(volunteer_user)
        response = self.client.get(reverse('volunteer_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-plat="19.000000"')
        self.assertContains(response, 'data-plon="72.000000"')
        self.assertContains(response, 'destination=19.000000,72.000000')
        self.assertNotContains(response, 'Custom pickup point')

