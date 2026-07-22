import json
from pathlib import Path

from scripts.jlpt_grammar_epub_pipeline import (
    JP_RUBY_PATTERN,
    canonicalize_entry_ids_in_payload,
    canonicalize_plan_member_ids,
    parse_grammar_markdown,
    ruby_text_to_html,
    validate_plan,
)


def test_parse_counts():
    repo = Path(__file__).resolve().parent.parent
    n5 = parse_grammar_markdown(repo / 'N5_grammar_list.md', 'N5')
    n4 = parse_grammar_markdown(repo / 'N4_grammar_list.md', 'N4')
    assert len(n5) == 84
    assert len(n4) == 132


def test_ruby_pattern_accepts_split_mixed_script():
    assert JP_RUBY_PATTERN.fullmatch('口[くち]コミを見[み]た。')
    assert JP_RUBY_PATTERN.fullmatch('申[もう]し込[こ]みは明日[あした]まで。')


def test_ruby_pattern_rejects_whole_mixed_script_annotation():
    assert not JP_RUBY_PATTERN.fullmatch('口コミ[くちこみ]を見た。')


def test_ruby_to_html():
    html = ruby_text_to_html('早[はや]く寝[ね]たほうがいい。')
    assert '<ruby>早<rt>はや</rt></ruby>' in html
    assert '<ruby>寝<rt>ね</rt></ruby>' in html


def test_canonicalize_plan_member_ids_repairs_wrong_level_prefix():
    repo = Path(__file__).resolve().parent.parent
    entries = parse_grammar_markdown(repo / 'N2_grammar_list.md', 'N2')
    bad_plan = json.loads((repo / 'tests' / 'fixtures' / 'n2_bad_family_plan_wrong_prefix.json').read_text(encoding='utf-8'))

    repaired = canonicalize_plan_member_ids(bad_plan, {entry.entry_id for entry in entries})

    validate_plan(entries, repaired)
    all_ids = [member_id for family in repaired['families'] for member_id in family['member_ids']]
    assert all(member_id.startswith('n2_') for member_id in all_ids)


def test_canonicalize_entry_ids_in_payload_repairs_wrong_level_prefix():
    valid_ids = {'n2_001_ageku', 'n2_002_aruiwa', 'n2_003_bakari'}
    payload = {
        'entry_id': 'n4_001_ageku',
        'contrasts': [
            {'other_entry_id': 'n4_002_aruiwa'},
            {'other_entry_id': 'n4_003_bakari'},
        ],
    }

    repaired = canonicalize_entry_ids_in_payload(payload, valid_ids)

    assert repaired['entry_id'] == 'n2_001_ageku'
    assert [item['other_entry_id'] for item in repaired['contrasts']] == ['n2_002_aruiwa', 'n2_003_bakari']
