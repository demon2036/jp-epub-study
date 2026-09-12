"""Assemble the expanded authored lessons and the reviewed reading corpus."""
from pathlib import Path
from copy import deepcopy
import json
import re

ROOT = Path(__file__).resolve().parent
CORPUS = json.loads((ROOT / 'corpus.json').read_text())
ORDER = CORPUS['main_order'] + CORPUS['supplement_order']

def parse(text):
    return re.findall(r'^## ([^\n]+)\n(.*?)(?=^## |\Z)', text, re.M | re.S)

def plain_ruby(text):
    return re.sub(r'\[[^\]]+\]', '', text)

def clean(text):
    text = re.sub(r'([^\s\[\]、。；：，（）]+)\[([^\]]+)\]', r'\1（\2）', text)
    text = text.replace('值段', '値段').replace('害う', '損なう')
    return text.strip()

def prose_word(item):
    return f'**{item["word"]}（{item["reading"]}）**，{clean(item["meaning"])}'

def reviewed_data(data):
    data = deepcopy(data)
    fixes = {'強行': 'きょうこう', '強硬': 'きょうこう', '畑違い': 'はたけちがい',
             '代替わり': 'だいがわり', '命を育む': 'いのちをはぐくむ',
             '信頼を育む': 'しんらいをはぐくむ', '豊かな心を育む': 'ゆたかなこころをはぐくむ',
             '予めご了承ください': 'あらかじめごりょうしょうください'}
    def visit(value):
        if isinstance(value, dict):
            if value.get('word') in fixes and 'reading' in value:
                value['reading'] = fixes[value['word']]
            for v in value.values(): visit(v)
        elif isinstance(value, list):
            for v in value: visit(v)
    visit(data)
    return data

def reviewed_readings(char, data):
    rows = deepcopy(data['readings'])
    for row in rows:
        kana = row['kana']
        # Keep the source key for the coverage audit, while correcting the lesson.
        row['baseline_kana'] = kana
        if char == '貝' and kana == 'カイ':
            row['kana'] = 'かい'
            row['type'] = '训读 · 复合词中的同一读音'
            row['usage'] = '貝類里的かい仍是日语的贝类名称，后面接表示类别的るい。一个和语词可以和字音成分组合；再换上表示毒、遗址或肌肉的成分，就得到貝毒、貝塚、貝柱。'
            row['takeaway'] = '把かい当作同一个“贝”来认：实物是貝，分类是貝類，遗址是貝塚。复合词后半部分改变了谈论角度。'
        kinds = {
            ('仕', 'し'): '字音；仕事中的し另由する而来',
            ('課', 'かす'): '字音构成的动词',
            ('昨', 'きのう'): '整词读法 · 昨日',
            ('海', 'あま'): '整词读法 · 海女',
            ('流', 'はやる'): '整词表记 · 流行る',
            ('栄', 'え'): '借字表记 · 見栄',
            ('埼', 'さい'): '地名读法 · 埼玉',
            ('神', 'こう'): '地名读法 · 神戸',
        }
        row['type'] = kinds.get((char, kana), row['type'])
        if char == '科' and kana == 'とが':
            row['example_sentence']['kana'] = 'かれはとがをおかしたことをくいている。'
        if char == '四' and kana == 'よっ':
            row['kana'] = 'よっつ'
            row['usage'] = '四つ（よっつ）是和语数物的一整个形式。数到四个物件时，よっつ中间停一拍；数日期则用四日（よっか），换成日数单位か，同样保留停顿。把两词各读完整，声音和用途就会一起留下。'
            row['takeaway'] = '物件四个是よっつ，日期四日是よっか。它们属于同一和语数词家族，各自保留固定词尾。'
        if char == '強' and kana == 'ごう':
            row['usage'] = 'ごう见于強引、強盗、強奪等固定词，常能接到硬推、强夺这一画面。与強化（きょうか）、強行（きょうこう）的きょう放在一起，能看出相近意思的词也会各自保留不同字音。'
            row['examples'] = [dict(word='強情', reading='ごうじょう', meaning='固执、倔强', link='态度硬，不愿改变主意；把强硬放到性格上。'),
                               dict(word='強盗', reading='ごうとう', meaning='强盗；抢劫', link='用暴力强取，把硬夺的动作画出来。'),
                               dict(word='強奪', reading='ごうだつ', meaning='强行夺取', link='夺走对象这一动作带着强力，是ごう这一词族的另一入口。')]
            row['takeaway'] = '用強引、強盗、強奪接住ごう的声音；说强行执行则读強行（きょうこう），词义相近也要认准完整词。'
        if char == '畑' and kana == 'はた':
            row['usage'] = 'はた常在畑作（はたさく）、畑地（はたち）等复合词中出现，仍指非水田的耕地。单独谈一块田，常说はたけ；比喻专业领域的畑違い也保留はたけ，读はたけちがい。'
            row['takeaway'] = '畑作、畑地把はた与农业组合连起来；畑違い（はたけちがい）则从完整的はたけ伸向不同专业领域。'
        if char == '草' and kana == 'ぐさ':
            row['usage'] = 'くさ在一些复合词后半读成ぐさ。言い草、笑い草、語り草把草这一可取用的材料感，伸向说话内容、笑料和谈资；前半动词说明这些材料被用来做什么。'
            row['example_sentence']['jp_ruby'] = 'その言い草は失礼です。'
            for e in row['examples']:
                if e['word'] == '食い草':
                    e.update(word='語り草', reading='かたりぐさ', meaning='谈资；人们长久谈论的话题', link='語り是讲述，草把内容当作可反复讲述的材料，和笑い草的笑料并看。')
        if char == '代' and kana == 'よ':
            row['usage'] = 'よ指世代、时代，见神代（かみよ）、千代（ちよ）、御代（みよ），也见较有文语感的代々（よよ）。把时间想成一代接一代的长度，よ就能与世（よ）的时代感连起来。'
            for e in row['examples']:
                if e['word'] == '代替わり':
                    e.update(word='千代', reading='ちよ', meaning='千代；很长久的岁月', link='用许多世代的接续表示长久，常见于祝愿或诗歌。')
                elif e['word'] == '代々':
                    e['link'] = 'よよ是带文语色彩的读法；日常叙述世代相传也常读だいだい。'
        if char == '交' and kana == 'まざる':
            row['usage'] = '交ざる（まざる）表示不同成分混在同一群体、同一范围里。用交字时，常把成分各自仍能辨认的画面放在前面：大人中混有孩子，沙子里夹着小石。'
            row['anchor'].update(word='大人に子どもが交ざる', reading='おとなにこどもがまざる', meaning='孩子混在大人中', hint='先看同一群体里的不同成员，大人与孩子各自仍能认出来。')
            row['example_sentence'].update(jp_ruby='大人に子どもが交ざって遊んでいる。', kana='おとなにこどもがまざってあそんでいる。', zh='孩子们混在大人中一起玩。', note='交ざる报告不同成员已在同一群体中；谁安排他们凑在一起，可以另说交ぜる。颜色融为一体时常写混ざる。')
            row['takeaway'] = 'まざる看已经混在一起的状态；用交字，把各成分仍可辨认的画面留在眼前。'
        if char == '交' and kana == 'まぜる':
            row['usage'] = '交ぜる（まぜる）把不同成员或物件放在一起：洗牌，把孩子编进大人的队伍，或在谈话里夹入英语。它让实施混入、调换顺序的动作成为重点。'
            row['anchor'].update(word='トランプを交ぜる', reading='トランプをまぜる', meaning='洗牌、把纸牌混合', hint='手把纸牌次序打乱，每张牌仍然是一张可辨认的牌。')
            row['example_sentence'].update(jp_ruby='ゲームの前に、トランプをよく交ぜます。', kana='げーむのまえに、とらんぷをよくまぜます。', zh='游戏开始前，先把牌充分洗匀。', note='这里的を标出主动混合的对象。把颜料融在一起通常写混ぜる，牌各自仍可辨认则适合交ぜる。')
            for e in row['examples']:
                if e['word'] == '二つの色を交ぜる':
                    e.update(word='チームに子どもを交ぜる', reading='チームにこどもをまぜる', meaning='把孩子编入队伍', link='不同成员放进同一组，孩子仍是可辨认的成员。')
        if char == '暗' and kana == 'くらます':
            row['examples'] = [e for e in row['examples'] if e['word'] != '部屋を暗ます']
        if char == '行' and kana == 'ぎょう':
            for e in row['examples']:
                if e['word'] == '一行':
                    e.update(meaning='一行文字', link='文字排成的一行读いちぎょう；同行的一伙人则读いっこう。把文字页和旅行团分成两个画面。')
        if char == '代' and kana == 'かえる':
            row['example_sentence'].update(jp_ruby='書面をもって挨拶に代えます。', kana='しょめんをもってあいさつにかえます。', zh='谨以书面代替当面致意。', note='让书面表达承担原本由当面致辞承担的作用，所以是“挨拶に代える”。代父亲发言则说父に代わって挨拶する。')
            for e in row['examples']:
                if e['word'] == '父に代えて':
                    e.update(word='挨拶に代えて', reading='あいさつにかえて', meaning='以此代替致辞', link='文章或简短发言接过原本致辞的作用，常用作正式文字的收尾或标题。')
        if char == '給' and kana == 'たまう':
            row['usage'] = '給う（たまう）在古典中可表示赐予，也可接在其他动词后抬高动作主体。现代小说中的命令式〜たまえ另有鲜明口气：上级、长辈或自居高位者要求对方行动。读“待ち給え”，要把人物关系也读出来。'
            row['example_sentence']['note'] = '待ち給え在这里是居上位者说“你且等一下”的命令口气；给同事礼貌提出请求时可以说少し待ってください。'
            for e in row['examples']:
                if e['word'] == '待ち給え':
                    e.update(meaning='你且等一下（居上位者的命令口吻）', link='たまえ是たまう的命令形。现代这种用法带出说话人的身份、姿态或旧式人物口吻。')
            row['takeaway'] = '古典たまう可以抬高动作主体；现代“〜たまえ”则要听出居上位者的命令口吻。两种场景都从整个表达来认。'
        if char == '詩' and kana == 'うた':
            row['anchor']['word'] = '詩'
            for e in row['examples']:
                e['word'] = e['word'].replace('詩（うた）', '詩')
        if char == '害' and kana == 'そこなう':
            row['anchor']['word'] = '健康を損なう'
            row['usage'] = 'そこなう表示损伤健康、名誉、利益等原本应保持的良好状态。现代通常写損なう；在害字的读音中认到它时，也把“使受损”这条意义联系接回来。'
        if char == '仕' and kana == 'し':
            row['usage'] = '仕有し这一字音，如奉仕（ほうし）。仕事（しごと）里的し则来自する的连用形：做某件事。字相同，词的组成各有来路；把工作当作“要做的事”，最容易接回这个词。'
        if char == '海' and kana == 'あま':
            row['usage'] = '海女（あま）是潜水采集贝类、海藻等的女性。あま也可以写海人，指以海为生的人；读海女时，把两个汉字一起对应这个职业名。'
        if char == '栄' and kana == 'え':
            row['usage'] = '見栄（みえ）从見える的見え联系到“显给别人看的样子”。栄这个字突出体面、显眼的感觉；見栄を張る便是撑起好看的外表，常指逞强、讲排场。'
        if char == '課' and kana == 'かす':
            row['usage'] = '課す（かす）把字音か接到する／す这一动词化系统上，表示给人加上任务、义务或负担。宿題を課す、税を課す，都是把一项需要承担的事情加到对象身上。'
        if char == '等' and kana == 'とう':
            row['usage'] += ' 基本字音とう见于等分（とうぶん）、等級（とうきゅう）；平等（びょうどう）把这一成分读成どう。'
        if char == '昔' and kana == 'しゃく':
            row['usage'] += ' 今昔（こんじゃく）中听到的是浊音じゃく；昔的这一字音以しゃく为基本形式。'
        if char == '埼' and kana == 'さい':
            row['usage'] = '埼玉（さいたま）是需要整体认出的地名。旧名さきたま留下了由来线索；现代県名固定为さいたま，さきたま也继续保存在相关古地名、设施名里。'
        if char == '笑' and kana == 'えむ':
            row['usage'] += ' えむ是微笑；微笑む（ほほえむ）把“脸颊上含笑”的整个词写成这三个字。'
        if char == '引' and kana == 'ひける':
            for item in row['examples']:
                if item['word'] == '日が引ける':
                    item.update(word='仕事が引ける', reading='しごとがひける', meaning='工作结束、下班', link='结束当天的工作，从工作场所退出；这一用法也常写退ける。')
        row = json.loads(json.dumps(row, ensure_ascii=False).replace('害う', '損なう'))
    return rows

def example(row):
    s = row['example_sentence']
    return '\n\n'.join('> ' + value for value in [plain_ruby(s['jp_ruby']), s['kana'], s['zh']])

def group_md(group, heading):
    text = [f'### {heading}', clean(group['why_it_works'])]
    text.extend(prose_word(item) + '。' + clean(item.get('note', '')) for item in group['items'])
    text.append('**' + clean(group['takeaway']) + '**')
    return '\n\n'.join(text)

def assemble(allow_partial=False):
    extras = {}
    for path in sorted((ROOT / 'extra-readings').glob('*.md')):
        for title, body in parse(path.read_text()):
            char, kana, word, reading, kind = title.split('｜')
            assert len(body) >= 160 and body.count('> ') >= 3, ('Extra reading needs explanation and example', title)
            extras.setdefault(char, []).append({'kana': kana, 'word': word, 'reading': reading, 'kind': kind, 'body': body.strip()})
    authored = {}
    for path in sorted((ROOT / 'editorial').glob('*.md')):
        for title, body in parse(path.read_text()):
            char, heading = title.split('｜', 1)
            assert char not in authored, ('duplicate authored chapter', char)
            q = re.search(r'^@question (.+)$', body, re.M)
            a = re.search(r'^@answer (.+)$', body, re.M)
            assert q and a, ('chapter needs a reasoning question and answer', char)
            body = re.sub(r'^@(?:question|answer) .+\n?', '', body, flags=re.M).strip()
            assert len(body) >= 350, ('authored explanation too short', char, len(body))
            authored[char] = (heading, body, q[1], a[1])
    trials = {h[0]: (h.split('｜', 1)[1], b) for h, b in parse((ROOT / 'trial-chapters.md').read_text())}
    trial_manifest = json.loads((ROOT / 'trial-readings.json').read_text())
    trial_answers = dict(re.findall(r'<h2 id="answer-[^"]+">([^<]+)</h2>\s*(.*?)(?=<h2 |\Z)', (ROOT / 'trial-answers.md').read_text(), re.S))
    missing = [c for c in ORDER if c not in trials and c not in authored]
    if missing and not allow_partial:
        raise AssertionError(('Missing authored explanations', ''.join(missing)))
    lessons, manifest, answers = [], {}, {}
    for char in ORDER:
        if char in missing:
            continue
        if char in trials:
            title, body = trials[char]
            rows = deepcopy(trial_manifest['chapters'][char])
            for row in rows:
                row['baseline_kana'] = row['kana']
            answer = next((b for h, b in trial_answers.items() if h.startswith(char)), None)
            assert answer, ('Trial answers not found', char)
            body = re.sub(r'answers\.xhtml#answer-[a-f0-9]+', f'answers-{ord(char):x}.xhtml', body)
            answer = answer.split('<h2 id="mixed-answers">', 1)[0].strip()
            answers[char] = answer
            lessons.append({'char': char, 'title': title, 'body': body, 'kind': 'main' if char in CORPUS['main_order'] else 'supplement'})
            manifest[char] = rows
            continue
        title, lead, question, answer = authored[char]
        data = reviewed_data(CORPUS['data'][char])
        rows = reviewed_readings(char, data)
        parts = [lead]
        navigation = []
        for index, row in enumerate(rows, 1):
            a = row['anchor']
            heading = f'{row["kana"]} · {a["word"]}：{a["meaning"]}'
            navigation.append({'kana': row['kana'], 'baseline_kana': row['baseline_kana'], 'word': a['word'], 'kind': row['type'], 'section': heading})
            paras = [f'### {heading}', clean(row['usage']), example(row)]
            note = clean(row['example_sentence'].get('note', ''))
            hint = clean(a.get('hint', ''))
            if note:
                paras.append(note)
            related = [prose_word(e) + '。' + clean(e.get('link', '')) for e in row['examples']]
            if related:
                paras.append('把这个用法向外展开：\n\n' + '\n\n'.join(related))
            if hint and hint not in note:
                paras.append('回想这个词时，' + hint[0].lower() + hint[1:])
            paras.append('**' + clean(row['takeaway']) + '**')
            parts.append('\n\n'.join(paras))
        for row in extras.get(char, []):
            assert row['kana'] not in [r['kana'] for r in navigation], ('Duplicate extra reading', char, row['kana'])
            heading = f'{row["kana"]} · {row["word"]}：把读音接回词的构成'
            navigation.append({'kana': row['kana'], 'baseline_kana': row['kana'], 'word': row['word'], 'kind': row['kind'], 'section': heading})
            parts.append('### ' + heading + '\n\n' + row['body'])
        # One substantial contrast keeps the lesson focused while adding a new usage decision.
        near = data['near_synonym_groups'][0] if data['near_synonym_groups'] else None
        if near:
            parts.append(group_md(near, near['title']))
        elif data['scenario_contrast_groups']:
            near = data['scenario_contrast_groups'][0]
            parts.append(group_md(near, near['title']))
        anchors = '；'.join(r['anchor']['word'] for r in rows)
        anchor_answers = '；'.join(f'{r["anchor"]["word"]}：{r["anchor"]["reading"]}' for r in rows)
        if extras.get(char):
            anchors += '；' + '；'.join(r['word'] for r in extras[char])
            anchor_answers += '；' + '；'.join(f'{r["word"]}：{r["reading"]}' for r in extras[char])
        target = next((r for r in rows if len(r['kana']) >= 3 and '音读' not in r['type']), rows[0])
        sentence = target['example_sentence']
        if near:
            selection = near['items'][:3]
            words = '、'.join(e['word'] for e in selection)
            q4 = f'把「{words}」分别放进一个适合的场景，说出你选择它的理由。'
            a4 = '；'.join(f'{e["word"]}（{e["reading"]}）：{e["meaning"]}。{clean(e.get("note", ""))}' for e in selection)
        else:
            q4 = '把本章的中心画面换到另一个对象上，说出两个相关词，并说明它们的联系。'
            a4 = '；'.join(f'{e["word"]}（{e["reading"]}）：{e["meaning"]}。{clean(e.get("link", ""))}' for e in rows[0]['examples'][:2])
        questions = [f'读出并解释这些词：{anchors}。', question,
                     f'用本章的词表达：“{sentence["zh"]}”说明句中谁在发生变化、做动作或承载这个性质。', q4]
        answer_items = [anchor_answers + '。', answer,
                        plain_ruby(sentence['jp_ruby']) + f'（{sentence["kana"]}）' + clean(sentence.get('note', '')), a4]
        parts.append('### 遮住上文，试着把关系找回来\n\n' + '\n\n'.join(f'{i}. {q}' for i, q in enumerate(questions, 1))
                     + f'\n\n[查看答案与理由](answers-{ord(char):x}.xhtml)')
        answers[char] = '\n\n'.join(f'{i}. {a}' for i, a in enumerate(answer_items, 1))
        lessons.append({'char': char, 'title': title, 'body': '\n\n'.join(parts), 'kind': 'main' if char in CORPUS['main_order'] else 'supplement'})
        manifest[char] = navigation
    baseline = {c['kanji']: [r['kana'] for r in c['readings']] for c in CORPUS['baseline']}
    for char in manifest:
        if char not in baseline:
            continue
        actual = {r['baseline_kana'] for r in manifest[char]}
        assert set(baseline[char]) <= actual, (char, 'Missing source reading', set(baseline[char]) - actual)
    result = {'order': ''.join(d['char'] for d in lessons), 'main_order': CORPUS['main_order'],
              'supplement_order': CORPUS['supplement_order'], 'missing_authored': missing,
              'lessons': lessons, 'readings': manifest, 'answers': answers, 'baseline_readings': baseline}
    (ROOT / 'assembled.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (ROOT / 'chapters.md').write_text('\n\n'.join('## ' + d['char'] + '｜' + d['title'] + '\n\n' + d['body'] for d in lessons))
    print(json.dumps({'chapters': len(lessons), 'missing_authored': ''.join(missing), 'reading_entries': sum(map(len, manifest.values())), 'text_characters': sum(len(d['body']) for d in lessons)}, ensure_ascii=False))

if __name__ == '__main__':
    import sys
    assemble('--partial' in sys.argv)
