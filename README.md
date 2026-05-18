# 📰 IANews

Agregador de noticias diarias para GitHub Pages. Se actualiza automáticamente cada día a las 9:00 h (hora España) vía GitHub Actions.

**Categorías:**
- 🌍 **Noticias generales** — 10 artículos (Google News ES, BBC Mundo, El País)
- 💻 **Tecnología** — 10 artículos (Google News, Xataka, Genbeta)
- 🏆 **Deportes** — 10 artículos (F1, MotoGP, Formula E, fútbol europeo)

---

## Setup (5 pasos)

### 1. Sube los archivos a tu repo

```bash
git clone https://github.com/TU_USUARIO/TU_REPO.git
cp -r ~/Documents/Github/news-dashboard/. TU_REPO/
cd TU_REPO
git add .
git commit -m "feat: añadir IANews"
git push
```

### 2. Activa GitHub Pages

En tu repo → **Settings → Pages → Source**: selecciona `Deploy from a branch`, rama `main`, carpeta `/ (root)`.

### 3. Lanza el workflow por primera vez

**Actions → Actualizar noticias → Run workflow**

Esto genera el `index.html` real con las noticias del día.

### 4. Espera unos segundos y visita tu web

```
https://TU_USUARIO.github.io/TU_REPO/
```

### 5. (Opcional) Ejecutar localmente

```bash
pip install feedparser
python generate_news.py
# Abre index.html en el navegador
```

---

## Personalización

| Qué cambiar | Dónde |
|-------------|-------|
| Hora de actualización | `.github/workflows/update-news.yml` → campo `cron` |
| Fuentes de noticias | `generate_news.py` → variables `GENERAL_FEEDS`, `TECH_FEEDS`, `SPORTS_CONFIG` |
| Número de artículos | `generate_news.py` → parámetro `limit` en cada categoría |
| Colores / diseño | `generate_news.py` → variable `CSS` |
