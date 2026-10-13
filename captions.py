"""Sentence-aware subtitle layout, independent of the GUI."""
import re


class SentenceBuffer:
    """Join recognition fragments until punctuation or a pause ends the thought."""
    def __init__(self):
        self.pending = ""
        self.chunks = 0

    def feed(self, text):
        if not text.strip():
            return self.flush()
        parts = split_sentences((self.pending + " " + text).strip())
        self.chunks += 1
        if parts and not re.search(r'[.!?。！？][\"\u201d\u2019\u300d\u300f]*$', parts[-1]):
            self.pending = parts.pop()
        else:
            self.pending = ""
        if self.pending and self.chunks >= 3:
            # Recognition may omit punctuation; do not hold speech indefinitely.
            parts.append(self.pending)
            self.pending = ""
        if not self.pending:
            self.chunks = 0
        return " ".join(parts)

    def flush(self):
        text = self.pending
        self.pending = ""
        self.chunks = 0
        return text


def split_sentences(text):
    text = " ".join(text.split())
    # Preserve punctuation and quotes; decimals are not sentence boundaries.
    return [part.strip() for part in re.findall(
        r'.+?(?:[.!?。！？]+[\"\u201d\u2019\u300d\u300f]*(?=\s|$|[^\x00-\x7f])|$)', text)
        if part.strip()]


def wrap_lines(text, measure, width):
    """Wrap at spaces where available, and at glyph boundaries for CJK."""
    remaining = " ".join(text.split())
    lines = []
    while remaining:
        end = 0
        while end < len(remaining) and measure(remaining[:end + 1]) <= width:
            end += 1
        if end == len(remaining):
            lines.append(remaining)
            break
        end = max(1, end)
        space = remaining.rfind(" ", 0, end + 1)
        if space > 0:
            end = space
        lines.append(remaining[:end].strip())
        remaining = remaining[end:].lstrip()
    return lines


def caption_pages(text, measure, width, max_lines=3):
    """Prefer page boundaries between sentences; never truncate content."""
    pages, current = [], ""
    for sentence in split_sentences(text):
        candidate = (current + " " + sentence).strip()
        if len(wrap_lines(candidate, measure, width)) <= max_lines:
            current = candidate
            continue
        if current:
            pages.append("\n".join(wrap_lines(current, measure, width)))
            current = ""
        lines = wrap_lines(sentence, measure, width)
        if len(lines) <= max_lines:
            current = sentence
        else:
            # An unusually long sentence still needs pages at the minimum size.
            pages.extend("\n".join(lines[i:i + max_lines])
                         for i in range(0, len(lines), max_lines))
    if current:
        pages.append("\n".join(wrap_lines(current, measure, width)))
    return pages
