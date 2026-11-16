"""Generate text-free 1600x900 brand backgrounds for vm-autopost.

Run locally (needs the logo + in-game screenshots on the build machine):
  python tools/gen_backgrounds.py --logo PATH --shots-root PATH
Writes images/{en,jp,tr}/NNN.jpg and images/{acc}/manifest.json.
manifest entry: {"file": "001.jpg", "zone": [x0,y0,x1,y1], "align": "left|center"}
The zone is the empty dark area where post.py overlays the headline.
"""
import argparse, glob, json, math, os, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1600, 900
GOLD = (250, 196, 0)
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANTON = os.path.join(HERE, 'fonts', 'Anton-Regular.ttf')

# (r,g,b multipliers of a base luminance) — all dark, brand-tinted
PALETTES = {
    'warm':  (1.00, 0.85, 0.40),
    'amber': (1.00, 0.70, 0.25),
    'navy':  (0.45, 0.60, 1.00),
    'ink':   (0.70, 0.70, 0.75),
    'olive': (0.85, 0.85, 0.45),
}

def load_logo(path):
    L = Image.open(path).convert('RGB')
    a = np.array(L).astype(int)
    m = (a.max(2) > 40).astype('uint8') * 255
    logo = L.convert('RGBA')
    logo.putalpha(Image.fromarray(m).filter(ImageFilter.GaussianBlur(0.8)))
    bx, by, br = 605, 640, 135  # the ball inside the logo
    ball = logo.crop((bx - br, by - br, bx + br, by + br))
    cm = Image.new('L', ball.size, 0)
    ImageDraw.Draw(cm).ellipse([2, 2, 2 * br - 2, 2 * br - 2], fill=255)
    ball.putalpha(cm)
    return logo, ball

def background(pal, cx=0.5, cy=0.45, strength=22, rng=None):
    g = np.linspace(0, 1, W)[None, :]; v = np.linspace(0, 1, H)[:, None]
    base = 10 + strength * np.exp(-((g - cx) ** 2) / 0.08) * np.exp(-((v - cy) ** 2) / 0.2)
    r, gg, b = PALETTES[pal]
    arr = np.dstack([base * r, base * gg, base * b])
    if rng is not None:  # subtle film grain
        arr = arr + np.random.default_rng(rng.randint(0, 10**9)).normal(0, 1.2, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype('uint8')).convert('RGBA')

def glow_lines(im, xs, alpha=60, width=6, slope=0.6, color=GOLD):
    gl = Image.new('RGBA', (W, H)); d = ImageDraw.Draw(gl)
    for x in xs:
        d.line([(W * x, H), (W * x + H * slope, 0)], fill=color + (alpha,), width=width)
    return Image.alpha_composite(im, gl.filter(ImageFilter.GaussianBlur(3)))

def trail(im, cx, cy, bd, direction=-1):
    tr = Image.new('RGBA', (W, H)); d = ImageDraw.Draw(tr)
    for k in range(9):
        off = (k - 4) * bd * 0.09; ln = bd * (1.0 + 0.6 * ((k * 37) % 5) / 4)
        yy = cy + off
        col = GOLD + (220,) if k % 3 else (255, 255, 255, 150)
        x1 = cx + direction * bd * 0.2
        d.line([(x1 + direction * (ln + bd * 0.1), yy + ln * 0.25), (x1, yy)], fill=col, width=max(3, int(bd * 0.04)))
    return Image.alpha_composite(im, tr.filter(ImageFilter.GaussianBlur(bd * 0.012)))

def draw_ball(size, rot=0, line=(30, 30, 30), fill=(245, 245, 240), gold=GOLD):
    """Vector volleyball (white/gold panels) with Pillow only."""
    s = size * 3
    im = Image.new('RGBA', (s, s)); d = ImageDraw.Draw(im)
    d.ellipse([0, 0, s - 1, s - 1], fill=fill + (255,))
    pan = Image.new('RGBA', (s, s)); pd = ImageDraw.Draw(pan)
    w = max(4, s // 45)
    for k in range(3):
        a = k * 120
        pd.pieslice([-s * 0.4, -s * 0.4, s * 1.4, s * 1.4], a, a + 40, fill=gold + (255,))
    mask = Image.new('L', (s, s)); ImageDraw.Draw(mask).ellipse([0, 0, s - 1, s - 1], fill=255)
    im = Image.composite(Image.alpha_composite(im, pan), im, mask)
    d = ImageDraw.Draw(im)
    for k in range(3):
        a = math.radians(k * 120 + 20)
        ox, oy = s / 2 + math.cos(a) * s * 0.55, s / 2 + math.sin(a) * s * 0.55
        r = s * 0.42
        d.ellipse([ox - r, oy - r, ox + r, oy + r], outline=line + (255,), width=w)
    im.putalpha(Image.fromarray(np.minimum(np.array(im.split()[3]), np.array(mask))))
    d = ImageDraw.Draw(im)
    d.ellipse([w // 2, w // 2, s - w // 2, s - w // 2], outline=line + (255,), width=w)
    return im.rotate(rot, Image.BICUBIC).resize((size, size), Image.LANCZOS)

def net_pattern(im, y0, y1, alpha=45, step=34):
    n = Image.new('RGBA', (W, H)); d = ImageDraw.Draw(n)
    for x in range(-step, W + step, step):
        d.line([(x, y0), (x, y1)], fill=(255, 255, 255, alpha), width=2)
    for y in range(y0, y1 + 1, step):
        d.line([(0, y), (W, y)], fill=(255, 255, 255, alpha), width=2)
    d.rectangle([0, y0 - 10, W, y0], fill=GOLD + (160,))
    return Image.alpha_composite(im, n)

def court_lines(im, alpha=70):
    c = Image.new('RGBA', (W, H)); d = ImageDraw.Draw(c)
    # perspective court: trapezoid + attack lines + center line
    bl, br, tl, tr_ = (180, H + 40), (W - 180, H + 40), (560, 330), (W - 560, 330)
    col = GOLD + (alpha,)
    d.line([bl, tl, tr_, br], fill=col, width=6)
    for t in (0.33, 0.55, 0.78):
        y = 330 + (H + 40 - 330) * t
        xl = tl[0] + (bl[0] - tl[0]) * t; xr = tr_[0] + (br[0] - tr_[0]) * t
        d.line([(xl, y), (xr, y)], fill=col, width=4 if t != 0.55 else 7)
    return Image.alpha_composite(im, c.filter(ImageFilter.GaussianBlur(1.5)))

def wordmark(im, x, y, h, logo, align='left'):
    """Small logo + VOLLEYBALL MANAGER wordmark."""
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(ANTON, int(h * 0.42))
    t1, t2 = 'VOLLEYBALL', ' MANAGER'
    tw = d.textlength(t1, font=f) + d.textlength(t2, font=f)
    total = h + 14 + tw
    if align == 'center': x = int(x - total / 2)
    im.alpha_composite(logo.resize((h, h), Image.LANCZOS), (int(x), int(y)))
    ty = y + h * 0.22
    d.text((x + h + 14, ty), t1, font=f, fill='white')
    d.text((x + h + 14 + d.textlength(t1, font=f), ty), t2, font=f, fill=GOLD)

def phone(shot_path, height, crop_top_ratio=None):
    s = Image.open(shot_path).convert('RGB')
    w, h = s.size
    ratio = 0.47  # visible screen aspect w/h
    ch = min(h, int(w / ratio))
    s = s.crop((0, 0, w, ch))
    sh = height - 24; sw = int(sh * w / ch)
    s = s.resize((sw, sh), Image.LANCZOS)
    pw, ph = sw + 24, height
    r = int(pw * 0.11)
    body = Image.new('RGBA', (pw, ph)); d = ImageDraw.Draw(body)
    d.rounded_rectangle([0, 0, pw - 1, ph - 1], r, fill=(8, 8, 10, 255), outline=GOLD + (200,), width=3)
    m = Image.new('L', (sw, sh)); ImageDraw.Draw(m).rounded_rectangle([0, 0, sw - 1, sh - 1], r - 10, fill=255)
    body.paste(s, (12, 12), m)
    return body

def place(im, ph, x, y, angle=0):
    if angle:
        ph = ph.rotate(angle, Image.BICUBIC, expand=True)
    sh = Image.new('RGBA', (W, H))
    a = ph.split()[3].point(lambda v: int(v * 0.75))
    blk = Image.new('RGBA', ph.size, (0, 0, 0, 255)); blk.putalpha(a)
    sh.alpha_composite(blk, (int(x + 18), int(y + 24)))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(22)))
    im.alpha_composite(ph, (int(x), int(y)))
    return im

# ---------------- layouts ----------------
def L_logo_right(rng, logo, ball, pal):
    im = background(pal, cx=0.72, cy=0.45, rng=rng)
    im = glow_lines(im, [0.50, 0.53, 0.88, 0.91], alpha=rng.randint(45, 75))
    lh = rng.randint(600, 700)
    im.alpha_composite(logo.resize((lh, lh), Image.LANCZOS), (int(W * 0.72 - lh / 2), (H - lh) // 2))
    return im, [90, 130, 860, 780], 'left'

def L_logo_left(rng, logo, ball, pal):
    im = background(pal, cx=0.28, cy=0.5, rng=rng)
    im = glow_lines(im, [0.04, 0.07, 0.40, 0.43], alpha=rng.randint(45, 75))
    lh = rng.randint(600, 700)
    im.alpha_composite(logo.resize((lh, lh), Image.LANCZOS), (int(W * 0.27 - lh / 2), (H - lh) // 2))
    return im, [760, 130, 1520, 780], 'left'

def L_logo_top(rng, logo, ball, pal):
    im = background(pal, cx=0.5, cy=0.3, rng=rng)
    im = glow_lines(im, [0.08, 0.11, 0.80, 0.83], alpha=rng.randint(40, 65))
    lh = rng.randint(330, 380)
    im.alpha_composite(logo.resize((lh, lh), Image.LANCZOS), ((W - lh) // 2, 40))
    return im, [140, 40 + lh + 30, 1460, 850], 'center'

def L_ball_trail(rng, logo, ball, pal):
    im = background(pal, cx=0.75, cy=0.4, rng=rng)
    bd = rng.randint(380, 460); cx, cy = int(W * rng.uniform(0.74, 0.8)), int(H * rng.uniform(0.38, 0.5))
    im = trail(im, cx, cy, bd)
    b = ball
    im.alpha_composite(b.resize((bd, bd), Image.LANCZOS).rotate(rng.randint(-40, 40), Image.BICUBIC), (cx - bd // 2, cy - bd // 2))
    wordmark(im, 90, 60, 70, logo)
    return im, [90, 190, 860, 830], 'left'

def L_net(rng, logo, ball, pal):
    im = background(pal, cx=0.5, cy=0.7, rng=rng)
    im = net_pattern(im, 70, rng.randint(300, 360), alpha=rng.randint(30, 50))
    bd = rng.randint(220, 280)
    im.alpha_composite(ball.resize((bd, bd), Image.LANCZOS).rotate(rng.randint(0, 360), Image.BICUBIC), (int(W * rng.choice([0.12, 0.78])), 20))
    wordmark(im, W // 2, 790, 70, logo, align='center')
    return im, [140, 400, 1460, 770], 'center'

def L_court(rng, logo, ball, pal):
    im = background(pal, cx=0.5, cy=0.6, strength=26, rng=rng)
    im = court_lines(im, alpha=rng.randint(55, 90))
    wm = logo.resize((560, 560), Image.LANCZOS); a = wm.split()[3].point(lambda v: v * 0.10); wm.putalpha(a)
    im.alpha_composite(wm, ((W - 560) // 2, 170))
    wordmark(im, W // 2, 50, 76, logo, align='center')
    return im, [140, 200, 1460, 820], 'center'

def L_big_ball_corner(rng, logo, ball, pal):
    im = background(pal, cx=0.85, cy=0.8, rng=rng)
    lh = rng.randint(1000, 1150)
    wm = logo.resize((lh, lh), Image.LANCZOS); wm.putalpha(wm.split()[3].point(lambda v: int(v * 0.22)))
    im.alpha_composite(wm, (int(W - lh * 0.62), int(H - lh * 0.72)))
    im = glow_lines(im, [0.62, 0.65], alpha=55)
    wordmark(im, 90, 60, 70, logo)
    return im, [90, 190, 900, 830], 'left'

def S_one_right(rng, logo, ball, pal, shots):
    im = background(pal, cx=0.75, cy=0.5, rng=rng)
    im = glow_lines(im, [0.55, 0.58, 0.95], alpha=50)
    ph = phone(shots[0], 820)
    im = place(im, ph, int(W * 0.75 - ph.width / 2), 40, angle=rng.choice([0, 0, 4, -4]))
    wordmark(im, 90, 760, 72, logo)
    return im, [90, 90, 900, 730], 'left'

def S_one_left(rng, logo, ball, pal, shots):
    im = background(pal, cx=0.25, cy=0.5, rng=rng)
    im = glow_lines(im, [0.0, 0.03, 0.42], alpha=50)
    ph = phone(shots[0], 820)
    im = place(im, ph, int(W * 0.25 - ph.width / 2), 40, angle=rng.choice([0, 0, 4, -4]))
    wordmark(im, 720, 760, 72, logo)
    return im, [720, 90, 1520, 730], 'left'

def S_two_right(rng, logo, ball, pal, shots):
    im = background(pal, cx=0.72, cy=0.5, rng=rng)
    im = glow_lines(im, [0.50, 0.53, 0.92], alpha=45)
    p2 = phone(shots[1], 700); p1 = phone(shots[0], 820)
    im = place(im, p2, 1210, 140, angle=-6)
    im = place(im, p1, 900, 40, angle=3)
    wordmark(im, 80, 760, 68, logo)
    return im, [80, 90, 830, 730], 'left'

def S_three_fan(rng, logo, ball, pal, shots):
    im = background(pal, cx=0.7, cy=0.6, rng=rng)
    bd = 260
    im.alpha_composite(ball.resize((bd, bd), Image.LANCZOS), (W - bd + 40, -40))
    ps = [phone(s, 700) for s in shots[:3]]
    im = place(im, ps[0], 760, 170, angle=8)
    im = place(im, ps[2], 1250, 170, angle=-8)
    im = place(im, ps[1], 990, 70, angle=0)
    wordmark(im, 70, 770, 64, logo)
    return im, [70, 90, 760, 740], 'left'

def S_one_ball(rng, logo, ball, pal, shots):
    im = background(pal, cx=0.7, cy=0.5, rng=rng)
    bd = 330; cx, cy = 1420, 200
    bd = 300; cx, cy = 1450, 720
    im = trail(im, cx, cy, bd, direction=1)
    im.alpha_composite(ball.resize((bd, bd), Image.LANCZOS).rotate(25, Image.BICUBIC), (cx - bd // 2, cy - bd // 2))
    ph = phone(shots[0], 820)
    im = place(im, ph, 960, 40, angle=-3)
    wordmark(im, 90, 760, 72, logo)
    return im, [90, 90, 900, 730], 'left'

def S_league(rng, logo, ball, pal, shots):
    """Dedicated league promo: standings + roster phones of one league."""
    im = background(pal, cx=0.7, cy=0.5, strength=26, rng=rng)
    im = glow_lines(im, [0.48, 0.51, 0.93], alpha=60)
    bd = 210
    im = trail(im, 1480, 150, bd)
    im.alpha_composite(ball.resize((bd, bd), Image.LANCZOS), (1480 - bd // 2, 150 - bd // 2))
    p2 = phone(shots[1], 720); p1 = phone(shots[0], 820)
    im = place(im, p2, 1215, 150, angle=-6)
    im = place(im, p1, 905, 40, angle=3)
    wordmark(im, 80, 760, 68, logo)
    return im, [80, 90, 840, 730], 'left'

def shot_tag(path):
    n = os.path.basename(path)
    for key, tag in (('roster', 'squad'), ('standings', 'table'), ('table', 'table'), ('cl-ko', 'playoffs'), ('_ko', 'playoffs'),
                     ('cl-', 'cl'), ('cl_', 'cl'), ('fixture-detail', 'match'), ('fixture-home', 'home'), ('fix', 'fixtures'),
                     ('career', 'career'), ('info', 'career'), ('transfers', 'transfers'), ('museum', 'museum'), ('club_sheet', 'club'),
                     ('_lib', 'stats'), ('_pts', 'stats'), ('_rey', 'stats'), ('_set', 'stats'), ('best', 'stats')):
        if key in n: return tag
    return 'game'

LEAGUES = ['italy', 'poland', 'russia', 'efeler', 'japan', 'turkey-1']
LANG_SUFFIX = {'en': 'en', 'jp': 'ja', 'tr': 'tr'}

LOGO_LAYOUTS = [L_logo_right, L_logo_left, L_logo_top, L_ball_trail, L_net, L_court, L_big_ball_corner]
SHOT_LAYOUTS = [(S_one_right, 1), (S_one_left, 1), (S_two_right, 2), (S_three_fan, 3), (S_one_ball, 1)]

SHOT_GLOBS = {
    'en': ['cl-fixture/shots/cl-fix-en-ok.png', 'cl-fixture/shots/cl-ko-en.png', 'cl-fixture/shots/cl-table-en-ok.png',
           'cl-fixture/shots/fixture-detail-en.png', 'cl-fixture/shots/fixture-home-en.png', 'cl-fixture/shots/fixture-home-w13-en.png',
           'cl-fixture/shots/league-fix-en.png', 'cl-fixture/shots/league-table-en.png', 'cl-standings/shots/en_*.png',
           'italy-top-players/v2/shots/en_*.png', 'leagues-all/shots/*-en.png', 'player-career/shots/career_overview.png',
           'player-career/shots/info.png', 'player-career/shots/transfers.png', 'trophy-museum/shots/museum.png',
           'trophy-museum/shots/club_sheet.png', 'new-leagues/japan-standings-mobile-en.png'],
    'jp': ['cl-fixture/shots/*-ja.png', 'cl-fixture/shots/fixture-home-w7-ja-new.png', 'cl-standings/shots/ja_*.png',
           'italy-top-players/v2/shots/ja_*.png', 'leagues-all/shots/*-ja.png', 'new-leagues/*-mobile-ja.png'],
    'tr': ['cl-fixture/shots/cl-fix-tr-ok.png', 'cl-fixture/shots/cl-ko-tr.png', 'cl-fixture/shots/cl-table-tr-ok.png',
           'cl-fixture/shots/fixture-detail-tr.png', 'cl-fixture/shots/fixture-home-tr.png', 'cl-fixture/shots/fixture-home-w13-tr.png',
           'cl-fixture/shots/fixture-home-w7-tr.png', 'cl-fixture/shots/league-fix-tr.png', 'cl-fixture/shots/league-table-tr.png',
           'cl-standings/shots/tr_*.png', 'italy-top-players/v2/shots/tr_*.png', 'leagues-all/shots/*-tr.png',
           'cl-top-players/shots/cl-best-*.png'],
}
ACC_SEED = {'en': 101, 'jp': 202, 'tr': 303}
ACC_PALS = {'en': ['warm', 'navy', 'ink', 'warm', 'amber'], 'jp': ['ink', 'warm', 'navy', 'olive', 'warm'],
            'tr': ['warm', 'amber', 'navy', 'warm', 'olive']}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--logo', default='/workspace/vm-logo/profile_final.png')
    ap.add_argument('--shots-root', default='/workspace/vm-video')
    ap.add_argument('--n-logo', type=int, default=16)
    ap.add_argument('--n-shot', type=int, default=20)
    a = ap.parse_args()
    logo, ball = load_logo(a.logo)
    for acc in ('en', 'jp', 'tr'):
        rng = random.Random(ACC_SEED[acc])
        shots = []
        for g in SHOT_GLOBS[acc]:
            shots += sorted(glob.glob(os.path.join(a.shots_root, g)))
        shots = list(dict.fromkeys(shots)); rng.shuffle(shots)
        out = os.path.join(HERE, 'images', acc); os.makedirs(out, exist_ok=True)
        for f in glob.glob(os.path.join(out, '*.jpg')): os.remove(f)
        jobs = []
        for i in range(a.n_logo): jobs.append(('logo', LOGO_LAYOUTS[i % len(LOGO_LAYOUTS)]))
        for i in range(a.n_shot): jobs.append(('shot', SHOT_LAYOUTS[i % len(SHOT_LAYOUTS)]))
        rng.shuffle(jobs)
        manifest, si = [], 0
        for n, (kind, lay) in enumerate(jobs, 1):
            pal = ACC_PALS[acc][n % len(ACC_PALS[acc])]
            if kind == 'logo':
                im, zone, align = lay(rng, logo, ball, pal)
                src = []
            else:
                fn, k = lay
                src = [shots[(si + j) % len(shots)] for j in range(k)]; si += k
                im, zone, align = fn(rng, logo, ball, pal, src)
            name = f'{n:03d}.jpg'
            im.convert('RGB').save(os.path.join(out, name), quality=88, optimize=True)
            manifest.append({'file': name, 'zone': zone, 'align': align, 'layout': (lay.__name__ if kind == 'logo' else lay[0].__name__),
                             'palette': pal, 'pool': 'general', 'tags': sorted({shot_tag(x) for x in src}) if src else ['logo'],
                             'screenshots': [os.path.relpath(x, a.shots_root) for x in src]})
        for lg in LEAGUES:
            sfx = LANG_SUFFIX[acc]
            src = [os.path.join(a.shots_root, f'leagues-all/shots/{lg}-standings-{sfx}.png'),
                   os.path.join(a.shots_root, f'leagues-all/shots/{lg}-roster-{sfx}.png')]
            pal = ACC_PALS[acc][len(manifest) % len(ACC_PALS[acc])]
            im, zone, align = S_league(rng, logo, ball, pal, src)
            name = f'league_{lg}.jpg'
            im.convert('RGB').save(os.path.join(out, name), quality=88, optimize=True)
            manifest.append({'file': name, 'zone': zone, 'align': align, 'layout': 'S_league', 'palette': pal,
                             'tags': ['league_' + lg], 'pool': 'league',
                             'screenshots': [os.path.relpath(x, a.shots_root) for x in src]})
        json.dump(manifest, open(os.path.join(out, 'manifest.json'), 'w'), indent=1, ensure_ascii=False)
        print(acc, len(manifest), 'images,', len(shots), 'screenshots available')

if __name__ == '__main__':
    main()
