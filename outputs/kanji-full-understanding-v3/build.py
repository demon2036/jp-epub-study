"""Package the authored full edition, with complete per-record navigation."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import html
import json
import re
import sys
import uuid

from bs4 import BeautifulSoup
from ebooklib import epub
from PIL import Image, ImageDraw, ImageFont
import layout

ROOT = Path(__file__).resolve().parent
TITLE = '日语为什么这样读'
EDITION = '226字完整理解版'
EPUB_PATH = ROOT / f'{TITLE}_{EDITION}.epub'
ESC = html.escape
STYLE = layout.STYLE + '''
.indexgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,12em),1fr));gap:.8em;}
.indexcard{display:block;padding:.7em .9em;border:1px solid #dce5da;text-decoration:none;line-height:1.65;}
.indexcard .glyph{float:left;font-size:1.8em;margin-right:.45em;line-height:1.5;}
.indexcard .title{font-size:.82em;display:block;}.indexcard .meta{font-size:.7em;color:#657970;display:block;}
.group-heading{clear:both;} .smallprint{font-size:.8em;color:#63796b;}
'''
WEBSTYLE = '''
:root{--reading-size:19px}body{margin:0;font-size:var(--reading-size);background:#f3f1e9;}
.topbar{position:sticky;top:0;z-index:5;background:#164f47;color:white;display:flex;
 align-items:center;flex-wrap:wrap;gap:8px 18px;padding:12px 4%;font:14px/1.65 sans-serif;}
.topbar a{color:white;text-decoration:none}.tools{display:flex;gap:7px;margin-left:auto;}
button{border:1px solid #9ab9aa;background:transparent;color:white;padding:5px 10px;border-radius:3px;
font:14px/1.6 sans-serif;cursor:pointer}button:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid #bd843e;outline-offset:3px;}
.shell{max-width:1160px;margin:auto;display:grid;grid-template-columns:230px minmax(0,1fr);}
.side{position:sticky;top:90px;align-self:start;padding:25px 20px;max-height:77vh;overflow-y:auto;font:14px/1.8 sans-serif;}
.side a{text-decoration:none;color:#45634f}.side li{margin:.6em 0;}.side ol{padding-left:1.45em}
main{min-width:0;padding:32px 48px 70px;background:white;}h1,h2,h3,[id]{scroll-margin-top:120px;}
.hide-kana .reading{visibility:hidden;}.bookhead{text-align:center;margin:0 0 2em;}
.webcover{display:block;width:235px;max-width:70%;margin:0 auto 25px;box-shadow:0 7px 24px #213f3722;}
.download{display:inline-block;background:#164f47;color:white;padding:10px 20px;font:15px/1.8 sans-serif;text-decoration:none;border-radius:3px;}
#search{display:block;box-sizing:border-box;width:100%;border:1px solid #92af9d;padding:12px 14px;background:#fbfcf8;
 color:#263c32;font:17px/1.6 sans-serif;margin:1.2em 0 .4em;border-radius:3px;}
[hidden]{display:none!important}.searchcount{font:14px/1.8 sans-serif;color:#607464;}
@media(max-width:820px){.shell{display:block}.side{display:none}main{padding:26px 6% 55px;}
 .topbar{padding:10px 5%;gap:7px 13px}.tools{margin-left:0}.example{padding:.75em .85em}
 h1,h2,h3,[id]{scroll-margin-top:140px;}.hero{font-size:3.4em}.webcover{width:220px;}}
@media(max-width:360px){.readinggrid,.indexgrid{grid-template-columns:minmax(0,1fr)}}
@media print{.side,.topbar,.download,#search,.searchcount{display:none}.shell{display:block}main{padding:0}.pager{display:none}}
'''
SCRIPT = '''
let readingSize=19;
function changeSize(d){readingSize=Math.max(16,Math.min(26,readingSize+d));document.documentElement.style.setProperty('--reading-size',readingSize+'px');}
document.querySelector('#smaller').addEventListener('click',()=>changeSize(-1));
document.querySelector('#larger').addEventListener('click',()=>changeSize(1));
document.querySelector('#kana-toggle').addEventListener('click',function(){const h=document.body.classList.toggle('hide-kana');this.setAttribute('aria-pressed',String(h));this.textContent=h?'显示假名':'隐藏假名';});
const search=document.querySelector('#search');if(search){search.addEventListener('input',function(){
const q=this.value.trim().toLowerCase();let n=0;document.querySelectorAll('.indexcard').forEach(el=>{const hit=!q||el.dataset.search.toLowerCase().includes(q);el.hidden=!hit;if(hit)n++;});
document.querySelectorAll('.indexgroup').forEach(el=>{el.hidden=!el.querySelector('.indexcard:not([hidden])');});
document.querySelector('#searchcount').textContent=n?'找到 '+n+' 章':'没有匹配章节';});}
'''

def cover(reading_count, chapters, exercises):
    im = Image.new('RGB', (1200, 1800), '#f4f1e7')
    dr = ImageDraw.Draw(im)
    def put(x, y, value, size, color='#164f47', heavy=False):
        font=ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-'+('Bold' if heavy else 'Regular')+'.ttc',size)
        dr.text((x,y),value,font=font,fill=color)
    dr.rectangle((70,75,1130,1725),outline='#c5d0c4',width=2)
    put(130,145,TITLE,83,heavy=True)
    put(137,280,'226字 · 完整理解版',47,'#9b613d')
    dr.line((138,405,1062,405),fill='#9b613d',width=3)
    put(138,465,'把声音接到场景',58,heavy=True)
    put(138,550,'让一个词带出一组词',58,heavy=True)
    for i,c in enumerate('下生言書光新動語日理'):
        put(146+(i%5)*185,755+(i//5)*220,c,138)
    dr.line((138,1285,1062,1285),fill='#c5d0c4',width=2)
    put(138,1350,'逐项读音 · 构词来路 · 例句与练习',34,'#546b5d')
    put(138,1420,f'{chapters} 章  /  {reading_count} 项读音讲解',34,'#546b5d')
    put(138,1490,f'{exercises} 道回想练习与答案',34,'#546b5d')
    put(138,1615,'个人日语学习读本 · 第三版',28,'#718075')
    im.save(ROOT/'cover.jpg',quality=94)

def pager(prev_path=None,next_path=None,answer_path=None):
    links=['<a href="contents.xhtml">全书目录</a>']
    if prev_path: links.append(f'<a href="{prev_path}">上一章</a>')
    if next_path: links.append(f'<a href="{next_path}">下一章</a>')
    if answer_path: links.append(f'<a href="{answer_path}">本章答案</a>')
    return '<nav class="pager">'+'　·　'.join(links)+'</nav>'

def main():
    assembled=json.loads((ROOT/'assembled.json').read_text())
    partial='--partial' in sys.argv
    assert partial or not assembled['missing_authored'], 'Finish every authored chapter before publishing'
    lessons=assembled['lessons']; manifest=assembled['readings']; order=assembled['order']
    readings=sum(map(len,manifest.values()))
    mixed_md=(ROOT/('practice.md' if (ROOT/'practice.md').exists() else 'trial-practice.md')).read_text()
    mixed_answers=(ROOT/'practice-answers.md').read_text() if (ROOT/'practice-answers.md').exists() else (ROOT/'trial-answers.md').read_text().split('<h2 id="mixed-answers">',1)[1].split('</h2>',1)[1]
    mixed_md=mixed_md.replace('answers.xhtml#mixed-answers','practice-answers.xhtml')
    mixed_count=len(re.findall(r'^## ',mixed_md,re.M))
    # Current trial practice uses numbered h2s; route section is excluded.
    mixed_count=len(re.findall(r'^## [一二三四五六七八九十\d]+[、．.｜：：]',mixed_md,re.M)) or 8
    exercises=len(lessons)*4+mixed_count
    cover(readings,len(lessons),exercises)
    groups=[]
    original=json.loads((ROOT/'corpus.json').read_text())['baseline']
    for grade in sorted({x['grade'] for x in original}):
        chars=''.join(x['kanji'] for x in original if x['grade']==grade and x['kanji'] in order)
        if chars: groups.append((f'group-{grade}',f'第{grade}组 · {chars[0]}—{chars[-1]}',chars))
    supp=''.join(c for c in assembled['supplement_order'] if c in order)
    if supp: groups.append(('supplements','联读篇 · 六个连接全书的字',supp))
    lookup={d['char']:d for d in lessons}
    index=['<h1>全书目录</h1>',f'<p>{len(lessons)}章 · {readings}项读音讲解 · {exercises}道练习与答案</p>',
           '<p><a href="intro.xhtml">导读：为什么这样读</a>　·　<a href="patterns.xhtml">声音与构词的连接方法</a>　·　<a href="practice.xhtml">混合场景</a>　·　<a href="answer-index.xhtml">答案目录</a></p>']
    index.append('<div class="web-search"><label for="search" class="smallprint">按汉字、假名、例词或讲解主题查找</label><input id="search" type="search" placeholder="例如：生、かえる、连浊、r／s"/><p id="searchcount" class="searchcount" aria-live="polite">全部章节</p></div>')
    for gid,title,chars in groups:
        index.append(f'<section class="indexgroup" id="{gid}"><h2 class="group-heading">{title} · {len(chars)}字</h2><div class="indexgrid">')
        for c in chars:
            lesson=lookup[c]; kana=' '.join(r['kana'] for r in manifest[c]); words=' '.join(r['word'] for r in manifest[c])
            searchable=c+' '+lesson['title']+' '+kana+' '+words
            index.append(f'<a class="indexcard" data-search="{ESC(searchable)}" href="char-{ord(c):x}.xhtml"><span class="glyph" lang="ja">{c}</span><span class="title">{ESC(lesson["title"])}</span><span class="meta">{len(manifest[c])}项读音 · 4道练习</span></a>')
        index.append('</div></section>')
    index_html=''.join(index)
    epub_index=BeautifulSoup(index_html,'html.parser')
    epub_index.select_one('.web-search').decompose()
    for el in epub_index.select('[data-search]'): del el['data-search']
    docs=[('contents.xhtml','全书目录',str(epub_index),None)]
    source_intro=(ROOT/'intro.md').read_text()
    source_intro=source_intro.replace('这本书仍然读十个字：**下、上、出、入、起、落、止、動、開、照**。每章先用一个具体场景讲动词，再把读音、构词、句子和常见新词接起来。','这本书完整整理原清单中的 **226 个字、742 条读音记录**，并保留「上、入、起、落、照、雨」六个联读字。每章先用具体场景说明词义、构词与声音的联系，再逐项展开读音、例句和常见新词。')
    source_intro=source_intro.replace('前三道回想动词与句子，第四道把本章其余读音和词义串起来。','先回想读音，再解释构词关系，随后把词放回句子与相邻场景。')
    for path,title,source in [('intro.xhtml','导读｜从场景理解声音',source_intro),('patterns.xhtml','声音与构词的连接方法',(ROOT/'patterns.md').read_text() if (ROOT/'patterns.md').exists() else '# 声音与构词的连接方法\n\n从每章的场景出发，回想词干、构词、连浊和字音之间的关系。')]:
        fragment,heads,n,cov=layout.render(source,path.removesuffix('.xhtml'))
        docs.append((path,title,fragment+pager(),None))
    total_examples=0; cover_rows=[]; char_counts={}; chapter_titles={}; heading_map={}
    for idx,lesson in enumerate(lessons):
        c=lesson['char'];docid=f'char-{ord(c):x}';path=docid+'.xhtml'
        fragment,headings,n,coverage=layout.render(lesson['body'],docid,c,manifest[c])
        total_examples+=n;cover_rows.extend(coverage);heading_map[c]=headings
        fragment=fragment.replace('answers.xhtml#answer-'+format(ord(c),'x'),f'answers-{ord(c):x}.xhtml')
        covered={r['anchor'] for r in coverage}
        local='<nav class="localtoc" aria-label="本章讲解"><p class="label">先看联系，再逐项读</p>'+''.join(f'<p><a href="#{anchor}">{ESC(t)}</a></p>' for anchor,t in headings if anchor not in covered)+'</nav>'
        body=(f'<p class="eyebrow">{"逐字理解" if lesson["kind"]=="main" else "联读篇"} · {idx+1:03d} / {len(lessons)}</p>'
              f'<div class="hero" lang="ja">{c}</div><h1>{ESC(lesson["title"])}</h1>'
              +layout.reading_navigation(coverage)+local+fragment)
        body+=pager(f'char-{ord(order[idx-1]):x}.xhtml' if idx else 'intro.xhtml',f'char-{ord(order[idx+1]):x}.xhtml' if idx+1<len(order) else 'practice.xhtml',f'answers-{ord(c):x}.xhtml')
        char_counts[c]=len(BeautifulSoup(body,'html.parser').get_text())
        chapter_titles[c]=c+'｜'+lesson['title']
        docs.append((path,chapter_titles[c],body,c))
    for path,title,source in [('practice.xhtml','混合场景与回想路线',mixed_md),('practice-answers.xhtml','混合场景答案',mixed_answers)]:
        frag,heads,n,_=layout.render(source,path.removesuffix('.xhtml'))
        total_examples+=n; docs.append((path,title,frag+pager(),None))
    answer_index='<h1>逐章练习答案</h1><p>先完成章末的回想题，再对照理由。</p><div class="indexgrid">'+''.join(f'<a class="indexcard" href="answers-{ord(c):x}.xhtml">{ESC(chapter_titles[c])}</a>' for c in order)+'</div>'+pager()
    docs.append(('answer-index.xhtml','逐章练习答案',answer_index,None))
    for c in order:
        frag,heads,n,_=layout.render(assembled['answers'][c],f'answers-{ord(c):x}')
        total_examples+=n
        docs.append((f'answers-{ord(c):x}.xhtml',c+'｜练习答案',f'<h1>{c}｜答案与理由</h1>'+frag+f'<p><a href="char-{ord(c):x}.xhtml#practice-{ord(c):x}">回到本章练习</a>　·　<a href="answer-index.xhtml">答案目录</a></p>',None))
    book=epub.EpubBook();book.set_identifier('urn:uuid:40b61f5a-b01e-4e31-adf5-e08ed0f13ded')
    book.set_title(TITLE+'：'+EDITION);book.set_language('zh-CN');book.add_author('个人日语学习读本')
    book.add_metadata('DC','description',f'原清单226字逐项讲解，附6字联读。{readings}项读音讲解，{exercises}道练习与答案。')
    css=epub.EpubItem(uid='style',file_name='style.css',media_type='text/css',content=STYLE.encode());book.add_item(css)
    book.set_cover('cover.jpg',(ROOT/'cover.jpg').read_bytes(),create_page=False)
    front=epub.EpubHtml(title='封面',file_name='cover.xhtml',lang='zh-CN');front.content=f'<body class="cover-page"><img src="cover.jpg" alt="{TITLE}：{EDITION}"/></body>';front.add_item(css);book.add_item(front)
    pages={};spine=[front,'nav']
    for path,title,body,c in docs:
        page=epub.EpubHtml(title=title,file_name=path,lang='zh-CN');page.content='<body>'+body+'</body>';page.add_item(css);book.add_item(page);pages[path]=page;spine.append(page)
    toc=[pages['contents.xhtml'],(pages['intro.xhtml'],(epub.Link('intro.xhtml#why-r-s','为什么る与す会成对','why-r-s'),)),pages['patterns.xhtml']]
    for gid,title,chars in groups:
        toc.append((epub.Section(title,href=f'char-{ord(chars[0]):x}.xhtml'),tuple(pages[f'char-{ord(c):x}.xhtml'] for c in chars)))
    toc.extend([pages['practice.xhtml'],pages['practice-answers.xhtml'],(pages['answer-index.xhtml'],tuple(pages[f'answers-{ord(c):x}.xhtml'] for c in order))])
    book.toc=tuple(toc);book.spine=spine;book.add_item(epub.EpubNcx());nav=epub.EpubNav();nav.add_item(css);book.add_item(nav)
    epub.write_epub(str(EPUB_PATH),book)

    # Lightweight pages preserve quick mobile navigation in this long edition.
    preview=ROOT/'preview';preview.mkdir(exist_ok=True)
    sidebar='<aside class="side" aria-label="全书章节"><p><a href="contents.xhtml">全部章节</a></p><ol>'+''.join(f'<li><a href="char-{ord(c):x}.xhtml">{ESC(chapter_titles[c])}</a></li>' for c in order)+'</ol></aside>'
    def web_page(title,body,is_index=False):
        body=(sidebar+'<main>'+body+'</main>')
        def rewrite(m):
            target=m[1];fragment=m[2] or ''
            if target=='contents': dest='../阅读预览.html'
            elif target=='nav': dest='../阅读预览.html'
            else: dest=target+'.html'
            return 'href="'+dest+fragment+'"'
        body=re.sub(r'href="([^"#]+)\.xhtml(#[^"]+)?"',rewrite,body)
        if is_index:
            body=body.replace('href="../阅读预览.html','href="阅读预览.html')
            body=re.sub(r'href="((?!阅读预览)[^"#]+)\.html',r'href="preview/\1.html',body)
        prefix='' if is_index else '../'
        return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>'+f'<title>{ESC(title)} · {TITLE}</title><style>{STYLE}{WEBSTYLE}</style></head><body>'\
            +f'<header class="topbar"><a href="{prefix}阅读预览.html">全书目录</a><a href="{prefix}{ESC(EPUB_PATH.name)}" download>下载 EPUB</a><div class="tools"><button id="smaller" aria-label="减小字号">A−</button><button id="larger" aria-label="增大字号">A＋</button><button id="kana-toggle" aria-pressed="false">隐藏假名</button></div></header><div class="shell">'+body+'</div><script>'+SCRIPT+'</script></body></html>'
    for path,title,body,c in docs:
        if path=='contents.xhtml': continue
        (preview/path.replace('.xhtml','.html')).write_text(web_page(title,body))
    head=f'<div class="bookhead"><img class="webcover" src="cover.jpg" alt="{TITLE}封面"/><p class="smallprint">226字完整理解版 · 附六字联读</p><a class="download" href="{ESC(EPUB_PATH.name)}" download>下载完整 EPUB</a></div>'
    (ROOT/'阅读预览.html').write_text(web_page('全书目录',head+index_html,True))
    baseline=assembled['baseline_readings'];covered=0;missing=[]
    for c,values in baseline.items():
        actual={r['baseline_kana'] for r in manifest.get(c,[])}
        for value in values:
            if value in actual: covered+=1
            else: missing.append({'character':c,'reading':value})
    coverage_report={'baseline_entries':sum(map(len,baseline.values())),'baseline_covered':covered,'missing':missing,'entries':cover_rows}
    (ROOT/'reading-coverage.json').write_text(json.dumps(coverage_report,ensure_ascii=False,indent=2))
    report={'title':TITLE,'edition':EDITION,'draft':partial,'chapters':len(lessons),'main_chapters':sum(d['kind']=='main' for d in lessons),'supplement_chapters':sum(d['kind']=='supplement' for d in lessons),'reading_entries':readings,'baseline_covered':covered,'chapter_exercises':len(lessons)*4,'mixed_exercises':mixed_count,'example_cards_in_chapters_and_exercises':total_examples,'chapter_characters':char_counts,'total_chapter_characters':sum(char_counts.values()),'epub_bytes':EPUB_PATH.stat().st_size,'sha256':hashlib.sha256(EPUB_PATH.read_bytes()).hexdigest(),'built_at':datetime.now(timezone.utc).isoformat()}
    (ROOT/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='chapter_characters'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
