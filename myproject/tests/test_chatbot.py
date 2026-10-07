import json
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from apps.main.services.chatbot import FALLBACK_MESSAGE


class ChatbotTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.home = self.client.get(reverse('home'))
        self.csrf = self.home.cookies['csrftoken'].value
        self.url = reverse('chatbot_message')

    def post_message(self, message):
        return self.client.post(
            self.url,
            data=json.dumps({'message': message}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=self.csrf,
        )

    def test_home_page_includes_additive_chat_launcher(self):
        self.assertContains(self.home, 'May I Help You?')
        self.assertContains(self.home, 'main/css/chatbot.css')
        self.assertContains(self.home, 'main/js/chatbot.js')
        with open('apps/main/static/main/css/chatbot.css', encoding='utf-8') as css_file:
            css = css_file.read()
        with open('apps/main/static/main/js/chatbot.js', encoding='utf-8') as js_file:
            js = js_file.read()
        self.assertIn('.rb-help__panel[hidden] { display: none; }', css)
        self.assertIn("event.key === 'Enter'", js)
        self.assertIn('event.shiftKey', js)
        self.assertIn('form.requestSubmit()', js)

    def test_missing_key_returns_friendly_fallback(self):
        with patch.dict('os.environ', {}, clear=True):
            response = self.post_message('How do I donate food?')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['reply'], FALLBACK_MESSAGE)

    def test_empty_and_overlong_messages_are_rejected(self):
        empty = self.post_message('  ')
        overlong = self.post_message('x' * 1201)
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(overlong.status_code, 400)

    def test_csrf_is_required(self):
        response = Client(enforce_csrf_checks=True).post(
            self.url,
            data=json.dumps({'message': 'How do I register?'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    @patch('apps.main.chatbot_views.ask_help', return_value='Choose Food Donor to post a donation.')
    def test_valid_question_returns_existing_json_response_shape(self, mock_ask_help):
        response = self.post_message('How do I donate food?')
        mock_ask_help.assert_called_once_with('How do I donate food?')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'reply': 'Choose Food Donor to post a donation.'})

    @patch('apps.main.chatbot_views.ask_help')
    def test_invalid_messages_are_rejected_before_provider_call(self, mock_ask_help):
        malformed = self.client.post(
            self.url, data='{', content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf
        )
        empty = self.post_message('  ')
        overlong = self.post_message('x' * 1201)
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(overlong.status_code, 400)
        mock_ask_help.assert_not_called()

    def test_csrf_anonymous_post_and_method_contract(self):
        anon = Client(enforce_csrf_checks=True)
        csrf = anon.get(reverse('home')).cookies['csrftoken'].value
        with patch('apps.main.chatbot_views.ask_help', return_value='Helpful answer.'):
            response = anon.post(
                self.url,
                data=json.dumps({'message': 'How do I register?'}),
                content_type='application/json',
                HTTP_X_CSRFTOKEN=csrf,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'reply': 'Helpful answer.'})
        self.assertEqual(anon.get(self.url).status_code, 405)

    def test_endpoint_rejects_non_json_requests(self):
        response = self.client.post(self.url, {'message': 'hello'}, HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(response.status_code, 400)
