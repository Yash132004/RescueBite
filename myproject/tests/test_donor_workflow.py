import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from apps.main.models import Donor, Food, NGO, Volunteer
from apps.main.services.matching import find_nearest_receiver, haversine


class DonorWorkflowTests(TestCase):
    def setUp(self):
        self.donor_user = User.objects.create_user(
            username='donor-workflow@example.test',
            email='donor-workflow@example.test',
            password='DonorPass!23456',
        )
        self.donor = Donor.objects.create(
            user=self.donor_user,
            organization_name='Workflow Donor',
            contact='1234567890',
            email='donor-workflow@example.test',
            latitude='19.000000',
            longitude='72.000000',
        )

    def test_donation_creation_claim_and_volunteer_pickup_remain_visible_to_donor(self):
        donor_client = Client(enforce_csrf_checks=True)
        donor_client.force_login(self.donor_user)
        dashboard = donor_client.get(reverse('donor_dashboard'))
        self.assertEqual(dashboard.status_code, 200)

        csrf = dashboard.cookies['csrftoken'].value
        create_response = donor_client.post(
            reverse('create_food_donation'),
            {
                'name': 'Vegetable meals',
                'food_quantity': '12 trays',
                'description': 'Prepared today',
                'expiry_hours': '8',
                'pickup_latitude': '19.076000',
                'pickup_longitude': '72.877700',
            },
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertRedirects(create_response, reverse('donor_dashboard'))

        food = Food.objects.get(donor=self.donor)
        self.assertEqual(food.status, 'AVAILABLE')
        self.assertEqual(food.name, 'Vegetable meals')

        ngo_user = User.objects.create_user(
            username='ngo-workflow@example.test',
            email='ngo-workflow@example.test',
            password='NgoPass!234567',
        )
        ngo = NGO.objects.create(
            user=ngo_user,
            organization_name='Workflow NGO',
            contact='2345678901',
            email='ngo-workflow@example.test',
            password='NgoPass!234567',
            latitude='19.100000',
            longitude='72.800000',
        )
        ngo_client = Client(enforce_csrf_checks=True)
        self.assertFalse(hasattr(ngo_user, 'volunteer'))
        login_page = ngo_client.get(reverse('login'))
        login_csrf = login_page.cookies['csrftoken'].value
        ngo_login = ngo_client.post(reverse('login'), {
            'email': 'ngo-workflow@example.test',
            'password': 'NgoPass!234567',
        }, HTTP_X_CSRFTOKEN=login_csrf)
        self.assertRedirects(ngo_login, reverse('receiver_dashboard'))
        volunteer_access = ngo_client.get(reverse('volunteer_dashboard'))
        self.assertEqual(volunteer_access.status_code, 302)
        self.assertTrue(volunteer_access.url.startswith(reverse('login')))
        receiver_page = ngo_client.get(reverse('receiver_dashboard'))
        self.assertContains(receiver_page, 'Vegetable meals')
        ngo_csrf = receiver_page.cookies['csrftoken'].value

        claim_response = ngo_client.post(
            reverse('accept_donation'),
            data=json.dumps({'food_id': food.pk}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=ngo_csrf,
        )
        self.assertEqual(claim_response.status_code, 200)
        self.assertTrue(claim_response.json()['success'])
        food.refresh_from_db()
        self.assertEqual(food.status, 'ASSIGNED')
        self.assertEqual(food.assigned_ngo, ngo)
        claimed_page = ngo_client.get(reverse('receiver_dashboard'))
        self.assertContains(claimed_page, 'data-status="ASSIGNED"')
        self.assertContains(claimed_page, 'Vegetable meals')

        volunteer_user = User.objects.create_user(
            username='volunteer-workflow@example.test',
            email='volunteer-workflow@example.test',
            password='VolunteerPass!234',
        )
        Volunteer.objects.create(
            user=volunteer_user,
            username='workflow-volunteer',
            email='volunteer-workflow@example.test',
            phone='3456789012',
            password='VolunteerPass!234',
            latitude='19.050000',
            longitude='72.850000',
        )
        volunteer_client = Client(enforce_csrf_checks=True)
        volunteer_client.force_login(volunteer_user)
        volunteer_page = volunteer_client.get(reverse('volunteer_dashboard'))
        self.assertContains(volunteer_page, 'Vegetable meals')
        volunteer_csrf = volunteer_page.cookies['csrftoken'].value
        accept_response = volunteer_client.post(
            reverse('volunteer_accept_delivery'),
            data=json.dumps({'food_id': food.pk}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=volunteer_csrf,
        )
        self.assertEqual(accept_response.status_code, 200)
        self.assertTrue(accept_response.json()['success'])
        food.refresh_from_db()
        self.assertEqual(food.status, 'IN_TRANSIT')
        self.assertIn(
            ('IN_TRANSIT', 'Picked up by volunteer - in transit'),
            Food._meta.get_field('status').choices,
        )
        self.assertContains(ngo_client.get(reverse('receiver_dashboard')), 'data-status="IN_TRANSIT"')

        donor_page = donor_client.get(reverse('donor_dashboard'))
        self.assertContains(donor_page, 'data-status="IN_TRANSIT"')
        self.assertContains(donor_page, 'Workflow NGO')
        self.assertContains(donor_page, 'data-donor-lat="19.076000"')
        self.assertContains(donor_page, 'data-donor-lng="72.877700"')
        self.assertEqual(donor_page.context['open_food_count'], 0)
        self.assertEqual(donor_page.context['total_donations'], 1)

    def test_matching_helpers_still_return_nearest_receiver(self):
        nearest_user = User.objects.create_user(
            username='nearest-ngo@example.test',
            email='nearest-ngo@example.test',
            password='NgoPass!234567',
        )
        nearest = NGO.objects.create(
            user=nearest_user,
            organization_name='Nearest NGO',
            contact='2345678901',
            email='nearest-ngo@example.test',
            password='NgoPass!234567',
            latitude='19.010000',
            longitude='72.010000',
        )
        farther_user = User.objects.create_user(
            username='farther-ngo@example.test',
            email='farther-ngo@example.test',
            password='NgoPass!234567',
        )
        NGO.objects.create(
            user=farther_user,
            organization_name='Farther NGO',
            contact='3456789012',
            email='farther-ngo@example.test',
            password='NgoPass!234567',
            latitude='20.000000',
            longitude='73.000000',
        )

        matched, distance = find_nearest_receiver(self.donor)

        self.assertEqual(matched, nearest)
        self.assertGreater(distance, 0)
        self.assertAlmostEqual(haversine(0, 0, 0, 1), 111.19, places=1)

    def test_donation_validation_rejects_zero_shelf_life_and_partial_pickup(self):
        Food.objects.create(
            donor=self.donor,
            name='Existing meal',
            food_quantity='3 boxes',
            expiry_hours=6,
            status='RECEIVED',
        )
        self.client.force_login(self.donor_user)
        response = self.client.post(reverse('create_food_donation'), {
            'name': 'Invalid meal',
            'food_quantity': '1 tray',
            'expiry_hours': '0',
            'pickup_latitude': '19.076000',
            'pickup_longitude': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('expiry_hours', response.context['form'].errors)
        self.assertIn('pickup_longitude', response.context['form'].errors)
        self.assertContains(response, 'Existing meal')
        self.assertEqual(Food.objects.filter(donor=self.donor).count(), 1)
        self.assertEqual(response.context['open_food_count'], 0)

