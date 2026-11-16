# vm-autopost

Serverless daily X (Twitter) poster for **Volleyball Manager** (men's volleyball manager game, coming soon to Google Play).
Runs on GitHub Actions; no server, no cost beyond X API usage.

| Account | Schedule (UTC) | Local time |
|---|---|---|
| @VManagerJP | 12:00 | 21:00 JST |
| @VManagerEN | 14:00 | 09:00 US Eastern / 15:00 CET |
| @VManagerTR | 18:00 | 21:00 Türkiye |

## How it works
1. `post.py --account en|jp|tr` takes the next entry from `texts/{acc}.json` (in file order).
2. It picks a background from `images/{acc}/`: if the entry has an `image_tag` (e.g. `league_italy`, `transfers`, `cl`, `logo`) the least-used image with that tag is used, otherwise the next image of the general rotation.
3. The headline is drawn onto the empty zone of the background (`manifest.json` → `zone`) with the bundled fonts (Anton for EN/TR, Noto Sans JP Bold for JP). Last line gold `#FAC400`, others white, gold bar underneath.
4. The image is uploaded with `POST https://api.x.com/2/media/upload` (OAuth 1.0a user context) and posted with `POST /2/tweets`. Post text = `caption` + blank line + `hashtags`.
5. `state/{acc}.json` is advanced only after a successful post and committed back by the workflow. After the last entry it starts again from the top.

## Text entries
```json
{"id": "en-001", "type": "league|feature|question|tip|fan|soon",
 "headline": "SUPERLEGA IS IN THE GAME",
 "caption": "1–2 short sentences.",
 "hashtags": ["#VolleyballManager", "#SuperLega", "#Volleyball"],
 "image_tag": "league_italy"}
```
Japanese headlines use `|` to mark allowed line breaks (never drawn). Keep caption+hashtags under 260 weighted characters (CJK counts double).

## Secrets (Settings → Secrets and variables → Actions)
| Name | Purpose |
|---|---|
| `X_APP_CONSUMER_KEY`, `X_APP_CONSUMER_SECRET` | App-level API key/secret, shared by all accounts |
| `X_EN_ACCESS_TOKEN`, `X_EN_ACCESS_SECRET` | @VManagerEN user token |
| `X_JP_ACCESS_TOKEN`, `X_JP_ACCESS_SECRET` | @VManagerJP user token |
| `X_TR_ACCESS_TOKEN`, `X_TR_ACCESS_SECRET` | @VManagerTR user token |

Optional per-account override: `X_{ACC}_CONSUMER_KEY` / `X_{ACC}_CONSUMER_SECRET` (used before `X_APP_*`).
If an account's credentials are missing, the run prints `[skip]` and exits successfully.

## Local use
```bash
pip install -r requirements.txt
python post.py --account jp --dry-run            # renders out/jp.jpg, no network, no state change
python post.py --account tr --dry-run --count 10 # preview the next 10 posts
```
Manual run on GitHub: Actions → *Daily X post* → *Run workflow* (dry run is ticked by default; untick to really post).

## Regenerating backgrounds
`tools/gen_backgrounds.py` builds the 1600×900 text-free backgrounds (logo designs + real in-game screenshots framed in phones, plus one promo per league). It needs the source logo and screenshots, which are not in this repo.

## Fonts
Anton (SIL OFL 1.1) and Noto Sans JP Bold (SIL OFL 1.1) — licences in `fonts/`.
