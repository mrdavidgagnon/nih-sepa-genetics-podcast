from pathlib import Path
from datetime import datetime, timezone
from xml.sax.saxutils import escape
import shutil, subprocess, re, sys
import os, tempfile
import json

ROOT=Path(__file__).resolve().parent.parent
SITE=ROOT/'feed-site'
BASE_URL='https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast'
def interview_episodes():
    """Interview episodes to publish, derived from the manifest and the state
    ledger. An episode is publishable only when the durable ledger shows a
    passing render and its audio exists on disk, so a failed or partial render
    can never reach the feed.
    """
    try:
        manifest = json.loads((ROOT/'pipeline'/'manifest.json').read_text())
    except (OSError, ValueError):
        return []
    try:
        state = json.loads(STATE_PATH.read_text())
    except (OSError, ValueError):
        state = {}
    out = []
    for num, rec in sorted(manifest.get('episodes', {}).items()):
        srec = state.get('episodes', {}).get(num, {})
        if srec.get('status') not in ('rendered', 'published'):
            continue
        fn = f'episode-{num}.mp3'
        if not (ROOT/'episodes'/num/fn).exists():
            continue
        title = rec.get('title', 'Untitled')
        desc = rec.get('description', '')
        out.append((num, title, fn, desc, f'episode-{num}', f'episode-{num}'))
    return out


STATE_PATH = ROOT/'pipeline'/'state.json'
READ_MANIFEST = ROOT/'pipeline'/'read-episodes.json'
LEGACY_PUB_DATE = 'Wed, 26 Aug 2026 03:45:00 +0000'

EP = interview_episodes()

def read_episodes():
    """Read-lane episodes (verbatim single-voice readings, numbered 501+).

    Only episodes whose fidelity gate passed are published; a reading that failed
    verification must not reach the feed.
    """
    try:
        manifest = json.loads(READ_MANIFEST.read_text())
    except (OSError, ValueError):
        return []
    out = []
    for num, rec in sorted(manifest.get('episodes', {}).items()):
        if not rec.get('verified'):
            continue
        audio = ROOT/'episodes'/num/rec.get('audio', f'episode-{num}.mp3')
        if not audio.exists():
            continue
        out.append((num, rec))
    return out

def read_notes_html(num, rec):
    """Disclosure for a verbatim reading: no Rowan, no synthetic-interview text."""
    base = f"episode-{num}-reading"
    produced = rec.get('built_at', '')
    try:
        produced = datetime.fromisoformat(produced).strftime('%a, %d %b %Y %H:%M:%S +0000')
    except (TypeError, ValueError):
        produced = LEGACY_PUB_DATE
    return (
        '<p>Produced: '+escape(produced)+'</p>'
        '<p>This episode is a complete automated text-to-speech reading of the body text of one work, '
        'read verbatim by a synthetic voice. It is not an interview, not a summary, and not a dramatization: '
        'Dr. Rowan Field does not appear. No human reviewed this audio before publication.</p>'
        '<p>The reading covers body text only. Front matter, running heads, page numbers, figures, tables and '
        'their captions, equations, acknowledgements, appendices, and the reference list are not read, and '
        'figure and table content is not described, so any argument that depends on seeing them is incomplete '
        'here. PDF text extraction is imperfect; treat anything that sounds wrong as an extraction artifact '
        'rather than the authors\u2019 words and consult the original.</p>'
        '<p>Verbatim fidelity was checked automatically before publishing: '
        +escape(f"{(rec.get('coverage') or 0)*100:.2f}%")+
        ' of the '+escape(str(rec.get('source_words','?')))+' extracted body words are present in the reading, in source order.</p>'
        '<p><a href="'+base+'-notes.md">Full source notes, extraction record, and direct Zotero link</a></p>'
        '<ol><li>'+escape(rec.get('citation',''))+'</li></ol>'
    )

def production_dates():
    """Return RFC 2822 production dates from durable render/publish checkpoints."""
    try:
        state = json.loads(STATE_PATH.read_text())
    except (OSError, ValueError):
        return {}
    dates = {}
    for number, record in state.get('episodes', {}).items():
        transitions = record.get('transitions', [])
        # Rendering is the production event; published is a safe fallback for
        # older records that predate the rendered checkpoint.
        event = next((x for x in transitions if x.get('to') == 'rendered'), None)
        event = event or next((x for x in transitions if x.get('to') == 'published'), None)
        if event and event.get('at'):
            try:
                dt = datetime.fromisoformat(event['at'].replace('Z', '+00:00'))
                dates[number] = dt.strftime('%a, %d %b %Y %H:%M:%S +0000')
            except ValueError:
                pass
    return dates

def atomic_copy(src, dst):
    """Copy an asset through a same-directory temporary file."""
    dst = Path(dst)
    fd, name = tempfile.mkstemp(prefix=f'.{dst.name}.', dir=str(dst.parent))
    os.close(fd)
    try:
        shutil.copy2(src, name)
        os.replace(name, dst)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def atomic_text(path, text):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def duration(path):
    sys.path.insert(0,'/data/.openclaw/workspace/vendor/two-voice-tts')
    import imageio_ffmpeg
    x=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-i',str(path)],capture_output=True,text=True).stderr
    m=re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)',x)
    sec=int(m.group(1))*3600+int(m.group(2))*60+round(float(m.group(3))) if m else 0
    return f'{sec//3600:02d}:{(sec%3600)//60:02d}:{sec%60:02d}'

def notes_html(num):
    if num in ('033','034'):
        t=(ROOT/'episodes'/num/'episode-notes.md').read_text()
        links=[]
        for line in t.splitlines():
            if re.match(r'^\d+\.\s+', line):
                links.append(re.sub(r'^\d+\.\s+', '', line))
        produced = production_dates().get(num, LEGACY_PUB_DATE)
        return '<p>Produced: '+escape(produced)+'</p><p>Pre-recorded audio provided by David Gagnon and added to the feed as-is at his request. It was not scripted or rendered by the podcast pipeline and was not reviewed or transcribed before posting.</p><p><a href="episode-'+num+'-notes.md">Full source notes</a></p><ol>'+''.join('<li>'+escape(x)+'</li>' for x in links)+'</ol>'
    t=(ROOT/'episodes'/num/'episode-notes.md').read_text()
    # Keep feed notes concise while preserving the direct notes link, disclosures,
    # and a complete source list in the RSS extended content.
    links=[]
    for line in t.splitlines():
        if re.match(r'^\d+\.\s+', line):
            links.append(re.sub(r'^\d+\.\s+', '', line))
    produced = production_dates().get(num, LEGACY_PUB_DATE)
    return '<p>Produced: '+escape(produced)+'</p><p>This is a synthetic/dramatized interview with fictional research correspondent Dr. Rowan Field. Rowan is a fictional composite; no cited author was interviewed or is speaking through Rowan. Dialogue paraphrases and synthesizes the research, preserves evidence limits, and contains no fabricated author quotations.</p><p>This is an AI-generated summary that may contain errors and is not a substitute for reading the cited sources.</p><p><a href="episode-'+num+'-notes.md">Full source notes, evidence limitations, and direct Zotero links</a></p><ol>'+''.join('<li>'+escape(x)+'</li>' for x in links)+'</ol>'

def main():
    for num,title,fn,desc,guid,base in EP:
        src=ROOT/'episodes'/num/fn; dst=SITE/(base+'.mp3'); atomic_copy(src,dst); atomic_copy(ROOT/'episodes'/num/'episode-notes.md',SITE/(base+'-notes.md'))
    for num, rec in read_episodes():
        base = f"episode-{num}-reading"
        atomic_copy(ROOT/'episodes'/num/rec.get('audio', f'episode-{num}.mp3'), SITE/(base+'.mp3'))
        atomic_copy(ROOT/'episodes'/num/'episode-notes.md', SITE/(base+'-notes.md'))
    items=[]
    # Preserve the existing pilot entry verbatim enough for stable GUID and links.
    dates = production_dates()
    for num,title,fn,desc,guid,base in EP:
        if num == '036':
            fn = 'episode-036.mp3'

        p=SITE/(base+'.mp3'); pub_date = dates.get(num, LEGACY_PUB_DATE); items.append(f'''      <item><title>{escape(title)}</title><description>{escape(desc)}</description><content:encoded><![CDATA[{notes_html(num)}]]></content:encoded><guid isPermaLink="false">moral-machines-{guid}</guid><pubDate>{pub_date}</pubDate><enclosure url="{BASE_URL}/{base}.mp3" length="{p.stat().st_size}" type="audio/mpeg"/><itunes:duration>{duration(p)}</itunes:duration><itunes:episode>{int(num)}</itunes:episode><itunes:episodeType>full</itunes:episodeType><itunes:explicit>false</itunes:explicit><itunes:image href="{BASE_URL}/cover.png"/></item>''')
    for num, rec in read_episodes():
        base = f"episode-{num}-reading"
        path = SITE/(base+'.mp3')
        title = f"Reading {num}: {rec.get('title','Untitled')}"
        desc = ('Complete verbatim text-to-speech reading of the body text of '
                + rec.get('citation','') +
                ' Not an interview and not a summary; body text only, unreviewed.')
        try:
            pub = datetime.fromisoformat(rec.get('built_at','')).strftime('%a, %d %b %Y %H:%M:%S +0000')
        except (TypeError, ValueError):
            pub = LEGACY_PUB_DATE
        items.append(f'''      <item><title>{escape(title)}</title><description>{escape(desc)}</description><content:encoded><![CDATA[{read_notes_html(num, rec)}]]></content:encoded><guid isPermaLink="false">moral-machines-{escape(rec.get('guid', base))}</guid><pubDate>{pub}</pubDate><enclosure url="{BASE_URL}/{base}.mp3" length="{path.stat().st_size}" type="audio/mpeg"/><itunes:duration>{duration(path)}</itunes:duration><itunes:episode>{int(num)}</itunes:episode><itunes:episodeType>full</itunes:episodeType><itunes:explicit>false</itunes:explicit><itunes:image href="{BASE_URL}/cover.png"/></item>''')
    xml=f'''<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Human in the Loop: Moral Machine Edition</title><link>{BASE_URL}/</link><description>Playful, dramatized interviews synthesizing research on machine ethics, moral decision-making, and autonomous systems. Built for the 2026 NIH SEPA project. Private unlisted review feed.</description><language>en-us</language><copyright>© 2026 Field Day Lab, UW–Madison</copyright><itunes:author>Field Day Lab, UW–Madison</itunes:author><itunes:explicit>false</itunes:explicit><itunes:type>episodic</itunes:type><itunes:category text="Education"/><itunes:image href="{BASE_URL}/cover.png"/><image><url>{BASE_URL}/cover.png</url><title>Human in the Loop: Moral Machine Edition</title><link>{BASE_URL}/</link></image>\n'''+ '\n'.join(items)+'\n</channel></rss>\n'
    atomic_text(SITE/'feed.xml', xml)
    index_items=[]
    for num,title,fn,desc,guid,base in EP:
        if num == '036':
            fn = 'episode-036.mp3'

        index_items.append(f'<li><a href="{base}.mp3">Episode {num} — {escape(title)}</a> · <a href="{base}-notes.md">notes</a></li>')
    for num, rec in read_episodes():
        base = f"episode-{num}-reading"
        index_items.append(f'<li><a href="{base}.mp3">Reading {num} — {escape(rec.get("title","Untitled"))}</a> (verbatim) · <a href="{base}-notes.md">notes</a></li>')
    atomic_text(SITE/'index.html', '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Human in the Loop: Moral Machine Edition</title></head><body><h1>Human in the Loop: Moral Machine Edition</h1><p>Private, unlisted research-review podcast feed.</p><p><a href="feed.xml">RSS feed</a> · <a href="needs-full-text.html">Full-text queue</a></p><h2>Episodes</h2><ul>'+''.join(index_items)+'</ul></body></html>')
    print('published local feed',len(items),'items')
if __name__=='__main__': main()
