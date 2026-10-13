import json
import queue
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app import App
from captions import SentenceBuffer
from backend import OllamaClient
from presentation import load_presentation, prepared_translation, recognition_hint, translation_context


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.data = load_presentation('examples/presentation-context.json')

    def test_matching_preserves_changed_claims_and_target(self):
        source = self.data['slides'][0]['prepared'][0]['source']
        self.assertIsNotNone(prepared_translation(self.data, 0, source.upper().rstrip('.'), 'Japanese'))
        for text in ('Event cameras do not detect changes in brightness.', 'Event cameras detect 2 changes in brightness.', ''):
            self.assertIsNone(prepared_translation(self.data, 0, text, 'Japanese'))
        self.assertIsNone(prepared_translation(self.data, 0, source, 'French'))
        self.assertIsNone(prepared_translation(self.data, 1, source, 'Japanese'))

    def test_hints_and_language_scoped_references(self):
        self.assertIn('event camera', recognition_hint(self.data, 0))
        reference = json.loads(translation_context(self.data, 0, 'French'))
        self.assertEqual(reference['glossary'], {})
        self.assertEqual(reference['prepared'], [])

    def test_invalid_input_and_text_import(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'context.json'
            for data in ({'slides': []}, {'slides': [{'prepared': [{'source': 'Hello'}]}]}):
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    load_presentation(path)
            path = Path(folder) / 'slides.txt'
            path.write_text('First slide\n---\nSecond slide')
            self.assertEqual(len(load_presentation(path)['slides']), 2)

    def test_pptx_uses_presentation_order(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'slides.pptx'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('ppt/presentation.xml', '<p:presentation xmlns:p="p" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId r:id="r2"/><p:sldId r:id="r1"/></p:sldIdLst></p:presentation>')
                archive.writestr('ppt/_rels/presentation.xml.rels', '<Relationships><Relationship Id="r1" Target="slides/slide1.xml"/><Relationship Id="r2" Target="slides/slide2.xml"/></Relationships>')
                for i in (1, 2):
                    archive.writestr(f'ppt/slides/slide{i}.xml', f'<slide xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>Slide {i}</a:t></slide>')
            self.assertEqual(load_presentation(path)['slides'][0]['text'], 'Slide 2')

    def test_markdown_deck_front_matter_and_code_fences(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'slides.MD'
            path.write_text('---\nmarp: true\n---\n# First slide\n\n- Event cameras\n```text\n---\n```\n  ---  \n## Second slide\nLatency\n---\n')
            slides = load_presentation(path)['slides']
            self.assertEqual([s['title'] for s in slides], ['First slide', 'Second slide'])
            self.assertIn('```text\n---\n```', slides[0]['text'])
            self.assertNotIn('marp:', slides[0]['text'])

    def test_single_markdown_slide_without_front_matter(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'slides.markdown'
            path.write_text('# Overview\n\nPresentation context')
            self.assertEqual(load_presentation(path)['slides'][0]['title'], 'Overview')

    def test_prepared_caption_bypasses_ollama_and_fallback_has_context(self):
        app = App.__new__(App)
        app.events = queue.Queue()
        client = Mock()
        client.translate.return_value = 'Fallback'
        config = {'Translate to': 'Japanese', 'Ollama model': 'local'}
        App.translate_caption(app, self.data['slides'][0]['prepared'][0]['source'], 'now', config, client, (self.data, 0))
        client.translate.assert_not_called()
        App.translate_caption(app, 'A different claim.', 'now', config, client, (self.data, 0))
        self.assertIn('glossary', client.translate.call_args.kwargs['context'])

    def test_slide_change_flushes_old_context_and_hints_new_context(self):
        app = App.__new__(App)
        app.events = queue.Queue()
        app.active_context = (self.data, 0)
        app.context_snapshot = (self.data, 1)
        app.sentence_buffer = SentenceBuffer()
        app.sentence_buffer.feed('Unfinished old slide')
        app.translate_caption = Mock()
        app.recognizer = Mock()
        app.recognizer.transcribe.return_value = ([SimpleNamespace(text='New slide.')], None)
        config = {'Spoken language': 'English'}
        app.process(b'\0\0' * 100, 16000, config, Mock())
        self.assertEqual(app.translate_caption.call_args_list[0].args[-1], (self.data, 0))
        self.assertEqual(app.translate_caption.call_args_list[1].args[-1], (self.data, 1))
        self.assertIn('Lower latency', app.recognizer.transcribe.call_args.kwargs['initial_prompt'])

    def test_reference_is_separate_from_spoken_text(self):
        client = OllamaClient()
        client.request = Mock(return_value={'message': {'content': 'Translated'}})
        client.translate('Actual speech', 'Japanese', 'local', context='Slide context')
        payload = client.request.call_args.args[1]
        self.assertEqual(payload['messages'][-1]['content'], 'Actual speech')
        self.assertIn('Slide context', payload['messages'][1]['content'])


if __name__ == '__main__':
    unittest.main()
