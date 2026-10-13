"""Local presentation context and conservative prepared-script matching."""
import json
import posixpath
import re
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def load_presentation(path):
    path = Path(path)
    if path.suffix.lower() == '.pptx':
        with zipfile.ZipFile(path) as archive:
            rels = ET.fromstring(archive.read('ppt/_rels/presentation.xml.rels'))
            targets = {r.attrib['Id']: r.attrib['Target'] for r in rels}
            root = ET.fromstring(archive.read('ppt/presentation.xml'))
            slides = []
            for slide in root.findall('.//{*}sldId'):
                target = targets[slide.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
                name = target.lstrip('/') if target.startswith('/') else posixpath.normpath('ppt/' + target)
                xml = ET.fromstring(archive.read(name))
                text = '\n'.join(t.text or '' for t in xml.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}t'))
                slides.append({'title': text.split('\n')[0], 'text': text})
        data = {'slides': slides}
    elif path.suffix.lower() in ('.md', '.markdown'):
        data = {'slides': markdown_slides(path.read_text(encoding='utf-8-sig'))}
    elif path.suffix.lower() == '.txt':
        data = {'slides': [{'text': text.strip()} for text in path.read_text(encoding='utf-8-sig').split('\n---\n')]}
    else:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    validate(data)
    return data


def markdown_slides(text):
    """Split Markdown decks, preserving separators inside fenced code blocks."""
    lines = text.splitlines()
    # Marp and other Markdown slide tools commonly start with YAML front matter.
    if lines and lines[0].strip() == '---':
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == '---'), None)
        if end is not None and any(re.match(r'^\w[\w-]*\s*:', line) for line in lines[1:end]):
            lines = lines[end + 1:]
    slides, current, fence = [], [], None
    for line in lines:
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if marker:
            run, suffix = marker.groups()
            if fence is None:
                fence = (run[0], len(run))
            elif run[0] == fence[0] and len(run) >= fence[1] and not suffix.strip():
                fence = None
        if fence is None and line.strip() == '---':
            slides.append('\n'.join(current).strip())
            current = []
        else:
            current.append(line)
    slides.append('\n'.join(current).strip())
    result = []
    for content in filter(None, slides):
        heading = re.search(r'^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$', content, re.MULTILINE)
        result.append({'title': heading.group(1) if heading else content.splitlines()[0], 'text': content})
    return result


def validate(data):
    if not isinstance(data, dict) or not isinstance(data.get('slides'), list) or not data['slides']:
        raise ValueError('Presentation must contain a nonempty slides list.')
    glossary = data.get('glossary', {})
    if not isinstance(glossary, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in glossary.items()):
        raise ValueError('Glossary must map source terms to translated terms.')
    for slide in data['slides']:
        if not isinstance(slide, dict) or any(not isinstance(slide.get(k, ''), str) for k in ('title', 'text', 'notes')):
            raise ValueError('Each slide must have text fields: title, text, notes.')
        prepared = slide.get('prepared', [])
        if not isinstance(prepared, list):
            raise ValueError('Prepared translations must be a list.')
        for pair in prepared:
            if not isinstance(pair, dict) or any(not isinstance(pair.get(k), str) or not pair[k].strip() for k in ('source', 'translation', 'target')):
                raise ValueError('Each prepared entry needs source, translation, and target language.')


def recognition_hint(data, index):
    slide = data['slides'][index]
    terms = ', '.join(data.get('glossary', {}))
    return (terms + '\n' + slide.get('title', '') + '\n' + slide.get('text', '') + '\n' + slide.get('notes', ''))[:1200].strip()


def translation_context(data, index, target):
    slide = data['slides'][index]
    return json.dumps({'slide': {k: slide.get(k, '')[:4000] for k in ('title', 'text', 'notes')},
                       'glossary': data.get('glossary', {}) if data.get('target', '').casefold() == target.casefold() else {},
                       'prepared': [p for p in slide.get('prepared', []) if p['target'].casefold() == target.casefold()]}, ensure_ascii=False)[:16000]


def normalized(text):
    text = unicodedata.normalize('NFKC', text).casefold()
    return re.sub(r'[^\w]', '', text)


def prepared_translation(data, index, text, target):
    # Exact normalized matches avoid replacing changed numbers, negations or claims.
    key = normalized(text)
    if not key:
        return None
    matches = {p['translation'] for p in data['slides'][index].get('prepared', [])
               if p['target'].casefold() == target.casefold() and normalized(p['source']) == key}
    return next(iter(matches)) if len(matches) == 1 else None
