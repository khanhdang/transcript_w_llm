import unittest

from captions import SentenceBuffer, caption_pages, split_sentences, wrap_lines


class CaptionTests(unittest.TestCase):
    def test_fragments_join_before_translation(self):
        buffer = SentenceBuffer()
        self.assertEqual(buffer.feed("Today we will discuss"), "")
        self.assertEqual(buffer.feed("local translation. Next we will"),
                         "Today we will discuss local translation.")
        self.assertEqual(buffer.feed("show a demo."), "Next we will show a demo.")
        self.assertEqual(buffer.flush(), "")

    def test_pause_and_stop_flush_pending_text(self):
        buffer = SentenceBuffer()
        buffer.feed("An unfinished thought")
        self.assertEqual(buffer.feed(""), "An unfinished thought")
        buffer.feed("Final words")
        self.assertEqual(buffer.flush(), "Final words")

    def test_missing_punctuation_has_bounded_wait(self):
        buffer = SentenceBuffer()
        buffer.feed("first")
        buffer.feed("second")
        self.assertEqual(buffer.feed("third"), "first second third")

    def test_wrap_preserves_words(self):
        self.assertEqual(wrap_lines("Hello world. Welcome everyone.", len, 15),
                         ["Hello world.", "Welcome", "everyone."])

    def test_several_complete_sentences_share_a_caption(self):
        self.assertEqual(caption_pages("Hello everyone. Welcome to my talk.", len, 20),
                         ["Hello everyone.\nWelcome to my talk."])

    def test_pages_break_between_sentences(self):
        text = "One sentence is here. Another sentence is here. Last sentence is here."
        pages = caption_pages(text, len, 25, max_lines=2)
        self.assertEqual(pages, ["One sentence is here.\nAnother sentence is here.",
                                 "Last sentence is here."])

    def test_cjk_sentence_boundaries(self):
        self.assertEqual(split_sentences("こんにちは。今日は発表します！よろしくお願いします。"),
                         ["こんにちは。", "今日は発表します！", "よろしくお願いします。"])

    def test_long_sentence_does_not_lose_content(self):
        text = "A very long sentence with many words " * 12 + "ends here."
        pages = caption_pages(text, len, 25)
        self.assertTrue(all(len(page.splitlines()) <= 3 for page in pages))
        self.assertEqual(" ".join(" ".join(pages).split()), text)

    def test_decimal_and_quotes(self):
        self.assertEqual(split_sentences('The value is 3.14. She said "hello!" Next sentence.'),
                         ['The value is 3.14.', 'She said "hello!"', 'Next sentence.'])


if __name__ == "__main__":
    unittest.main()
