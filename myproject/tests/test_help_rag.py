import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from config.settings import _load_project_env

from apps.main.services import chatbot
from apps.main.services.chatbot import FALLBACK_MESSAGE, OUT_OF_SCOPE_MESSAGE
from apps.main.services.help_rag.chunker import (
    MAX_CHUNK_TOKENS,
    chunk_markdown,
    extract_pinned_limitations,
    token_count,
)
from apps.main.services.help_rag.index import build_index, check_index, read_index
from apps.main.services.help_rag.prompts import SYSTEM_INSTRUCTIONS, build_generation_input
from apps.main.services.help_rag.retrieval import make_bm25, retrieve, tokenize


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTEXT_PATH = PROJECT_ROOT / 'RESCUEBITE_PRODUCT_CONTEXT.md'


class ProjectEnvTests(SimpleTestCase):
    def test_project_env_loads_settings_without_overriding_process_environment(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            env_file = Path(directory) / '.env'
            env_file.write_text(
                '# local Gemini settings\nGEMINI_API_KEY=file-key\nGEMINI_MODEL="file-model"\n',
                encoding='utf-8',
            )
            with patch.dict(os.environ, {'GEMINI_MODEL': 'process-model'}, clear=True):
                _load_project_env(env_file)
                self.assertEqual(os.environ['GEMINI_API_KEY'], 'file-key')
                self.assertEqual(os.environ['GEMINI_MODEL'], 'process-model')


class HelpChunkerTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.markdown = CONTEXT_PATH.read_text(encoding='utf-8')
        cls.chunks = chunk_markdown(cls.markdown)

    def test_heading_paths_tables_faqs_and_exclusions(self):
        self.assertTrue(self.chunks)
        self.assertTrue(all(chunk['text'].startswith(chunk['section']) for chunk in self.chunks))
        sections = [chunk['section'] for chunk in self.chunks]
        self.assertTrue(any('NGO browsing and claiming' in section for section in sections))
        self.assertFalse(any(section.startswith(('15.', '16.')) for section in sections))
        self.assertFalse(any('Chatbot Knowledge Boundaries' in chunk['text'] for chunk in self.chunks))

        # Every Markdown table in the source remains intact inside one chunk.
        lines = self.markdown.splitlines()
        table = []
        for line in lines + ['']:
            if line.lstrip().startswith('|'):
                table.append(line)
            elif table:
                block = '\n'.join(table)
                self.assertTrue(any(block in chunk['text'] for chunk in self.chunks), block[:80])
                table = []

        faq_chunks = [chunk for chunk in self.chunks if chunk['section'].startswith('13. Frequently Asked Questions >')]
        self.assertGreaterEqual(len(faq_chunks), 10)
        self.assertEqual(len(faq_chunks), len(set(chunk['section'] for chunk in faq_chunks)))
        self.assertTrue(any('What is RescueBite?' in chunk['section'] for chunk in faq_chunks))

    def test_chunk_sizes_nonempty_and_oversized_paragraph_splits(self):
        self.assertTrue(all(chunk['text'].strip() for chunk in self.chunks))
        self.assertTrue(all(token_count(chunk['text']) <= MAX_CHUNK_TOKENS for chunk in self.chunks))
        large = ' '.join(f"paragraphword{i}" for i in range(1400))
        chunks = chunk_markdown(f"## 1. Test Section\n\n{large}", max_tokens=80)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(token_count(chunk['text']) <= 80 for chunk in chunks))

    def test_limitations_are_extracted_but_not_indexed(self):
        pinned = extract_pinned_limitations(self.markdown)
        self.assertIn('must not claim or assume', pinned)
        self.assertIn('Unknown / Not specified', pinned)
        self.assertFalse(any('can and cannot answer' in chunk['text'].lower() for chunk in self.chunks))


class HelpIndexTests(SimpleTestCase):
    def test_index_round_trip_hash_check_and_source_change(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            source = Path(directory) / 'context.md'
            target = Path(directory) / 'index.json'
            source.write_text(
                '## 1. Product Overview\n\nRescueBite shares food.\n\n'
                '## 15. Chatbot Knowledge Boundaries\n### The chatbot must not claim or assume\n- No actions.\n\n'
                '## 16. Source Areas / Verification Notes\n**Unknown / Not specified:** Support contact.\n',
                encoding='utf-8',
            )
            embed = Mock(return_value=[[0.2, 0.8]])
            artifact = build_index(source, target, embed, 'fake-embedding-model')
            self.assertEqual(read_index(target), artifact)
            self.assertIn('No actions.', artifact['limitations'])
            self.assertIn('Support contact.', artifact['limitations'])
            self.assertEqual(check_index(target, source)['source_sha256'], artifact['source_sha256'])
            with self.assertRaisesRegex(ValueError, 'embedding model'):
                check_index(target, source, 'other-model')
            embed.assert_called_once()

            source.write_text(source.read_text(encoding='utf-8') + '\nUpdated.\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'stale'):
                check_index(target, source)

    def test_build_help_index_check_flag_fails_when_missing_or_stale(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            path = Path(directory) / 'missing.json'
            with self.assertRaises(CommandError):
                call_command('build_help_index', '--check', path=path)
            stale = Path(directory) / 'stale.json'
            stale.write_text(json.dumps({
                'version': 1, 'source_sha256': 'old-hash', 'embedding_model': 'test',
                'limitations': 'Pinned rules.', 'chunks': [{'section': 'one', 'text': 'one'}],
                'embeddings': [[1.0]],
            }), encoding='utf-8')
            with self.assertRaisesRegex(CommandError, 'stale'):
                call_command('build_help_index', '--check', path=stale)

            build_index(
                CONTEXT_PATH, stale, lambda texts: [[1.0, 0.0] for _ in texts],
                'old-model',
            )
            with patch.dict('os.environ', {'GEMINI_EMBEDDING_MODEL': 'gemini-embedding-001'}):
                with self.assertRaisesRegex(CommandError, 'embedding model'):
                    call_command('build_help_index', '--check', path=stale)

    def test_build_help_index_command_builds_and_checks_with_mock_sdk(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            path = Path(directory) / 'index.json'
            class FakeOpenAI:
                def __init__(self, **kwargs):
                    self.embeddings = SimpleNamespace(create=self.create_embeddings)

                @staticmethod
                def create_embeddings(**kwargs):
                    return SimpleNamespace(data=[
                        SimpleNamespace(index=i, embedding=[1.0, 0.0])
                        for i, _ in enumerate(kwargs['input'])
                    ])

            with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GEMINI_MODEL': 'gemini-2.5-flash'}, clear=True), patch.dict(
                sys.modules, {'openai': SimpleNamespace(OpenAI=FakeOpenAI)}
            ):
                call_command('build_help_index', path=path)
            self.assertTrue(path.exists())
            call_command('build_help_index', '--check', path=path)

    def test_build_help_index_retries_rate_limits(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            path = Path(directory) / 'index.json'

            class RateLimitError(Exception):
                status_code = 429

            class FakeOpenAI:
                calls = 0

                def __init__(self, **kwargs):
                    self.embeddings = SimpleNamespace(create=self.create_embeddings)

                def create_embeddings(self, **kwargs):
                    type(self).calls += 1
                    if type(self).calls == 1:
                        raise RateLimitError('private provider details')
                    return SimpleNamespace(data=[
                        SimpleNamespace(index=i, embedding=[1.0, 0.0])
                        for i, _ in enumerate(kwargs['input'])
                    ])

            with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GEMINI_MODEL': 'gemini-2.5-flash'}, clear=True), patch.dict(
                sys.modules, {'openai': SimpleNamespace(OpenAI=FakeOpenAI)}
            ), patch('apps.main.management.commands.build_help_index.time.sleep') as sleep:
                call_command('build_help_index', path=path)
            self.assertTrue(path.exists())
            sleep.assert_called_once_with(1)
            self.assertGreater(FakeOpenAI.calls, 2)

    def test_gemini_index_build_accepts_sdk_response_without_embedding_indexes(self):
        """Gemini may omit index values; preserve response order for batched vectors."""
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            path = Path(directory) / 'index.json'

            class FakeOpenAI:
                offset = 0

                def __init__(self, **kwargs):
                    self.embeddings = SimpleNamespace(create=self.create_embeddings)

                def create_embeddings(self, **kwargs):
                    # Same shape as OpenAI's CreateEmbeddingResponse.data entries,
                    # with the Gemini-compatible endpoint's optional index absent.
                    data = []
                    for item_offset, _ in enumerate(kwargs['input']):
                        item_number = type(self).offset + item_offset
                        data.append(SimpleNamespace(
                            index=None,
                            embedding=[float(item_number)] + [0.25] * 3071,
                        ))
                    type(self).offset += len(data)
                    return SimpleNamespace(data=data)

            with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GEMINI_MODEL': 'gemini-2.5-flash'}, clear=True), patch.dict(
                sys.modules, {'openai': SimpleNamespace(OpenAI=FakeOpenAI)}
            ):
                call_command('build_help_index', path=path)

            artifact = read_index(path)
            self.assertEqual(len(artifact['chunks']), len(artifact['embeddings']))
            self.assertTrue(all(len(vector) == 3072 for vector in artifact['embeddings']))
            self.assertEqual(
                [vector[0] for vector in artifact['embeddings']],
                [float(index) for index in range(len(artifact['chunks']))],
            )

    def test_build_command_reports_sanitized_failure_and_preserves_cause(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            path = Path(directory) / 'index.json'

            class FakeOpenAI:
                def __init__(self, **kwargs):
                    self.embeddings = SimpleNamespace(create=self.create_embeddings)

                @staticmethod
                def create_embeddings(**kwargs):
                    raise TypeError('provider reported api_key=test-key')

            with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GEMINI_MODEL': 'gemini-2.5-flash'}, clear=True), patch.dict(
                sys.modules, {'openai': SimpleNamespace(OpenAI=FakeOpenAI)}
            ):
                with self.assertRaises(CommandError) as caught:
                    call_command('build_help_index', path=path)

            self.assertIsInstance(caught.exception.__cause__, TypeError)
            self.assertIn('TypeError:', str(caught.exception))
            self.assertIn('test_help_rag.py:', str(caught.exception))
            self.assertIn('api_key=[REDACTED]', str(caught.exception))
            self.assertNotIn('test-key', str(caught.exception))


class HelpRetrievalTests(SimpleTestCase):
    def test_identifier_tokens_and_hybrid_ranking_surface_accept_delivery_chunk(self):
        query = 'IN_TRANSIT /volunteer/accept-delivery/'
        tokens = tokenize(query)
        self.assertIn('in_transit', tokens)
        self.assertIn('volunteer/accept-delivery', tokens)
        self.assertIn('accept-delivery', tokens)

        chunks = [
            {'section': 'Volunteer delivery acceptance',
             'text': 'POST /volunteer/accept-delivery/ changes status to IN_TRANSIT.'},
            {'section': 'Donor listing', 'text': 'Donors create AVAILABLE food listings.'},
            {'section': 'NGO claiming', 'text': 'NGOs claim food and set it to ASSIGNED.'},
        ]
        vectors = [[1, 0], [1, 0], [1, 0]]
        results, best = retrieve(
            {'chunks': chunks, 'embeddings': vectors}, query, [1, 0],
            bm25=make_bm25(chunks),
        )
        self.assertEqual(results[0]['section'], 'Volunteer delivery acceptance')
        self.assertEqual(best, 1.0)

    def test_prompt_includes_retrieved_context_and_pinned_limitations(self):
        prompt = build_generation_input(
            'How do I claim food?',
            [{'section': 'NGO browsing and claiming', 'text': 'NGOs claim eligible food.'}],
            'No account data; delivery completion is not implemented.',
        )
        self.assertIn('BEGIN RETRIEVED PRODUCT CONTEXT', prompt)
        self.assertIn('NGOs claim eligible food.', prompt)
        self.assertIn('BEGIN PINNED LIMITATIONS', prompt)
        self.assertIn('delivery completion is not implemented', prompt)
        self.assertIn('untrusted', SYSTEM_INSTRUCTIONS.lower())


class HelpServiceTests(SimpleTestCase):
    def setUp(self):
        chatbot.reset_index_cache()

    def tearDown(self):
        chatbot.reset_index_cache()

    def make_index(self, path):
        return build_index(
            CONTEXT_PATH, path, lambda texts: [[1.0, 0.0] for _ in texts],
            'gemini-embedding-001',
        )

    def fake_openai(self, query_vector, response_text='Grounded answer.'):
        completions = SimpleNamespace(create=Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=response_text))])))
        embeddings = SimpleNamespace(create=Mock(return_value=SimpleNamespace(
            data=[SimpleNamespace(embedding=query_vector)]
        )))
        return SimpleNamespace(OpenAI=Mock(return_value=SimpleNamespace(
            embeddings=embeddings, chat=SimpleNamespace(completions=completions),
        )))

    @patch.dict('os.environ', {}, clear=True)
    def test_missing_key_and_missing_index_return_fallback(self):
        self.assertEqual(chatbot.ask_help('What is RescueBite?'), FALLBACK_MESSAGE)
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory, patch.dict(
            'os.environ', {'GEMINI_API_KEY': 'test-key', 'GEMINI_MODEL': 'gemini-2.5-flash'}, clear=True
        ), override_settings(HELP_RAG_INDEX_PATH=Path(directory) / 'absent.json'):
            chatbot.reset_index_cache()
            self.assertEqual(chatbot.ask_help('What is RescueBite?'), FALLBACK_MESSAGE)

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GEMINI_MODEL': 'gemini-2.5-flash'}, clear=True)
    def test_low_similarity_skips_generation(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            index_path = Path(directory) / 'index.json'
            self.make_index(index_path)
            fake = self.fake_openai([0.0, 1.0])
            with override_settings(HELP_RAG_INDEX_PATH=index_path), patch.dict('sys.modules', {'openai': fake}):
                chatbot.reset_index_cache()
                answer = chatbot.ask_help('How do I create a donation?')
            self.assertEqual(answer, OUT_OF_SCOPE_MESSAGE)
            fake.OpenAI.return_value.chat.completions.create.assert_not_called()
            fake.OpenAI.return_value.embeddings.create.assert_called_once()

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GEMINI_MODEL': 'gemini-2.5-flash'}, clear=True)
    def test_provider_exception_and_timeout_return_fallback(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            index_path = Path(directory) / 'index.json'
            self.make_index(index_path)
            class RateLimitError(Exception):
                status_code = 429

            class AuthenticationError(Exception):
                status_code = 401

            class BadRequestError(Exception):
                status_code = 400

            for failure in (
                RuntimeError('provider detail api_key=test-key; question=What is RescueBite?'),
                TimeoutError('request timed out for What is RescueBite?'),
                RateLimitError('private rate limit'), AuthenticationError('private auth detail'),
                BadRequestError('private rejected request detail'),
            ):
                fake = self.fake_openai([1.0, 0.0])
                fake.OpenAI.return_value.chat.completions.create.side_effect = failure
                with self.subTest(error=type(failure).__name__), override_settings(HELP_RAG_INDEX_PATH=index_path), patch.dict('sys.modules', {'openai': fake}), self.assertLogs('apps.main.services.chatbot', level='WARNING') as captured:
                    chatbot.reset_index_cache()
                    self.assertEqual(chatbot.ask_help('What is RescueBite?'), FALLBACK_MESSAGE)
                    logged = '\n'.join(captured.output)
                    self.assertNotIn('test-key', logged)
                    self.assertNotIn('What is RescueBite?', logged)
                    self.assertIn(type(failure).__name__, logged)
                    self.assertIn('chatbot.py:', logged)
                    if isinstance(failure, RuntimeError):
                        self.assertIn('provider detail', logged)
                        self.assertIn('api_key=[REDACTED]', logged)
                    if isinstance(failure, TimeoutError):
                        self.assertIn('answer generation', '\n'.join(captured.output))
                    if isinstance(failure, BadRequestError):
                        self.assertIn('HTTP 400', '\n'.join(captured.output))

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GEMINI_MODEL': 'gemini-2.5-flash'}, clear=True)
    def test_wrong_embedding_model_index_falls_back(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            index_path = Path(directory) / 'index.json'
            self.make_index(index_path)
            fake = self.fake_openai([1.0, 0.0])
            with override_settings(HELP_RAG_INDEX_PATH=index_path), patch.dict(
                'sys.modules', {'openai': fake}
            ), patch.dict('os.environ', {
                'GEMINI_API_KEY': 'test-key', 'GEMINI_MODEL': 'gemini-2.5-flash',
                'GEMINI_EMBEDDING_MODEL': 'other-model'
            }, clear=True):
                chatbot.reset_index_cache()
                self.assertEqual(chatbot.ask_help('What is RescueBite?'), FALLBACK_MESSAGE)
                fake.OpenAI.assert_not_called()

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GEMINI_MODEL': 'gemini-2.5-flash'}, clear=True)
    def test_service_embeds_once_and_generates_with_retrieved_context(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            index_path = Path(directory) / 'index.json'
            self.make_index(index_path)
            fake = self.fake_openai([1.0, 0.0], 'Donors can create food listings.')
            with override_settings(HELP_RAG_INDEX_PATH=index_path), patch.dict('sys.modules', {'openai': fake}):
                chatbot.reset_index_cache()
                answer = chatbot.ask_help('How can a donor create a donation?')
            self.assertEqual(answer, 'Donors can create food listings.')
            client = fake.OpenAI.return_value
            fake.OpenAI.assert_called_once_with(
                api_key='test-key',
                base_url='https://generativelanguage.googleapis.com/v1beta/openai/',
                timeout=45,
                max_retries=0,
            )
            client.embeddings.create.assert_called_once()
            client.chat.completions.create.assert_called_once()
            generation_input = client.chat.completions.create.call_args.kwargs['messages'][1]['content']
            self.assertIn('BEGIN PINNED LIMITATIONS', generation_input)
            self.assertIn('BEGIN RETRIEVED PRODUCT CONTEXT', generation_input)
            self.assertEqual(client.chat.completions.create.call_args.kwargs['temperature'], 0.1)
            self.assertEqual(client.chat.completions.create.call_args.kwargs['max_tokens'], 1200)
            self.assertEqual(client.chat.completions.create.call_args.kwargs['reasoning_effort'], 'none')

    @patch.dict('os.environ', {
        'GEMINI_API_KEY': 'test-key',
        'GEMINI_MODEL': 'gemini-3.8-flash',
        'GEMINI_EMBEDDING_MODEL': 'gemini-embedding-001',
    }, clear=True)
    def test_gemini_3_uses_supported_low_reasoning_and_longer_timeout(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            index_path = Path(directory) / 'index.json'
            self.make_index(index_path)
            fake = self.fake_openai([1.0, 0.0], 'Grounded Gemini 3 answer.')
            with override_settings(HELP_RAG_INDEX_PATH=index_path), patch.dict(
                'sys.modules', {'openai': fake}
            ):
                chatbot.reset_index_cache()
                self.assertEqual(
                    chatbot.ask_help('What is RescueBite?'), 'Grounded Gemini 3 answer.'
                )
            fake.OpenAI.assert_called_once_with(
                api_key='test-key',
                base_url='https://generativelanguage.googleapis.com/v1beta/openai/',
                timeout=45,
                max_retries=0,
            )
            self.assertEqual(
                fake.OpenAI.return_value.chat.completions.create.call_args.kwargs[
                    'reasoning_effort'
                ],
                'low',
            )
            self.assertNotIn(
                'temperature',
                fake.OpenAI.return_value.chat.completions.create.call_args.kwargs,
            )
