from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from apps.main.models import Donor, NGO, Volunteer, Food


class RescueBiteSmokeTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_urls_reverse(self):
        """Verify all existing named URLs reverse successfully."""
        url_names = [
            'home',
            'login',
            'logout',
            'donor_dashboard',
            'receiver_dashboard',
            'volunteer_dashboard',
            'create_food_donation',
            'accept_donation',
            'volunteer_accept_delivery',
        ]
        for name in url_names:
            url = reverse(name)
            self.assertTrue(bool(url))

    def test_public_pages_load(self):
        """Verify public pages render 200 OK with correct templates."""
        res_home = self.client.get('/', HTTP_HOST='127.0.0.1')
        self.assertEqual(res_home.status_code, 200)
        self.assertTemplateUsed(res_home, 'main/home.html')

        res_login = self.client.get('/login/', HTTP_HOST='127.0.0.1')
        self.assertEqual(res_login.status_code, 200)
        self.assertTemplateUsed(res_login, 'main/login.html')

    def test_protected_dashboards_redirect_anonymous(self):
        """Verify unauthenticated access to dashboards redirects to login."""
        dashboards = [
            reverse('donor_dashboard'),
            reverse('receiver_dashboard'),
            reverse('volunteer_dashboard'),
        ]
        for url in dashboards:
            res = self.client.get(url, HTTP_HOST='127.0.0.1')
            self.assertEqual(res.status_code, 302)
