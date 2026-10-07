from django.contrib.auth import SESSION_KEY
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from apps.main.models import Donor, NGO, Volunteer


class RegistrationAndLoginFlowTests(TestCase):
    registration_cases = (
        {
            'submit': 'volunteer_submit',
            'email': 'volunteer@example.test',
            'password': 'VolunteerPass!234',
            'model': Volunteer,
            'dashboard': 'volunteer_dashboard',
            'fields': {
                'username': 'volunteer-one',
                'phone': '1112223333',
                'latitude': '19.076000',
                'longitude': '72.877700',
            },
        },
        {
            'submit': 'ngo_submit',
            'email': 'ngo@example.test',
            'password': 'NgoPass!234567',
            'model': NGO,
            'dashboard': 'receiver_dashboard',
            'fields': {
                'organization_name': 'Test NGO',
                'contact': '2223334444',
                'latitude': '19.100000',
                'longitude': '72.800000',
            },
        },
        {
            'submit': 'donor_submit',
            'email': 'donor@example.test',
            'password': 'DonorPass!23456',
            'model': Donor,
            'dashboard': 'donor_dashboard',
            'fields': {
                'organization_name': 'Test Donor',
                'contact': '3334445555',
                'latitude': '19.200000',
                'longitude': '72.900000',
            },
        },
    )

    @staticmethod
    def post_data(case):
        return {
            **case['fields'],
            'email': case['email'],
            'password': case['password'],
            case['submit']: 'Register',
        }

    def test_each_registration_creates_matching_profile_and_can_login(self):
        for case in self.registration_cases:
            with self.subTest(role=case['submit']):
                client = Client(enforce_csrf_checks=True)
                home_response = client.get(reverse('home'))
                csrf_token = home_response.cookies['csrftoken'].value

                response = client.post(
                    reverse('home'),
                    self.post_data(case),
                    HTTP_X_CSRFTOKEN=csrf_token,
                )

                self.assertRedirects(response, reverse(case['dashboard']))
                user = User.objects.get(username=case['email'])
                profile = case['model'].objects.get(user=user)
                self.assertEqual(profile.email, case['email'])
                self.assertTrue(user.check_password(case['password']))
                self.assertNotEqual(user.password, case['password'])
                if case['model'] in (Volunteer, NGO):
                    self.assertTrue(check_password(case['password'], profile.password))
                self.assertEqual(client.session[SESSION_KEY], str(user.pk))

                logout_response = client.get(reverse('logout'))
                self.assertRedirects(logout_response, reverse('login'))
                self.assertNotIn(SESSION_KEY, client.session)
                login_page = client.get(reverse('login'))
                login_csrf = login_page.cookies['csrftoken'].value
                login_response = client.post(reverse('login'), {
                    'email': case['email'].upper(),
                    'password': case['password'],
                }, HTTP_X_CSRFTOKEN=login_csrf)
                self.assertRedirects(login_response, reverse(case['dashboard']))
                self.assertEqual(client.session[SESSION_KEY], str(user.pk))

    def test_invalid_registration_keeps_correct_tab_and_does_not_create_user(self):
        case = self.registration_cases[0]
        data = self.post_data(case)
        data.pop('phone')

        response = self.client.post(reverse('home'), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['submitted_form'], 'vol_form')
        self.assertTrue(response.context['vol_form'].errors)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Volunteer.objects.count(), 0)

    def test_duplicate_email_across_roles_is_rejected_on_submitted_tab(self):
        volunteer = self.registration_cases[0]
        self.client.post(reverse('home'), self.post_data(volunteer))
        donor = self.registration_cases[2]
        data = self.post_data(donor)
        data['email'] = volunteer['email'].upper()

        response = self.client.post(reverse('home'), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['submitted_form'], 'donor_form')
        self.assertIn('email', response.context['donor_form'].errors)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Donor.objects.count(), 0)

    def test_existing_user_with_non_email_username_can_login_by_profile_email(self):
        user = User.objects.create_user(
            username='legacy-account',
            email='legacy@example.test',
            password='LegacyPass!234',
        )
        Donor.objects.create(
            user=user,
            organization_name='Legacy Donor',
            contact='5556667777',
            email='legacy@example.test',
            latitude='19.000000',
            longitude='72.000000',
        )

        response = self.client.post(reverse('login'), {
            'email': 'LEGACY@example.test',
            'password': 'LegacyPass!234',
        })

        self.assertRedirects(response, reverse('donor_dashboard'))
        self.assertEqual(self.client.session[SESSION_KEY], str(user.pk))

    def test_incorrect_credentials_do_not_authenticate(self):
        User.objects.create_user(
            username='known@example.test',
            email='known@example.test',
            password='CorrectPass!234',
        )

        response = self.client.post(reverse('login'), {
            'email': 'known@example.test',
            'password': 'WrongPass!234',
        })

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertContains(response, 'Invalid email or password.')

    def test_role_specific_pages_and_actions_reject_other_roles(self):
        user = User.objects.create_user(
            username='wrong-role@example.test',
            email='wrong-role@example.test',
            password='WrongRolePass!234',
        )
        Donor.objects.create(
            user=user,
            organization_name='Wrong Role Donor',
            contact='5556667777',
            email='wrong-role@example.test',
            latitude='19.000000',
            longitude='72.000000',
        )
        self.client.force_login(user)

        self.assertRedirects(
            self.client.get(reverse('volunteer_dashboard')),
            reverse('login'),
        )
        self.assertRedirects(
            self.client.get(reverse('receiver_dashboard')),
            reverse('login'),
        )
        response = self.client.post(
            reverse('accept_donation'),
            data='{}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['success'])

    def test_ambiguous_multi_role_account_is_not_routed_by_precedence(self):
        user = User.objects.create_user(
            username='multi-role@example.test',
            email='multi-role@example.test',
            password='MultiRolePass!234',
        )
        Volunteer.objects.create(
            user=user,
            username='multi-role',
            email='multi-role@example.test',
            phone='1111111111',
            password='MultiRolePass!234',
            latitude='19.000000',
            longitude='72.000000',
        )
        Donor.objects.create(
            user=user,
            organization_name='Also a donor',
            contact='2222222222',
            email='multi-role-donor@example.test',
            latitude='19.000000',
            longitude='72.000000',
        )

        response = self.client.post(reverse('login'), {
            'email': 'multi-role@example.test',
            'password': 'MultiRolePass!234',
        })

        self.assertRedirects(response, reverse('login'))
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_navigation_labels_match_authentication_state(self):
        anonymous_response = self.client.get(reverse('home'))
        self.assertContains(anonymous_response, 'href="/login/">Login</a>')

        user = User.objects.create_user(
            username='nav@example.test',
            email='nav@example.test',
            password='NavPass!23456',
        )
        self.client.force_login(user)
        authenticated_response = self.client.get(reverse('home'))
        self.assertContains(authenticated_response, 'href="/logout/">Logout</a>')

