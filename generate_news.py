#!/usr/bin/env python3
"""
Genera index.html con las noticias del día para GitHub Pages.
Fuentes en inglés se traducen automáticamente al español.
Se ejecuta diariamente vía GitHub Actions.
"""

import feedparser
import html as html_module
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests as _req
import trafilatura
from deep_translator import GoogleTranslator

# ─── Fuentes ──────────────────────────────────────────────────────────────────
# Tuplas (url, idioma). "en" → se traduce automáticamente al español.

GENERAL_FEEDS = [
    # Fuentes españolas e hispanas — sin traducción
    ("https://feeds.elpais.com/rss/elpais/portada.xml",          "es"),
    ("https://feeds.elpais.com/rss/elpais/internacional.xml",    "es"),
    ("https://rss.elconfidencial.com/espana/",                   "es"),
    ("https://rss.dw.com/rdf/rss-es-all",                        "es"),  # Deutsche Welle
    ("https://feeds.bbci.co.uk/mundo/rss.xml",                   "es"),  # BBC Mundo
    # Fuentes internacionales en inglés — se traducen
    ("https://www.theguardian.com/world/rss",                    "en"),  # The Guardian
    ("https://feeds.bbci.co.uk/news/world/rss.xml",              "en"),  # BBC World
]

TECH_FEEDS = [
    # Español
    ("https://feeds.xataka.com/xataka/portada",                  "es"),
    # Inglés — se traducen
    ("https://www.theverge.com/rss/index.xml",                   "en"),  # The Verge
    ("https://feeds.arstechnica.com/arstechnica/index",          "en"),  # Ars Technica
    ("https://www.tomshardware.com/feeds/all",                   "en"),  # Tom's Hardware (Nvidia/Intel/AMD)
    ("https://9to5mac.com/feed/",                                "en"),  # Apple / iOS
    ("https://www.engadget.com/rss.xml",                         "en"),  # Engadget
]

SPORTS_CONFIG = {
    "Formula 1": {
        "feeds": [
            ("https://news.google.com/rss/search?q=Formula+1+F1+Gran+Premio&hl=es&gl=ES&ceid=ES:es", "es"),
            ("https://feeds.bbci.co.uk/sport/formula1/rss.xml", "en"),
        ],
        "limit": 3, "color": "#E10600", "icon": "🏎️",
    },
    "MotoGP": {
        "feeds": [
            ("https://news.google.com/rss/search?q=MotoGP+Gran+Premio+moto&hl=es&gl=ES&ceid=ES:es", "es"),
        ],
        "limit": 2, "color": "#FF6B00", "icon": "🏍️",
    },
    "Formula E": {
        "feeds": [
            ("https://news.google.com/rss/search?q=%22Formula+E%22+ABB+el%C3%A9ctrico&hl=es&gl=ES&ceid=ES:es", "es"),
        ],
        "limit": 2, "color": "#00B4D8", "icon": "⚡",
    },
    "Fútbol": {
        "feeds": [
            ("https://feeds.as.com/mrss-s/pages/as/site/as.com/portada/", "es"),
            ("https://feeds.bbci.co.uk/sport/football/rss.xml",           "en"),  # BBC Sport
            ("https://www.skysports.com/rss/12040",                       "en"),  # Sky Sports
        ],
        "limit": 5, "color": "#16A34A", "icon": "⚽",
    },
}

MAX_CONTENT_CHARS = 5000

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
}


# ─── RSS helpers ──────────────────────────────────────────────────────────────

def _strip_html(text):
    return re.sub(r"<[^>]+>", " ", text).strip()


def _source_from_entry(entry, feed):
    feed_title = feed.feed.get("title", "")
    if "google" in feed_title.lower():
        m = re.search(r"\s[-–]\s([^-–]+)$", entry.get("title", ""))
        if m:
            return m.group(1).strip()
    return feed_title or "Desconocido"


def _clean_title(raw):
    title = html_module.unescape(raw).strip()
    return re.sub(r"\s[-–]\s[^-–]{2,40}$", "", title).strip()


def _rss_summary(entry):
    raw = entry.get("summary", entry.get("description", ""))
    return html_module.unescape(_strip_html(raw)).strip()


def fetch_items(feed_specs, limit=15):
    """feed_specs: list of (url, lang) tuples."""
    items, seen = [], set()
    for url, lang in feed_specs:
        try:
            feed = feedparser.parse(url, agent=_BROWSER_HEADERS["User-Agent"])
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
                    "title":       title,
                    "link":        entry.get("link", "#"),
                    "source":      _source_from_entry(entry, feed),
                    "published":   entry.get("published", ""),
                    "rss_summary": _rss_summary(entry),
                    "content":     "",
                    "lang":        lang,
                })
                if len(items) >= limit:
                    return items
        except Exception as exc:
            print(f"  ⚠  {url}: {exc}", file=sys.stderr)
        time.sleep(0.2)
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
        time.sleep(0.3)
    return items


# ─── Fetch artículo completo ───────────────────────────────────────────────────

def _fetch_article_content(item):
    """Descarga y extrae el texto. Usa browser headers para evitar bloqueos."""
    # Intento 1: requests con headers de navegador real
    try:
        resp = _req.get(item["link"], headers=_BROWSER_HEADERS, timeout=15, allow_redirects=True)
        if resp.ok:
            text = trafilatura.extract(
                resp.text,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
            )
            if text and len(text) > 200:
                item["content"] = text[:MAX_CONTENT_CHARS]
                return
    except Exception as exc:
        print(f"  ⚠  requests: {item['link'][:60]}… → {exc}", file=sys.stderr)

    # Intento 2: fetcher propio de trafilatura
    try:
        downloaded = trafilatura.fetch_url(item["link"])
        if downloaded:
            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
            )
            if text and len(text) > 200:
                item["content"] = text[:MAX_CONTENT_CHARS]
                return
    except Exception as exc:
        print(f"  ⚠  trafilatura: {item['link'][:60]}… → {exc}", file=sys.stderr)

    # Fallback: resumen del RSS
    item["content"] = item["rss_summary"] or "Contenido no disponible."


def enrich_with_content(items):
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_article_content, item): item for item in items}
        done = 0
        for future in as_completed(futures):
            done += 1
            try:
                future.result()
            except Exception as exc:
                print(f"  ⚠  content worker: {exc}", file=sys.stderr)
            print(f"  → {done}/{len(futures)} artículos procesados", end="\r")
    print()


# ─── Traducción ───────────────────────────────────────────────────────────────

def _translate(text, source="en", target="es"):
    if not text or not text.strip():
        return text
    try:
        # Google Translate tiene límite ~4900 chars por petición
        chunks = [text[i:i + 4800] for i in range(0, len(text), 4800)]
        parts = []
        for chunk in chunks:
            translated = GoogleTranslator(source=source, target=target).translate(chunk)
            parts.append(translated or chunk)
            if len(chunks) > 1:
                time.sleep(0.4)
        return " ".join(parts)
    except Exception as exc:
        print(f"  ⚠  traducción: {exc}", file=sys.stderr)
        return text


def translate_english_items(items):
    en_items = [item for item in items if item.get("lang") == "en"]
    if not en_items:
        return
    print(f"  🌐 Traduciendo {len(en_items)} artículos del inglés...")
    for i, item in enumerate(en_items, 1):
        item["title"] = _translate(item["title"])
        if item["content"]:
            item["content"] = _translate(item["content"])
        print(f"  → {i}/{len(en_items)} traducidos", end="\r")
        time.sleep(0.5)  # respetar límites de la API gratuita
    print()


# ─── Formateo ─────────────────────────────────────────────────────────────────

def _fmt_date(s):
    if not s:
        return ""
    try:
        import email.utils
        dt = email.utils.parsedate_to_datetime(s)
        return dt.strftime("%d %b %Y · %H:%M")
    except Exception:
        return s[:16]


def _prepare_data(general, tech, sports):
    data = {}
    for prefix, items in [("g", general), ("t", tech), ("s", sports)]:
        for i, item in enumerate(items):
            data[f"{prefix}{i}"] = {
                "title":   item["title"],
                "link":    item["link"],
                "source":  item.get("source", ""),
                "date":    _fmt_date(item.get("published", "")),
                "content": item.get("content", ""),
                "sport":   item.get("sport", ""),
                "color":   item.get("color", ""),
                "icon":    item.get("icon", ""),
                "lang":    item.get("lang", "es"),
            }
    return data


# ─── Plantillas HTML ──────────────────────────────────────────────────────────

def _card(item_id, item, sport=False):
    title = html_module.escape(item["title"])
    src   = html_module.escape(item.get("source", ""))
    date  = html_module.escape(_fmt_date(item.get("published", "")))

    badge = ""
    if sport:
        color = html_module.escape(item.get("color", "#555"))
        icon  = html_module.escape(item.get("icon", ""))
        sp    = html_module.escape(item.get("sport", ""))
        badge = f'<span class="badge" style="background:{color}">{icon} {sp}</span>'

    return f"""
    <article class="card" onclick="openModal('{item_id}')" role="button" tabindex="0"
             onkeydown="if(event.key==='Enter')openModal('{item_id}')">
      {badge}
      <h3>{title}</h3>
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
    --body-txt: #cbd5e1;
    --accent-g: #3b82f6;
    --accent-t: #a855f7;
    --accent-s: #f59e0b;
    --radius:   12px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }

  body { background: var(--bg); color: var(--text); min-height: 100vh; }

  /* ── Header ── */
  header {
    text-align: center;
    padding: 3rem 1rem 2rem;
    background: linear-gradient(180deg, #1e3a5f 0%, var(--bg) 100%);
    border-bottom: 1px solid var(--border);
  }
  header h1 { font-size: clamp(1.8rem, 4vw, 2.8rem); font-weight: 800; letter-spacing: -.5px; }
  header .tagline { color: var(--muted); margin-top: .4rem; font-size: .95rem; }
  header .updated {
    display: inline-block; margin-top: .8rem;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 999px; padding: .3rem 1rem;
    font-size: .8rem; color: var(--muted);
  }

  /* ── Layout ── */
  main { max-width: 1280px; margin: 0 auto; padding: 2.5rem 1rem 4rem; }

  .section { margin-bottom: 3rem; }
  .section-header {
    display: flex; align-items: center; gap: .7rem;
    margin-bottom: 1.2rem; padding-bottom: .7rem;
    border-bottom: 2px solid var(--accent);
  }
  .section-header h2 { font-size: 1.3rem; font-weight: 700; }
  .section.general { --accent: var(--accent-g); }
  .section.tech    { --accent: var(--accent-t); }
  .section.sports  { --accent: var(--accent-s); }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--accent); flex-shrink: 0; }

  /* ── Grid ── */
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }

  /* ── Card ── */
  .card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 1.1rem 1.2rem;
    display: flex; flex-direction: column; gap: .6rem;
    cursor: pointer; user-select: none;
    transition: background .15s, transform .15s, box-shadow .15s;
  }
  .card:hover {
    background: var(--hover); transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,0,0,.4);
  }
  .card:focus-visible { outline: 2px solid var(--accent-g); outline-offset: 2px; }
  .card h3 { font-size: .92rem; font-weight: 600; line-height: 1.45; flex: 1; color: var(--text); }
  .card footer { display: flex; justify-content: space-between; align-items: center; gap: .5rem; flex-wrap: wrap; }
  .src  { font-size: .75rem; color: var(--muted); }
  .date { font-size: .72rem; color: var(--muted); opacity: .8; }

  .badge {
    display: inline-block; font-size: .7rem; font-weight: 700;
    padding: .2rem .55rem; border-radius: 999px; color: #fff; align-self: flex-start;
  }

  /* ── Modal overlay ── */
  .modal-overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,.78);
    display: flex; align-items: flex-start; justify-content: center;
    padding: 2rem 1rem 3rem;
    overflow-y: auto; z-index: 1000;
    opacity: 0; pointer-events: none;
    transition: opacity .2s ease;
  }
  .modal-overlay.open { opacity: 1; pointer-events: all; }

  /* ── Modal box ── */
  .modal-box {
    background: #1a2843;
    border: 1px solid var(--border);
    border-radius: 18px;
    max-width: 740px; width: 100%;
    padding: 2rem 2.2rem 2rem;
    position: relative;
    transform: translateY(24px);
    transition: transform .22s ease;
  }
  .modal-overlay.open .modal-box { transform: translateY(0); }

  .modal-close {
    position: absolute; top: 1.1rem; right: 1.1rem;
    background: transparent; border: 1px solid var(--border);
    color: var(--muted); border-radius: 50%;
    width: 34px; height: 34px; font-size: 1rem;
    cursor: pointer; display: flex; align-items: center; justify-content: center;
    transition: background .15s, color .15s;
  }
  .modal-close:hover { background: var(--border); color: var(--text); }

  .modal-sport-badge { display: inline-block; margin-bottom: .8rem; }

  #modal-title {
    font-size: 1.25rem; font-weight: 700; line-height: 1.45;
    padding-right: 2.5rem; margin-bottom: .75rem; color: var(--text);
  }

  .modal-meta {
    display: flex; gap: 1.2rem; margin-bottom: 1.5rem;
    flex-wrap: wrap; border-bottom: 1px solid var(--border); padding-bottom: 1rem;
    align-items: center;
  }
  .modal-meta span { font-size: .8rem; color: var(--muted); }
  .modal-meta .meta-source { color: #60a5fa; font-weight: 600; }
  .translated-badge {
    font-size: .68rem; background: #1e3a5f; border: 1px solid #3b82f6;
    color: #93c5fd; border-radius: 999px; padding: .15rem .5rem;
  }

  #modal-content { color: var(--body-txt); font-size: .925rem; line-height: 1.8; }
  #modal-content p { margin-bottom: .9rem; }
  #modal-content p:last-child { margin-bottom: 0; }

  .modal-footer {
    margin-top: 1.75rem; padding-top: 1rem;
    border-top: 1px solid var(--border);
    display: flex; justify-content: flex-end;
  }
  .modal-footer a {
    font-size: .82rem; color: var(--muted); text-decoration: none;
    padding: .4rem .9rem; border: 1px solid var(--border); border-radius: 8px;
    transition: color .15s, border-color .15s;
  }
  .modal-footer a:hover { color: var(--text); border-color: var(--text); }

  /* ── Site footer ── */
  footer.site-footer {
    text-align: center; padding: 1.5rem 1rem;
    color: var(--muted); font-size: .8rem; border-top: 1px solid var(--border);
  }
  footer.site-footer a { color: var(--muted); }
"""

JS = """
const DATA = JSON.parse(document.getElementById('iadata').textContent);

function openModal(id) {
  const a = DATA[id];
  if (!a) return;

  // Badge deportivo
  const badgeEl = document.getElementById('modal-sport-badge');
  if (a.sport) {
    badgeEl.textContent = a.icon + ' ' + a.sport;
    badgeEl.style.cssText = 'background:' + a.color + ';display:inline-block;font-size:.72rem;font-weight:700;padding:.2rem .6rem;border-radius:999px;color:#fff;margin-bottom:.8rem;';
  } else {
    badgeEl.style.display = 'none';
    badgeEl.textContent = '';
  }

  document.getElementById('modal-title').textContent = a.title;
  document.getElementById('modal-source').textContent = a.source;
  document.getElementById('modal-date').textContent   = a.date;

  // Badge de traducción
  const transBadge = document.getElementById('modal-translated');
  if (a.lang === 'en') {
    transBadge.style.display = 'inline';
    transBadge.textContent = '🌐 Traducido del inglés';
  } else {
    transBadge.style.display = 'none';
  }

  // Renderizar párrafos del artículo
  const contentEl = document.getElementById('modal-content');
  contentEl.innerHTML = '';
  (a.content || 'Contenido no disponible.')
    .split(/\\n+/)
    .map(p => p.trim())
    .filter(p => p.length > 0)
    .forEach(p => {
      const el = document.createElement('p');
      el.textContent = p;
      contentEl.appendChild(el);
    });

  document.getElementById('modal-link').href = a.link;

  const overlay = document.getElementById('modal');
  overlay.classList.add('open');
  overlay.removeAttribute('hidden');
  document.body.style.overflow = 'hidden';
  document.getElementById('modal-close-btn').focus();
}

function closeModal() {
  const overlay = document.getElementById('modal');
  overlay.classList.remove('open');
  document.body.style.overflow = '';
  setTimeout(() => overlay.setAttribute('hidden', ''), 220);
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal();
});
document.getElementById('modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeModal();
});
"""


def generate_html(general, tech, sports):
    updated = datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC")
    data = _prepare_data(general, tech, sports)
    data_json = json.dumps(data, ensure_ascii=False)

    def cards(items, prefix, sport=False):
        if not items:
            return "<p class='src' style='padding:.5rem'>No se encontraron noticias.</p>"
        return "\n".join(
            _card(f"{prefix}{i}", item, sport=sport)
            for i, item in enumerate(items)
        )

    g_cards = cards(general, "g")
    t_cards = cards(tech, "t")
    s_cards = cards(sports, "s", sport=True)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <meta name="description" content="IANews: noticias del día de actualidad, tecnología y deportes."/>
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
    <div class="section-header"><span class="dot"></span><h2>🌍 Noticias Generales</h2></div>
    <div class="grid">{g_cards}</div>
  </section>

  <section class="section tech">
    <div class="section-header"><span class="dot"></span><h2>💻 Tecnología</h2></div>
    <div class="grid">{t_cards}</div>
  </section>

  <section class="section sports">
    <div class="section-header"><span class="dot"></span><h2>🏆 Deportes</h2></div>
    <div class="grid">{s_cards}</div>
  </section>
</main>

<footer class="site-footer">
  Actualizado automáticamente cada día con GitHub Actions ·
  <a href="https://github.com/loiro85/IANews" target="_blank" rel="noopener">Ver repositorio</a>
</footer>

<!-- ── Modal ─────────────────────────────────────────── -->
<div id="modal" class="modal-overlay" hidden>
  <div class="modal-box" role="dialog" aria-modal="true" aria-labelledby="modal-title">
    <button id="modal-close-btn" class="modal-close" onclick="closeModal()" aria-label="Cerrar">✕</button>
    <span id="modal-sport-badge"></span>
    <h2 id="modal-title"></h2>
    <div class="modal-meta">
      <span class="meta-source" id="modal-source"></span>
      <span id="modal-date"></span>
      <span id="modal-translated" class="translated-badge" style="display:none"></span>
    </div>
    <div id="modal-content"></div>
    <div class="modal-footer">
      <a id="modal-link" href="#" target="_blank" rel="noopener noreferrer">
        Abrir artículo original ↗
      </a>
    </div>
  </div>
</div>

<!-- ── Datos embebidos ─────────────────────────────────── -->
<script type="application/json" id="iadata">{data_json}</script>
<script>{JS}</script>

</body>
</html>"""


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("📰 Obteniendo noticias generales...")
    general = fetch_items(GENERAL_FEEDS, limit=12)
    print(f"   → {len(general)} titulares")

    print("💻 Obteniendo noticias de tecnología...")
    tech = fetch_items(TECH_FEEDS, limit=12)
    print(f"   → {len(tech)} titulares")

    print("🏆 Obteniendo noticias de deportes...")
    sports = fetch_sports()
    print(f"   → {len(sports)} titulares")

    all_items = general + tech + sports
    print(f"\n🔍 Descargando artículos completos ({len(all_items)} en paralelo)...")
    enrich_with_content(all_items)

    print("\n🌐 Traduciendo artículos en inglés...")
    translate_english_items(general + tech + sports)

    html = generate_html(general, tech, sports)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("✅  index.html generado correctamente.")


if __name__ == "__main__":
    main()
