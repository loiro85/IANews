#!/usr/bin/env python3
"""
Genera index.html con las noticias del día para GitHub Pages.
Se ejecuta diariamente vía GitHub Actions.
"""

import feedparser
import html as html_module
import re
import sys
import time
from datetime import datetime, timezone

# ─── Feeds generales ──────────────────────────────────────────────────────────

GENERAL_FEEDS = [
    "https://news.google.com/rss?hl=es&gl=ES&ceid=ES:es",
    "https://feeds.bbci.co.uk/mundo/rss.xml",
    "https://rss.elpais.com/rss/elpais/portada.xml",
]

TECH_FEEDS = [
    "https://news.google.com/rss/search?q=tecnolog%C3%ADa+inteligencia+artificial+innovaci%C3%B3n&hl=es&gl=ES&ceid=ES:es",
    "https://feeds.xataka.com/xataka/portada",
    "https://www.genbeta.com/rss",
]

SPORTS_CONFIG = {
    "Formula 1": {
        "feeds": [
            "https://news.google.com/rss/search?q=Formula+1+F1+Gran+Premio&hl=es&gl=ES&ceid=ES:es",
        ],
        "limit": 3,
        "color": "#E10600",
        "icon": "🏎️",
    },
    "MotoGP": {
        "feeds": [
            "https://news.google.com/rss/search?q=MotoGP+Gran+Premio+moto&hl=es&gl=ES&ceid=ES:es",
        ],
        "limit": 2,
        "color": "#FF6B00",
        "icon": "🏍️",
    },
    "Formula E": {
        "feeds": [
            'https://news.google.com/rss/search?q=%22Formula+E%22+ABB+el%C3%A9ctrico&hl=es&gl=ES&ceid=ES:es',
        ],
        "limit": 2,
        "color": "#00B4D8",
        "icon": "⚡",
    },
    "Fútbol": {
        "feeds": [
            "https://news.google.com/rss/search?q=Champions+League+LaLiga+Premier+Bundesliga+Serie+A+UEFA&hl=es&gl=ES&ceid=ES:es",
            "https://feeds.as.com/mrss-s/pages/as/site/as.com/portada/",
        ],
        "limit": 3,
        "color": "#16A34A",
        "icon": "⚽",
    },
}

AGENT = "Mozilla/5.0 (compatible; NewsAggregator/1.0)"


# ─── Helpers de fetch ─────────────────────────────────────────────────────────

def _source_from_entry(entry, feed):
    feed_title = feed.feed.get("title", "")
    if "google" in feed_title.lower():
        m = re.search(r"\s[-–]\s([^-–]+)$", entry.get("title", ""))
        if m:
            return m.group(1).strip()
    return feed_title or "Desconocido"


def _clean_title(raw):
    title = html_module.unescape(raw).strip()
    # Google News añade " - Fuente" al final
    return re.sub(r"\s[-–]\s[^-–]{2,40}$", "", title).strip()


def fetch_items(urls, limit=15):
    items, seen = [], set()
    for url in urls:
        try:
            feed = feedparser.parse(url, agent=AGENT)
            for entry in feed.entries:
                raw = entry.get("title", "").strip()
                if not raw:
                    continue
                title = _clean_title(raw)
                key = title.lower()[:60]
                if key in seen:
                    continue
                seen.add(key)
                items.append({
                    "title": title,
                    "link": entry.get("link", "#"),
                    "source": _source_from_entry(entry, feed),
                    "published": entry.get("published", ""),
                })
                if len(items) >= limit:
                    return items
        except Exception as exc:
            print(f"  ⚠  {url}: {exc}", file=sys.stderr)
        time.sleep(0.3)
    return items[:limit]


def fetch_sports():
    items, seen = [], set()
    for sport, cfg in SPORTS_CONFIG.items():
        raw = fetch_items(cfg["feeds"], limit=cfg["limit"] + 5)
        count = 0
        for item in raw:
            if count >= cfg["limit"]:
                break
            key = item["title"].lower()[:60]
            if key in seen:
                continue
            seen.add(key)
            item.update({"sport": sport, "color": cfg["color"], "icon": cfg["icon"]})
            items.append(item)
            count += 1
        time.sleep(0.5)
    return items


# ─── HTML ─────────────────────────────────────────────────────────────────────

def _fmt_date(s):
    if not s:
        return ""
    try:
        import email.utils
        dt = email.utils.parsedate_to_datetime(s)
        return dt.strftime("%d %b %Y · %H:%M")
    except Exception:
        return s[:16]


def _esc(t):
    return html_module.escape(str(t))


def _card(item, sport=False):
    title = _esc(item["title"])
    link  = _esc(item["link"])
    src   = _esc(item.get("source", ""))
    date  = _esc(_fmt_date(item.get("published", "")))

    badge = ""
    if sport:
        color = _esc(item.get("color", "#555"))
        icon  = _esc(item.get("icon", ""))
        sp    = _esc(item.get("sport", ""))
        badge = f'<span class="badge" style="background:{color}">{icon} {sp}</span>'

    return f"""
    <article class="card">
      {badge}
      <h3><a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a></h3>
      <footer>
        <span class="src">{src}</span>
        <span class="date">{date}</span>
      </footer>
    </article>"""


CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:       #0f172a;
    --surface:  #1e293b;
    --hover:    #2d3f58;
    --border:   #334155;
    --text:     #e2e8f0;
    --muted:    #94a3b8;
    --accent-g: #3b82f6;
    --accent-t: #a855f7;
    --accent-s: #f59e0b;
    --radius:   12px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }

  body { background: var(--bg); color: var(--text); min-height: 100vh; }

  /* Header */
  header {
    text-align: center;
    padding: 3rem 1rem 2rem;
    background: linear-gradient(180deg, #1e3a5f 0%, var(--bg) 100%);
    border-bottom: 1px solid var(--border);
  }
  header h1 { font-size: clamp(1.8rem, 4vw, 2.8rem); font-weight: 800; letter-spacing: -0.5px; }
  header .tagline { color: var(--muted); margin-top: .4rem; font-size: .95rem; }
  header .updated {
    display: inline-block;
    margin-top: .8rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: .3rem 1rem;
    font-size: .8rem;
    color: var(--muted);
  }

  /* Layout */
  main { max-width: 1280px; margin: 0 auto; padding: 2.5rem 1rem 4rem; }

  .section { margin-bottom: 3rem; }
  .section-header {
    display: flex;
    align-items: center;
    gap: .7rem;
    margin-bottom: 1.2rem;
    padding-bottom: .7rem;
    border-bottom: 2px solid var(--accent);
  }
  .section-header h2 { font-size: 1.3rem; font-weight: 700; }

  .section.general  { --accent: var(--accent-g); }
  .section.tech     { --accent: var(--accent-t); }
  .section.sports   { --accent: var(--accent-s); }

  .dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--accent); flex-shrink: 0;
  }

  /* Grid */
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
  }

  /* Card */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.1rem 1.2rem;
    display: flex;
    flex-direction: column;
    gap: .6rem;
    transition: background .15s, transform .15s, box-shadow .15s;
  }
  .card:hover {
    background: var(--hover);
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,0,0,.4);
  }

  .card h3 { font-size: .92rem; font-weight: 600; line-height: 1.45; flex: 1; }
  .card h3 a { color: var(--text); text-decoration: none; }
  .card h3 a:hover { color: var(--accent, #60a5fa); text-decoration: underline; }

  .card footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: .5rem;
    flex-wrap: wrap;
  }
  .src  { font-size: .75rem; color: var(--muted); }
  .date { font-size: .72rem; color: var(--muted); opacity: .8; }

  .badge {
    display: inline-block;
    font-size: .7rem;
    font-weight: 700;
    padding: .2rem .55rem;
    border-radius: 999px;
    color: #fff;
    align-self: flex-start;
  }

  /* Footer */
  footer.site-footer {
    text-align: center;
    padding: 1.5rem 1rem;
    color: var(--muted);
    font-size: .8rem;
    border-top: 1px solid var(--border);
  }
  footer.site-footer a { color: var(--muted); }
"""


def generate_html(general, tech, sports):
    updated = datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC")

    g_cards = "\n".join(_card(i) for i in general) or "<p class='src'>No se encontraron noticias.</p>"
    t_cards = "\n".join(_card(i) for i in tech)    or "<p class='src'>No se encontraron noticias.</p>"
    s_cards = "\n".join(_card(i, sport=True) for i in sports) or "<p class='src'>No se encontraron noticias.</p>"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <meta name="description" content="IANews: noticias del día de actualidad, tecnología y deportes de motor y fútbol europeo."/>
  <title>IANews · Noticias del día</title>
  <style>{CSS}</style>
</head>
<body>

<header>
  <h1>📰 IANews</h1>
  <p class="tagline">Noticias del día · Actualidad · Tecnología · Deportes</p>
  <span class="updated">🕐 {updated}</span>
</header>

<main>
  <section class="section general">
    <div class="section-header">
      <span class="dot"></span>
      <h2>🌍 Noticias Generales</h2>
    </div>
    <div class="grid">
      {g_cards}
    </div>
  </section>

  <section class="section tech">
    <div class="section-header">
      <span class="dot"></span>
      <h2>💻 Tecnología</h2>
    </div>
    <div class="grid">
      {t_cards}
    </div>
  </section>

  <section class="section sports">
    <div class="section-header">
      <span class="dot"></span>
      <h2>🏆 Deportes</h2>
    </div>
    <div class="grid">
      {s_cards}
    </div>
  </section>
</main>

<footer class="site-footer">
  Actualizado automáticamente cada día con GitHub Actions ·
  <a href="https://github.com" target="_blank" rel="noopener">Ver repositorio</a>
</footer>

</body>
</html>"""


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("📰 Obteniendo noticias generales...")
    general = fetch_items(GENERAL_FEEDS, limit=10)
    print(f"   → {len(general)} artículos")

    print("💻 Obteniendo noticias de tecnología...")
    tech = fetch_items(TECH_FEEDS, limit=10)
    print(f"   → {len(tech)} artículos")

    print("🏆 Obteniendo noticias de deportes...")
    sports = fetch_sports()
    print(f"   → {len(sports)} artículos")

    html = generate_html(general, tech, sports)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("✅  index.html generado correctamente.")


if __name__ == "__main__":
    main()
