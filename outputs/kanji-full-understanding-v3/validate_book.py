"""Validate the delivered book's coverage, reading destinations and internal links."""
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit
import json
import posixpath
import re
import zipfile
from bs4 import BeautifulSoup
from lxml import etree

ROOT = Path(__file__).resolve().parent
EPUB = ROOT / '日语为什么这样读_226字完整理解版.epub'
assembled = json.loads((ROOT / 'assembled.json').read_text())
original = json.loads((ROOT / 'corpus.json').read_text())['baseline']
expected = {x['kanji']: [r['kana'] for r in x['readings']] for x in original}
assert expected == assembled['baseline_readings']
assert len(original) == 226 and len(assembled['lessons']) == 232
assert not assembled['missing_authored']
coverage = json.loads((ROOT / 'reading-coverage.json').read_text())
assert coverage['baseline_covered'] == coverage['baseline_entries'] == 742
assert not coverage['missing']
assert len(coverage['entries']) == 824

with zipfile.ZipFile(EPUB) as archive:
    names = set(archive.namelist())
    trees = {n: etree.fromstring(archive.read(n)) for n in names if n.endswith(('.xhtml', '.opf', '.ncx'))}
    soups = {n: BeautifulSoup(archive.read(n), 'xml') for n in names if n.endswith('.xhtml')}
    ids = {}
    for name, tree in trees.items():
        found = tree.xpath('//@id')
        assert len(found) == len(set(found)), (name, 'duplicate ids')
        ids[name] = set(found)
    internal_refs = 0
    for name, tree in trees.items():
        for ref in tree.xpath('//@href|//@src'):
            url = urlsplit(ref)
            assert not url.scheme and not url.netloc, (name, 'unexpected external reference', ref)
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(url.path))) if url.path else name
            assert target in names, (name, ref, 'target missing')
            if url.fragment:
                assert unquote(url.fragment) in ids.get(target, set()), (name, ref, 'anchor missing')
            internal_refs += 1
    chapter_paths = [n for n in names if re.fullmatch(r'EPUB/char-[a-f0-9]+\.xhtml', n)]
    assert len(chapter_paths) == 232
    reading_links = 0
    chapter_questions = 0
    chapter_answers = 0
    example_cards = 0
    for lesson in assembled['lessons']:
        c = lesson['char']; soup = soups[f'EPUB/char-{ord(c):x}.xhtml']
        links = soup.select('.readinglink')
        assert len(links) == len(assembled['readings'][c])
        reading_links += len(links)
        for card in soup.select('.example'):
            assert len(card.select('.jp')) == len(card.select('.reading')) == len(card.select('.translation')) == 1
            assert not re.search(r'[一-鿿]', card.select_one('.reading').get_text()), (c, 'unread kanji in kana line')
        practice = soup.find(id=f'practice-{ord(c):x}')
        assert practice
        questions = practice.find_next_sibling('ol').find_all('li', recursive=False)
        assert len(questions) == 4, (c, 'question count')
        chapter_questions += len(questions)
        ans = soups[f'EPUB/answers-{ord(c):x}.xhtml']
        answers = ans.find('ol').find_all('li', recursive=False)
        assert len(answers) == 4, (c, 'answer count')
        chapter_answers += len(answers)
    for entry in coverage['entries']:
        c = entry['character']; soup = soups[f'EPUB/char-{ord(c):x}.xhtml']
        target = soup.find(id=entry['anchor']); assert target
        parts = [target]
        for node in target.next_siblings:
            if getattr(node, 'name', None) in {'h2', 'h3'}: break
            parts.append(node)
        fragment = BeautifulSoup(''.join(str(x) for x in parts), 'html.parser')
        assert len(fragment.get_text()) >= 160 and fragment.select('.example')
        assert entry['kana'] in fragment.get_text()
    for soup in soups.values():
        example_cards += len(soup.select('.example'))
        assert not soup.find('script')
        assert not re.search(r'没找到|不能证明|待补充|TODO|placeholder|ごうこう|はたちがい', soup.get_text())
    mixed_questions = soups['EPUB/practice.xhtml'].find_all('h2')
    mixed_questions = [h for h in mixed_questions if re.match(r'\d{2}｜', h.get_text())]
    mixed_answers = soups['EPUB/practice-answers.xhtml'].find_all('h3')
    assert len(mixed_questions) == len(mixed_answers) == 20

web_files = [ROOT / '阅读预览.html'] + sorted((ROOT / 'preview').glob('*.html'))
web_soups = {p: BeautifulSoup(p.read_text(), 'html.parser') for p in web_files}
web_ids = {p: {n['id'] for n in s.select('[id]')} for p, s in web_soups.items()}
web_refs = 0
for path, soup in web_soups.items():
    for el in soup.select('[href], [src]'):
        ref = el.get('href', el.get('src')); url = urlsplit(ref)
        assert not url.scheme and not url.netloc, (path, ref)
        target = (path.parent / unquote(url.path)).resolve() if url.path else path
        assert target.exists(), (path.name, ref, 'web target missing')
        if url.fragment:
            assert unquote(url.fragment) in web_ids.get(target, set()), (path.name, ref, 'web anchor missing')
        web_refs += 1
index_links = web_soups[ROOT / '阅读预览.html'].select('a.indexcard')
assert len(index_links) == 232
report = dict(chapters=232, baseline_entries=742, reading_entries=reading_links,
              chapter_questions=chapter_questions, chapter_answers=chapter_answers,
              mixed_questions=len(mixed_questions), mixed_answers=len(mixed_answers),
              example_cards_in_all_pages=example_cards, epub_internal_references=internal_refs,
              preview_pages=len(web_files), preview_internal_references=web_refs, errors=[])
(ROOT / 'qa/structure-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False, indent=2))
