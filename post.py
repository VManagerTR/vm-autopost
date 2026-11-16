#!/usr/bin/env python3
"""Volleyball Manager daily X auto-poster.

python post.py --account en|jp|tr [--dry-run] [--index N] [--count K]

Picks the next text entry for the account (texts/{acc}.json, in order), picks a
background (images/{acc}/manifest.json; by the entry's image_tag if present,
otherwise the next general background), renders the headline with Pillow,
uploads the image to X (POST /2/media/upload) and posts (POST /2/tweets).
State lives in state/{acc}.json and is only advanced after a successful post.

Credentials (env), first match wins:
  consumer key/secret : X_{ACC}_CONSUMER_KEY / X_{ACC}_CONSUMER_SECRET,
                        then X_APP_CONSUMER_KEY / X_APP_CONSUMER_SECRET
  user token/secret   : X_{ACC}_ACCESS_TOKEN / X_{ACC}_ACCESS_SECRET
If any is missing the account is skipped with exit code 0.
"""
import argparse, datetime, io, json, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
GOLD = (250, 196, 0)
FONTS = {'en': 'Anton-Regular.ttf', 'tr': 'Anton-Regular.ttf', 'jp': 'NotoSansJP-Bold.otf'}
MAX_SIZE = {'en': 150, 'tr': 150, 'jp': 124}
API = 'https://api.x.com/2'
NO_START = set('、。，．・：；？！ー」』）】〉》ぁぃぅぇぉっゃゅょァィゥェォッャュョ…!?,.)')
NO_END = set('「『（【〈《(')


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write('\n')


# ---------------------------------------------------------------- selection
def default_state():
    return {'next_text': 0, 'next_general': 0, 'image_uses': {}, 'cycle': 0, 'history': []}


def pick(acc, state, index=None):
    texts = load_json(os.path.join(ROOT, 'texts', f'{acc}.json'))
    manifest = load_json(os.path.join(ROOT, 'images', acc, 'manifest.json'))
    i = state['next_text'] if index is None else index
    entry = texts[i % len(texts)]
    uses = state.get('image_uses', {})
    tag = entry.get('image_tag')
    cands = [m for m in manifest if tag and tag in m.get('tags', [])]
    if cands:  # least-used image carrying the tag, stable tie-break
        img = min(cands, key=lambda m: (uses.get(m['file'], 0), m['file']))
        general_step = 0
    else:
        general = [m for m in manifest if m.get('pool', 'general') == 'general']
        img = general[state['next_general'] % len(general)]
        general_step = 1
    return texts, entry, img, i, general_step


# ---------------------------------------------------------------- rendering
def _units(acc, text):
    """Breakable units. Latin: words. Japanese: segments separated by '|'
    (the author marks natural break points; '|' is never drawn)."""
    if acc == 'jp':
        return [u for u in text.split('|') if u], ''
    return text.split(), ' '


def _splits(units, n):
    if n == 1:
        yield [units]
        return
    for k in range(1, len(units) - n + 2):
        for rest in _splits(units[k:], n - 1):
            yield [units[:k]] + rest


def layout(acc, text, draw, zone):
    x0, y0, x1, y1 = zone
    zw, zh = x1 - x0, y1 - y0
    path = os.path.join(ROOT, 'fonts', FONTS[acc])
    fixed = [text.split('\n')] if '\n' in text else None
    units, sep = _units(acc, text)
    for size in range(MAX_SIZE[acc], 40, -4):
        font = ImageFont.truetype(path, size)
        lh = int(size * (1.08 if acc != 'jp' else 1.32))
        best = None
        options = fixed or []
        if not fixed:
            for n in range(1, min(3, len(units)) + 1):
                for sp in _splits(units, n):
                    options.append([sep.join(p) for p in sp])
        for lines in options:
            if len(lines) * lh > zh * 0.82:
                continue
            ws = [draw.textlength(l, font=font) for l in lines]
            if max(ws) > zw:
                continue
            score = (len(lines), max(ws) - min(ws))
            if best is None or score < best[0]:
                best = (score, lines)
        if best:
            return font, lh, best[1]
    raise ValueError(f'headline does not fit: {text!r}')


def render(acc, entry, img_meta):
    im = Image.open(os.path.join(ROOT, 'images', acc, img_meta['file'])).convert('RGBA')
    zone = img_meta['zone']
    d = ImageDraw.Draw(im)
    font, lh, lines = layout(acc, entry['headline'], d, zone)
    x0, y0, x1, y1 = zone
    bar_h, gap = 8, int(lh * 0.35)
    total = len(lines) * lh + gap + bar_h
    y = y0 + ((y1 - y0) - total) // 2
    center = img_meta.get('align') == 'center'
    asc_fix = font.getbbox('H')[1] if acc != 'jp' else font.getbbox('あ')[1]
    shadow = Image.new('RGBA', im.size)
    sd = ImageDraw.Draw(shadow)
    pos = []
    for k, line in enumerate(lines):
        w = d.textlength(line, font=font)
        x = x0 + ((x1 - x0) - w) / 2 if center else x0
        color = GOLD if (k == len(lines) - 1 and len(lines) > 1) else (255, 255, 255)
        pos.append((x, y - asc_fix, line, color, w))
        sd.text((x + 4, y - asc_fix + 6), line, font=font, fill=(0, 0, 0, 200))
        y += lh
    im = Image.alpha_composite(im, shadow.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(im)
    for x, yy, line, color, w in pos:
        d.text((x, yy), line, font=font, fill=color)
    bw = min(320, max(pw for *_, pw in pos) * 0.45)
    by = y + gap - int(lh * 0.1)
    bx = x0 + ((x1 - x0) - bw) / 2 if center else x0
    d.rectangle([bx, by, bx + bw, by + bar_h], fill=GOLD)
    return im.convert('RGB')


def post_text(entry):
    return entry['caption'].strip() + '\n\n' + ' '.join(entry.get('hashtags', []))


# ---------------------------------------------------------------- X API
def credentials(acc):
    A = acc.upper()
    get = lambda *names: next((os.environ[n] for n in names if os.environ.get(n)), None)
    ck = get(f'X_{A}_CONSUMER_KEY', 'X_APP_CONSUMER_KEY')
    cs = get(f'X_{A}_CONSUMER_SECRET', 'X_APP_CONSUMER_SECRET')
    at = get(f'X_{A}_ACCESS_TOKEN')
    asec = get(f'X_{A}_ACCESS_SECRET')
    return (ck, cs, at, asec) if all((ck, cs, at, asec)) else None


def publish(creds, jpeg_bytes, text):
    from requests_oauthlib import OAuth1Session
    s = OAuth1Session(*creds)
    r = s.post(f'{API}/media/upload', files={'media': ('post.jpg', jpeg_bytes, 'image/jpeg')},
               data={'media_category': 'tweet_image'}, timeout=120)
    if r.status_code >= 300:
        raise RuntimeError(f'media upload failed: {r.status_code} {r.text[:500]}')
    media_id = r.json()['data']['id']
    r = s.post(f'{API}/tweets', json={'text': text, 'media': {'media_ids': [media_id]}}, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f'post failed: {r.status_code} {r.text[:500]}')
    return r.json()['data']['id'], media_id


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--account', required=True, choices=['en', 'jp', 'tr'])
    ap.add_argument('--dry-run', action='store_true', help='render to out/ only, no network, no state change')
    ap.add_argument('--index', type=int, help='dry-run a specific text index')
    ap.add_argument('--count', type=int, default=1, help='dry-run: render this many consecutive posts')
    a = ap.parse_args()
    acc = a.account
    state_path = os.path.join(ROOT, 'state', f'{acc}.json')
    state = load_json(state_path, None) or default_state()

    if a.dry_run:
        os.makedirs(os.path.join(ROOT, 'out'), exist_ok=True)
        sim = json.loads(json.dumps(state))
        start = sim['next_text'] if a.index is None else a.index
        sim['next_text'] = start
        for k in range(a.count):
            texts, entry, img, i, gstep = pick(acc, sim)
            out = render(acc, entry, img)
            name = f'{acc}.jpg' if a.count == 1 else f'{acc}_{i % len(texts):03d}.jpg'
            out.save(os.path.join(ROOT, 'out', name), quality=92)
            print(f'[dry-run] {acc} text={entry["id"]} image={img["file"]} -> out/{name}')
            print('  ' + post_text(entry).replace('\n', '\n  '))
            sim['next_text'] += 1; sim['next_general'] += gstep
            sim['image_uses'][img['file']] = sim['image_uses'].get(img['file'], 0) + 1
        return 0

    creds = credentials(acc)
    if not creds:
        print(f'[skip] {acc}: X credentials not configured (need X_{acc.upper()}_ACCESS_TOKEN/SECRET and consumer key/secret)')
        return 0
    texts, entry, img, i, gstep = pick(acc, state)
    buf = io.BytesIO(); render(acc, entry, img).save(buf, 'JPEG', quality=92)
    text = post_text(entry)
    tweet_id, media_id = publish(creds, buf.getvalue(), text)
    print(f'[posted] {acc} text={entry["id"]} image={img["file"]} tweet={tweet_id}')
    state['next_text'] = i + 1
    if state['next_text'] % len(texts) == 0:
        state['cycle'] = state.get('cycle', 0) + 1
    state['next_general'] += gstep
    state['image_uses'][img['file']] = state['image_uses'].get(img['file'], 0) + 1
    state['history'] = (state.get('history', []) + [{
        'time': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        'text_id': entry['id'], 'image': img['file'], 'tweet_id': tweet_id}])[-200:]
    save_json(state_path, state)
    return 0


if __name__ == '__main__':
    sys.exit(main())
