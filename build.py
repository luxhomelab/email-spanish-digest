#!/usr/bin/env python3
"""
Build script for the Spanified static site (spanified.com).

Reads Jinja2 templates from templates/ and digest JSON files from data/digests/,
and renders a static site:

  - Static pages   -> repo root (index.html, subscribe.html, success.html,
                      confirm.html, unsubscribe.html)
  - Issue pages    -> archive/YYYY-MM-DD.html
  - Archive listing -> archive/index.html + archive/N.html (10 per page)
  - Sitemap        -> sitemap.xml
  - Podcast feed   -> podcast.xml (+ podcast/chapters/), episodes from data/podcast/

Usage: python3 build.py [--out dist] [--listmonk local] [--analytics on|off|auto]   (idempotent)

  Local dev against the dev Listmonk instead of prod:
    python3 build.py --listmonk local
  (endpoint + dev list UUID are picked automatically; override with
  --list-uuid / --es-list-uuid or env LISTMONK_URL / LISTMONK_LIST_UUID /
  LISTMONK_ES_LIST_UUID)
"""

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from email.utils import format_datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, pass_context
from markupsafe import Markup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(SCRIPT_DIR, "templates")
DATA_DIR = os.path.join(SCRIPT_DIR, "data", "digests")
# Spanish translations of data/digests: same filenames and schema.
ES_DATA_DIR = os.path.join(SCRIPT_DIR, "data", "digests_es")
ARTICLES_SRC_DIR = os.path.join(SCRIPT_DIR, "data", "articles")
# Spanish translations: same filenames, slugs, frontmatter keys and directives.
ARTICLES_ES_SRC_DIR = os.path.join(SCRIPT_DIR, "data", "articles_es")
OUT_DIR = SCRIPT_DIR
ARCHIVE_DIR = os.path.join(OUT_DIR, "archive")
ARTICLES_DIR = os.path.join(OUT_DIR, "articles")

SITE_URL = "https://spanified.com"
PAGE_SIZE = 10
ARTICLES_PAGE_SIZE = 10

# Listmonk backend for the native subscribe form (templates/partials/
# subscribe-form.html renders these into action / l value).
# The form POSTs urlencoded natively to <base>/api/public/subscription
# (Listmonk public API, which also accepts form-encoded `l`). A Cloudflare
# Worker in front of the endpoint verifies the Turnstile token server-side
# and issues the post-success redirect (Listmonk itself returns JSON here).
# Default is prod; local dev builds pass --listmonk local (or LISTMONK_URL)
# so the browser talks to the dev instance instead of prod.
LISTMONK_PROD_URL = "https://newsletter.spanified.com"
LISTMONK_LOCAL_URL = "https://listmonk.dslab.fyi"
LISTMONK_PROD_LIST_UUID = "d4edf463-70a3-45e5-a964-a39b48c49b2d"
LISTMONK_LOCAL_LIST_UUID = "5dcb6e29-0181-4c55-b68a-705133b53e10"
# Spanish forms (lang=es, the /es/ pages) subscribe to their own list.
LISTMONK_PROD_ES_LIST_UUID = "dc4801f8-3282-46e2-bbf9-488baff41312"
LISTMONK_LOCAL_ES_LIST_UUID = "cc400145-5ebe-4a7c-98e1-b0a336250224"

# Static pages rendered 1:1 from templates.
# Pages listed here are rendered to dist root. NOINDEX_PAGES are still
# rendered (linked from the site) but kept out of sitemap.xml.
NOINDEX_PAGES = {
    "success.html",
    "confirm.html",
    "unsubscribe.html",
    "search.html",
    "404.html",
}
STATIC_PAGES = [
    "index.html",
    "subscribe.html",
    "success.html",
    "confirm.html",
    "unsubscribe.html",
    "contact.html",
    "privacy.html",
    "cookies.html",
    "terms.html",
    "editor.html",
    "about.html",
    "search.html",
    "404.html",
]

# Spanish subscribe flow (plus the privacy/terms/cookies pages it links to
# and the about/editor/contact pages), rendered from templates/es/<name> to
# <out>/es/<name> (served as /es/subscribe etc.). ES_INDEXED_PAGES go into
# sitemap.xml; the rest are noindex like their English twins.
ES_PAGES = [
    "subscribe.html",
    "confirm.html",
    "success.html",
    "unsubscribe.html",
    "privacy.html",
    "terms.html",
    "cookies.html",
    "about.html",
    "editor.html",
    "contact.html",
]
ES_INDEXED_PAGES = {"subscribe.html", "privacy.html", "terms.html", "cookies.html",
                    "about.html", "editor.html", "contact.html"}

# Static assets copied verbatim into the output dir (hand-written pages,
# images, domain config, localized pages).
STATIC_COPY = [
    "CNAME",
    "robots.txt",
    "t.html",
    "yt.html",
    "wa.html",
    "mail.html",
    "success.jpg",
    "confirm.jpg",
    "logo.jpg",
    "logo-30.webp",
    "logo-60.webp",
    "logo-90.webp",
    "favicon.ico",
    "favicon.svg",
    "favicon.png",
    "apple-touch-icon.png",
    "static",
]

# Category emoji — mirrors format_email.py in spain-news-en.
CATEGORY_EMOJI = {
    "property": "🏠",
    "economy": "💰",
    "politics": "🏛️",
    "work": "👥",
    "visa": "📋",
    "health": "🏥",
    "migration": "🌍",
    "taxes": "📊",
    "events": "📅",
    "housing": "🏘️",
}
DEFAULT_EMOJI = "📰"

# SEO meta titles + descriptions per category (from SEO review, 2026-09-14).
CATEGORY_META = {
    "economy": ("Spain Economy News: Inflation, Jobs & GDP — Spanified", "Spain economy explained for expats: GDP growth, inflation, salaries and Bank of Spain data. Track the numbers that hit your prices and savings."),
    "politics": ("Spanish Politics News: Laws & Elections — Spanified", "Spanish politics without the noise: coalition deals, regional elections, new laws and EU relations. What Madrid decides, explained for residents."),
    "work": ("Jobs in Spain: Workers' Rights, SMI & Hiring — Spanified", "Jobs and labour in Spain: hiring trends, minimum wage (SMI), workers' rights, strikes and workplace reforms. Essential reading for workers."),
    "property": ("Spanish Property: Prices, Mortgages & Rent Caps — Spanified", "Spanish property news in English: house prices by region, rental caps, housing laws and mortgage trends. For buyers, renters and landlords."),
    "events": ("Events in Spain: Holidays, Festivals & Strikes — Spanified", "What's on in Spain: national holidays, festivals, strikes affecting travel, and major cultural moments. Daily life in the country, in brief."),
    "health": ("Healthcare in Spain: SNS News & Waiting Lists — Spanified", "Healthcare in Spain explained: public system (SNS) updates, waiting lists, new treatments and health alerts. Practical news for residents."),
    "taxes": ("Spanish Taxes: IRPF, Renta & Deadlines Explained — Spanified", "Spanish taxes without tears: IRPF brackets, renta and modelo 720 deadlines, deductions and Hacienda reforms. What you owe and when."),
    "visa": ("Spain Visas & Residency: Nomad, NIE & TIE — Spanified", "Visas and residency in Spain: digital nomad permit, Beckham Law, NIE/TIE procedures and immigration rules. The paperwork side, decoded."),
    "housing": ("Renting in Spain: Tenant Rights & Rental Prices — Spanified", "Renting and housing access in Spain: rental prices, tenant rights (LAU), evictions and regional housing plans. What protects you as a tenant."),
    "migration": ("Spain Migration: Arrivals, Policy & Integration — Spanified", "Migration and life between countries: arrivals data, integration policies, consular services and stories of people moving to and from Spain."),
}

# Unique SEO descriptions per category (2-3 sentences each).
CATEGORY_DESCRIPTIONS = {
    "economy": "Spain's economy in plain English: GDP growth, inflation, jobs data, EU funds, and what the Bank of Spain actually says. We track the numbers that affect prices, salaries, and savings — without the jargon.",
    "politics": "Spanish politics without the noise: coalition deals, regional elections, new laws, and EU relations. Short summaries of what was decided in Madrid — and what it means for people living in Spain.",
    "work": "Jobs and labour in Spain: hiring trends, workers' rights, minimum wage (SMI), strikes, and workplace reforms. Essential reading if you work here or plan to.",
    "property": "Spanish property market in English: house prices by region, rental caps, new housing laws, and mortgage trends. For buyers, renters, and landlords watching Spain's bricks.",
    "events": "What's on in Spain: national holidays, festivals, strikes affecting travel, and major cultural and sporting moments. The day-to-day life of the country, in brief.",
    "health": "Healthcare in Spain explained: public system (SNS) updates, waiting lists, new treatments, and public-health alerts. Practical news for residents and newcomers alike.",
    "taxes": "Spanish taxes without tears: IRPF brackets, deadlines (renta, modelo 720), deductions, and reforms from Hacienda. What you owe, when, and what changed this year.",
    "visa": "Visas and residency in Spain: digital nomad permits, Beckham Law, NIE/TIE procedures, and immigration rule changes. The paperwork side of Spanish life, decoded.",
    "housing": "Renting and housing access in Spain: rental prices, tenant rights (LAU), evictions data, and regional housing plans. Where the market is going — and what protects you as a tenant.",
    "migration": "Migration and life between countries: arrivals data, integration policies, consular services, and stories of people moving to and from Spain. The human side of the statistics.",
}


# --- i18n -------------------------------------------------------------------
# One mechanism for every Spanish (/es/) page that reuses an English template:
#
#   * Render the template with page_lang="es". base.html then sets
#     <html lang="es"> and swaps in the Spanish header/footer; the cookie
#     banner and subscribe form switch language (and Listmonk list) on it too.
#   * UI strings: gettext-style, the English text is the key. Templates call
#     {{ t("Share:") }} or {{ t("{n} news", n=count) }}; Python calls
#     tr(lang, "Share:"). English pages get the key back unchanged; Spanish
#     pages get ES_STRINGS[key]. A key missing from ES_STRINGS falls back to
#     English and is listed as a WARN at the end of the build.
#   * Links: {{ lang_url("/category/economy") }} / localize(lang, path) give
#     the /es/ twin on a Spanish page when ES_PATHS has it, else the English
#     path. ES_PATHS holds English paths whose Spanish twin is built (and
#     both are indexable); the build registers each digest, archive page and
#     category it renders in Spanish. The same set drives hreflang pairs
#     (partials/hreflang.html via `alt_path`, sitemap_hreflang).
#
# Longer per-slug copy (category SEO titles and descriptions) lives in
# *_ES dicts next to the English ones instead of in ES_STRINGS.
ES_STRINGS = {
    # Brand / breadcrumbs / navigation
    "Home": "Inicio",
    "Archive": "Archivo",
    "Page {n}": "Página {n}",
    "Spain Daily Digest": "España al Día",
    # Category display names (slug.capitalize() is the key)
    "Property": "Inmobiliario",
    "Housing": "Vivienda",
    "Economy": "Economía",
    "Politics": "Política",
    "Work": "Trabajo",
    "Visa": "Visados",
    "Health": "Sanidad",
    "Migration": "Migración",
    "Taxes": "Impuestos",
    "Events": "Agenda",
    "News": "Noticias",
    # Digest meta (digest_meta_title / digest_meta_description)
    "Spain News in English": "Noticias de España",
    "Spain News in English, {day}": "Noticias de España, {day}",
    "Spain News {day}": "Noticias de España, {day}",
    "Spain News {day}, {year} | Spain Daily Digest": "Noticias de España, {day} de {year} | España al Día",
    "Spain news, {date}: {title}": "Noticias de España, {date}: {title}",
    "; plus {n} more stories": "; y {n} noticias más",
    "Spain Daily Digest for {date} — the day's top news from Spain, summarized in English.":
        "España al Día del {date}: las noticias más importantes de España, resumidas.",
    # digest.html
    "Spain Daily Digest for {date} — the day's top stories from Spain, summarized in English.":
        "España al Día del {date}: las noticias más importantes del día en España, resumidas.",
    "Spain Daily Digest:": "España al Día:",
    "Edited by": "Editado por",
    "{n} story": "{n} noticia",
    "{n} stories": "{n} noticias",
    "◆ IMPORTANT": "◆ IMPORTANTE",
    "Explainer:": "Guía:",
    "Calculator:": "Calculadora:",
    "More news on this topic:": "Más noticias sobre este tema:",
    "Sunday shopping reminder": "Recordatorio para las compras del domingo",
    "Mercadona is closed tomorrow": "Mercadona cierra mañana",
    "Most supermarkets in Spain shut on Sundays. If the fridge is looking empty, shop today.":
        "La mayoría de los supermercados de España cierran los domingos. Si la nevera está vacía, haz la compra hoy.",
    "Mercadona is closed today": "Mercadona cierra hoy",
    "Corner shops, petrol-station stores and some city-centre supermarkets stay open.":
        "Abren las tiendas de barrio, las de las gasolineras y algunos supermercados del centro.",
    "Enjoyed this digest? Share it with a friend.": "¿Te ha gustado esta edición? Compártela con alguien.",
    "Tools and guides for today's news": "Calculadoras y guías para las noticias de hoy",
    "This digest is based on real news, created with the help of AI and reviewed by a human.":
        "Esta edición se basa en noticias reales, se elabora con ayuda de IA y la revisa una persona.",
    "More digests": "Más ediciones",
    "Copied!": "¡Copiado!",
    # Share (partials/share.html, attach_share)
    "Share:": "Compartir:",
    "Share on {network}": "Compartir en {network}",
    "Copy link": "Copiar enlace",
    "Copy": "Copiar",
    "{headline} — Spain Daily Digest": "{headline} | España al Día",
    "{title} — via Spanified": "{title}, vía Spanified",
    # Subscribe CTA card (partials/cta-form-card.html)
    "Free · Every morning · 5-minute read": "Gratis · Cada mañana · 5 minutos de lectura",
    "Spain's top news, in English, every morning": "Las noticias más importantes de España, cada mañana",
    "One short email a day — what happened in Spain and why it matters. Free, no spam, unsubscribe anytime.":
        "Un email breve al día: qué ha pasado en España y por qué importa. Gratis, sin spam y te das de baja cuando quieras.",
    "Join 1,000+ email subscribers · cancel anytime": "Únete a más de 1.000 suscriptores · date de baja cuando quieras",
    "Subscribe free": "Suscribirme gratis",
    # Hub cards (hub_card, partials/hub-cards.html)
    "Calculator": "Calculadora",
    "Guide": "Guía",
    "Net Salary Calculator": "Calculadora de sueldo neto",
    "Your payslip after IRPF and Social Security, and the Renta refund.":
        "Tu nómina después del IRPF y la Seguridad Social, y la devolución de la Renta.",
    "Autónomo Tax Calculator": "Calculadora de impuestos para autónomos",
    "Social security quota and IRPF for the self-employed.": "Cuota de la Seguridad Social e IRPF de los autónomos.",
    "Property Buying Cost Calculator": "Calculadora de gastos de compra de vivienda",
    "ITP, IVA/IGIC, AJD, notary and registry fees by region.": "ITP, IVA/IGIC, AJD, notaría y registro por comunidad autónoma.",
    "Rental Yield Calculator": "Calculadora de rentabilidad del alquiler",
    "Net yield, cash flow and IRR with resident and non-resident taxes.":
        "Rentabilidad neta, flujo de caja y TIR con impuestos de residentes y no residentes.",
    "Electricity Bill Calculator": "Calculadora de la factura de la luz",
    "PVPC and tariff comparison for your monthly bill.": "PVPC y comparación de tarifas para tu factura mensual.",
    "A {n}-minute read": "{n} minutos de lectura",
    # archive.html
    "Spanish News in English: Daily Archive — Spain Daily": "Archivo diario de noticias de España | España al Día",
    " — Page {n}": ", página {n}",
    "Browse every Spain Daily edition: Spanish news in English, summarized each day from the Spanish press.":
        "Todas las ediciones de España al Día: las noticias de España, resumidas cada día a partir de la prensa española.",
    " Page {n}.": " Página {n}.",
    "Spain Daily archive": "Archivo de España al Día",
    " — page {n}": ", página {n}",
    "Every edition of the Spain Daily digest.": "Todas las ediciones de España al Día.",
    "Latest": "Última",
    "{n} news": "{n} noticias",
    "No digests yet. Check back soon.": "Todavía no hay ediciones. Vuelve pronto.",
    "« First": "« Primera",
    "← Prev": "← Anterior",
    "Next →": "Siguiente →",
    # category.html
    "{name} News in Spain, in English — Spanified": "{name}: noticias de España | Spanified",
    "{name} news in Spain": "{name}: noticias de España",
    "{n} news · newest first · updated every morning": "{n} noticias · las más recientes primero · se actualiza cada mañana",
    "Get {name} news in your inbox every morning →": "Recibe cada mañana las noticias de {name} en tu email →",
    "{name} in Spain: calculators and guides": "{name} en España: calculadoras y guías",
    "→ Read the full digest": "→ Leer la edición completa",
    # Articles (article.html, articles.html, article_toc_html, load_articles)
    "Articles": "Artículos",
    "Articles — Spanified": "Guías prácticas para vivir en España | Spanified",
    "Spanified articles — practical guides to living in Spain: electricity, taxes, visas, property and everyday life.":
        "Artículos de Spanified: guías prácticas para vivir en España sobre la luz, los impuestos, los visados, la vivienda y el día a día.",
    "Spanified articles": "Artículos de Spanified",
    "Practical guides to living in Spain — learned by doing.": "Guías prácticas para vivir en España, aprendidas sobre el terreno.",
    "No articles yet. Check back soon.": "Todavía no hay artículos. Vuelve pronto.",
    "{n} min read": "{n} min de lectura",
    "By": "Por",
    "Founder and Editor": "Fundador y editor",
    "In this guide": "En esta guía",
    "Frequently asked questions": "Preguntas frecuentes",
    "Related calculators and guides": "Calculadoras y guías relacionadas",
    "Found this useful? Share it with a friend.": "¿Te ha resultado útil? Compártelo con alguien.",
    "Written from first-hand experience in Spain and reviewed by a human.":
        "Escrito a partir de la experiencia propia en España y revisado por una persona.",
    # Video player (video_embed_html); the videos themselves are in English
    "Video chapters": "Capítulos del vídeo",
    "{n} chapters": "{n} capítulos",
    "Play video": "Ver el vídeo",
    "Play video: {caption} ({mins} min)": "Ver el vídeo (en inglés): {caption} ({mins} min)",
    "{caption}. <a {link}>Watch on YouTube</a>": "{caption}. Vídeo en inglés. <a {link}>Verlo en YouTube</a>",
    # Home page (index.html). Adapted for the Spanish edition: it summarizes
    # the Spanish press in Spanish, so "in English" claims are dropped.
    # Quizzes are English-only pages; their intro says so (calculators have /es/ twins).
    "Spain Daily: Spanish News in English | Spanified": "España al Día: las noticias de España, cada mañana | Spanified",
    "Spanish news in English, every morning: Spain Daily sums up Spain's top stories on rents, taxes, visas and jobs. Read online or by email. Free.":
        "Las noticias de España, cada mañana: España al Día resume lo más importante sobre alquileres, impuestos, visados y empleo. Léelo en la web o por email. Gratis.",
    "Spain Daily": "España al Día",
    "Spanified Spain Daily": "Spanified España al Día",
    "Spain Daily newsletter": "Newsletter España al Día",
    "Spanified: Spain Daily, a free morning newsletter with Spain's top news in plain English, plus calculators, quizzes and guides for life in Spain.":
        "Spanified: España al Día, una newsletter gratuita cada mañana con las noticias más importantes de España en lenguaje claro, además de guías para vivir en España.",
    "Free daily newsletter with Spain's top news in plain English, a 5-minute read.":
        "Newsletter diaria y gratuita con las noticias más importantes de España en lenguaje claro, en 5 minutos de lectura.",
    "Spain Daily digest": "Resumen de España al Día",
    "Spanish news in English: Spain Daily, every morning": "Las noticias de España, cada mañana: España al Día",
    "Spain Daily by": "España al Día, de",
    " is a daily digest of Spanish newspapers in English: your 5-minute catch-up on what's happening in Spain.":
        ", es un resumen diario de la prensa española: cinco minutos para ponerte al día de lo que pasa en España.",
    "Get Spain Daily by email": "Recibir España al Día por email",
    "Read today's edition": "Leer la edición de hoy",
    "Free. One email around 08:00 Madrid time, seven days a week. Join 1,000+ email subscribers, cancel anytime.":
        "Gratis. Un email sobre las 08:00, hora de Madrid, los siete días de la semana. Únete a más de 1.000 suscriptores y date de baja cuando quieras.",
    "Read the full edition: {date}": "Leer la edición completa del {date}",
    "Browse past editions": "Ver ediciones anteriores",
    "How Spain Daily works": "Cómo funciona España al Día",
    "Spanish news sources": "fuentes de noticias españolas",
    "El País, El Mundo and 9 more": "El País, El Mundo y 9 más",
    "email in English": "email al día",
    "Around 08:00 Madrid time, every day": "Sobre las 08:00, hora de Madrid, cada día",
    "minutes to read": "minutos de lectura",
    "And you're up to speed on Spain": "Y ya estás al día de lo que pasa en España",
    "About Spain Daily": "Sobre España al Día",
    "What is Spain Daily?": "¿Qué es España al Día?",
    "Spain moves fast. Every morning we read the Spanish press cover to cover and hand you only the news that affects your life.":
        "En España pasan muchas cosas cada día. Cada mañana leemos la prensa española de arriba abajo y te contamos solo lo que afecta a tu vida.",
    "What you get": "Qué recibes",
    "A daily Spain news digest: short summaries in plain English, zero clickbait.":
        "Un resumen diario de la actualidad de España: noticias breves en lenguaje claro, sin titulares engañosos.",
    "What it covers": "De qué trata",
    "Rents, taxes, visas, jobs and the other stories that change daily life here.":
        "Alquileres, impuestos, visados, empleo y el resto de noticias que cambian el día a día.",
    "Who it's for": "Para quién es",
    "People who live in Spain, are planning the move or are watching from afar.":
        "Para quien vive en España, prepara la mudanza o sigue el país desde fuera.",
    "Which Spanish newspapers do we read?": "¿Qué periódicos leemos?",
    "Spain Daily is a newsletter, not a newspaper. We do not report the news ourselves: every day we aggregate the Spanish press, translate and summarize the stories in English, and link each one to its source.":
        "España al Día es una newsletter, no un periódico. No hacemos periodismo propio: cada día reunimos lo que publica la prensa española, lo resumimos y enlazamos cada noticia a su fuente.",
    "Sources": "Fuentes",
    "agency": "agencia",
    "International news makes the cut only when it directly affects Spain. It is":
        "Lo internacional entra solo cuando afecta directamente a España. Es",
    "Spanish news in English": "la prensa española en cinco minutos",
    ", built for the English-language reader who wants the Spanish press without reading it in Spanish.":
        ", pensada para quien quiere estar al día sin leer una docena de periódicos.",
    "How Spain Daily is made": "Cómo se hace España al Día",
    "How it works": "Cómo funciona",
    "We aggregate the Spanish press": "Reunimos la prensa española",
    "National dailies, wires and regional titles. We pick what affects your life: rents, taxes, visas, jobs.":
        "Diarios nacionales, agencias y cabeceras regionales. Elegimos lo que afecta a tu vida: alquileres, impuestos, visados y empleo.",
    "We summarize in plain English": "Lo resumimos en lenguaje claro",
    "Short factual briefs with links to the sources, AI-assisted and checked by":
        "Notas breves y factuales con enlace a las fuentes, redactadas con ayuda de IA y revisadas por",
    "the editor": "el editor",
    " before every send.": " antes de cada envío.",
    "You read it in 5 minutes": "Lo lees en 5 minutos",
    "In your inbox around 08:00 Madrid time, seven days a week.":
        "En tu bandeja de entrada sobre las 08:00, hora de Madrid, los siete días de la semana.",
    "Who makes the digest": "Quién hace el resumen",
    "Founder and editor, based in Spain": "Fundador y editor, vive en España",
    "Dmytro shapes each edition himself: he checks every AI-written summary against the original reporting and cuts anything that falls short.":
        "Dmytro prepara cada edición en persona: compara cada resumen hecho con IA con la noticia original y quita lo que no está a la altura.",
    "Meet the editor": "Conoce al editor",
    "editions": "ediciones",
    "since {date}": "desde el {date}",
    "followers on Threads and Reddit, all languages combined": "seguidores en Threads y Reddit, sumando todos los idiomas",
    "News by topic": "Noticias por tema",
    "Latest news by topic": "Últimas noticias por tema",
    "Interactive tools and quizzes": "Calculadoras y tests interactivos",
    "More from Spanified": "Más de Spanified",
    "Practical calculators, quick quizzes and guides for life in Spain. Free, no sign-up.":
        "Calculadoras prácticas, tests rápidos y guías para vivir en España. Gratis y sin registro.",
    "Calculators for life in Spain": "Calculadoras para vivir en España",
    "Taxes, property and bills worked out in plain English.":
        "Impuestos, vivienda y facturas, calculados paso a paso.",
    "Open calculator": "Abrir la calculadora",
    "Quizzes, two minutes each": "Tests de dos minutos",
    "Real stories from Spain, mixed with inventions. Can you tell which is which?":
        "Noticias reales de España mezcladas con inventos. ¿Sabes distinguirlas? Los tests están en inglés.",
    "Take the quiz: {title}": "Hacer el test (en inglés): {title}",
    "{title} quiz cover": "Portada del test {title}",
    "Take the quiz": "Hacer el test",
    "Latest articles": "Últimos artículos",
    "Practical guides to living in Spain — learned by doing, written in plain English.":
        "Guías prácticas para vivir en España, aprendidas sobre el terreno y escritas en lenguaje claro.",
    "Read the article": "Leer el artículo",
    "All articles": "Todos los artículos",
    "Questions": "Preguntas",
    "Questions, answered": "Preguntas frecuentes",
    "The short version of what readers ask us most. Anything else?":
        "Respuestas breves a lo que más nos preguntan. ¿Tienes otra duda?",
    "Write to us": "Escríbenos",
    "Subscribe": "Suscribirse",
    "Start tomorrow morning with Spain Daily": "Empieza mañana el día con España al Día",
    "Join 1,000+ email subscribers. Free, one email a day, cancel anytime.":
        "Únete a más de 1.000 suscriptores. Gratis, un email al día y te das de baja cuando quieras.",
}

# --- ES: static pages -------------------------------------------------------
# Latest-edition preview on /subscribe and /es/subscribe
# (partials/latest-edition-preview.html).
ES_STRINGS.update({
    "The latest edition, as it arrived in readers' inboxes": "La última edición, tal como llegó a los lectores",
    "And {n} more stories.": "Y {n} noticias más.",
    "Read this edition in full": "Leer la edición completa",
})
# Site header (partials/header.html, shared by both languages).
ES_STRINGS.update({
    "Spanified home": "Spanified: página de inicio",
    "Spain news in plain English": "Las noticias de España, cada mañana",
    "Show menu": "Mostrar menú",
    "Hide menu": "Ocultar menú",
    "Calculators": "Calculadoras",
    "Quizzes": "Tests",
    "Real or AI? — Spain news": "¿Real o IA? Noticias de España",
    "Real Law or Myth? — Spanish law": "¿Ley real o mito? Leyes españolas",
    "About": "Sobre nosotros",
    "Contact": "Contacto",
})

ES_MONTHS_SHORT = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"]

# English paths (e.g. "/archive/2026-11-23", "/archive/", "/category/work")
# whose /es/ twin is built. Starts with the home page ("/" -> /es/) and the
# indexed ES_PAGES; main() adds the digests, archive pages and categories
# rendered in Spanish.
ES_PATHS = {"/"} | {"/" + name[:-len(".html")] for name in ES_INDEXED_PAGES}

_untranslated = set()


def tr(lang, text, **kw):
    """Translate an English UI string (the key) for `lang`, then format it."""
    if lang == "es":
        out = ES_STRINGS.get(text)
        if out is None:
            _untranslated.add(text)
            out = text
    else:
        out = text
    return out.format(**kw) if kw else out


def localize(lang, path):
    """The /es/ twin of an English site path on Spanish pages, when built."""
    if lang != "es":
        return path
    base = path.split("#", 1)[0]
    return "/es" + path if base in ES_PATHS else path


_INTERNAL_HREF_RE = re.compile(r'href="(/(?!/)[^"]*)"')


def localize_links(lang, html_text):
    """localize() every internal href="/..." in rendered HTML (article
    bodies, FAQ answers): Spanish pages link the /es/ twins."""
    if lang != "es":
        return html_text
    return _INTERNAL_HREF_RE.sub(lambda m: f'href="{localize(lang, m.group(1))}"', html_text)


# Social accounts per language. The Spanish edition has its own Threads
# account and subreddit and no Facebook page; templates read the current
# page's set via socials() (partials/social.html, the success pages).
SOCIALS = {
    "en": {
        "threads": "https://www.threads.com/@spaindaily",
        "reddit": "https://www.reddit.com/r/SpainDaily/",
        "facebook": "https://www.facebook.com/spanified",
    },
    "es": {
        "threads": "https://www.threads.com/@spaindailyes",
        "reddit": "https://www.reddit.com/r/EspanaAlDia/",
    },
}


def register_i18n(env):
    """Expose t(), lang_url() and socials() to templates; all read page_lang."""
    env.globals["t"] = pass_context(lambda ctx, text, **kw: tr(ctx.get("page_lang", "en"), text, **kw))
    env.globals["lang_url"] = pass_context(lambda ctx, path: localize(ctx.get("page_lang", "en"), path))
    env.globals["socials"] = pass_context(lambda ctx: SOCIALS.get(ctx.get("page_lang", "en"), SOCIALS["en"]))


# Spanish twins of CATEGORY_META / CATEGORY_DESCRIPTIONS (same slugs).
CATEGORY_META_ES = {
    "economy": ("Economía de España: inflación, empleo y PIB | Spanified", "La economía de España, explicada: crecimiento del PIB, inflación, salarios y datos del Banco de España. Las cifras que afectan a tus precios y ahorros."),
    "politics": ("Política en España: leyes y elecciones | Spanified", "La política española sin ruido: pactos de gobierno, elecciones autonómicas, nuevas leyes y relación con la UE. Lo que se decide en Madrid, explicado."),
    "work": ("Empleo en España: derechos laborales, SMI y contratos | Spanified", "Empleo y trabajo en España: contratación, salario mínimo (SMI), derechos laborales, huelgas y reformas. Lectura esencial si trabajas en España."),
    "property": ("Inmobiliario en España: precios, hipotecas y alquiler | Spanified", "El mercado inmobiliario en España: precios por comunidad, topes al alquiler, leyes de vivienda e hipotecas. Para compradores, inquilinos y caseros."),
    "events": ("Agenda de España: festivos, fiestas y huelgas | Spanified", "Qué pasa en España: festivos nacionales, fiestas, huelgas que afectan a los viajes y grandes citas culturales. La vida diaria del país, en breve."),
    "health": ("Sanidad en España: SNS y listas de espera | Spanified", "La sanidad en España, explicada: novedades del sistema público (SNS), listas de espera, nuevos tratamientos y alertas sanitarias."),
    "taxes": ("Impuestos en España: IRPF, Renta y plazos | Spanified", "Los impuestos en España, claros: tramos del IRPF, plazos de la Renta y del modelo 720, deducciones y reformas de Hacienda. Qué pagas y cuándo."),
    "visa": ("Visados y residencia en España: nómada, NIE y TIE | Spanified", "Visados y residencia en España: permiso de nómada digital, Ley Beckham, trámites de NIE y TIE y normas de extranjería. El papeleo, explicado."),
    "housing": ("Alquiler en España: derechos del inquilino y precios | Spanified", "Alquiler y acceso a la vivienda en España: precios, derechos del inquilino (LAU), desahucios y planes autonómicos. Lo que te protege como inquilino."),
    "migration": ("Migración en España: llegadas e integración | Spanified", "Migración y vida entre países: datos de llegadas, políticas de integración, servicios consulares e historias de quienes llegan a España o se van."),
}

CATEGORY_DESCRIPTIONS_ES = {
    "economy": "La economía de España en lenguaje claro: crecimiento del PIB, inflación, datos de empleo, fondos europeos y lo que dice el Banco de España. Seguimos las cifras que afectan a precios, salarios y ahorros, sin jerga.",
    "politics": "La política española sin ruido: pactos de gobierno, elecciones autonómicas, nuevas leyes y relación con la UE. Resúmenes breves de lo que se decide en Madrid y de lo que significa para quien vive en España.",
    "work": "Empleo y trabajo en España: tendencias de contratación, derechos laborales, salario mínimo (SMI), huelgas y reformas. Lectura esencial si trabajas en España o piensas hacerlo.",
    "property": "El mercado inmobiliario español: precios de la vivienda por comunidad, topes al alquiler, nuevas leyes de vivienda e hipotecas. Para compradores, inquilinos y caseros que siguen el ladrillo en España.",
    "events": "Qué pasa en España: festivos nacionales, fiestas, huelgas que afectan a los viajes y grandes citas culturales y deportivas. La vida diaria del país, en breve.",
    "health": "La sanidad en España, explicada: novedades del sistema público (SNS), listas de espera, nuevos tratamientos y alertas de salud pública. Noticias prácticas para residentes y recién llegados.",
    "taxes": "Los impuestos en España, sin complicaciones: tramos del IRPF, plazos (Renta, modelo 720), deducciones y reformas de Hacienda. Qué debes pagar, cuándo y qué ha cambiado este año.",
    "visa": "Visados y residencia en España: permisos de nómada digital, Ley Beckham, trámites de NIE y TIE y cambios en las normas de extranjería. El lado burocrático de vivir en España, explicado.",
    "housing": "Alquiler y acceso a la vivienda en España: precios del alquiler, derechos del inquilino (LAU), datos de desahucios y planes autonómicos de vivienda. Hacia dónde va el mercado y qué te protege como inquilino.",
    "migration": "Migración y vida entre países: datos de llegadas, políticas de integración, servicios consulares e historias de quienes llegan a España o se marchan. El lado humano de las estadísticas.",
}


def display_date(date_str, lang="en"):
    """Long date in the page language: 'September 10, 2026' / '10 de septiembre de 2026'."""
    return format_date_es(date_str) if lang == "es" else format_date(date_str)


def format_date(date_str):
    """'2026-09-10' -> 'September 10, 2026'."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.strftime('%B')} {dt.day}, {dt.year}"
    except (ValueError, TypeError):
        return date_str


ES_MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def format_date_es(date_str):
    """'2026-09-10' -> '10 de septiembre de 2026'."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.day} de {ES_MONTHS[dt.month - 1]} de {dt.year}"
    except (ValueError, TypeError):
        return date_str


def mercadona_line(date_str, lang="en"):
    """Weekend Mercadona reminder, keyed to the edition's own date."""
    try:
        weekday = datetime.strptime(date_str, "%Y-%m-%d").weekday()
    except (ValueError, TypeError):
        return None
    if weekday == 5:  # Saturday
        return {
            "title": tr(lang, "Mercadona is closed tomorrow"),
            "note": tr(lang, "Most supermarkets in Spain shut on Sundays. If the fridge is looking empty, shop today."),
        }
    if weekday == 6:  # Sunday
        return {
            "title": tr(lang, "Mercadona is closed today"),
            "note": tr(lang, "Corner shops, petrol-station stores and some city-centre supermarkets stay open."),
        }
    return None


def category_name(slug, lang="en"):
    """Display name of a category slug: 'economy' -> 'Economy' / 'Economía'."""
    return tr(lang, (slug or "news").capitalize())


def top_categories(items, n=3, lang="en"):
    """Most frequent categories as display strings, e.g. '💰 Economy'."""
    counts = Counter(item.get("category", "") for item in items)
    result = []
    for category, _ in counts.most_common(n):
        if not category:
            continue
        emoji = CATEGORY_EMOJI.get(category, DEFAULT_EMOJI)
        result.append(f"{emoji} {category_name(category, lang)}")
    return result


def load_digests(data_dir=None):
    """Load and sort (newest first) all digest JSON files in data/digests/
    (or `data_dir`, e.g. ES_DATA_DIR)."""
    data_dir = data_dir or DATA_DIR
    digests = []
    if os.path.isdir(data_dir):
        for filename in sorted(os.listdir(data_dir)):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(data_dir, filename)
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"WARN: skipping {filename}: {exc}", file=sys.stderr)
                continue
            date = data.get("date") or filename[:-5]
            data["date"] = date
            digests.append(data)
    digests.sort(key=lambda d: d.get("date", ""), reverse=True)
    return digests


def digest_context(data, lang="en", title_subject=True):
    """Normalize a digest dict into the context passed to digest.html.

    With lang="es" (data/digests_es) the page lives at /es/archive/<date>.
    Spanish digests have no rotating headline, so the email subject stands in.
    `title_subject=False` keeps the subject out of the meta title: older
    Spanish subjects are translated taglines ("España hoy. Brevemente."), so
    the title leads with the top story, as the English twin does.
    """
    items = data.get("items", [])
    date = data.get("date", "")
    subject = (data.get("subject") or "").strip()
    headline = (data.get("headline") or data.get("variant")
                or (subject if lang == "es" else "") or tr(lang, "Spain Daily Digest"))
    words = len(headline.split()) + sum(
        len((i.get("title", "") + " " + i.get("body", "")).split()) for i in items
    )
    tag_cats = [category_name(c, lang) for c in dict.fromkeys(
        i.get("category", "") for i in items if i.get("category"))][:3]
    return {
        "lang": lang,
        "date": date,
        "date_display": display_date(date, lang),
        "headline": headline,
        "stories": items,
        "mercadona": mercadona_line(date, lang),
        "story_count": len(items),
        "top_categories": top_categories(items, lang=lang),
        "url": lang_path(lang, f"/archive/{date}"),
        "subject": subject,
        "title_subject": subject if title_subject else "",
        "meta_title": digest_meta_title(date, items, subject if title_subject else None, lang=lang),
        "meta_description": digest_meta_description(date, headline, items, lang=lang),
        "word_count": words,
        "tag_categories": tag_cats,
    }


def lang_path(lang, path):
    """Path of a page built in `lang`: '/archive/' -> '/es/archive/' for es.

    Unlike localize(), this does not check ES_PATHS: use it for the URL of
    the page being rendered, not for links to other pages."""
    return "/es" + path if lang == "es" else path


def short_date(date_str, lang="en"):
    """'2026-09-10' -> 'Sep 10, 2026' / '10 sept, 2026'."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if lang == "es":
            return f"{dt.day} {ES_MONTHS_SHORT[dt.month - 1]}, {dt.year}"
        return f"{dt.strftime('%b')} {dt.day}, {dt.year}"
    except (ValueError, TypeError):
        return date_str


def digest_meta_title(date, items, subject=None, dated=False, lang="en"):
    """Story-first title: '<email subject> | Spain News in English'.

    Leads with the edition's email subject (written to summarize the day's
    main stories) and the evergreen query expats search for. The date is in
    the URL, H1, description and datePublished, so it is left out unless
    `dated` is set (see `dedupe_digest_titles`). Older digests without
    a subject fall back to the top story title plus the date. The lead is cut
    at a word boundary so the whole title stays under ~82 characters.
    """
    day = short_date(date, lang).rsplit(",", 1)[0]
    subject = (subject or "").strip()
    if subject:
        top = subject
        suffix = tr(lang, "Spain News in English, {day}", day=day) if dated else tr(lang, "Spain News in English")
    else:
        top = next((i.get("title", "").strip() for i in items if i.get("title")), "")
        suffix = tr(lang, "Spain News {day}", day=day)
    if not top:
        return tr(lang, "Spain News {day}, {year} | Spain Daily Digest", day=day, year=date[:4])
    room = 82 - len(suffix) - 3
    if len(top) > room:
        top = top[:room - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return f"{top} | {suffix}"


def dedupe_digest_titles(digests):
    """Add the date to titles whose subject repeats another edition's.

    Without the date the subject is all that tells digest titles apart, and
    recurring stories can produce the same subject twice.
    """
    counts = Counter(d["title_subject"].lower() for d in digests if d.get("title_subject"))
    for d in digests:
        if d.get("title_subject") and counts[d["title_subject"].lower()] > 1:
            d["meta_title"] = digest_meta_title(
                d["date"], d["stories"], d["title_subject"], dated=True, lang=d.get("lang", "en"))
    return digests


def digest_meta_description(date, headline, items, lang="en"):
    """Unique per-day description built from the day's story titles.

    The headline is a rotating tagline ('Spain today. Briefly.'), so it is
    not used. Stories are added in order, skipping any that would not fit in
    ~155 chars (Google shows that much whole in the snippet); when room is
    left, the count of the other stories closes it.
    """
    titles = [i.get("title", "").strip().rstrip(".") for i in items]
    titles = [t for t in titles if t]
    if not titles:
        return tr(lang, "Spain Daily Digest for {date} — the day's top news from Spain, summarized in English.", date=date)
    desc = tr(lang, "Spain news, {date}: {title}", date=display_date(date, lang), title=titles[0])
    used = 1
    for t in titles[1:]:
        if len(desc) + len(t) + 2 <= 157:
            desc += f"; {t}"
            used += 1
    rest = len(titles) - used
    more = tr(lang, "; plus {n} more stories", n=rest) if rest > 1 else ""
    if more and len(desc) + len(more) <= 157:
        desc += more
    return desc if len(desc) <= 157 else desc[:154].rsplit(" ", 1)[0] + "…"


def archive_url(page, lang="en"):
    return lang_path(lang, "/archive/" if page == 1 else f"/archive/{page}")


def pagination(page, total_pages, lang="en"):
    # Compact window: current + up to 2 neighbours each side (max 5 numbers).
    # Near the edges the window shifts so it stays full when possible.
    start = min(max(page - 2, 1), max(total_pages - 4, 1))
    end = min(start + 4, total_pages)
    return {
        "current": page,
        "total_pages": total_pages,
        "first_url": archive_url(1, lang),
        "prev_url": archive_url(page - 1, lang) if page > 1 else None,
        "next_url": archive_url(page + 1, lang) if page < total_pages else None,
        "pages": [
            {"number": p, "url": archive_url(p, lang), "current": p == page}
            for p in range(start, end + 1)
        ],
    }


def articles_url(page):
    if page == 1:
        return "/articles/"
    return f"/articles/{page}"


def articles_pagination(page, total_pages, lang="en"):
    start = min(max(page - 2, 1), max(total_pages - 4, 1))
    end = min(start + 4, total_pages)
    url = lambda p: lang_path(lang, articles_url(p))
    return {
        "current": page,
        "total_pages": total_pages,
        "first_url": url(1),
        "prev_url": url(page - 1) if page > 1 else None,
        "next_url": url(page + 1) if page < total_pages else None,
        "pages": [
            {"number": p, "url": url(p), "current": p == page}
            for p in range(start, end + 1)
        ],
    }


def parse_article_file(path):
    """Parse data/articles/*.md with --- frontmatter --- + markdown body."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    meta = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            front = text[3:end].strip().strip("-\n")
            body = text[end + 4:].lstrip("\n")
            for line in front.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip()
    return meta, body


def article_inline_md(s):
    """Escape + inline markdown (bold, italic, links) -> HTML.

    Shared by the article body converter and the FAQ answer parser, so
    **bold** and links work identically in body text and FAQ answers.
    """
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)

    def _link(m):
        text, url = m.group(1), m.group(2)
        if url.startswith("http://") or url.startswith("https://"):
            return f'<a href="{url}" target="_blank" rel="noopener">{text}</a>'
        return f'<a href="{url}">{text}</a>'

    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, s)
    return s


def inline_md_plain(s):
    """Inline markdown -> plain text: [label](url) becomes label, ** and *
    markers drop. For JSON-LD text, which must carry no markup or URLs
    (a raw "(/calculators/x)" there is also an unlocalized link on /es/)."""
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    return re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", s)


# "300 000 €", "1 000–6 000 €", "80 m²": glue digit groups and units with
# no-break spaces so a narrow column never strands "000 €" on its own line.
_NBSP_THOUSANDS_RE = re.compile(r"(?<=\d) (?=\d{3}(?!\d))")
_NBSP_UNIT_RE = re.compile(r"(?<=\d) (?=(?:€|%|m²|km)(?!\w))")
_HTML_TAG_SPLIT_RE = re.compile(r"(<[^>]*>)")


def nbsp_numbers(html_text):
    """Apply the number no-break rules to text only, never inside tags."""
    parts = _HTML_TAG_SPLIT_RE.split(html_text)
    for i in range(0, len(parts), 2):
        parts[i] = _NBSP_UNIT_RE.sub(" ", _NBSP_THOUSANDS_RE.sub(" ", parts[i]))
    return "".join(parts)


ARTICLE_FIGURE_RE = re.compile(r'^!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)$')
# "::: graphic <name>" on its own line -> the hand-written HTML partial
# templates/partials/article-graphics/<article-slug>/<name>.html, inlined as is.
ARTICLE_GRAPHIC_RE = re.compile(r"^:::\s*graphic\s+([a-z0-9][a-z0-9-]*)$")
ARTICLE_GRAPHICS_DIR = os.path.join(TEMPLATES_DIR, "partials", "article-graphics")


def article_graphic_html(slug, name, lang="en"):
    """Read an article's HTML graphic partial; warn and return "" if missing.

    Spanish pages use the translated copy <slug>/es/<name>.html (same markup,
    Spanish text); a missing copy warns and falls back to the English one.
    Partials of an article listed in ARTICLE_GRAPHIC_DATA are Jinja templates
    rendered with that article's data (in `lang`) as `d`; all others are
    inlined as is."""
    path = os.path.join(ARTICLE_GRAPHICS_DIR, slug or "", f"{name}.html")
    if lang == "es":
        es_path = os.path.join(ARTICLE_GRAPHICS_DIR, slug or "", "es", f"{name}.html")
        if os.path.isfile(es_path):
            path = es_path
        else:
            print(f"WARN: no Spanish article graphic, using English: {es_path}", file=sys.stderr)
    try:
        with open(path, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        print(f"WARN: article graphic not found: {path}", file=sys.stderr)
        return ""
    loader = ARTICLE_GRAPHIC_DATA.get(slug or "")
    if loader is None:
        return source.strip()
    env = Environment(autoescape=True, trim_blocks=True, lstrip_blocks=True)
    env.filters["md"] = lambda s: Markup(article_inline_md(s or ""))
    env.globals["js_version"] = js_version()
    return env.from_string(source).render(d=loader(lang)).strip()


# Spain general election, 29 Nov 2026: curated promises with feasibility
# ratings, translated from the research. data/election-2026/meta.json holds
# the scale, topics and parties; items/<party>.json the promises, each keyed
# by its index `i` in the research files.
ELECTION_2026_DIR = os.path.join(SCRIPT_DIR, "data", "election-2026")
ELECTION_RATINGS = "ABCDV"
_election_cache = None  # {lang: data}


def _election_es_overlay(meta, raw_by_party):
    """Swap the English text of the election data for the Spanish one, in place.

    data/election-2026/es/ holds only the translated text: meta.json (rating,
    chance, need, topic and approach labels; per-party bloc and notes) and
    items/<party>.json ([{i, title, detail, c, ref, pos?, neg?, s: [titles]}]).
    Ratings, numbers and URLs always come from the English files. The build
    fails when a promise or source has no translation or the shapes differ."""
    es_dir = os.path.join(ELECTION_2026_DIR, "es")
    with open(os.path.join(es_dir, "meta.json"), encoding="utf-8") as fh:
        es = json.load(fh)
    for r in meta["ratings"]:
        r.update(es["ratings"][r["key"]])
    if set(es["chances"]) != set(meta["chances"]) or set(es["needs"]) != set(meta["needs"]):
        raise ValueError("election es/meta.json: chances/needs keys differ from meta.json")
    meta["chances"], meta["needs"] = es["chances"], es["needs"]
    for t in meta["topics"]:
        t["label"] = es["topics"][t["key"]]
    for key, rows in meta["approaches"].items():
        labels = es["approaches"][key]
        if len(labels) != len(rows):
            raise ValueError(f"election es/meta.json: approaches for {key} need {len(rows)} labels")
        for row, label in zip(rows, labels):
            row["label"] = label
    for party in meta["parties"]:
        party.update(es["parties"][party["key"]])
        with open(os.path.join(es_dir, "items", f"{party['key']}.json"), encoding="utf-8") as fh:
            tr_by_i = {it["i"]: it for it in json.load(fh)}
        raw = raw_by_party[party["key"]]
        if set(tr_by_i) != {it["i"] for it in raw}:
            raise ValueError(f"election es/items/{party['key']}.json: promises differ from the English file")
        for it in raw:
            t = tr_by_i[it["i"]]
            if len(t["s"]) != len(it["s"]) or any(bool(t.get(f)) != bool(it.get(f)) for f in ("pos", "neg")):
                raise ValueError(f"election es item {party['key']}#{it['i']}: sources or pros/cons differ from English")
            for field in ("title", "detail", "c", "ref", "pos", "neg"):
                if it.get(field):
                    it[field] = t[field]
            it["s"] = [dict(src, t=title) for src, title in zip(it["s"], t["s"])]


def load_election_2026(lang="en"):
    """Load and validate the election data; the build fails on bad data.

    lang="es" gives the same promises, ratings and numbers with the Spanish
    text (see _election_es_overlay)."""
    global _election_cache
    if _election_cache is None:
        _election_cache = {}
    if lang in _election_cache:
        return _election_cache[lang]
    with open(os.path.join(ELECTION_2026_DIR, "meta.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    raw_by_party = {}
    for party in meta["parties"]:
        with open(os.path.join(ELECTION_2026_DIR, "items", f"{party['key']}.json"), encoding="utf-8") as fh:
            raw_by_party[party["key"]] = json.load(fh)
    if lang == "es":
        _election_es_overlay(meta, raw_by_party)
    topics = {t["key"]: t for t in meta["topics"]}
    topic_order = {t["key"]: n for n, t in enumerate(meta["topics"])}
    parties = []
    items = []
    for party in meta["parties"]:
        key = party["key"]
        raw = raw_by_party[key]
        by_i = {}
        for it in raw:
            where = f"election item {key}#{it.get('i')}"
            if it["f"] not in ELECTION_RATINGS or it["t"] not in meta["chances"]:
                raise ValueError(f"{where}: bad rating or chance")
            if it["topic"] not in topics:
                raise ValueError(f"{where}: unknown topic {it['topic']}")
            if any(n not in meta["needs"] for n in it["n"]):
                raise ValueError(f"{where}: unknown need in {it['n']}")
            # Pros and cons exist exactly for the feasible (A/B) promises.
            if (it["f"] in "AB") != bool(it.get("pos") and it.get("neg")):
                raise ValueError(f"{where}: pros/cons must be set for A/B items only")
            if it.get("url") and not it["url"].startswith("https://"):
                raise ValueError(f"{where}: url must be https")
            if any(not s.get("t") or not s.get("u", "").startswith("https://") for s in it["s"]):
                raise ValueError(f"{where}: every source needs a title and an https URL")
            item = dict(it, party=key, id=f"{key}-{it['i']}")
            by_i[it["i"]] = item
            items.append(item)
        totals = party["totals"]
        n = sum(totals.values())
        parties.append(dict(
            party, count=n,
            feasible_pct=round(100 * (totals["A"] + totals["B"]) / n),
            shares=[(r, totals[r], 100 * totals[r] / n) for r in ELECTION_RATINGS],
            headline_items=[by_i[i] for i in party["headline"]],
            shown=len(raw),
        ))
    if sum(p["count"] for p in parties) != meta["total_items"]:
        raise ValueError("election party totals do not add up to total_items")
    party_order = {p["key"]: n for n, p in enumerate(parties)}
    items.sort(key=lambda it: (topic_order[it["topic"]], ELECTION_RATINGS.index(it["f"]), party_order[it["party"]]))
    for it in items:
        party = parties[party_order[it["party"]]]
        it["party_name"] = party["name"]
        it["party_color"] = party["color"]
        it["programme"] = party["programme"]
        it["topic_label"] = topics[it["topic"]]["label"]
    by_topic = [(t, [it for it in items if it["topic"] == t["key"]]) for t in meta["topics"]]
    # Topic comparison: each topic's promises grouped by approach (rows) and
    # rating (columns). Every promise of a listed topic sits in exactly one row.
    by_id = {it["id"]: it for it in items}
    compare = []
    for t, topic_items in by_topic:
        rows = meta["approaches"].get(t["key"])
        if not rows:
            continue
        placed = [i for row in rows for i in row["items"]]
        expected = sorted(it["id"] for it in topic_items)
        if sorted(placed) != expected:
            raise ValueError(f"election approaches for {t['key']} must list each of its promises once")
        present = [r for r in ELECTION_RATINGS if any(it["f"] == r for it in topic_items)]
        compare.append(dict(
            topic=t, count=len(topic_items),
            parties=len({it["party"] for it in topic_items}),
            ratings=present,
            rows=[dict(label=row["label"], cells=[
                (r, sorted((by_id[i] for i in row["items"] if by_id[i]["f"] == r),
                           key=lambda it: party_order[it["party"]]))
                for r in present]) for row in rows],
        ))
    _election_cache[lang] = dict(
        meta,
        ratings_by_key={r["key"]: r for r in meta["ratings"]},
        parties=parties,
        parties_by_feasibility=sorted(parties, key=lambda p: -p["feasible_pct"]),
        promises=items,
        by_topic=by_topic,
        compare=compare,
        as_of_display=display_date(meta["as_of"], lang),
        election_display=display_date(meta["election"], lang),
    )
    return _election_cache[lang]


# Article slug -> loader of the data its "::: graphic" partials render with.
ARTICLE_GRAPHIC_DATA = {"spain-election-2026-promises": load_election_2026}


# YouTube videos from data/videos.json, keyed by video id. Rendered as a
# click-to-load facade (thumbnail + play button; static/js/video-embed.js
# swaps in a youtube-nocookie iframe) with VideoObject JSON-LD. Used by
# "::: video <id>" in article markdown and video_embed(id) in templates.
VIDEOS_PATH = os.path.join(SCRIPT_DIR, "data", "videos.json")
ARTICLE_VIDEO_RE = re.compile(r"^:::\s*video\s+([A-Za-z0-9_-]{11})$")
_videos_cache = None


def load_videos():
    global _videos_cache
    if _videos_cache is None:
        try:
            with open(VIDEOS_PATH, encoding="utf-8") as fh:
                _videos_cache = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARN: cannot read {VIDEOS_PATH}: {exc}", file=sys.stderr)
            _videos_cache = {}
    return _videos_cache


# Spanish region names that take an article mid-sentence ("el País Vasco es
# donde...", "en la Comunidad Valenciana"). Used by the generated ES FAQs.
ES_REGION_ARTICLE = {
    "País Vasco": "el País Vasco",
    "Comunidad Valenciana": "la Comunidad Valenciana",
    "Región de Murcia": "la Región de Murcia",
    "Illes Balears": "las Illes Balears",
}


def es_region(name):
    return ES_REGION_ARTICLE.get(name, name)


def video_embed_html(video_id, lang="en"):
    """Facade + VideoObject JSON-LD for one video; warn and return "" if unknown.

    The videos are in English: Spanish pages get Spanish player labels and a
    caption that says so, and the visible chapter list uses each chapter's
    "title_es" when present; the video title and JSON-LD stay English."""
    v = load_videos().get(video_id)
    if not v:
        print(f"WARN: video not in data/videos.json: {video_id}", file=sys.stderr)
        return ""
    secs = int(v["duration"])
    mins, s = divmod(secs, 60)
    clock = f"{mins}:{s:02d}"
    watch = f"https://www.youtube.com/watch?v={video_id}"
    watch_attrs = f'href="{watch}" target="_blank" rel="noopener"'

    thumb = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
    caption = html.escape(v.get("caption") or v["title"])
    ld = {
        "@context": "https://schema.org", "@type": "VideoObject",
        "name": v["title"], "description": v["description"],
        "thumbnailUrl": [thumb, f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"],
        "uploadDate": v["upload_date"], "duration": f"PT{mins}M{s}S",
        "embedUrl": f"https://www.youtube.com/embed/{video_id}", "url": watch,
        "publisher": {"@type": "Organization", "name": "Spanified", "url": SITE_URL + localize(lang, "/")},
    }
    chapters = v.get("chapters") or []
    if chapters:
        # Key moments: each chapter is a Clip that ends where the next starts.
        ends = [c["t"] for c in chapters[1:]] + [secs]
        ld["hasPart"] = [
            {"@type": "Clip", "name": c["title"], "startOffset": c["t"],
             "endOffset": end, "url": f"{watch}&t={c['t']}s"}
            for c, end in zip(chapters, ends)
        ]
    ld_json = json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")
    chapters_html = ""
    if chapters:
        items = "".join(
            f'<li{" class=\"ve-chap-key\"" if c.get("highlight") else ""}>'
            f'<a class="ve-chap" href="{watch}&amp;t={c["t"]}s" target="_blank" rel="noopener" data-start="{c["t"]}">'
            f'<span class="ve-chap-time">{c["t"] // 60}:{c["t"] % 60:02d}</span>'
            f'<span class="ve-chap-title">{html.escape((lang == "es" and c.get("title_es")) or c["title"])}</span></a></li>'
            for c in chapters
        )
        chapters_html = (
            f'<nav class="ve-chapters" aria-label="{tr(lang, "Video chapters")}">'
            f'<p class="ve-chapters-head">{tr(lang, "{n} chapters", n=len(chapters))}</p><ol>{items}</ol></nav>\n'
        )
    return (
        f'<figure class="video-embed{" has-chapters" if chapters else ""}" data-pagefind-ignore>\n'
        f'<div class="ve-player"><a class="ve-frame" href="{watch}" target="_blank" rel="noopener" data-video-id="{video_id}"'
        f' data-video-title="{caption}" aria-label="{tr(lang, "Play video: {caption} ({mins} min)", caption=caption, mins=mins)}">'
        f'<img src="{thumb}" alt="" width="1280" height="720" loading="lazy" decoding="async">'
        f'<span class="ve-play"><span class="ve-play-icon"><svg viewBox="0 0 24 24" aria-hidden="true">'
        f'<path d="M8 5.5v13l10.5-6.5z"/></svg></span>'
        f'<span class="ve-play-label">{tr(lang, "Play video")}</span><span class="ve-time">{clock}</span></span></a></div>\n'
        f'{chapters_html}'
        f'<figcaption class="ve-caption">{tr(lang, "{caption}. <a {link}>Watch on YouTube</a>", caption=caption, link=watch_attrs)}</figcaption>\n'
        f'<script type="application/ld+json">{ld_json}</script>\n'
        f'<script src="/static/js/video-embed.js?v={js_version()}" defer></script>\n'
        f"</figure>"
    )



def video_embed(video_id, lang="en"):
    """Jinja global: {{ video_embed("<id>", page_lang) }} in templates."""
    return Markup(video_embed_html(video_id, lang or "en"))

# "::: toc" on its own line -> table of contents of every h2 in the article.
ARTICLE_TOC_MARKER = "::: toc"
_TOC_PLACEHOLDER = "\x00toc\x00"


def article_heading_id(text_html, used):
    """Anchor id for a heading: lowercase words joined by '-', unique in `used`."""
    plain = html.unescape(re.sub(r"<[^>]+>", "", text_html))
    # Fold accents (autónomo -> autonomo) so ids stay readable, not "aut-nomo".
    plain = unicodedata.normalize("NFKD", plain).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-") or "section"
    hid, n = base, 2
    while hid in used:
        hid, n = f"{base}-{n}", n + 1
    used.add(hid)
    return hid


def article_toc_html(entries, lang="en"):
    """<nav> table of contents from (id, title_html) pairs; two columns on
    wide screens, filled top to bottom (--rows sets the split)."""
    items = "\n".join(f'<li><a href="#{hid}">{title}</a></li>' for hid, title in entries)
    rows = (len(entries) + 1) // 2
    return (
        '<nav class="art-toc" aria-labelledby="art-toc-title">\n'
        f'<p class="art-toc-title" id="art-toc-title">{tr(lang, "In this guide")}</p>\n'
        f'<ol class="art-toc-list" style="--rows: {rows}">\n{items}\n</ol>\n'
        "</nav>"
    )


def article_markdown_to_html(md, slug=None, toc_extra=(), lang="en"):
    """Minimal markdown -> HTML (stdlib only): headings, bold, italic,
    links, unordered lists, figures (16:9 images), HTML graphic partials
    ("::: graphic <name>", looked up under the article's slug), a table of
    contents ("::: toc", listing every h2 plus `toc_extra` (id, title)
    pairs), paragraphs, hr. Input is escaped first. Every h2 gets an id.
    `lang` picks the language of the graphics and the TOC label."""
    lines = md.splitlines()
    out = []
    in_list = False
    in_para = []
    headings = []
    used_ids = {hid for hid, _ in toc_extra}

    def h2(text):
        title = article_inline_md(text)
        hid = article_heading_id(title, used_ids)
        headings.append((hid, title))
        return f'<h2 id="{hid}">{title}</h2>'

    def flush_para():
        if in_para:
            text = " ".join(in_para)
            out.append(f"<p>{article_inline_md(text)}</p>")
            in_para.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_para()
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        if stripped in ("---", "***"):
            flush_para()
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append("<hr>")
            continue
        if stripped.startswith("## "):
            flush_para()
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(h2(stripped[3:].strip()))
            continue
        if stripped.startswith("### "):
            flush_para()
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h3>{article_inline_md(stripped[4:].strip())}</h3>")
            continue
        if stripped.startswith("# "):
            flush_para()
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(h2(stripped[2:].strip()))
            continue
        if stripped.startswith("> "):
            flush_para()
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<blockquote>{article_inline_md(stripped[2:].strip())}</blockquote>")
            continue
        if stripped == ARTICLE_TOC_MARKER:
            flush_para()
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(_TOC_PLACEHOLDER)
            continue
        m = ARTICLE_GRAPHIC_RE.match(stripped)
        if m:
            flush_para()
            if in_list:
                out.append("</ul>")
                in_list = False
            graphic = article_graphic_html(slug, m.group(1), lang)
            if graphic:
                out.append(graphic)
            continue
        m = ARTICLE_VIDEO_RE.match(stripped)
        if m:
            flush_para()
            if in_list:
                out.append("</ul>")
                in_list = False
            video = video_embed_html(m.group(1), lang)
            if video:
                out.append(video)
            continue
        m = ARTICLE_FIGURE_RE.match(stripped)
        if m:
            # ![alt](src "caption") on its own line -> figure; the image links
            # to its full-size file so dense infographics can be zoomed on phones.
            flush_para()
            if in_list:
                out.append("</ul>")
                in_list = False
            alt, src, caption = m.group(1), m.group(2), m.group(3)
            src_attr = html.escape(src)
            fig = (
                f'<figure class="art-figure"><a href="{src_attr}" target="_blank" rel="noopener">'
                f'<img src="{src_attr}" alt="{html.escape(alt)}" width="1600" height="900" loading="lazy" decoding="async"></a>'
            )
            if caption:
                fig += f"<figcaption>{article_inline_md(caption)}</figcaption>"
            out.append(fig + "</figure>")
            continue
        if stripped.startswith("- "):
            flush_para()
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = article_inline_md(stripped[2:].strip())
            # "**term** rest" items render as a two-column grid (main.css);
            # wrap the rest in one span so inner <em>/<strong> stay inline.
            m_term = re.match(r"(<strong>.*?</strong>)\s*(.+)$", item)
            if m_term:
                item = f"{m_term.group(1)}<span>{m_term.group(2)}</span>"
            out.append(f"<li>{item}</li>")
            continue
        if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2 and stripped[1] != "*":
            # Single-line italic emphasis used as author byline -> keep as paragraph.
            in_para.append(stripped)
            continue
        in_para.append(stripped)
    flush_para()
    if in_list:
        out.append("</ul>")
    toc = article_toc_html(headings + list(toc_extra), lang)
    return nbsp_numbers("\n".join(toc if part == _TOC_PLACEHOLDER else part for part in out))


def split_article_faq(body_md):
    """Split an article body at its trailing '## FAQ' heading (whole line).

    Returns (body_md_without_faq, faq): the body part renders exactly as
    before; faq is a list of {"q", "a", "a_html"} dicts parsed by
    parse_faq_section. Articles without a FAQ section come back with an
    empty list.
    """
    lines = body_md.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "## FAQ":
            return "\n".join(lines[:i]).rstrip(), parse_faq_section("\n".join(lines[i + 1:]))
    return body_md, []


def parse_faq_section(section_md):
    """Parse a '## FAQ' section into [{"q", "a", "a_html"}] items.

    '### ' headings are the questions; the paragraphs after a heading
    (joined with spaces) are its answer. "a" is the answer as plain text
    (inline_md_plain, for the FAQPage JSON-LD); "a_html" is the same
    answer rendered with article_inline_md so **bold** and links
    work in the visible FAQ.
    """
    faq = []
    question = None
    paragraphs = []
    current = []
    for line in section_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            if current:
                paragraphs.append(" ".join(current))
                current = []
            if question is not None:
                answer = " ".join(paragraphs)
                faq.append({"q": question, "a": inline_md_plain(answer), "a_html": nbsp_numbers(article_inline_md(answer))})
                paragraphs = []
            question = stripped[4:].strip()
        elif not stripped:
            if current:
                paragraphs.append(" ".join(current))
                current = []
        else:
            current.append(stripped)
    if current:
        paragraphs.append(" ".join(current))
    if question is not None:
        answer = " ".join(paragraphs)
        faq.append({"q": question, "a": inline_md_plain(answer), "a_html": nbsp_numbers(article_inline_md(answer))})
    return faq


def load_articles(lang="en"):
    """Load data/articles/*.md (lang="es": data/articles_es/*.md), newest
    first. Returns article context dicts.

    `path` is the English path (/articles/<slug>), the key for hub cards,
    guide links and ES_PATHS; `url` is where this language's page lives
    (/es/articles/<slug> for Spanish, same slug)."""
    articles = []
    src = ARTICLES_ES_SRC_DIR if lang == "es" else ARTICLES_SRC_DIR
    if not os.path.isdir(src):
        return articles
    for filename in sorted(os.listdir(src)):
        if not filename.endswith(".md"):
            continue
        path = os.path.join(src, filename)
        try:
            meta, body_md = parse_article_file(path)
        except OSError as exc:
            print(f"WARN: skipping article {filename}: {exc}", file=sys.stderr)
            continue
        body_md, faq = split_article_faq(body_md)
        slug = meta.get("slug") or filename[:-3]
        title = meta.get("title") or slug.replace("-", " ").capitalize()
        date = meta.get("date") or "2026-10-02"
        toc_extra = [("faq", tr(lang, "Frequently asked questions"))] if faq else []
        body_html = article_markdown_to_html(body_md, slug, toc_extra, lang)
        words = len(_article_words(body_md))
        reading_time = max(1, round(words / READING_WPM))
        en_path = f"/articles/{slug}"
        url = lang_path(lang, en_path)
        page_url = f"{SITE_URL}{url}"
        articles.append({
            "lang": lang,
            "src_path": f"data/{'articles_es' if lang == 'es' else 'articles'}/{filename}",
            "slug": slug,
            "title": title,
            "meta_title": meta.get("meta_title") or f"{title} — Spanified",
            "meta_description": meta.get("meta_description") or meta.get("excerpt") or "",
            "excerpt": meta.get("excerpt") or "",
            "date": date,
            # Optional `updated:` frontmatter (YYYY-MM-DD) for substantive
            # revisions; feeds dateModified / article:modified_time.
            "updated": max(meta.get("updated") or date, date),
            "date_display": display_date(date, lang),
            "author": meta.get("author") or "Dmytro Shvechikov",
            "image_alt": meta.get("image_alt") or "",
            "story_keywords": [k.strip() for k in (meta.get("story_keywords") or "").split(",") if k.strip()],
            "story_categories": [c.strip().lower() for c in (meta.get("story_categories") or "").split(",") if c.strip()],
            # Optional `related:` (comma-separated calculator/article URLs) for
            # the cards under the FAQ; falls back to CATEGORY_HUBS.
            "related": [u.strip() for u in (meta.get("related") or "").split(",") if u.strip()],
            "body_html": body_html,
            "word_count": words,
            "reading_time": reading_time,
            "path": en_path,
            "url": url,
            "faq": faq,
            "share": share_links(page_url, f"{title} — Spanified"),
        })
    articles.sort(key=lambda a: a.get("date", ""), reverse=True)
    return articles


# Average adult silent reading speed for non-fiction (Brysbaert, 2019).
READING_WPM = 238

_MD_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MD_DIRECTIVE_RE = re.compile(r"^\s*:::.*$", re.M)
_URL_RE = re.compile(r"https?://\S+")
_MD_SYNTAX_RE = re.compile(r"[*_`#>|]+")
_HAS_WORD_RE = re.compile(r"\w")


def _article_words(md):
    """Words a reader actually sees: link text but not URLs, no ::: directives,
    and no markdown syntax tokens (list dashes, table pipes, **, #)."""
    text = _MD_DIRECTIVE_RE.sub("", md)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _URL_RE.sub("", text)
    text = _MD_SYNTAX_RE.sub(" ", text)
    return [w for w in text.split() if _HAS_WORD_RE.search(w)]


def load_social_stats():
    """Load social stats from data/social_stats.json with safe defaults."""
    try:
        path = os.path.join(SCRIPT_DIR, "data", "social_stats.json")
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"threads_followers": 4100, "reddit_members": 1000}


AVATAR_DIR_URL = "/static/img/avatars/"
# Retina ladder for .t-avatar (displayed at 32px, see static/css/main.css).
# Files are produced by tools/gen_avatar_webp.py: <name>-32/64/96.webp.
AVATAR_SRCSET_WIDTHS = (32, 64, 96)


def load_testimonials():
    """Load testimonials from data/testimonials.json.

    Avatar files live in static/img/avatars/ and are wired into the
    template directly via ``avatar_url`` (the 64px @2x WebP used as ``src``)
    plus ``avatar_variants`` (the 32/64/96px ladder rendered as a srcset —
    the template appends ``?v=`` to every URL so cache-busting stays in one
    place).

    ``avatar`` in the JSON is a ``-64.webp`` name; anything else falls back
    to a single-image src with no srcset.
    """
    try:
        path = os.path.join(SCRIPT_DIR, "data", "testimonials.json")
        with open(path, encoding="utf-8") as fh:
            testimonials = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    for t in testimonials:
        name = t.get("avatar") or ""
        t["avatar_url"] = f"{AVATAR_DIR_URL}{name}"
        t["avatar_variants"] = []
        stem = name[: -len("-64.webp")] if name.endswith("-64.webp") else ""
        if stem:
            t["avatar_variants"] = [
                (width, f"{AVATAR_DIR_URL}{stem}-{width}.webp")
                for width in AVATAR_SRCSET_WIDTHS
            ]
    return testimonials


# /subscribe "Before you subscribe" FAQ: rendered as <details> and as FAQPage
# JSON-LD, so answers stay plain text.
SUBSCRIBE_FAQ_ITEMS = [
    ("How often will I get an email?", "Once a day, around 08:00 Madrid time, weekends included."),
    ("Is it really free?", "Yes. There is no paywall, and your email is used only to send Spain Daily. It is never sold."),
    ("What happens after I sign up?", "We send you a confirmation email right away. Click the link in it to start getting Spain Daily. If it does not arrive within a few minutes, check your spam or promotions folder."),
    ("Is it written by AI?", "AI helps translate and summarize the Spanish stories. An editor reviews every edition before it is sent, and each story links to its original source so you can check it."),
]

# Spanish twin of SUBSCRIBE_FAQ_ITEMS for /es/subscribe.
ES_SUBSCRIBE_FAQ_ITEMS = [
    ("¿Cada cuánto llega el email?", "Una vez al día, sobre las 08:00 hora de Madrid, también los fines de semana."),
    ("¿De verdad es gratis?", "Sí. No hay muro de pago y tu email solo se usa para enviarte España al Día. Nunca se vende."),
    ("¿Qué pasa después de suscribirme?", "Te enviamos enseguida un email de confirmación. Haz clic en el enlace que contiene para empezar a recibir España al Día. Si no llega en unos minutos, revisa las carpetas de spam y promociones."),
    ("¿Lo escribe una IA?", "La IA ayuda a resumir las noticias. Un editor revisa cada edición antes de enviarla, y cada noticia enlaza a su fuente original para que puedas comprobarla."),
]


FAQ_ITEMS = [
    ("Where can I read Spanish news in English?", "On Spain Daily: every morning we publish a free edition with Spain's top stories in plain English, online and by email. Each item links to the original Spanish source, so you can read the full article if you want to."),
    ("Is Spain Daily a newspaper or a newsletter?", "Spain Daily is a newsletter, not a newspaper. We do not do original reporting: we aggregate Spanish outlets, then translate and summarize their stories in English and link to each source. The summaries are AI-assisted and checked by an editor before every send."),
    ("Which Spanish newspapers does Spain Daily summarize?", "Spain Daily reads national and regional Spanish media: El País, Cinco Días, El Mundo, La Vanguardia, elDiario.es, El Confidencial, 20 Minutos, Heraldo, Diario Sur and Expansión, plus the Europa Press agency. International news is included only when it directly affects Spain. Every story shows its source."),
    ("Can Spain Daily replace an English-language newspaper about Spain?", "No, it is meant to sit alongside one. Spain Daily is a five-minute daily briefing with links to the original reporting, so you get the headlines on rents, taxes, visas and jobs fast and can go deeper in the source or in an English-language outlet."),
    ("What is a good English-language newsletter about Spain?", "Spain Daily is a free English-language newsletter about Spain: one email a day, around 08:00 Madrid time, seven days a week, with a five-minute read on the news that affects life in Spain. You can try it by reading the latest edition online before you subscribe."),
    ("What is Spanified?", "Spanified is a free newsletter that summarizes the most important news from Spain in plain English — rents, taxes, visas, jobs and everyday life."),
    ("How often does the digest arrive?", "Every morning, seven days a week. Five minutes with your coffee and you're up to speed."),
    ("Is it really free?", "Yes — free forever. No paywall, no trial, just the news."),
    ("What language is it in?", "The summaries are written in clear English, based on the Spanish press we read cover to cover each morning."),
    ("Where can I read past editions?", "Every edition stays online in the archive — browse by date or search the whole history."),
]


# Spanish twin of FAQ_ITEMS for the /es/ home page. Adapted, not literal:
# the Spanish edition summarizes the Spanish press in Spanish.
ES_FAQ_ITEMS = [
    ("¿Dónde puedo leer un resumen de las noticias de España?", "En España al Día: cada mañana publicamos una edición gratuita con las noticias más importantes de España, en la web y por email. Cada noticia enlaza a su fuente original, por si quieres leer el artículo completo."),
    ("¿España al Día es un periódico o una newsletter?", "Es una newsletter, no un periódico. No hacemos periodismo propio: leemos los medios españoles, resumimos sus noticias y enlazamos cada fuente. Los resúmenes se hacen con ayuda de IA y un editor los revisa antes de cada envío."),
    ("¿Qué periódicos españoles resume España al Día?", "Leemos medios nacionales y regionales: El País, Cinco Días, El Mundo, La Vanguardia, elDiario.es, El Confidencial, 20 Minutos, Heraldo, Diario Sur y Expansión, además de la agencia Europa Press. Lo internacional entra solo cuando afecta directamente a España. Cada noticia indica su fuente."),
    ("¿Puede España al Día sustituir a un periódico?", "No, está pensada para complementarlo. España al Día es un resumen diario de cinco minutos con enlaces a la información original: te enteras rápido de lo que pasa con los alquileres, los impuestos, los visados y el empleo, y puedes ampliar en la fuente."),
    ("¿Hay una buena newsletter gratuita sobre la actualidad de España?", "España al Día es una newsletter gratuita sobre España: un email al día, sobre las 08:00 hora de Madrid, los siete días de la semana, con cinco minutos de lectura sobre las noticias que afectan a la vida en España. Puedes leer la última edición en la web antes de suscribirte."),
    ("¿Qué es Spanified?", "Spanified es el proyecto que publica España al Día, una newsletter gratuita que resume las noticias más importantes de España en lenguaje claro: alquileres, impuestos, visados, empleo y vida diaria."),
    ("¿Cada cuánto llega el resumen?", "Cada mañana, los siete días de la semana. Cinco minutos con el café y ya estás al día."),
    ("¿De verdad es gratis?", "Sí, y lo seguirá siendo. Sin muro de pago ni periodo de prueba: solo las noticias."),
    ("¿En qué idioma está?", "En español claro, a partir de la prensa española que leemos de arriba abajo cada mañana. También hay una edición en inglés, Spain Daily."),
    ("¿Dónde puedo leer ediciones anteriores?", "Todas las ediciones siguen en la web, en el archivo: puedes consultarlas por fecha."),
]

# --- ES: quizzes ------------------------------------------------------------
# Spanish quizzes live at /es/quiz/<slug> (English slugs). The English quiz
# data/quizzes/<slug>.json stays the source of truth for structure (ids,
# isReal, sources, score bands, art); data/quizzes/es/<slug>.json overlays
# the text only: title, card/hook copy, button labels, meta description,
# each question's headline/summary/explanation (keyed by id) and each
# result's title/text/shareText (keyed by slug). load_quizzes("es") fails
# the build when the overlay's ids or slugs drift from the English file.
# Persona and hook images are the English art (static/img/quiz/<slug>/).
# Strings the quiz JS builds (score line, buttons, verdicts) live in
# QUIZ_STRINGS in static/js/quiz-logic.js, picked by <html lang>.
QUIZZES_DIR = os.path.join(SCRIPT_DIR, "data", "quizzes")
QUIZ_TOP_TEXT = ("title", "card_kicker", "hook_sub", "real_label", "fake_label", "meta_description")
QUIZ_QUESTION_TEXT = ("headline", "summary", "explanation")
QUIZ_RESULT_TEXT = ("title", "text", "shareText")

ES_STRINGS.update({
    # Home page quiz block: the quizzes now have Spanish twins, so these
    # replace the "(en inglés)" variants of the home block above.
    "Real stories from Spain, mixed with inventions. Can you tell which is which?":
        "Noticias y leyes reales de España mezcladas con inventos. ¿Sabes distinguirlas?",
    "Take the quiz: {title}": "Hacer el test: {title}",
    # Quiz pages (quiz.html, quiz-result.html, quiz-success.html, quiz-subscribed.html)
    "Quiz": "Test",
    "Spanified quiz": "Test de Spanified",
    "Some of these really happened in Spain. The rest we made up. Can you guess which is which?":
        "Algunas de estas cosas pasaron de verdad en España. El resto nos lo hemos inventado. ¿Sabes cuál es cuál?",
    "Try the first one. Real or fake?": "Empieza por la primera. ¿Real o falsa?",
    "Start the quiz": "Empezar el test",
    "2 minutes · 10 questions · no email needed to play": "2 minutos · 10 preguntas · no hace falta email para jugar",
    "Your answers": "Tus respuestas",
    "Your persona is sealed": "Tu personaje está sellado",
    "Open it with your email": "Ábrelo con tu email",
    "Confirm the link we send you and your persona opens right away. You also get Spain's top news in English every morning, free.":
        "Confirma el enlace que te enviamos y tu personaje se abre al momento. Además recibirás cada mañana las noticias más importantes de España, gratis.",
    "Reveal my persona": "Ver mi personaje",
    "{n} daily editions · free · unsubscribe anytime": "{n} ediciones diarias · gratis · date de baja cuando quieras",
    "No thanks, just show my result": "No, gracias, solo quiero ver mi resultado",
    "Your persona": "Tu personaje",
    "Think a friend would score higher? Send it.": "¿Crees que alguien sacaría más nota? Mándaselo.",
    "Spain's news, in plain English": "Las noticias de España, en lenguaje claro",
    "One sharp email every morning. Free, unsubscribe anytime.":
        "Un email claro cada mañana. Gratis y te das de baja cuando quieras.",
    "↺ Retake the quiz": "↺ Repetir el test",
    "Try the other quiz: {title}": "Prueba el otro test: {title}",
    "Try the other quiz": "Prueba el otro test",
    "Play now →": "Jugar ahora →",
    "Take the quiz yourself": "Haz tú el test",
    "Share your result": "Comparte tu resultado",
    "Your friend scored <strong>{score}/10</strong> — {title}": "Te retan con un <strong>{score}/10</strong>: {title}",
    "{result} — {quiz} — Spanified": "{result} | {quiz} | Spanified",
    "{result} — {quiz}": "{result}: {quiz}",
    "Can you beat {score}/10? Take the quiz": "¿Superas el {score}/10? Haz el test",
    "Subscribed — your quiz result — Spanified": "Suscripción confirmada: tu resultado del test | Spanified",
    "You're subscribed — see your {title} quiz result.": "Suscripción confirmada. Mira tu resultado del test «{title}».",
    "Email confirmed. Spain Daily arrives tomorrow morning.": "Email confirmado. España al Día te llega mañana por la mañana.",
    "{title} quiz result": "Resultado del test {title}",
    "Can't wait until tomorrow?": "¿No puedes esperar a mañana?",
    "Read the latest digest": "Leer la última edición",
    "Your result is on another device": "Tu resultado está en otro dispositivo",
    "Your result lives on the device and browser where you took the quiz. Open this page from there, or retake the quiz here. It takes 2 minutes and needs no email.":
        "Tu resultado se guarda en el dispositivo y el navegador donde hiciste el test. Abre esta página desde allí o repite el test aquí. Son 2 minutos y no hace falta email.",
    "Retake the quiz": "Repetir el test",
    "Quiz signup received — Spanified": "Hemos recibido tu suscripción desde el test | Spanified",
    "Quiz signup received. Confirm your email to reveal your result.":
        "Hemos recibido tu suscripción. Confirma tu email para ver tu resultado.",
    "Check your inbox": "Revisa tu bandeja de entrada",
    "One click left": "Te queda un clic",
    "You're subscribing to <strong>Spain Daily</strong> — one free email every morning. Click the confirmation link in your email — your quiz result will open right after.":
        "Te estás suscribiendo a <strong>España al Día</strong>, un email gratis cada mañana. Pulsa el enlace de confirmación del email y tu resultado del test se abrirá justo después.",
    "<strong>Open the email</strong> from Spain Daily (arrives within a minute)":
        "<strong>Abre el email</strong> de España al Día (llega en menos de un minuto)",
    "<strong>Click the confirmation link</strong> inside": "<strong>Pulsa el enlace de confirmación</strong> que lleva dentro",
    "<strong>Your quiz result opens</strong> — persona, score breakdown and shareable badge":
        "<strong>Se abre tu resultado del test</strong>: personaje, desglose de la puntuación e insignia para compartir",
    "Until you click that link, you're <strong>not</strong> subscribed yet — your result stays locked.":
        "Hasta que pulses ese enlace, tu suscripción <strong>no</strong> estará activa y tu resultado seguirá bloqueado.",
    "Can't find the email?": "¿No encuentras el email?",
    "Check your <strong>Spam</strong> and <strong>Promotions</strong> tabs — it often lands there.":
        "Mira en las pestañas de <strong>Spam</strong> y <strong>Promociones</strong>. Suele acabar ahí.",
    "If you find it, mark it as <strong>not spam</strong> or move it to your inbox.":
        "Si lo encuentras, márcalo como <strong>no es spam</strong> o muévelo a la bandeja de entrada.",
    "Wrong address?": "¿Dirección equivocada?",
    "{title} — Spanified": "{title} | Spanified",
    "{title} — 10 questions, 2 minutes, half of it really happened in Spain. Take the quiz:":
        "{title}: 10 preguntas, 2 minutos y la mitad es real. Haz el test:",
})


def _quiz_es_overlay(quiz, es):
    """English quiz dict + Spanish text overlay -> Spanish quiz dict.

    Raises ValueError when question ids or result slugs differ, so a new
    English question can't ship on /es/ untranslated."""
    slug = quiz["slug"]
    q_ids = [q["id"] for q in quiz.get("questions", [])]
    r_slugs = [r["slug"] for r in quiz.get("results", [])]
    es_q, es_r = es.get("questions", {}), es.get("results", {})
    if set(q_ids) != set(es_q) or set(r_slugs) != set(es_r):
        raise ValueError(
            f"data/quizzes/es/{slug}.json is out of sync with data/quizzes/{slug}.json: "
            f"questions missing {sorted(set(q_ids) - set(es_q))} extra {sorted(set(es_q) - set(q_ids))}; "
            f"results missing {sorted(set(r_slugs) - set(es_r))} extra {sorted(set(es_r) - set(r_slugs))}")
    out = dict(quiz)
    out.update({k: es[k] for k in QUIZ_TOP_TEXT if k in es})
    out["questions"] = [dict(q, **{k: es_q[q["id"]][k] for k in QUIZ_QUESTION_TEXT}) for q in quiz["questions"]]
    out["results"] = [dict(r, **{k: es_r[r["slug"]][k] for k in QUIZ_RESULT_TEXT}) for r in quiz["results"]]
    return out


def load_quizzes(lang="en"):
    """Every data/quizzes/<slug>.json, sorted by file name. lang="es" returns
    only the quizzes with a Spanish overlay (data/quizzes/es/<slug>.json),
    their text replaced by it."""
    quizzes = []
    if not os.path.isdir(QUIZZES_DIR):
        return quizzes
    for filename in sorted(os.listdir(QUIZZES_DIR)):
        if not filename.endswith(".json"):
            continue
        with open(os.path.join(QUIZZES_DIR, filename), encoding="utf-8") as fh:
            quiz = json.load(fh)
        if lang == "es":
            es_file = os.path.join(QUIZZES_DIR, "es", filename)
            if not os.path.isfile(es_file):
                continue
            with open(es_file, encoding="utf-8") as fh:
                quiz = _quiz_es_overlay(quiz, json.load(fh))
        quizzes.append(quiz)
    return quizzes


def register_es_quiz_paths():
    """Add /quiz/<slug> to ES_PATHS for every quiz with a Spanish overlay
    (hreflang, sitemap, switcher, lang_url). Call before rendering."""
    ES_PATHS.update(f"/quiz/{q['slug']}" for q in load_quizzes("es"))


def es_quiz_paths():
    """English paths of the quiz pages that have a /es/ twin, sorted."""
    return sorted(p for p in ES_PATHS if p.startswith("/quiz/"))


def load_quiz_cards(homepage=False, lang="en"):
    """Light metadata for every quiz (load_quizzes(lang)).

    Used for the homepage "Quizzes" block and the "try the other quiz"
    cross-links (neighbours = every quiz except the current one). `url` is
    the English path; templates pass it through lang_url().
    Cover art lives at /static/img/quiz/<slug>/quiz-cover.jpg by convention;
    on the homepage the first quiz (ai-or-real) is promoted with its OG/hook
    art (quiz-hook.jpg) instead; cross-link cards keep the default art.
    """
    cards = []
    for quiz in load_quizzes(lang):
        slug = quiz.get("slug")
        title = quiz.get("title")
        if not slug or not title:
            continue
        cover = f"/static/img/quiz/{slug}/quiz-cover.jpg"
        if homepage and slug == "ai-or-real":
            cover = f"/static/img/quiz/{slug}/quiz-hook.jpg"
        cards.append({
            "slug": slug,
            "title": title,
            "kicker": quiz.get("card_kicker") or "Spanified quiz",
            "hook": quiz.get("hook_sub") or (
                "10 headlines from Spain — half really happened, "
                "half we made up. Can you tell which is which?"
            ),
            "cover": cover,
            "url": f"/quiz/{slug}",
        })
    return cards


def render_llms_txt(digests, articles=(), salary_pages=(), autonomo_pages=(), rental_yield_pages=()):
    latest = digests[0]["date"] if digests else "n/a"
    lines = [
        "# Spanified — Spain Daily",
        "> A free newsletter summarizing the most important news from Spain in plain English. Every morning, 5-minute read.",
        "",
        f"Latest edition: {latest}",
        "",
        "## Key pages",
        f"- Home: {SITE_URL}/",
        f"- Archive (all editions): {SITE_URL}/archive/",
        f"- Articles (guides): {SITE_URL}/articles/",
        f"- Search (newest first): {SITE_URL}/search",
        f"- About & methodology: {SITE_URL}/about",
        f"- Editor: {SITE_URL}/editor",
        f"- Subscribe: {SITE_URL}/subscribe",
        "",
        "## Calculators (2026 tax data)",
        f"- Net salary (gross to net, payslip, IRPF withholding vs Renta, all regions): {SITE_URL}/calculators/net-salary",
        *([f"- Net salary for common gross wages ({len(salary_pages)} pages, e.g. {SITE_URL}{salary_pages[0]}); index on {SITE_URL}/calculators/net-salary"] if salary_pages else []),
        f"- Autónomo tax (self-employed quota and IRPF): {SITE_URL}/calculators/autonomo-tax",
        *([f"- Autónomo net pay by revenue and what to earn for a target take-home ({len(autonomo_pages)} pages, e.g. {SITE_URL}{autonomo_pages[0]}); index on {SITE_URL}/calculators/autonomo-tax"] if autonomo_pages else []),
        f"- Property buying cost (ITP, IVA/IGIC, AJD by region): {SITE_URL}/calculators/property-buying-cost",
        f"- Rental yield (net yield, cash flow, IRR after tax): {SITE_URL}/calculators/rental-yield",
        *([f"- Rental yield and rent needed by purchase price ({len(rental_yield_pages)} pages, e.g. {SITE_URL}{rental_yield_pages[0]}); index on {SITE_URL}/calculators/rental-yield"] if rental_yield_pages else []),
        f"- Electricity bill (PVPC and tariffs): {SITE_URL}/calculators/electricity-bill",
        "",
        "## Guides",
        *[f"- {a['title']}: {SITE_URL}{a['url']}" for a in articles],
        "",
        *(["## Spanish edition (España al Día)",
            "- The same editions and guides in Spanish, under /es/. Each page names its English twin with hreflang.",
            *[f"- {label}: {SITE_URL}{localize('es', path)}" for label, path in (
                ("Home", "/"), ("Archive", "/archive/"), ("Articles", "/articles/"), ("Subscribe", "/subscribe"),
                ("Net salary calculator", "/calculators/net-salary"), ("Autónomo tax calculator", "/calculators/autonomo-tax"),
                ("Property buying cost calculator", "/calculators/property-buying-cost"),
                ("Rental yield calculator", "/calculators/rental-yield"), ("Electricity bill calculator", "/calculators/electricity-bill"))
              if path in ES_PATHS],
            f"- Spanish editions: {SITE_URL}/es/archive/<YYYY-MM-DD>",
            ""] if "/" in ES_PATHS else []),
        "## How to cite",
        f"- Link editions as {SITE_URL}/archive/<YYYY-MM-DD>#news-<N>.",
        "- Publisher: Spanified. Editor: Dmytro Shvechikov.",
        "",
        "## Topics",
        "- property, economy, politics, work, visa, health, migration, taxes, events",
    ]
    dest = os.path.join(OUT_DIR, "llms.txt")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("  wrote llms.txt")


def render_es_pages(env, proof, es_digests=()):
    """templates/es/<name> -> <out>/es/<name>. /es/subscribe previews the
    latest Spanish edition (linking /es/archive/<date>)."""
    es_dir = os.path.join(OUT_DIR, "es")
    os.makedirs(es_dir, exist_ok=True)

    def crumbs(name, path):
        return [{"name": tr("es", "Home"), "url": "/es/"}, {"name": name, "url": path, "current": True}]

    contexts = {
        "subscribe.html": {"proof": proof, "faq": ES_SUBSCRIBE_FAQ_ITEMS, "js_version": js_version(),
                           "latest": es_digests[0] if es_digests else None,
                           "crumbs": crumbs("Suscribirse", "/es/subscribe"),
                           "emoji": CATEGORY_EMOJI, "default_emoji": DEFAULT_EMOJI},
        "about.html": {"crumbs": crumbs("Sobre nosotros", "/es/about")},
        "editor.html": {"crumbs": crumbs("Editor", "/es/editor")},
        "contact.html": {"crumbs": crumbs("Contacto", "/es/contact")},
        "confirm.html": {"crumbs": crumbs("Confirmar", "/es/confirm")},
        "success.html": {"crumbs": crumbs("Suscripción confirmada", "/es/success")},
        "unsubscribe.html": {"crumbs": crumbs("Darse de baja", "/es/unsubscribe")},
    }
    for name in ES_PAGES:
        output = env.get_template(f"es/{name}").render(page_lang="es", **contexts.get(name, {}))
        with open(os.path.join(es_dir, name), "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"  wrote es/{name}")


def render_es_home(env, es_digests, es_articles, proof):
    """/es/ (<out>/es/index.html): templates/index.html with page_lang="es",
    fed the Spanish digests and articles. Category links only list topics
    whose Spanish page is built; the editor stats count Spanish editions."""
    topics = [
        {"name": category_name(slug, "es"), "slug": slug}
        for slug in CATEGORY_EMOJI if f"/category/{slug}" in ES_PATHS
    ]
    es_proof = dict(proof)
    es_proof.update({
        "total_issues": len(es_digests),
        "total_issues_display": f"{len(es_digests):,}".replace(",", "."),
        "first_issue": format_date_es(es_digests[-1]["date"]) if es_digests else "",
        "followers_display": f"{proof['threads'] + proof['reddit']:,}".replace(",", "."),
    })
    output = env.get_template("index.html").render(
        page_lang="es", latest=es_digests[0] if es_digests else None, topics=topics, faq=ES_FAQ_ITEMS,
        proof=es_proof, quizzes=load_quiz_cards(homepage=True, lang="es"), articles=list(es_articles)[:3],
        alt_path=es_alt_path("/"))
    os.makedirs(lang_out_dir("es"), exist_ok=True)
    with open(lang_out_dir("es", "index.html"), "w", encoding="utf-8") as fh:
        fh.write(output)
    print("  wrote es/index.html")


def render_static(env, digests, es_digests=(), es_articles=()):
    latest = digests[0] if digests else None
    topics = [
        {"emoji": emoji, "name": category.capitalize(), "slug": category.lower()}
        for category, emoji in CATEGORY_EMOJI.items()
    ]

    # --- social proof -------------------------------------------------------
    social = load_social_stats()
    testimonials = load_testimonials()
    total_issues = len(digests)
    if digests:
        first_issue = format_date(digests[-1]["date"])
        first_issue_es = format_date_es(digests[-1]["date"])
    else:
        first_issue = first_issue_es = ""
    threads_n = social.get("threads_followers", 4100)
    reddit_n = social.get("reddit_members", 1000)
    proof = {
        "total_issues": total_issues,
        "first_issue": first_issue,
        "first_issue_es": first_issue_es,
        "total_issues_es": f"{total_issues:,}".replace(",", "."),
        "threads": threads_n,
        "reddit": reddit_n,
        "threads_display": f"{threads_n:,}",
        "reddit_display": f"{reddit_n:,}",
        "testimonials": testimonials,
        # Home page editor stats (index.html).
        "total_issues_display": total_issues,
        "followers_display": f"{threads_n + reddit_n:,}",
    }

    contexts = {
        "index.html": {"latest": latest, "topics": topics, "emoji": CATEGORY_EMOJI, "faq": FAQ_ITEMS, "proof": proof, "quizzes": load_quiz_cards(homepage=True), "articles": load_articles()[:3], "alt_path": es_alt_path("/")},
        "about.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "About", "url": "/about", "current": True}]},
        "contact.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Contact", "url": "/contact", "current": True}]},
        "editor.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Editor", "url": "/editor", "current": True}]},
        "subscribe.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Subscribe", "url": "/subscribe", "current": True}], "proof": proof, "latest": latest, "emoji": CATEGORY_EMOJI, "default_emoji": DEFAULT_EMOJI, "faq": SUBSCRIBE_FAQ_ITEMS, "js_version": js_version()},
        "unsubscribe.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Unsubscribe", "url": "/unsubscribe", "current": True}]},
        "confirm.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Confirm", "url": "/confirm", "current": True}]},
        "search.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Search", "url": "/search", "current": True}]},
        "success.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Success", "url": "/success", "current": True}]},
        "404.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Not found", "url": "/404", "current": True}]},
    }
    for name in STATIC_PAGES:
        template = env.get_template(name)
        output = template.render(**contexts.get(name, {}))
        dest = os.path.join(OUT_DIR, name)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"  wrote {name}")
    render_es_pages(env, proof, es_digests)
    render_es_home(env, es_digests, es_articles, proof)
    render_calculators(env)
    render_quizzes(env, proof=proof,
                   latest_url=f"/archive/{latest['date']}" if latest else None)
    render_quizzes(env, proof=proof, lang="es",
                   latest_url=lang_path("es", f"/archive/{es_digests[0]['date']}") if es_digests else None)


# Calculator hubs: (template, slug under /calculators/, breadcrumb name, share text).
CALCULATOR_PAGES = [
    ("calculator-net-salary.html", "net-salary", "Net Salary",
     "Spain Net Salary Calculator — payslip, IRPF and Renta refund by region — Spanified"),
    ("calculator-autonomo.html", "autonomo-tax", "Autónomo Tax",
     "Autónomo Tax Calculator — Spain self-employed taxes — Spanified"),
    ("calculator-property-buying-cost.html", "property-buying-cost", "Property Buying Cost",
     "Spain Property Buying Cost Calculator — ITP, IVA/IGIC & AJD by region — Spanified"),
    ("calculator-rental-yield.html", "rental-yield", "Rental Yield",
     "Spain Rental Yield Calculator — net yield after tax — Spanified"),
    ("calculator-electricity.html", "electricity-bill", "Electricity Bill",
     "Spain Electricity Bill Calculator — PVPC & Tariff Comparison — Spanified"),
]


# OG card per calculator hub: (H1, tagline), both through tr().
CALCULATOR_OG = {
    "net-salary": ("Spain Net Salary Calculator", "IRPF, Social Security & Renta, by region"),
    "autonomo-tax": ("Autónomo Tax Calculator", "Cuota, IRPF & take-home pay, by region"),
    "property-buying-cost": ("Spain Property Buying Cost Calculator", "ITP, IVA/IGIC & AJD, by region"),
    "rental-yield": ("Spain Rental Yield Calculator", "Net yield after costs & tax"),
    "electricity-bill": ("Spain Electricity Bill Calculator", "PVPC vs fixed-price tariffs"),
}


def calculator_og_image(lang, slug, title, summary):
    """Render the calculator page's OG card; returns its absolute URL."""
    from og_images import save_calculator_card
    return SITE_URL + save_calculator_card(OUT_DIR, lang, slug, title, summary)


def render_calculators(env, langs=("en", "es")):
    """Render calculator pages (static shell, logic runs client-side), in
    English and, under /es/calculators/, in Spanish (same template, page_lang)."""
    for lang in langs:
        calc_dir = lang_out_dir(lang, "calculators")
        os.makedirs(calc_dir, exist_ok=True)
        for template_name, slug, crumb, share_text in CALCULATOR_PAGES:
            path = f"/calculators/{slug}"
            crumbs = [
                {"name": tr(lang, "Home"), "url": localize(lang, "/")},
                {"name": tr(lang, crumb), "url": lang_path(lang, path), "current": True},
            ]
            page_url = SITE_URL + lang_path(lang, path)
            share = share_links(page_url, tr(lang, share_text))
            h1, tagline = CALCULATOR_OG[slug]
            og_image = calculator_og_image(lang, slug, f"{tr(lang, h1)} {CALC_YEAR}", tr(lang, tagline))
            output = env.get_template(template_name).render(
                og_image=og_image,
                page_lang=lang, page_url=page_url, alt_path=es_alt_path(path),
                crumbs=crumbs, js_version=js_version(), share=share, calc_year=CALC_YEAR,
                ns_links=net_salary_links(lang=lang), au_links=autonomo_links(lang=lang),
                ry_links=rental_yield_links(lang=lang), current_slug="")
            with open(os.path.join(calc_dir, f"{slug}.html"), "w", encoding="utf-8") as fh:
                fh.write(output)
            print(f"  wrote {lang_path(lang, path)[1:]}.html")


# Fiscal year of the calculator data (SS quotas, IRPF scales). Bump ONLY
# together with the engine data (quotas/brackets/deductions), never alone.
CALC_YEAR = 2026


# --- ES: calculators ----------------------------------------------------------
# Spanish twins of every calculator page under /es/calculators/<English slug>:
# the five hubs and the programmatic amount pages. Same templates with
# page_lang="es": short UI strings go through t()/tr() (the ES_STRINGS block
# below), long copy (meta, FAQ, explainers) is written per language in the
# template, and the amount pages build their Spanish copy in the *_page_context
# functions. Numbers use Spanish format (30.000 €, 7,7 %). Browser-side text
# (static/js/*.js) is translated by static/js/calc-i18n.js and the
# static/js/<calc>-es.js dictionaries.

NBSP = "\u00a0"
# 1,234.5 -> 1.234,5
ES_NUMBER_MARKS = str.maketrans(",.", ".,")


def calculator_paths():
    """English paths of every calculator page (hubs and amount pages)."""
    ns, au, ry = load_net_salary_pages(), load_autonomo_pages(), load_rental_yield_pages()
    return ([f"/calculators/{slug}" for _, slug, _, _ in CALCULATOR_PAGES]
            + [f"/calculators/{net_salary_slug('annual', a)}" for a in ns["annual"]]
            + [f"/calculators/{net_salary_slug('monthly', m)}" for m in ns["monthly"]]
            + [f"/calculators/{autonomo_slug('revenue', a)}" for a in au["revenue"]]
            + [f"/calculators/{autonomo_slug('monthly', m)}" for m in au["monthly"]]
            + [f"/calculators/{rental_yield_slug(p)}" for p in ry["prices"]])


def register_es_calculator_paths():
    """Add every calculator page to ES_PATHS (all have a Spanish twin)."""
    ES_PATHS.update(calculator_paths())


ES_STRINGS.update({
    # OG cards (CALCULATOR_OG and the amount pages)
    "IRPF, Social Security & Renta, by region": "IRPF, Seguridad Social y Renta, por comunidad",
    "Cuota, IRPF & take-home pay, by region": "Cuota, IRPF y sueldo neto, por comunidad",
    "ITP, IVA/IGIC & AJD, by region": "ITP, IVA/IGIC y AJD, por comunidad",
    "Net yield after costs & tax": "Rentabilidad neta tras gastos e impuestos",
    "PVPC vs fixed-price tariffs": "PVPC frente a tarifas de precio fijo",
    "{net} net a year  •  {rate} effective rate": "{net} netos al año  •  tipo efectivo {rate}",
    "Cuota {quota} a month  •  {rate} total burden": "Cuota de {quota} al mes  •  {rate} de carga total",
    "{gross} gross  •  {net} net yield": "{gross} bruta  •  {net} neta",
    # Breadcrumbs and share texts (render_calculators)
    "Net Salary": "Sueldo neto",
    "Autónomo Tax": "Impuestos de autónomos",
    "Property Buying Cost": "Gastos de compra de vivienda",
    "Rental Yield": "Rentabilidad del alquiler",
    "Electricity Bill": "Factura de la luz",
    "Spain Net Salary Calculator — payslip, IRPF and Renta refund by region — Spanified":
        "Calculadora de sueldo neto: nómina, IRPF y Renta por comunidad | Spanified",
    "Autónomo Tax Calculator — Spain self-employed taxes — Spanified":
        "Calculadora de impuestos para autónomos en España | Spanified",
    "Spain Property Buying Cost Calculator — ITP, IVA/IGIC & AJD by region — Spanified":
        "Calculadora de gastos de compra de vivienda: ITP, IVA/IGIC y AJD | Spanified",
    "Spain Rental Yield Calculator — net yield after tax — Spanified":
        "Calculadora de rentabilidad del alquiler después de impuestos | Spanified",
    "Spain Electricity Bill Calculator — PVPC & Tariff Comparison — Spanified":
        "Calculadora de la factura de la luz: PVPC y comparador de tarifas | Spanified",
    # Shared by the calculator templates
    "Frequently Asked Questions": "Preguntas frecuentes",
    "More Spain calculators": "Más calculadoras para España",
    " — your payslip after IRPF and Social Security, the Renta refund and every region compared.":
        ": tu nómina después del IRPF y la Seguridad Social, la devolución de la Renta y todas las comunidades comparadas.",
    " — social security quota and IRPF if you are self-employed.":
        ": la cuota de la Seguridad Social y el IRPF si trabajas por cuenta propia.",
    " — ITP, IVA/IGIC, AJD, notary and registry fees by region, before you buy.":
        ": ITP, IVA/IGIC, AJD, notaría y registro por comunidad, antes de comprar.",
    " — net yield, cash-on-cash and IRR of a Spanish rental, with resident and non-resident taxes.":
        ": rentabilidad neta, rentabilidad sobre lo invertido y TIR de un alquiler en España, con impuestos de residentes y no residentes.",
    "Calculation Error:": "Error de cálculo:",
    "Please check your inputs or contact support if the problem persists.":
        "Revisa los datos o escríbenos si el problema continúa.",
    # calculator-electricity.html
    "Spain Electricity Bill Calculator": "Calculadora de la factura de la luz",
    "Monthly electricity bill + supplier comparison — contracted power, kWh, taxes and VAT, in English.":
        "Tu factura de la luz mensual y una comparativa de comercializadoras: potencia contratada, kWh, impuestos e IVA.",
    "Consumption": "Consumo",
    "Billing period": "Periodo de facturación",
    "Length of the bill you are modelling. Most Spanish bills cover 30 days (some meters bill bimonthly — use 60 then).":
        "Duración de la factura que quieres simular. La mayoría de las facturas en España son de 30 días (algunas son bimestrales: usa entonces 60).",
    "days ·": "días ·",
    "Contracted power": "Potencia contratada",
    "Your contracted capacity in kW (potencia contratada). You pay the capacity charge for it every day — see the supplier cards for the €/kW/day rate. Typical flats: 3.45–5.75 kW.":
        "Tu potencia contratada en kW. Pagas el término de potencia por ella todos los días: el precio en €/kW/día está en las fichas de las comercializadoras. Lo habitual en un piso: de 3,45 a 5,75 kW.",
    "Total kWh used during the billing period on a flat (fv) tariff. Check the number on your bill — it is the 'energía consumida' figure.":
        "Total de kWh consumidos en el periodo con una tarifa fija. Lo encontrarás en tu factura como «energía consumida».",
    "kWh / period ·": "kWh / periodo ·",
    "Punta (peak)": "Punta",
    "kWh consumed during peak hours (typically weekdays 10:00–14:00 and 18:00–22:00). The most expensive period on time-of-use tariffs.":
        "kWh consumidos en horas punta (normalmente de lunes a viernes de 10:00 a 14:00 y de 18:00 a 22:00). Es el periodo más caro en las tarifas por franjas.",
    "Llano (shoulder)": "Llano",
    "kWh consumed during shoulder hours — usually early morning and midday, priced between punta and valle.":
        "kWh consumidos en horas llano, normalmente a primera hora y a mediodía, con un precio entre punta y valle.",
    "Valle (off-peak)": "Valle",
    "kWh consumed during off-peak hours — nights and weekends. The cheapest period; shift laundry, dishwasher and EV charging here.":
        "kWh consumidos en horas valle: noches y fines de semana. Es el periodo más barato, así que conviene poner aquí la lavadora, el lavavajillas y la carga del coche eléctrico.",
    "Total consumption:": "Consumo total:",
    "Lowest estimated bill": "Factura estimada más baja",
    "Suppliers": "Comercializadoras",
    "+ Add supplier (up to 5)": "+ Añadir comercializadora (hasta 5)",
    "Default rates are illustrative figures based on typical Spanish market offers — always check the current tariff sheet (hoja de información) before switching supplier.":
        "Los precios por defecto son orientativos y se basan en ofertas habituales del mercado español. Antes de cambiar de comercializadora, revisa siempre la hoja de información de la tarifa actual.",
    "Supplier comparison": "Comparativa de comercializadoras",
    "Supplier": "Comercializadora",
    "Power": "Potencia",
    "Energy": "Energía",
    "Tax (5.11%)": "Impuesto (5,11 %)",
    "VAT": "IVA",
    "Saving": "Ahorro",
    "Bill breakdown": "Desglose de la factura",
    "Results are estimates for educational purposes. Regulated charges (electricity tax, network access, metering) change over time and your actual bill may differ.":
        "Los resultados son estimaciones con fines informativos. Los cargos regulados (impuesto eléctrico, peajes de acceso, medida) cambian con el tiempo y tu factura real puede ser distinta.",
    "Paying too much for electricity? Share this calculator.": "¿Pagas demasiado de luz? Comparte esta calculadora.",
    # "More Spain calculators" lists (the English keys start with " — ")
    " — ITP, IVA, AJD, notary and registry fees by region.": ": ITP, IVA, AJD, notaría y registro por comunidad.",
    " — ITP, IVA/IGIC, AJD, notary and registry fees by region.": ": ITP, IVA/IGIC, AJD, notaría y registro por comunidad.",
    " — compare with a payslip: IRPF, Social Security and the Renta refund.":
        ": compáralo con una nómina: IRPF, Seguridad Social y devolución de la Renta.",
    " — compare your salary with working as self-employed: quota and IRPF.":
        ": compara tu sueldo con trabajar por cuenta propia: cuota e IRPF.",
    " — estimate the monthly bill and compare tariffs, useful for the running costs of a rental.":
        ": calcula la factura mensual y compara tarifas, útil para los gastos de un piso en alquiler.",
    " — estimate the monthly bill and compare tariffs.": ": calcula la factura mensual y compara tarifas.",
    " — estimate your monthly bill and compare tariffs.": ": calcula tu factura mensual y compara tarifas.",
    " — net yield, cash flow and IRR of a rental flat after tax.":
        ": rentabilidad neta, flujo de caja y TIR de un piso en alquiler después de impuestos.",
    " — quota and IRPF if you are self-employed.": ": cuota e IRPF si trabajas por cuenta propia.",
    " — social security quota and IRPF if you are self-employed, or run your lets as a business.":
        ": cuota de la Seguridad Social e IRPF si trabajas por cuenta propia o gestionas tus alquileres como actividad económica.",
    " — what changes if you go freelance: Social Security brackets, form 130, IVA and deductions.":
        ": qué cambia si te haces autónomo: tramos de la Seguridad Social, modelo 130, IVA y deducciones.",
    " — your own region, age, family and months as autónomo.": ": con tu comunidad, tu edad, tu familia y tu antigüedad como autónomo.",
    " — your own region, family, flexible pay and the Beckham law.":
        ": con tu comunidad, tu familia, la retribución flexible y la Ley Beckham.",
    " — your own rent, mortgage, tax status, cash-on-cash and IRR.":
        ": con tu alquiler, tu hipoteca, tu residencia fiscal, la rentabilidad sobre lo invertido y la TIR.",
    " — your payslip after IRPF and Social Security, every region compared.":
        ": tu nómina después del IRPF y la Seguridad Social, con todas las comunidades comparadas.",
    "Autónomo taxes in Spain: the complete guide": "Impuestos de autónomos en España: la guía completa",
    # Region names (the <option> labels; build.py parses the English ones)
    "Andalusia": "Andalucía",
    "Aragon": "Aragón",
    "Asturias": "Asturias",
    "Balearic Islands": "Illes Balears",
    "Basque Country": "País Vasco",
    "Canary Islands": "Canarias",
    "Cantabria": "Cantabria",
    "Castilla and Leon": "Castilla y León",
    "Castilla-La Mancha": "Castilla-La Mancha",
    "Catalonia": "Cataluña",
    "Ceuta": "Ceuta",
    "Extremadura": "Extremadura",
    "Galicia": "Galicia",
    "La Rioja": "La Rioja",
    "Madrid": "Madrid",
    "Melilla": "Melilla",
    "Murcia": "Región de Murcia",
    "Navarre": "Navarra",
    "Valencian Community": "Comunidad Valenciana",
    # Shared calculator UI
    "Item": "Concepto",
    "Amount": "Importe",
    "Per month": "Al mes",
    "Per year": "Al año",
    "Region": "Comunidad",
    "Parameters": "Datos",
    "Property type": "Tipo de vivienda",
    "Reset to defaults": "Volver a los valores iniciales",
    "Personalise this calculation": "Personaliza este cálculo",
    "Versus Madrid": "Frente a Madrid",
    "reference": "referencia",
    "Lower": "Menos",
    "Higher": "Más",
    "Lower price": "Más barata",
    "Higher price": "Más cara",
    "Net a month": "Neto al mes",
    "Net a year": "Neto al año",
    "month": "mes",
    "months": "meses",
    "years": "años",
    "yr": "año",
    "a month": "al mes",
    "a year": "al año",
    "{amount} a month": "{amount} al mes",
    "€/mo": "€/mes",
    "€/yr": "€/año",
    "%/yr": "%/año",
    "€ / yr ·": "€ / año ·",
    "% of price": "% del precio",
    "% of rent": "% del alquiler",
    # Link grids (partials/*-links.html, *_links())
    "Net salary for other common wages": "Sueldo neto para otros sueldos habituales",
    "Net salary by monthly wage": "Sueldo neto según el sueldo mensual",
    "{amount} gross to net in Spain": "{amount} brutos en neto en España",
    "{amount} gross per month to net in Spain": "{amount} brutos al mes en neto en España",
    "Autónomo net pay by annual net revenue": "Lo que le queda a un autónomo según su rendimiento neto anual",
    "What an autónomo must earn to take home...": "Lo que tiene que ganar un autónomo para llevarse...",
    "Autónomo net pay on {amount} a year in Spain": "Neto de un autónomo con {amount} al año en España",
    "What an autónomo must earn to take home {amount} a month": "Lo que tiene que ganar un autónomo para llevarse {amount} al mes",
    "Rental yield by purchase price": "Rentabilidad del alquiler según el precio de compra",
    "Rental yield on a {amount} property in Spain": "Rentabilidad del alquiler de una vivienda de {amount} en España",
    # calculator-net-salary.html
    "Spain Net Salary Calculator": "Calculadora de sueldo neto",
    "Your payslip after Social Security and IRPF, what the Renta will refund or charge, and how your take-home pay compares across every region, including the foral Navarre and Basque Country.":
        "Tu nómina después de la Seguridad Social y el IRPF, lo que te devolverá o te cobrará la Renta y cómo queda tu sueldo neto en cada comunidad, incluidas las forales Navarra y País Vasco.",
    "Calculator views": "Vistas de la calculadora",
    "Calculator": "Calculadora",
    "Tax brackets by region": "Tramos del IRPF por comunidad",
    "Jump to your payslip ↓": "Ir a tu nómina ↓",
    "Salary": "Sueldo",
    "I know my": "Conozco mi",
    "Gross salary": "Sueldo bruto",
    "Target net pay": "Neto que quiero",
    "Gross: work out your net pay. Target net: work out the gross salary you need to take home that amount.":
        "Bruto: calcula tu sueldo neto. Neto que quiero: calcula el bruto que necesitas para cobrar esa cantidad.",
    "Amount per": "Importe por",
    "Adjust the amount": "Ajusta el importe",
    "Payslips a year": "Pagas al año",
    "14 prorated": "14 prorrateadas",
    "14: two extra payslips, usually in June and December. Prorated: the two extras are spread over 12 equal payslips. Your yearly total is the same.":
        "14: dos pagas extra, normalmente en junio y diciembre. Prorrateadas: las dos extras se reparten en 12 nóminas iguales. El total del año es el mismo.",
    "Where you live": "Dónde vives",
    "Your tax residence is the region where you spent the most days of the year; it sets the regional half of IRPF. Ceuta and Melilla residents pay 40% of the IRPF.":
        "Tu residencia fiscal es la comunidad donde pasaste más días del año; marca la mitad autonómica del IRPF. Los residentes en Ceuta y Melilla pagan el 40 % del IRPF.",
    "Payslip withholding uses one national table, so it is the same in every region; the regional difference shows up at the Renta. The Basque Country and Navarre are different: they run their own (foral) IRPF and withholding tables, and the Beckham law does not apply there.":
        "La retención de la nómina usa una única tabla estatal, así que es igual en todas las comunidades; la diferencia autonómica aparece en la Renta. El País Vasco y Navarra son distintos: tienen su propio IRPF foral y sus tablas de retención, y allí no se aplica la Ley Beckham.",
    "Tax regime": "Régimen fiscal",
    "Standard": "General",
    "Beckham law": "Ley Beckham",
    "Beckham law: special regime for people who moved to Spain for work (art. 93 LIRPF). 24% flat up to €600,000, 47% above, no deductions. Region and family do not change the tax. Not available in Navarre or the Basque Country.":
        "Ley Beckham: régimen especial para quien se traslada a España por trabajo (art. 93 LIRPF). Un 24 % fijo hasta 600.000 € y un 47 % por encima, sin deducciones. La comunidad y la familia no cambian el impuesto. No se aplica en Navarra ni en el País Vasco.",
    "About you": "Sobre ti",
    "Age": "Edad",
    "Under 65": "Menos de 65",
    "From 65 your personal minimum rises by €1,150, and by €1,400 more from 75.":
        "A partir de los 65 años tu mínimo personal sube 1.150 €, y 1.400 € más a partir de los 75.",
    "Contract": "Contrato",
    "Permanent": "Indefinido",
    "Temporary (under 1 year)": "Temporal (menos de 1 año)",
    "Temporary contracts pay 1.60% unemployment contribution instead of 1.55%, and contracts under a year have a 2% minimum withholding.":
        "Los contratos temporales cotizan un 1,60 % por desempleo en lugar de un 1,55 %, y los de menos de un año tienen una retención mínima del 2 %.",
    "Your disability": "Tu discapacidad",
    'Officially recognised degree. It raises your minimum and your deductible expenses. "With help" means you need assistance from others or have reduced mobility.':
        "Grado reconocido oficialmente. Sube tu mínimo y tus gastos deducibles. «Con ayuda» significa que necesitas ayuda de terceras personas o tienes movilidad reducida.",
    "None or under 33%": "Ninguna o menos del 33 %",
    "33% to 64%": "Del 33 al 64 %",
    "33% to 64%, with help or reduced mobility": "Del 33 al 64 %, con ayuda o movilidad reducida",
    "65% or more": "65 % o más",
    "Joint tax return": "Declaración conjunta",
    "Joint return (tributación conjunta): €3,400 off the base for a married couple, assumed here with a spouse without income; €2,150 for a single parent living with their children. On the payslip this only changes the income below which nothing is withheld, so above about €17,000 the withholding stays the same and the saving comes at the Renta. Basque Country: 4,896 € off the base for any family unit. Navarre: your spouse’s own personal minimum (2,364 €) or +668 € for a single parent, taken off the tax.":
        "Tributación conjunta: 3.400 € menos de base para un matrimonio, aquí con el cónyuge sin ingresos; 2.150 € para una familia monoparental que vive con sus hijos. En la nómina solo cambia el límite por debajo del cual no se retiene nada, así que a partir de unos 17.000 € la retención es la misma y el ahorro llega en la Renta. País Vasco: 4.896 € menos de base para cualquier unidad familiar. Navarra: el mínimo personal propio del cónyuge (2.364 €) o 668 € más para familias monoparentales, restados del impuesto.",
    "No, individual return": "No, declaración individual",
    "Married, spouse without income": "Casado/a, cónyuge sin ingresos",
    "Single parent with children": "Familia monoparental con hijos",
    "Moved town for this job": "Me he mudado por este trabajo",
    "Geographic mobility: if you accepted a job that made you move your home to another municipality, you deduct €2,000 more in the year of the move and the next one.":
        "Movilidad geográfica: si aceptaste un trabajo que te obligó a trasladar tu residencia a otro municipio, deduces 2.000 € más el año del traslado y el siguiente.",
    "Family": "Familia",
    "Children under 3": "Hijos menores de 3",
    "Children (and adopted or fostered children) under 3 who live with you. Each adds an extra €2,800 to the minimum.":
        "Hijos (también adoptados o en acogida) menores de 3 años que viven contigo. Cada uno suma 2.800 € más al mínimo.",
    "Children 3–24": "Hijos de 3 a 24",
    "Children aged 3 to 24 who live with you and earn under €8,000 a year. Disabled children count at any age.":
        "Hijos de 3 a 24 años que viven contigo y ganan menos de 8.000 € al año. Con discapacidad cuentan a cualquier edad.",
    "Shared with the other parent": "Compartidos con el otro progenitor",
    "Each parent applies half of the child minimum when both are entitled to it, e.g. with shared custody or separate tax returns.":
        "Cada progenitor aplica la mitad del mínimo por hijos cuando los dos tienen derecho, por ejemplo con custodia compartida o declaraciones separadas.",
    "Children with a disability": "Hijos con discapacidad",
    "Add a child with an officially recognised disability. They must also be counted above.":
        "Añade un hijo con una discapacidad reconocida oficialmente. También tiene que estar contado arriba.",
    "Add child": "Añadir hijo",
    "Parents 65–74": "Ascendientes de 65 a 74",
    "Parents or grandparents aged 65 to 74 who live with you at least half the year and earn under €8,000.":
        "Padres o abuelos de 65 a 74 años que viven contigo al menos medio año y ganan menos de 8.000 €.",
    "Parents 75+": "Ascendientes de 75+",
    "Parents or grandparents aged 75 or older who live with you. Each adds €1,400 on top.":
        "Padres o abuelos de 75 años o más que viven contigo. Cada uno suma 1.400 € más.",
    "Parents with a disability": "Ascendientes con discapacidad",
    "Add a parent or grandparent with an officially recognised disability who lives with you. Count them above if 65 or older; a younger one is counted automatically.":
        "Añade a un padre o abuelo con una discapacidad reconocida oficialmente que viva contigo. Si tiene 65 años o más, cuéntalo también arriba; si es más joven, se cuenta solo.",
    "Add parent": "Añadir ascendiente",
    "Flexible pay": "Retribución flexible",
    "Benefits paid instead of salary are free of IRPF up to a limit, but still pay Social Security.":
        "Las ventajas que se cobran en lugar de sueldo están exentas de IRPF hasta un límite, pero siguen cotizando a la Seguridad Social.",
    "Health insurance": "Seguro médico",
    "Private health insurance through your employer. Tax-free up to €500 per insured person (€1,500 if disabled).":
        "Seguro médico privado a través de tu empresa. Exento hasta 500 € por persona asegurada (1.500 € con discapacidad).",
    "People": "Personas",
    "Insured people: you, your spouse and children. €500 each is tax-free.":
        "Personas aseguradas: tú, tu cónyuge y tus hijos. 500 € por cada una están exentos.",
    "{label}: how it is paid": "{label}: cómo se paga",
    "From my salary": "Sale de mi sueldo",
    "On top of salary": "Además del sueldo",
    "Meal card": "Tarjeta restaurante",
    "Ticket or card for meals on working days. Tax-free up to €11 a day (about €2,420 a year).":
        "Tique o tarjeta para comidas en días laborables. Exento hasta 11 € al día (unos 2.420 € al año).",
    "Public transport": "Transporte público",
    "Transport card for commuting. Tax-free up to €1,500 a year.": "Tarjeta de transporte para ir al trabajo. Exenta hasta 1.500 € al año.",
    "Nursery": "Guardería",
    "Nursery school fees for children under 3, paid to the school. Fully tax-free.":
        "Cuotas de guardería de hijos menores de 3 años, pagadas al centro. Totalmente exentas.",
    "Pension and more": "Pensiones y más",
    "Your pension plan": "Tu plan de pensiones",
    "What you pay into a pension plan. It reduces your taxable base by up to €1,500, or more through a company plan.":
        "Lo que aportas a un plan de pensiones. Reduce tu base imponible hasta 1.500 €, o más con un plan de empresa.",
    "Employer pension": "Aportación de la empresa",
    "What your employer pays into your company pension plan. It is taxable pay, but you deduct it again, up to €8,500.":
        "Lo que tu empresa aporta a tu plan de pensiones de empleo. Tributa como sueldo, pero lo vuelves a deducir, hasta 8.500 €.",
    "Hours a week": "Horas a la semana",
    "Used for your net hourly pay (hours × 52 weeks).": "Sirve para calcular tu neto por hora (horas × 52 semanas).",
    "Accident insurance": "Accidentes de trabajo",
    "Workplace accident premium (AT/EP) your employer pays. It depends on the activity: about 1.5% for offices, up to 7% for construction.":
        "Cotización por accidentes de trabajo y enfermedades profesionales (AT/EP) que paga tu empresa. Depende de la actividad: un 1,5 % en oficinas y hasta un 7 % en la construcción.",
    "Your monthly payslip": "Tu nómina mensual",
    "Monthly payslip breakdown": "Desglose de la nómina mensual",
    "You keep": "Te quedas",
    "At the Renta": "En la Renta",
    "Payslip withholding vs the tax you really owe": "La retención de la nómina frente al impuesto que debes de verdad",
    "Where your employer's money goes": "Adónde va el dinero que paga tu empresa",
    "How it's calculated": "Cómo se calcula",
    "Social Security": "Seguridad Social",
    "Annual IRPF (your Renta)": "IRPF anual (tu Renta)",
    "Tax brackets": "Tramos del IRPF",
    "Combine state and regional": "Sumar estatal y autonómico",
    "Tax brackets, scrolls horizontally": "Tramos del IRPF, se desplaza en horizontal",
    "Payslip withholding": "Retención de la nómina",
    "Employer cost": "Coste para la empresa",
    "The same salary in every region": "El mismo sueldo en cada comunidad",
    "Net pay by region, scrolls horizontally": "Neto por comunidad, se desplaza en horizontal",
    "Difference": "Diferencia",
    "IRPF brackets, scrolls horizontally": "Tramos del IRPF, se desplaza en horizontal",
    "Taxable base": "Base liquidable",
    "State": "Estatal",
    "Regional": "Autonómico",
    "Every region at a glance": "Todas las comunidades de un vistazo",
    "Combined state and regional rate on the first euro, at 30,000 €, at 60,000 € and at the top. Click a region to see its full scale.":
        "Tipo estatal más autonómico en el primer euro, a 30.000 €, a 60.000 € y en el tramo más alto. Pulsa una comunidad para ver su escala completa.",
    "Rates by region, scrolls horizontally": "Tipos por comunidad, se desplaza en horizontal",
    "First €": "Primer €",
    "30,000 €": "30.000 €",
    "60,000 €": "60.000 €",
    "Top": "Máximo",
    "Top from": "Máximo desde",
    "Share your calculation: the link keeps every setting.": "Comparte tu cálculo: el enlace guarda todos los datos.",
    # calculator-net-salary-amount.html
    "Net a month, 12 payments": "Neto al mes, 12 pagas",
    "{amount} on the payslip": "{amount} en la nómina",
    "Net a month, 14 payments": "Neto al mes, 14 pagas",
    "plus 2 extra payslips of {amount}": "más 2 pagas extra de {amount}",
    "from {amount} gross": "de {amount} brutos",
    "From {amount} gross to net": "De {amount} brutos a neto",
    "Employee Social Security (6.5%)": "Seguridad Social del trabajador (6,5 %)",
    "IRPF income tax": "IRPF",
    "Net pay after the Renta": "Neto después de la Renta",
    "Effective rate (Social Security + IRPF)": "Tipo efectivo (Seguridad Social + IRPF)",
    "Tax on your next euro (IRPF)": "Impuesto sobre tu próximo euro (IRPF)",
    "IRPF withheld on your payslips": "Retención de IRPF en tus nóminas",
    "Expected Renta refund": "Devolución prevista de la Renta",
    "Expected Renta payment": "Pago previsto en la Renta",
    "What the employer pays in total": "Lo que paga la empresa en total",
    "{amount} gross in every region": "{amount} brutos en cada comunidad",
    "Net pay after the Renta, best first. Madrid is highlighted.": "Neto después de la Renta, de mayor a menor. Madrid aparece destacada.",
    "How salary tax works, on video": "Cómo tributa el sueldo, en vídeo",
    "The Social Security contribution, IRPF withholding, 12 or 14 payslips and the Renta behind these figures, with one worked salary.":
        "La cotización a la Seguridad Social, la retención de IRPF, las 12 o 14 pagas y la Renta que hay detrás de estas cifras, con un sueldo de ejemplo.",
    "Neighbouring wages": "Sueldos cercanos",
    "Estimate based on the {year} Social Security rates and AEAT IRPF scales; regional deductions are not included. Not tax advice.":
        "Estimación basada en los tipos de cotización de {year} y en las escalas de IRPF de la AEAT; no incluye las deducciones autonómicas. No es asesoramiento fiscal.",
    # calculator-autonomo.html
    "Autónomo Tax Calculator Spain": "Calculadora de impuestos para autónomos",
    "Taxes for autónomos in Spain, whether you freelance or are self-employed: Social Security quota + IRPF by region, income and family situation.":
        "Los impuestos de los autónomos en España: cuota de la Seguridad Social e IRPF según tu comunidad, tus ingresos y tu situación familiar.",
    "Annual net revenues": "Rendimiento neto anual",
    "Your total annual net revenue before any deductions. This is the starting point for all calculations — SS bracket, expenses deduction, and IRPF base are all derived from this figure.":
        "Tu rendimiento neto anual, antes de cualquier reducción. Todo el cálculo parte de esta cifra: el tramo de la Seguridad Social, la deducción de gastos y la base del IRPF.",
    "Tax region": "Comunidad autónoma",
    "Your autonomous community determines the regional half of your IRPF. Each region sets its own tax brackets and rates independently. Madrid is the lowest (top rate ~20.5%), Valencia among the highest (top rate ~29.5%).":
        "Tu comunidad autónoma marca la mitad autonómica de tu IRPF. Cada una fija sus propios tramos y tipos. Madrid es la más baja (tipo máximo de un 20,5 %) y la Comunidad Valenciana, de las más altas (tipo máximo de un 29,5 %).",
    "Navarre and the Basque Country use a separate foral tax system and aren't supported yet.":
        "Navarra y el País Vasco tienen un sistema fiscal foral propio y todavía no están incluidos.",
    "Autónomo type": "Tipo de autónomo",
    "Affects the SS bracket deduction: Individual = 7% of revenue (no cap). Director of your own SL = 3% (no cap). IRPF always uses a flat 10% deduction for everyone, on net profit after Social Security (max €3,000 in 2026).":
        "Cambia la deducción para el tramo de la Seguridad Social: persona física = 7 % de los ingresos (sin límite); administrador de tu propia SL = 3 % (sin límite). En el IRPF todos aplican un 10 % fijo sobre el rendimiento neto tras la Seguridad Social (máximo 3.000 € en 2026).",
    "Individual freelancer": "Autónomo persona física",
    "Company director / shareholder": "Administrador o socio de una sociedad",
    "Time as autónomo": "Antigüedad como autónomo",
    "New autonomos (first 12 months) pay a flat Tarifa Plana of €80/month plus the MEI levy, about €88.65/month in 2026. After month 12, the standard bracket-based quota applies.":
        "Los autónomos nuevos (primeros 12 meses) pagan una tarifa plana de 80 € al mes más el MEI, unos 88,65 € al mes en 2026. Pasado el mes 12 se aplica la cuota normal por tramos.",
    "< 1 year (tarifa plana ≈ €89/mo)": "< 1 año (tarifa plana ≈ 89 €/mes)",
    "1–2 years": "1 a 2 años",
    "> 2 years": "> 2 años",
    "Personal circumstances (optional)": "Situación personal (opcional)",
    "Age affects your personal minimum allowance, which reduces IRPF. Under 65: base €5,550. Age 65–74: +€1,150. Age 75+: +€1,400 additional. These are the state amounts; Madrid, Valencia, Andalucía and some other regions use higher ones for the regional half.":
        "La edad cambia tu mínimo personal, que reduce el IRPF. Menos de 65 años: 5.550 €. De 65 a 74: +1.150 €. Desde 75: +1.400 € más. Son los importes estatales; Madrid, la Comunidad Valenciana, Andalucía y otras comunidades usan importes más altos para la mitad autonómica.",
    "Dependent children": "Hijos a cargo",
    "Dependent children (under 25, living with you, income under €8,000/yr) increase your personal minimum: 1st child +€2,400 · 2nd +€2,700 · 3rd +€4,000 · 4th+ +€4,500 each (state amounts; several regions use higher ones for the regional half).":
        "Los hijos a cargo (menores de 25, que viven contigo y ganan menos de 8.000 € al año) suben tu mínimo: 1.º hijo +2.400 € · 2.º +2.700 € · 3.º +4.000 € · 4.º y siguientes +4.500 € cada uno (importes estatales; varias comunidades usan importes más altos para la mitad autonómica).",
    "Of which under 3 years old": "De ellos, menores de 3 años",
    "Each child under 3 adds an extra €2,800 (state amount; higher in some regions) to your personal minimum on top of the base child allowance. Must not exceed the total number of dependent children.":
        "Cada hijo menor de 3 años suma 2.800 € más a tu mínimo (importe estatal; más alto en algunas comunidades), además del mínimo por hijo. No puede superar el número total de hijos a cargo.",
    "Disability level": "Grado de discapacidad",
    "Disability allowances added to your personal minimum: 33–64% disability +€3,000 (plus €3,000 more with reduced mobility, total €6,000) · 65%+ disability +€12,000 always (€9,000 + €3,000 mobility supplement).":
        "Mínimo por discapacidad que se suma al tuyo: del 33 al 64 %, +3.000 € (y 3.000 € más con movilidad reducida, 6.000 € en total) · 65 % o más, siempre +12.000 € (9.000 € + 3.000 € por asistencia).",
    "None": "Ninguna",
    "33%+ (moderate)": "33 %+ (moderada)",
    "65%+ (severe)": "65 %+ (grave)",
    "Reduced mobility": "Movilidad reducida",
    "Reduced mobility (movilidad reducida) or need for third-party assistance: adds €3,000 on top of a 33–64% disability allowance (total €6,000). At 65%+ disability the €3,000 supplement applies automatically.":
        "Movilidad reducida o necesidad de ayuda de terceras personas: suma 3.000 € al mínimo por una discapacidad del 33 al 64 % (6.000 € en total). Con un 65 % o más, esos 3.000 € se aplican siempre.",
    "Dependent parents 65+": "Ascendientes de 65+",
    "Each cohabiting parent over 65 (or disabled, any age) adds €1,150. They must live with you and have annual income under €8,000 (excl. exempt income).":
        "Cada ascendiente mayor de 65 años que vive contigo (o con discapacidad, a cualquier edad) suma 1.150 €. Debe convivir contigo y tener rentas anuales inferiores a 8.000 € (sin contar las exentas).",
    "Of which over 75": "De ellos, mayores de 75",
    "Each cohabiting parent over 75 adds an extra €1,400 on top of the €1,150 above. Cannot exceed the number of dependent parents 65+. Same cohabitation and income conditions apply.":
        "Cada ascendiente mayor de 75 años suma 1.400 € más, además de los 1.150 € anteriores. No puede superar el número de ascendientes de 65+. Se aplican las mismas condiciones de convivencia y rentas.",
    "Tarifa plana — flat €80/month for first 12 months, plus the MEI levy (≈ €88.65/month charged). €80 was set for 2023–2025; no 2026 rule has fixed a new amount yet, so this is an estimate.":
        "Tarifa plana: 80 € al mes durante los primeros 12 meses, más el MEI (se cobran ≈ 88,65 € al mes). Los 80 € se fijaron para 2023-2025 y ninguna norma de 2026 ha fijado todavía un importe nuevo, así que es una estimación.",
    "60% Ceuta/Melilla reduction applied (art. 68.4 LIRPF). It covers income earned in Ceuta or Melilla, so this assumes your activity is carried on there.":
        "Se aplica la bonificación del 60 % de Ceuta y Melilla (art. 68.4 LIRPF). Cubre las rentas obtenidas en Ceuta o Melilla, así que se supone que tu actividad se desarrolla allí.",
    "Net take-home": "Neto que te queda",
    "Monthly SS": "Cuota mensual",
    "SS bracket": "tramo",
    "Total IRPF": "IRPF total",
    "effective rate": "tipo efectivo",
    "Total tax burden": "Carga fiscal total",
    "SS": "SS",
    "Net": "Neto",
    "Gross revenues": "Rendimiento bruto",
    "Social Security (annual)": "Seguridad Social (anual)",
    "General expenses deduction (IRPF · 10% after SS)": "Gastos de difícil justificación (IRPF · 10 % tras la SS)",
    "SS bracket basis (expenses deduction)": "Base para el tramo de la SS (deducción de gastos)",
    "Reduced net income": "Rendimiento neto reducido",
    "IRPF — state component": "IRPF, parte estatal",
    "IRPF — regional component": "IRPF, parte autonómica",
    "How IRPF is calculated": "Cómo se calcula el IRPF",
    "Effective SS rate:": "Tipo efectivo de la SS:",
    "Effective IRPF rate:": "Tipo efectivo del IRPF:",
    "Total tax burden:": "Carga fiscal total:",
    "Results are approximate and for educational purposes only. Tax rules change frequently. Consult a gestor or tax advisor for professional advice.":
        "Los resultados son aproximados y solo orientativos. Las normas fiscales cambian a menudo. Para tu caso, consulta a un gestor o asesor fiscal.",
    "Know a fellow autónomo? Share this calculator.": "¿Conoces a otro autónomo? Comparte esta calculadora.",
    # calculator-autonomo-amount.html
    "Assumes {year} rules, an established autónomo (2+ years), individual, living in Madrid, age 35, no dependants. Net revenue means income after business expenses, before Social Security and IRPF.":
        "Con las normas de {year}, un autónomo consolidado (más de 2 años), persona física, que vive en Madrid, de 35 años y sin hijos. El rendimiento neto son los ingresos menos los gastos del negocio, antes de la Seguridad Social y el IRPF.",
    "Net revenue needed a year": "Rendimiento neto necesario al año",
    "First year, tarifa plana": "Primer año, con tarifa plana",
    "You take home": "Te llevas",
    "a month after quota and IRPF": "al mes después de la cuota y el IRPF",
    "Net a month, established": "Neto al mes, consolidado",
    "{amount} quota a month": "{amount} de cuota al mes",
    "Net a month, tarifa plana": "Neto al mes, con tarifa plana",
    "first 12 months, €80 + MEI quota": "primeros 12 meses, cuota de 80 € + MEI",
    "from {amount} net revenue": "de {amount} de rendimiento neto",
    "From {amount} net revenue to take-home pay": "De {amount} de rendimiento neto a lo que te queda",
    "Net revenue": "Rendimiento neto",
    "Social Security quota ({amount} a month, bracket {bracket})": "Cuota de la Seguridad Social ({amount} al mes, tramo {bracket})",
    "IRPF income tax ({rate} of revenue)": "IRPF ({rate} del rendimiento)",
    "Take-home pay": "Lo que te queda",
    "Total burden (Social Security + IRPF)": "Carga total (Seguridad Social + IRPF)",
    "IRPF taxable base (after quota and {amount} allowance)": "Base del IRPF (tras la cuota y la reducción de {amount})",
    "Personal minimum": "Mínimo personal",
    "{amount} net revenue in every region": "{amount} de rendimiento neto en cada comunidad",
    "Take-home pay after Social Security and IRPF, best first. Madrid is highlighted.":
        "Lo que te queda después de la Seguridad Social y el IRPF, de mayor a menor. Madrid aparece destacada.",
    "Take-home pay by region, scrolls horizontally": "Neto por comunidad, se desplaza en horizontal",
    "How autónomo tax works, on video": "Cómo tributa un autónomo, en vídeo",
    "The Social Security brackets, tarifa plana and IRPF behind these figures, with worked examples at different revenues.":
        "Los tramos de la Seguridad Social, la tarifa plana y el IRPF que hay detrás de estas cifras, con ejemplos para distintos rendimientos.",
    "Neighbouring amounts": "Importes cercanos",
    # calculator-property-buying-cost.html
    "Spain Property Buying Cost Calculator": "Calculadora de gastos de compra de vivienda",
    "ITP, IVA/IGIC & AJD stamp duty plus notary and registry fees — by region.":
        "ITP, IVA o IGIC y AJD, más notaría y registro, por comunidad autónoma.",
    "Property price": "Precio de la vivienda",
    "The agreed purchase price of the property. All taxes (ITP, IVA/IGIC, AJD) are calculated as a percentage of this figure. Minimum €10,000.":
        "El precio de compra pactado. Todos los impuestos (ITP, IVA/IGIC, AJD) se calculan como un porcentaje de esta cifra. Mínimo 10.000 €.",
    "Your autonomous community sets the ITP transfer-tax rate (3–13%) and the AJD stamp-duty rate (0–1.5%). Madrid and Navarre are among the cheapest at 6% ITP; Catalunya tops out at 13% on high-value resales.":
        "Tu comunidad autónoma fija el tipo del ITP (del 3 al 13 %) y el del AJD (del 0 al 1,5 %). Madrid y Navarra están entre las más baratas, con un 6 % de ITP; Cataluña llega al 13 % en las viviendas de segunda mano más caras.",
    "ITP rates shown are general rates — reduced rates may apply for first homes, under-35s, families and rural areas.":
        "Los tipos de ITP son los generales; puede haber tipos reducidos para la primera vivienda, menores de 35 años, familias y zonas rurales.",
    "Resale (second-hand) homes pay ITP transfer tax. New builds pay VAT — 10% IVA everywhere except the Canary Islands (7% IGIC) — plus AJD stamp duty. You never pay both.":
        "La vivienda de segunda mano paga ITP. La obra nueva paga un 10 % de IVA en toda España salvo en Canarias (7 % de IGIC), más el AJD. Nunca se pagan los dos.",
    "Resale (second-hand)": "Segunda mano",
    "New build": "Obra nueva",
    "Calculate buying costs": "Calcular los gastos de compra",
    "Total buying costs": "Gastos de compra totales",
    "Total taxes": "Impuestos totales",
    "Notary & Registry": "Notaría y registro",
    "Cost breakdown": "Desglose de los gastos",
    "You may qualify for a reduced rate": "Puede que tengas derecho a un tipo reducido",
    "Reduced ITP or AJD rates may apply if: you are under 35, this is your first home, you have a large family (3+ children) or a disability ≥33%. Check with your regional tax authority (comunidad autónoma).":
        "Puede haber tipos reducidos de ITP o AJD si tienes menos de 35 años, es tu primera vivienda, eres familia numerosa (3 hijos o más) o tienes una discapacidad igual o superior al 33 %. Consúltalo con la hacienda de tu comunidad autónoma.",
    "Buying in Spain? Share this calculator.": "¿Compras casa en España? Comparte esta calculadora.",
    # calculator-rental-yield.html
    "Spain Rental Yield Calculator": "Calculadora de rentabilidad del alquiler",
    "Net rental yield after tax, gross yield, cash-on-cash, IRR and monthly cash flow — for residents and non-residents, with Spanish purchase, rental and sale taxes.":
        "Rentabilidad neta después de impuestos, rentabilidad bruta, rentabilidad sobre lo invertido, TIR y flujo de caja mensual, para residentes y no residentes, con los impuestos españoles de compra, alquiler y venta.",
    "Jump to results ↓": "Ir a los resultados ↓",
    "Purchase": "Compra",
    "Purchase price": "Precio de compra",
    "The agreed price of the property. Purchase taxes are calculated on it. Minimum €10,000.":
        "El precio pactado de la vivienda. Los impuestos de compra se calculan sobre él. Mínimo 10.000 €.",
    "Your autonomous community sets the ITP transfer-tax rate (3–13%) and the AJD stamp-duty rate (0–1.5%) used for the purchase.":
        "Tu comunidad autónoma fija el tipo del ITP (del 3 al 13 %) y el del AJD (del 0 al 1,5 %) que se aplican a la compra.",
    "Resale homes pay ITP transfer tax. New builds pay 10% IVA (7% IGIC in the Canary Islands) plus AJD stamp duty. You never pay both.":
        "La segunda mano paga ITP. La obra nueva paga un 10 % de IVA (7 % de IGIC en Canarias) más el AJD. Nunca se pagan los dos.",
    "Resale": "Segunda mano",
    "Closing costs": "Gastos de compraventa",
    "Notary, land registry, gestoría and valuation, as a percentage of the price. Purchase tax is added separately. 1.5–2.5% is typical.":
        "Notaría, registro, gestoría y tasación, como porcentaje del precio. El impuesto de compra se suma aparte. Lo habitual es un 1,5-2,5 %.",
    "Include renovation": "Incluir reforma",
    "Add an initial renovation. It is added to your cash outlay and amortized separately, and the flat is not rented during the works.":
        "Añade una reforma inicial. Se suma al dinero que pones y se amortiza aparte, y el piso no se alquila mientras duran las obras.",
    "Renovation cost": "Coste de la reforma",
    "Works duration": "Duración de las obras",
    "Months of the first year without rent.": "Meses del primer año sin alquiler.",
    "Value after repairs": "Valor tras la reforma",
    "Estimated market value once the works are done. The sale price grows from this value.":
        "Valor de mercado estimado al terminar las obras. El precio de venta se revaloriza a partir de este valor.",
    "Rent & costs": "Alquiler y gastos",
    "Monthly rent": "Alquiler mensual",
    "Rent you charge per month in year 1, before vacancy.": "El alquiler que cobras cada mes el primer año, antes de los meses vacíos.",
    "Vacancy": "Vacío",
    "Share of the year the flat stands empty or unpaid.": "Parte del año en que el piso está vacío o sin cobrar.",
    "Rent growth": "Subida del alquiler",
    "Yearly rent increase. Regulated residential leases are limited by the rent-update index.":
        "Subida anual del alquiler. En los alquileres de vivienda la actualización está limitada por el índice de referencia.",
    "IBI": "IBI",
    "Annual municipal property tax (Impuesto sobre Bienes Inmuebles).": "Impuesto municipal anual sobre la vivienda (Impuesto sobre Bienes Inmuebles).",
    "Community fee": "Comunidad",
    "Monthly homeowners association fee.": "Cuota mensual de la comunidad de propietarios.",
    "Home insurance": "Seguro de hogar",
    "Rent insurance": "Seguro de impago",
    "Optional non-payment insurance.": "Seguro opcional contra el impago del alquiler.",
    "Maintenance": "Mantenimiento",
    "Repairs and upkeep as a percentage of rent.": "Reparaciones y mantenimiento, como porcentaje del alquiler.",
    "Management": "Gestión",
    "Property manager fee as a percentage of rent. 0 if you self-manage.": "Honorarios de la gestora como porcentaje del alquiler. 0 si lo gestionas tú.",
    "Expense growth": "Subida de los gastos",
    "Yearly increase of IBI, community fee and insurance. Maintenance and management follow the rent.":
        "Subida anual del IBI, la comunidad y los seguros. El mantenimiento y la gestión siguen al alquiler.",
    "Rent and expense growth start in year 2, so the year-1 yields and monthly cash flow stay the same. They move the IRR, profit when sold, the chart and the year-by-year table.":
        "Las subidas del alquiler y de los gastos empiezan el segundo año, así que la rentabilidad y el flujo de caja del primer año no cambian. Sí mueven la TIR, el beneficio al vender, el gráfico y la tabla año a año.",
    "Financing": "Financiación",
    "Use a mortgage": "Con hipoteca",
    "Down payment": "Entrada",
    "Share of the price paid in cash. Taxes and costs are paid in cash on top.":
        "Parte del precio que pagas con ahorros. Los impuestos y gastos se pagan aparte, también con ahorros.",
    "Interest rate": "Tipo de interés",
    "Fixed annual rate.": "Tipo fijo anual.",
    "Term": "Plazo",
    "Opening fee": "Comisión de apertura",
    "One-off bank fee, paid in cash.": "Comisión única del banco, que pagas con ahorros.",
    "Taxes": "Impuestos",
    "Tax residency": "Residencia fiscal",
    "Residents pay IRPF at their marginal rate. Non-residents pay IRNR: 19% (EU/EEA, on net income) or 24% (outside the EU/EEA, on gross rent).":
        "Los residentes pagan IRPF a su tipo marginal. Los no residentes pagan IRNR: un 19 % (UE/EEE, sobre el rendimiento neto) o un 24 % (fuera de la UE/EEE, sobre la renta bruta).",
    "Spanish resident": "Residente en España",
    "Non-resident (EU/EEA)": "No residente (UE/EEE)",
    "Non-resident (outside EU/EEA)": "No residente (fuera de la UE/EEE)",
    "Marginal IRPF rate": "Tipo marginal del IRPF",
    "The rate on your next euro of income (state + regional), typically 19–47%. Rental income is added on top of your other income.":
        "El tipo de tu próximo euro de renta (estatal + autonómico), normalmente del 19 al 47 %. El alquiler se suma al resto de tus ingresos.",
    "Rental reduction": "Reducción por alquiler",
    "50%: standard long-term home let. 60%: renovated in the last 2 years, or lease signed before 26 May 2023. 70% / 90%: stressed housing zones, if conditions are met. A new 15–100% scale (RDL 29/2026) still awaits validation and is not modelled — see the FAQ.":
        "50 %: alquiler de vivienda habitual. 60 %: vivienda rehabilitada en los 2 últimos años o contrato anterior al 26 de mayo de 2023. 70 % / 90 %: zonas tensionadas, si se cumplen las condiciones. La nueva escala del 15 al 100 % (RDL 29/2026) aún no está convalidada y no se incluye; mira las preguntas frecuentes.",
    "Apply the Audiencia Nacional 2025 ruling (net base, under appeal)": "Aplicar la sentencia de la Audiencia Nacional de 2025 (base neta, recurrida)",
    "Judgment of 28 July 2025 (rec. 636/2021) lets non-EU owners deduct expenses. The Supreme Court has admitted an appeal, so the current rule is 24% on gross rent. Tick to see the best case: 24% on net income.":
        "La sentencia de 28 de julio de 2025 (rec. 636/2021) permite a los propietarios de fuera de la UE deducir gastos. El Tribunal Supremo ha admitido un recurso, así que la norma vigente sigue siendo el 24 % sobre la renta bruta. Márcala para ver el mejor caso: un 24 % sobre el rendimiento neto.",
    "Building share of value": "Parte del valor que es construcción",
    "Amortization applies to the building only, not the land. Use the construction value ÷ total cadastral value from your IBI bill (valor catastral). 70% is a common default.":
        "Solo se amortiza la construcción, no el suelo. Usa el valor catastral de la construcción ÷ el valor catastral total de tu recibo del IBI. Un 70 % es un valor habitual.",
    "Exit": "Venta",
    "Holding period": "Años hasta vender",
    "Years until you sell (1–50).": "Años hasta que vendes (de 1 a 50).",
    "Property value growth": "Revalorización de la vivienda",
    "Average yearly increase of the property value.": "Subida media anual del valor de la vivienda.",
    "Selling costs": "Gastos de venta",
    "Agent fee and other costs of selling, as a percentage of the sale price.": "Honorarios de la inmobiliaria y otros gastos de la venta, como porcentaje del precio de venta.",
    "Municipal plusvalía": "Plusvalía municipal",
    "Local land-value gain tax (plusvalía municipal), paid by the seller. Depends on your town and cadastral data; enter your own estimate.":
        "Impuesto municipal sobre el incremento de valor de los terrenos (plusvalía municipal), que paga quien vende. Depende de tu municipio y de los datos catastrales; pon tu propia estimación.",
    "Net yield": "Rentabilidad neta",
    "after expenses & tax, year 1": "tras gastos e impuestos, primer año",
    "Gross yield": "Rentabilidad bruta",
    "rent ÷ price": "alquiler ÷ precio",
    "Cash-on-cash": "Sobre lo invertido",
    "year 1, on cash invested": "primer año, sobre tu dinero",
    "Cash flow / month": "Flujo de caja / mes",
    "year 1, after tax": "primer año, tras impuestos",
    "incl. sale": "con la venta",
    "Cash needed up front": "Dinero necesario al comprar",
    "Profit when sold": "Beneficio al vender",
    "Your position year by year": "Tu posición año a año",
    "Total net position (cash + property)": "Posición neta total (dinero + vivienda)",
    "Cumulative net cash flow + net equity (value − mortgage).": "Flujo de caja neto acumulado + patrimonio neto (valor − hipoteca).",
    "Total equity / asset value": "Patrimonio total / valor del inmueble",
    "Property value with yearly appreciation, minus the mortgage still owed.": "Valor de la vivienda con su revalorización anual, menos la hipoteca pendiente.",
    "Cumulative net cash flow": "Flujo de caja neto acumulado",
    "Rent after costs, mortgage and tax, minus the cash you put in up front.":
        "El alquiler tras gastos, hipoteca e impuestos, menos el dinero que pusiste al comprar.",
    "Invested capital": "Capital invertido",
    "Initial cash outlay + mortgage principal repaid to date.": "Dinero inicial + capital de la hipoteca amortizado hasta la fecha.",
    "Years since purchase. Tap or hover the chart to read a year.": "Años desde la compra. Toca o pasa el ratón por el gráfico para ver un año.",
    "Year-1 rental tax": "Impuestos del alquiler, primer año",
    "Over": "En",
    "Year-by-year table": "Tabla año a año",
    "Year-by-year cash flow table, scrolls horizontally": "Tabla del flujo de caja año a año, se desplaza en horizontal",
    "Year": "Año",
    "Rent": "Alquiler",
    "Expenses": "Gastos",
    "Mortgage": "Hipoteca",
    "Interest": "Intereses",
    "Tax": "Impuestos",
    "Cash flow": "Flujo de caja",
    "Cumulative": "Acumulado",
    "IRR": "TIR",
    "NOI": "Rend. neto",
    "Net operating income": "Rendimiento neto de explotación",
    "Renting out a flat in Spain? Share this calculator.": "¿Alquilas un piso en España? Comparte esta calculadora.",
    # calculator-rental-yield-amount.html
    "Net yield, resident": "Rentabilidad neta, residente",
    "after costs and tax, year 1": "tras gastos e impuestos, primer año",
    "{rent} a month, {annual} a year": "{rent} al mes, {annual} al año",
    "Cash flow a month": "Flujo de caja al mes",
    "after costs and tax, no mortgage": "tras gastos e impuestos, sin hipoteca",
    "Rent needed on a {amount} property": "Alquiler necesario para una vivienda de {amount}",
    "Monthly rent for each target gross yield and the net yield it leaves, by tax status. The {pct} row is the Spanish average.":
        "Alquiler mensual para cada rentabilidad bruta objetivo y la rentabilidad neta que deja, según la residencia fiscal. La fila del {pct} es la media española.",
    "Rent needed by target yield, scrolls horizontally": "Alquiler necesario según la rentabilidad, se desplaza en horizontal",
    "Rent a month": "Alquiler al mes",
    "Rent a year": "Alquiler al año",
    "Net, resident": "Neta, residente",
    "Net, EU/EEA": "Neta, UE/EEE",
    "Net, non-EU": "Neta, fuera de la UE",
    "From {rent} a month to net yield": "De {rent} al mes a la rentabilidad neta",
    "Rent after 5% vacancy, minus running costs": "Alquiler tras un 5 % de vacío, menos los gastos",
    "Rental tax, Spanish resident": "Impuesto sobre el alquiler, residente en España",
    "Rental tax, EU/EEA non-resident (19%)": "Impuesto sobre el alquiler, no residente UE/EEE (19 %)",
    "Rental tax, non-EU non-resident (24% on gross rent)": "Impuesto sobre el alquiler, no residente fuera de la UE (24 % sobre la renta bruta)",
    "Net yield: resident / EU/EEA / non-EU": "Rentabilidad neta: residente / UE/EEE / fuera de la UE",
    "Purchase tax (ITP, Madrid)": "Impuesto de compra (ITP, Madrid)",
    "Closing costs (2%)": "Gastos de compraventa (2 %)",
    "Total invested": "Inversión total",
    "IRR over 30 years, incl. sale": "TIR a 30 años, con la venta",
    "{amount} property in every region": "Una vivienda de {amount} en cada comunidad",
    "Net yield for a resident at {rent} a month, best first. Madrid is highlighted. Only the purchase tax changes.":
        "Rentabilidad neta para un residente con {rent} al mes, de mayor a menor. Madrid aparece destacada. Solo cambia el impuesto de compra.",
    "Net yield by region, scrolls horizontally": "Rentabilidad neta por comunidad, se desplaza en horizontal",
    "Purchase tax": "Impuesto de compra",
    "Neighbouring prices": "Precios cercanos",
    "Estimate based on {year} rules: regional ITP tables, art. 23.2 LIRPF reduction, IRNR rates of 19% and 24%. Rent is rounded to €5. Not tax advice. Last tax data verification: October 2026.":
        "Estimación con las normas de {year}: tablas autonómicas del ITP, reducción del art. 23.2 LIRPF y tipos del IRNR del 19 % y el 24 %. El alquiler se redondea a 5 €. No es asesoramiento fiscal. Última revisión de los datos fiscales: octubre de 2026.",
})


NET_SALARY_PAGES_JSON = os.path.join(SCRIPT_DIR, "data", "net-salary-pages.json")
NET_SALARY_GRID_SCRIPT = os.path.join(SCRIPT_DIR, "scripts", "net-salary-grid.mjs")
NET_SALARY_TEMPLATE = os.path.join(TEMPLATES_DIR, "calculator-net-salary.html")


def net_salary_slug(kind, amount):
    """URL slug (flat sibling of /calculators/net-salary) for an annual or monthly page."""
    return f"net-salary-{amount}-euros" if kind == "annual" else f"net-salary-{amount}-euros-per-month"


def eur(x, lang="en"):
    """Whole-euro amount: 30000 -> '€30,000' (en) / '30.000 €' (es, NBSP before €)."""
    n = int(round(x))
    if lang == "es":
        return f"{n:,}".replace(",", ".") + NBSP + "€"
    return f"€{n:,}"


def pct(x, digits=1, lang="en"):
    """Fraction as percent: 0.077 -> '7.7%' (en) / '7,7 %' (es)."""
    return ypct(x * 100, digits, lang)


def load_net_salary_pages():
    """Amount lists for the programmatic net-salary pages (data/net-salary-pages.json)."""
    with open(NET_SALARY_PAGES_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def per_month(label, lang="en"):
    """'€2,000' -> '€2,000/mo' (en) / '2.000 €/mes' (es)."""
    return label + ("/mes" if lang == "es" else "/mo")


def net_salary_links(pages=None, lang="en"):
    """Link-grid items for partials/net-salary-links.html (annual and monthly chips)."""
    pages = pages or load_net_salary_pages()
    return {
        "annual": [
            {"amount": a, "slug": net_salary_slug("annual", a), "label": eur(a, lang),
             "title": tr(lang, "{amount} gross to net in Spain", amount=eur(a, lang))}
            for a in pages["annual"]
        ],
        "monthly": [
            {"amount": m, "slug": net_salary_slug("monthly", m), "label": per_month(eur(m, lang), lang),
             "title": tr(lang, "{amount} gross per month to net in Spain", amount=eur(m, lang))}
            for m in pages["monthly"]
        ],
    }


def select_options(template_path, select_id):
    """value -> English label of a <select>'s options in a calculator template.

    Labels may be wrapped in {{ t("...") }}; the English key is returned."""
    with open(template_path, encoding="utf-8") as fh:
        text = fh.read()
    select = re.search(rf'<select id="{select_id}">(.*?)</select>', text, re.S).group(1)
    return {value: re.sub(r'^\{\{ t\("(.*)"\) \}\}$', r"\1", label.strip())
            for value, label in re.findall(r'<option value="([^"]+)"[^>]*>([^<]+)</option>', select)}


def net_salary_region_names(lang="en"):
    """Region id -> display name, parsed from the hub's <select id="f-region"> (single mapping)."""
    return {k: tr(lang, v) for k, v in select_options(NET_SALARY_TEMPLATE, "f-region").items()}


def compute_net_salary_grid():
    """Run scripts/net-salary-grid.mjs with node; fails loudly when node or the script is missing."""
    import subprocess

    if shutil.which("node") is None:
        raise RuntimeError("node is required to build the net salary pages but was not found on PATH")
    res = subprocess.run(
        ["node", NET_SALARY_GRID_SCRIPT, NET_SALARY_PAGES_JSON],
        check=True, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", cwd=SCRIPT_DIR,
    )
    return json.loads(res.stdout)


def _signed_eur(value, lang="en"):
    """'+€1,234' / '−€1,234' (en), '+1.234 €' / '−1.234 €' (es)."""
    return ("+" if value >= 0 else "−") + eur(abs(value), lang)


def _net_salary_regions(entry, names, calc_year, lang="en"):
    regions = entry["regions"]
    ref = next(r for r in regions if r["region"] == "madrid")
    rows = []
    for r in regions:
        rows.append({
            "id": r["region"], "name": names.get(r["region"], r["region"]),
            "net_year": eur(r["annualTaxNet"], lang), "net_month": eur(r["monthlyNet"], lang),
            "irpf": eur(r["irpf"], lang),
            "diff": _signed_eur(r["annualTaxNet"] - ref["annualTaxNet"], lang)
            if r["region"] != "madrid" else tr(lang, "reference"),
            "is_ref": r["region"] == "madrid",
        })
    common = [r for r in regions if r["region"] not in ("ceuta", "melilla")]
    return rows, names.get(common[0]["region"]), names.get(common[-1]["region"]), common[0], common[-1], ref


def net_salary_page_context(kind, item, neighbours, names, calc_year, lang="en"):
    """Everything the amount template shows, computed once and formatted here."""
    amount = item["amount"]
    monthly = kind == "monthly"
    e = item["x12"] if monthly else item
    p12, p14 = e["p12"], e["p14"]
    gross = e["gross"]
    rows, best_name, worst_name, best, worst, ref = _net_salary_regions(e, names, calc_year, lang)
    m_net = p12["annualTaxNet"] / 12
    E = lambda x: eur(x, lang)  # noqa: E731
    es = lang == "es"
    ctx = {
        "kind": kind, "amount": amount, "slug": net_salary_slug(kind, amount),
        "amount_label": per_month(E(amount), lang) if monthly else E(amount),
        "crumb_label": E(amount) + ((" al mes" if es else " per month") if monthly else ""),
        "gross": E(gross), "gross_month": E(gross / 12),
        "net_month": E(m_net), "net_year": E(p12["annualTaxNet"]),
        "payslip12": E(p12["payslipRegular"]), "payslip14": E(p14["payslipRegular"]),
        "extra14": E(p14["payslipExtra"]),
        "ss": E(p12["ssTotal"]), "irpf": E(p12["irpfTotal"]), "withheld": E(gross - p12["ssTotal"] - p12["netAnnual"]),
        "effective": pct(p12["effectiveRate"], lang=lang),
        "marginal": pct(p12["marginalRate"], lang=lang) if p12["marginalRate"] is not None else None,
        "withholding": (f"{p12['withholdingRate']:.2f}".rstrip("0").rstrip(".").replace(".", ",") + NBSP + "%" if es
                        else f"{p12['withholdingRate']:.2f}%".rstrip("0").rstrip(".")),
        "employer": E(p12["employerCost"]),
        "refund_value": p12["refund"], "refund": E(abs(p12["refund"])),
        "regions": rows, "best": best_name, "worst": worst_name,
        "best_net": E(best["annualTaxNet"]), "worst_net": E(worst["annualTaxNet"]),
        "spread": E(best["annualTaxNet"] - worst["annualTaxNet"]),
        "ceuta_net": E(next(r for r in e["regions"] if r["region"] == "ceuta")["annualTaxNet"]),
        "query": item["query"], "calc_year": calc_year,
        "prev": neighbours[0], "next": neighbours[1],
    }
    if monthly:
        a14 = item["x14"]["p14"]
        ctx["alt"] = {
            "gross": E(a14["gross"]), "payslip": E(a14["payslipRegular"]), "extra": E(a14["payslipExtra"]),
            "net_year": E(a14["annualTaxNet"]), "net_month": E(a14["annualTaxNet"] / 12),
        }
    if es and monthly:
        title_core = f"{E(amount)} brutos al mes: {E(m_net)} netos en España ({calc_year})"
        desc = (f"{E(amount)} brutos al mes ({E(gross)} al año) dejan {E(m_net)} netos al mes tras la "
                f"Seguridad Social y el IRPF. Madrid, sin hijos. Con 14 pagas y por comunidad.")
        ctx["answer"] = (f"{E(amount)} brutos al mes, en 12 pagas, son {E(gross)} al año y dejan unos "
                         f"{E(m_net)} netos al mes en {calc_year}.")
    elif es:
        title_core = f"{E(amount)} brutos al año: {E(m_net)} netos al mes ({calc_year})"
        desc = (f"{E(amount)} brutos al año dejan {E(m_net)} netos al mes en 12 pagas, o {E(p14['payslipRegular'])} más "
                f"dos pagas extra de {E(p14['payslipExtra'])} en 14. Madrid, sin hijos. Mira tu comunidad.")
        ctx["answer"] = (f"{E(amount)} brutos al año dejan unos {E(m_net)} netos al mes en 12 pagas en {calc_year}, "
                         f"o {E(p12['annualTaxNet'])} al año.")
    elif monthly:
        title_core = f"{eur(amount)} Gross per Month to Net in Spain ({calc_year}): {eur(m_net)}"
        desc = (f"{eur(amount)} gross a month ({eur(gross)} a year) leaves {eur(m_net)} net a month in Spain "
                f"after Social Security and IRPF. Madrid, no dependants. Compare 14 payments and every region.")
        ctx["answer"] = (f"{eur(amount)} gross a month, paid in 12 payments, is {eur(gross)} a year and leaves about "
                         f"{eur(m_net)} net a month in {calc_year}.")
    else:
        title_core = f"{eur(amount)} Gross to Net in Spain ({calc_year}): {eur(m_net)}/month"
        desc = (f"{eur(amount)} gross a year leaves {eur(m_net)} net a month on 12 payments, or {eur(p14['payslipRegular'])} plus "
                f"two of {eur(p14['payslipExtra'])} on 14. Madrid, no dependants. Check your region.")
        ctx["answer"] = (f"{eur(amount)} gross a year leaves about {eur(m_net)} net a month on 12 payments in {calc_year}, "
                         f"or {eur(p12['annualTaxNet'])} a year.")
    ctx["title"] = title_core + " | Spanified"
    ctx["h1"] = title_core
    ctx["description"] = desc
    ctx["faqs"] = net_salary_faqs_es(ctx) if es else net_salary_faqs(ctx, p12, p14)
    return ctx


def net_salary_faqs_es(c):
    a = c["gross"] if c["kind"] == "annual" else eur(c["amount"], "es") + " al mes"
    g = c["gross"]
    if abs(c["refund_value"]) < 1:
        refund = f"Más o menos sales a cero. Con un sueldo de {g}, la retención de la nómina es casi exactamente el impuesto que debes en Madrid."
    elif c["refund_value"] > 0:
        refund = (f"Seguramente sí. Con un sueldo de {g}, la retención de la nómina es algo mayor que el impuesto que debes, así que la Renta "
                  f"te devuelve unos {c['refund']} al año en Madrid.")
    else:
        refund = (f"Seguramente no. Con un sueldo de {g}, la retención de la nómina es algo menor que el impuesto que debes, así que cuenta con "
                  f"pagar unos {c['refund']} en la Renta en Madrid.")
    return [
        (f"¿Cuánto son {a} brutos en neto en España?",
         f"{g} brutos al año dejan {c['net_year']} netos al año, unos {c['net_month']} al mes en 12 pagas, después de "
         f"{c['ss']} de Seguridad Social del trabajador y {c['irpf']} de IRPF (normas de {c['calc_year']}, Madrid, sin hijos, contrato indefinido)."),
        (f"¿Qué es mejor con {g}, 12 o 14 pagas?",
         f"El total del año es el mismo. En 12 pagas cobras {c['payslip12']} al mes en la nómina. En 14 pagas cobras "
         f"{c['payslip14']} durante 12 meses más dos pagas extra de {c['extra14']}, normalmente en junio y diciembre."),
        (f"¿En qué comunidad se paga menos IRPF con {g}?",
         f"Ceuta y Melilla son las que menos pagan, porque solo tributan el 40 % del IRPF ({c['ceuta_net']} netos al año). Entre las demás, "
         f"{es_region(c['best'])} es donde más te queda ({c['best_net']}) y {es_region(c['worst'])} donde menos ({c['worst_net']}), una diferencia de {c['spread']} al año."),
        (f"¿Me saldrá a devolver la Renta con {g}?",
         refund + " El resultado depende de tu comunidad y tu situación familiar, así que usa la calculadora para tu caso."),
    ]


def net_salary_faqs(c, p12, p14):
    a = c["amount_label"] if c["kind"] == "annual" else eur(c["amount"]) + " a month"
    g = c["gross"]
    refund = (f"Probably. On a {g} salary the payslip withholding is slightly higher than the tax you owe, so the Renta returns about "
              f"{c['refund']} a year in Madrid." if c["refund_value"] > 0 else
              f"Probably not. On a {g} salary the payslip withholding is slightly lower than the tax you owe, so expect to pay about "
              f"{c['refund']} with the Renta in Madrid.")
    if abs(c["refund_value"]) < 1:
        refund = f"Roughly break-even. On a {g} salary the payslip withholding is almost exactly the tax you owe in Madrid."
    return [
        (f"How much is {a} gross after tax in Spain?",
         f"{g} gross a year leaves {c['net_year']} net a year, about {c['net_month']} a month on 12 payments, after "
         f"{c['ss']} of employee Social Security and {c['irpf']} of IRPF ({c['calc_year']} rules, Madrid, no dependants, permanent contract)."),
        (f"Is it better to get 12 or 14 payments on {g}?",
         f"The yearly total is the same. On 12 payments you get {c['payslip12']} a month on your payslip. On 14 payments you get "
         f"{c['payslip14']} for 12 months plus two extra payslips of {c['extra14']}, usually in June and December."),
        (f"Which region pays the least tax on {g}?",
         f"Ceuta and Melilla pay least because they only owe 40% of the IRPF ({c['ceuta_net']} net a year). Among the other regions "
         f"{c['best']} leaves the most ({c['best_net']}) and {c['worst']} the least ({c['worst_net']}), a gap of {c['spread']} a year."),
        (f"Will I get a Renta refund on {g}?", refund + " The result depends on your region and family situation, so use the calculator for your own case."),
    ]


def render_net_salary_pages(env, grid=None, langs=("en", "es")):
    """Render calculators/net-salary-{N}-euros[-per-month].html for every amount,
    in English and under es/calculators/ in Spanish.

    Figures come from scripts/net-salary-grid.mjs (the browser calculator modules run in
    node), so the tax engine stays a single source of truth. Raises when node is missing:
    the build must never silently drop these pages from the sitemap.
    Returns the English URL paths (e.g. "/calculators/net-salary-30000-euros").
    """
    import glob

    calc_dir = os.path.join(OUT_DIR, "calculators")
    os.makedirs(calc_dir, exist_ok=True)
    # Clear stale pages so removed amounts don't linger.
    for path in glob.glob(os.path.join(calc_dir, "net-salary-*-euros*.html")):
        os.remove(path)

    grid = grid or compute_net_salary_grid()
    calc_year = CALC_YEAR
    template = env.get_template("calculator-net-salary-amount.html")
    urls = []
    for lang in langs:
        out_dir = lang_out_dir(lang, "calculators")
        os.makedirs(out_dir, exist_ok=True)
        if lang != "en":
            for path in glob.glob(os.path.join(out_dir, "net-salary-*-euros*.html")):
                os.remove(path)
        names = net_salary_region_names(lang)
        links = net_salary_links(lang=lang)
        count = 0
        for kind in ("annual", "monthly"):
            items = grid[kind]
            for i, item in enumerate(items):
                def nb(j):
                    if 0 <= j < len(items):
                        label = eur(items[j]["amount"], lang)
                        return {"label": per_month(label, lang) if kind == "monthly" else label,
                                "slug": net_salary_slug(kind, items[j]["amount"])}
                    return None
                ctx = net_salary_page_context(kind, item, (nb(i - 1), nb(i + 1)), names, calc_year, lang)
                path = f"/calculators/{ctx['slug']}"
                crumbs = [
                    {"name": tr(lang, "Home"), "url": localize(lang, "/")},
                    {"name": tr(lang, "Net Salary Calculator"), "url": localize(lang, "/calculators/net-salary")},
                    {"name": ctx["crumb_label"], "url": lang_path(lang, path), "current": True},
                ]
                page_url = SITE_URL + lang_path(lang, path)
                og_summary = tr(lang, "{net} net a year  •  {rate} effective rate",
                                net=ctx["net_year"], rate=ctx["effective"])
                og_image = calculator_og_image(lang, ctx["slug"], ctx["h1"], og_summary)
                output = template.render(
                    p=ctx, crumbs=crumbs, js_version=js_version(), calc_year=calc_year, og_image=og_image,
                    page_lang=lang, page_url=page_url, alt_path=es_alt_path(path),
                    share=share_links(page_url, ctx["title"]), ns_links=links, current_slug=ctx["slug"],
                    build_date=datetime.now().strftime("%Y-%m-%d"),
                )
                with open(os.path.join(out_dir, ctx["slug"] + ".html"), "w", encoding="utf-8") as fh:
                    fh.write(output)
                count += 1
                if lang == "en":
                    urls.append(path)
        print(f"  wrote {count} net salary amount pages ({lang})")
    return urls


RENTAL_YIELD_PAGES_JSON = os.path.join(SCRIPT_DIR, "data", "rental-yield-pages.json")
RENTAL_YIELD_GRID_SCRIPT = os.path.join(SCRIPT_DIR, "scripts", "rental-yield-grid.mjs")
RENTAL_YIELD_TEMPLATE = os.path.join(TEMPLATES_DIR, "calculator-rental-yield.html")


def rental_yield_slug(price):
    """URL slug (flat sibling of /calculators/rental-yield) for a purchase-price page."""
    return f"rental-yield-{price}-euros-property"


def ypct(x, digits=1, lang="en"):
    """Format a yield already expressed in percent: 3.577 -> '3.6%' (en) / '3,6 %' (es)."""
    if lang == "es":
        return f"{x:,.{digits}f}".translate(ES_NUMBER_MARKS) + NBSP + "%"
    return f"{x:.{digits}f}%"


def load_rental_yield_pages():
    """Price list and reference assumptions for the programmatic rental-yield pages."""
    with open(RENTAL_YIELD_PAGES_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def rental_yield_links(pages=None, lang="en"):
    """Link-grid items for partials/rental-yield-links.html."""
    pages = pages or load_rental_yield_pages()
    return [
        {"amount": p, "slug": rental_yield_slug(p), "label": eur(p, lang),
         "title": tr(lang, "Rental yield on a {amount} property in Spain", amount=eur(p, lang))}
        for p in pages["prices"]
    ]


def rental_yield_region_names(lang="en"):
    """Region id -> display name, parsed from the hub's <select id="f-regionId"> (single mapping)."""
    return {k: tr(lang, v) for k, v in select_options(RENTAL_YIELD_TEMPLATE, "f-regionId").items()}


def compute_rental_yield_grid():
    """Run scripts/rental-yield-grid.mjs with node; fails loudly when node or the script is missing."""
    import subprocess

    if shutil.which("node") is None:
        raise RuntimeError("node is required to build the rental yield pages but was not found on PATH")
    res = subprocess.run(
        ["node", RENTAL_YIELD_GRID_SCRIPT, RENTAL_YIELD_PAGES_JSON],
        check=True, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", cwd=SCRIPT_DIR,
    )
    return json.loads(res.stdout)


def rental_yield_page_context(item, neighbours, names, calc_year, ref_pct, lang="en"):
    """Everything the rental-yield amount template shows, computed once and formatted here."""
    es = lang == "es"
    E = lambda x: eur(x, lang)  # noqa: E731
    P = lambda x, d=1: ypct(x, d, lang)  # noqa: E731
    G = lambda x: f"{x:g}".replace(".", ",") + NBSP + "%" if es else f"{x:g}%"  # noqa: E731
    price = item["amount"]
    res, eu, non_eu = item["byStatus"]["resident"], item["byStatus"]["non_resident_eu"], item["byStatus"]["non_resident_non_eu"]
    madrid = next(r for r in item["regions"] if r["region"] == "madrid")
    targets = [{
        "label": G(t["targetPct"]), "rent": E(t["resident"]["rent"]), "annual": E(t["resident"]["annualRent"]),
        "net_res": P(t["resident"]["netYield"]), "net_eu": P(t["non_resident_eu"]["netYield"]),
        "net_non_eu": P(t["non_resident_non_eu"]["netYield"]), "is_ref": t["targetPct"] == ref_pct,
    } for t in item["targets"]]
    by_net = sorted(item["regions"], key=lambda r: -r["netYield"])

    def diff(r):
        if r["region"] == "madrid":
            return tr(lang, "reference")
        d = f"{r['netYield'] - madrid['netYield']:+.2f}".replace("-", "−")
        return d.replace(".", ",") + NBSP + "p. p." if es else d + " pp"

    rows = [{
        "name": names.get(r["region"], r["region"]), "tax": E(r["purchaseTax"]), "upfront": E(r["totalInvestment"]),
        "net": P(r["netYield"], 2), "diff": diff(r),
        "is_ref": r["region"] == "madrid", "up": r["region"] != "madrid" and r["netYield"] > madrid["netYield"],
        "down": r["region"] != "madrid" and r["netYield"] < madrid["netYield"],
    } for r in by_net]
    common = [r for r in by_net if r["region"] not in ("ceuta", "melilla")]
    cheapest = min(common, key=lambda r: r["totalInvestment"])
    dearest = max(common, key=lambda r: r["totalInvestment"])
    rent6 = next(t for t in item["targets"] if t["targetPct"] == 6)["resident"]["rent"] if any(t["targetPct"] == 6 for t in item["targets"]) else None
    ctx = {
        "amount": price, "slug": rental_yield_slug(price), "amount_label": E(price), "calc_year": calc_year,
        "ref_pct": G(ref_pct), "rent": E(item["refRent"]), "annual_rent": E(res["annualRent"]),
        "gross": P(res["grossYield"]), "net_res": P(res["netYield"]), "net_eu": P(eu["netYield"]), "net_non_eu": P(non_eu["netYield"]),
        "cash_flow": E(res["monthlyCashFlow"]), "irr": P(res["irr"]),
        "tax_madrid": E(res["purchaseTax"]), "closing": E(res["closingCosts"]), "upfront": E(res["totalInvestment"]),
        "ibi": E(item["costs"]["annualIBI"]), "community": E(item["costs"]["monthlyCommunity"]),
        "noi": E(res["firstYearNOI"]), "tax_res": E(res["firstYearTax"]), "tax_eu": E(eu["firstYearTax"]), "tax_non_eu": E(non_eu["firstYearTax"]),
        "rent6": E(rent6) if rent6 else None,
        "targets": targets, "regions": rows,
        "cheapest_name": names.get(cheapest["region"], cheapest["region"]), "cheapest_upfront": E(cheapest["totalInvestment"]),
        "dearest_name": names.get(dearest["region"], dearest["region"]), "dearest_upfront": E(dearest["totalInvestment"]),
        "best_name": names.get(common[0]["region"]), "best_net": P(common[0]["netYield"], 2),
        "worst_name": names.get(common[-1]["region"]), "worst_net": P(common[-1]["netYield"], 2),
        "query": item["query"], "prev": neighbours[0], "next": neighbours[1],
    }
    if es:
        ctx["h1"] = f"Rentabilidad del alquiler de una vivienda de {E(price)} en España ({calc_year})"
        ctx["title"] = f"Rentabilidad de un piso de {E(price)} en España ({calc_year}) | Spanified"
        ctx["description"] = (f"Un piso de {E(price)} alquilado por {E(item['refRent'])} al mes rinde un {ctx['gross']} bruto y un "
                              f"{ctx['net_res']} neto tras gastos e impuestos en Madrid. Alquiler para sacar del 4 al 8 %.")
        ctx["answer"] = (f"Un piso de {E(price)} alquilado por {E(item['refRent'])} al mes rinde un {ctx['gross']} bruto, unos "
                         f"{ctx['net_res']} netos tras gastos e impuestos para un residente en Madrid"
                         + (f". Para llegar al 6 % bruto necesitas {ctx['rent6']} al mes." if rent6 else "."))
        ctx["faqs"] = rental_yield_faqs_es(ctx)
        return ctx
    ctx["h1"] = f"Rental Yield on a {eur(price)} Property in Spain ({calc_year})"
    ctx["title"] = f"{eur(price)} Property in Spain: Rental Yield and Rent Needed ({calc_year}) | Spanified"
    ctx["description"] = (f"A {eur(price)} flat renting for {eur(item['refRent'])} a month is a {ctx['gross']} gross yield and about "
                          f"{ctx['net_res']} net after costs and tax in Madrid. Rent needed for 4% to 8%, by tax status and region.")
    ctx["answer"] = (f"A {eur(price)} flat renting for {eur(item['refRent'])} a month is a {ctx['gross']} gross yield, about "
                     f"{ctx['net_res']} net after costs and tax for a resident in Madrid"
                     + (f". To reach 6% gross you need {ctx['rent6']} a month." if rent6 else "."))
    ctx["faqs"] = rental_yield_faqs(ctx)
    return ctx


def rental_yield_faqs_es(c):
    a = c["amount_label"]
    return [
        (f"¿Qué alquiler necesito para que una vivienda de {a} sea rentable?",
         "Alquiler anual = precio × rentabilidad bruta objetivo. Con " + a + ": " + "; ".join(
             f"un {t['label']} pide {t['rent']} al mes" for t in c["targets"]) + ". La rentabilidad neta es menor por los meses vacíos, el IBI, la comunidad, el seguro, el mantenimiento y los impuestos."),
        (f"¿Cuál es la rentabilidad neta de una vivienda de {a} en España?",
         f"Con {c['rent']} al mes ({c['gross']} bruto), la rentabilidad neta es del {c['net_res']} para un residente en España, del {c['net_eu']} para un no residente de la UE/EEE "
         f"y del {c['net_non_eu']} para un no residente de fuera de la UE/EEE, que tributa sobre el alquiler bruto. Las cifras suponen un piso de segunda mano en Madrid, "
         f"un IBI de {c['ibi']} al año, una comunidad de {c['community']} al mes, un 5 % de vacío y un 5 % de mantenimiento, sin hipoteca."),
        (f"¿Cuánto dinero necesito para comprar una vivienda de {a} en España?",
         f"En Madrid, {c['tax_madrid']} de ITP y unos {c['closing']} de gastos de compraventa llevan el total a {c['upfront']}. En las comunidades peninsulares el total va "
         f"de {c['cheapest_upfront']} en {es_region(c['cheapest_name'])} a {c['dearest_upfront']} en {es_region(c['dearest_name'])}, porque el impuesto de transmisiones cambia según la comunidad."),
        (f"¿Es buena una rentabilidad bruta del {c['gross']} en España?",
         f"Está cerca de la media nacional, en torno al 5,5 % bruto (Global Property Guide, tercer trimestre de 2026). Tras gastos e impuestos queda en un {c['net_res']} neto con {a}, "
         f"así que compara pisos por la rentabilidad neta, no por la cifra que sale en el anuncio."),
    ]


def rental_yield_faqs(c):
    a = c["amount_label"]
    return [
        (f"What rent do I need for a good yield on a {a} property?",
         "Annual rent = price × target gross yield. On " + a + ": " + "; ".join(
             f"{t['label']} needs {t['rent']} a month" for t in c["targets"]) + ". Net yield is lower because of vacancy, IBI, community fees, insurance, maintenance and tax."),
        (f"What is the net rental yield on a {a} property in Spain?",
         f"At {c['rent']} a month ({c['gross']} gross) the net yield is {c['net_res']} for a Spanish resident, {c['net_eu']} for an EU/EEA non-resident "
         f"and {c['net_non_eu']} for a non-resident outside the EU/EEA, who is taxed on gross rent. The figures assume a Madrid resale flat, "
         f"IBI of {c['ibi']} a year, a community fee of {c['community']} a month, 5% vacancy and 5% maintenance, with no mortgage."),
        (f"How much cash do I need to buy a {a} property in Spain?",
         f"In Madrid, {c['tax_madrid']} of ITP and about {c['closing']} of closing costs bring the total to {c['upfront']}. Across the mainland regions the total ranges "
         f"from {c['cheapest_upfront']} in {c['cheapest_name']} to {c['dearest_upfront']} in {c['dearest_name']}, because the transfer tax differs by region."),
        (f"Is a {c['gross']} gross yield good in Spain?",
         f"It is close to the national average gross yield of about 5.5% (Global Property Guide, Q3 2026). After costs and tax it is {c['net_res']} net on {a}, "
         f"so compare flats on net yield, not on the headline figure in the listing."),
    ]


def render_rental_yield_pages(env, grid=None, langs=("en", "es")):
    """Render calculators/rental-yield-{N}-euros-property.html for every purchase price.

    Figures come from scripts/rental-yield-grid.mjs (the browser calculator modules run in
    node), so the yield engine stays a single source of truth. Raises when node is missing.
    Returns the English URL paths (e.g. "/calculators/rental-yield-200000-euros-property").
    """
    import glob

    calc_dir = os.path.join(OUT_DIR, "calculators")
    os.makedirs(calc_dir, exist_ok=True)
    for path in glob.glob(os.path.join(calc_dir, "rental-yield-*-euros-property.html")):
        os.remove(path)

    grid = grid or compute_rental_yield_grid()
    config = load_rental_yield_pages()
    calc_year = CALC_YEAR
    template = env.get_template("calculator-rental-yield-amount.html")
    items = grid["prices"]
    urls = []
    for lang in langs:
        out_dir = lang_out_dir(lang, "calculators")
        os.makedirs(out_dir, exist_ok=True)
        if lang != "en":
            for path in glob.glob(os.path.join(out_dir, "rental-yield-*-euros-property.html")):
                os.remove(path)
        names = rental_yield_region_names(lang)
        links = rental_yield_links(lang=lang)
        for i, item in enumerate(items):
            def nb(j):
                if 0 <= j < len(items):
                    return {"label": eur(items[j]["amount"], lang), "slug": rental_yield_slug(items[j]["amount"])}
                return None
            ctx = rental_yield_page_context(item, (nb(i - 1), nb(i + 1)), names, calc_year, config["referenceGrossPct"], lang)
            path = f"/calculators/{ctx['slug']}"
            crumbs = [
                {"name": tr(lang, "Home"), "url": localize(lang, "/")},
                {"name": tr(lang, "Rental Yield Calculator"), "url": localize(lang, "/calculators/rental-yield")},
                {"name": ctx["amount_label"], "url": lang_path(lang, path), "current": True},
            ]
            page_url = SITE_URL + lang_path(lang, path)
            og_image = calculator_og_image(lang, ctx["slug"], ctx["h1"],
                                           tr(lang, "{gross} gross  •  {net} net yield", gross=ctx["gross"], net=ctx["net_res"]))
            output = template.render(
                p=ctx, crumbs=crumbs, js_version=js_version(), calc_year=calc_year, og_image=og_image,
                page_lang=lang, page_url=page_url, alt_path=es_alt_path(path),
                share=share_links(page_url, ctx["title"]), ry_links=links, current_slug=ctx["slug"],
                build_date=datetime.now().strftime("%Y-%m-%d"),
            )
            with open(os.path.join(out_dir, ctx["slug"] + ".html"), "w", encoding="utf-8") as fh:
                fh.write(output)
            if lang == "en":
                urls.append(path)
        print(f"  wrote {len(items)} rental yield amount pages ({lang})")
    return urls


AUTONOMO_PAGES_JSON = os.path.join(SCRIPT_DIR, "data", "autonomo-pages.json")
AUTONOMO_GRID_SCRIPT = os.path.join(SCRIPT_DIR, "scripts", "autonomo-grid.mjs")
AUTONOMO_TEMPLATE = os.path.join(TEMPLATES_DIR, "calculator-autonomo.html")


def autonomo_slug(kind, amount):
    """URL slug (flat sibling of /calculators/autonomo-tax) for a revenue or a take-home-per-month page."""
    return f"autonomo-tax-{amount}-euros" if kind == "revenue" else f"autonomo-take-home-{amount}-euros-per-month"


def load_autonomo_pages():
    """Amount lists for the programmatic autónomo pages (data/autonomo-pages.json)."""
    with open(AUTONOMO_PAGES_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def autonomo_links(pages=None, lang="en"):
    """Link-grid items for partials/autonomo-links.html (revenue and take-home chips)."""
    pages = pages or load_autonomo_pages()
    return {
        "revenue": [
            {"amount": a, "slug": autonomo_slug("revenue", a), "label": eur(a, lang),
             "title": tr(lang, "Autónomo net pay on {amount} a year in Spain", amount=eur(a, lang))}
            for a in pages["revenue"]
        ],
        "monthly": [
            {"amount": m, "slug": autonomo_slug("monthly", m), "label": per_month(eur(m, lang), lang),
             "title": tr(lang, "What an autónomo must earn to take home {amount} a month", amount=eur(m, lang))}
            for m in pages["monthly"]
        ],
    }


def autonomo_region_names(lang="en"):
    """Region id -> display name, parsed from the hub's <select id="f-region"> (single mapping)."""
    return {k: tr(lang, v) for k, v in select_options(AUTONOMO_TEMPLATE, "f-region").items()}


def compute_autonomo_grid():
    """Run scripts/autonomo-grid.mjs with node; fails loudly when node or the script is missing."""
    import subprocess

    if shutil.which("node") is None:
        raise RuntimeError("node is required to build the autónomo pages but was not found on PATH")
    res = subprocess.run(
        ["node", AUTONOMO_GRID_SCRIPT, AUTONOMO_PAGES_JSON],
        check=True, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", cwd=SCRIPT_DIR,
    )
    return json.loads(res.stdout)


def autonomo_page_context(kind, item, neighbours, names, calc_year, lang="en"):
    """Everything the autónomo amount template shows, computed once and formatted here."""
    es = lang == "es"
    E = lambda x: eur(x, lang)  # noqa: E731
    monthly = kind == "monthly"
    amount = item["amount"]
    e, t = item["established"], item["tarifaPlana"]
    revenue = e["revenue"]
    regions = item["regions"]
    ref = next(r for r in regions if r["region"] == "madrid")
    rows = [{
        "name": names.get(r["region"], r["region"]),
        "net_year": E(r["netYear"]), "net_month": E(r["netMonth"]), "irpf": E(r["irpf"]),
        "diff": tr(lang, "reference") if r["region"] == "madrid" else _signed_eur(r["netYear"] - ref["netYear"], lang),
        "is_ref": r["region"] == "madrid",
    } for r in regions]
    common = [r for r in regions if r["region"] not in ("ceuta", "melilla")]
    best, worst = common[0], common[-1]
    ceuta = next(r for r in regions if r["region"] == "ceuta")
    rev_label, rev_month = E(revenue), E(revenue / 12)
    ctx = {
        "kind": kind, "amount": amount, "slug": autonomo_slug(kind, amount), "calc_year": calc_year,
        "revenue": rev_label, "revenue_month": rev_month,
        "quota": E(e["monthlyQuota"]), "quota_year": E(e["annualSS"]), "bracket": e["bracketId"],
        "irpf": E(e["irpfTotal"]), "irpf_month": E(e["irpfTotal"] / 12),
        "irpf_deduction": E(e["irpfDeduction"]), "personal_minimum": E(e["personalMinimum"]),
        "irpf_base": E(e["irpfBase"]),
        "burden": E(e["totalBurden"]), "burden_rate": pct(e["effectiveTotalRate"], lang=lang),
        "irpf_rate": pct(e["effectiveIrpfRate"], lang=lang),
        "net_year": E(e["netYear"]), "net_month": E(e["netMonth"]),
        "tp_net_year": E(t["netYear"]), "tp_net_month": E(t["netMonth"]), "tp_irpf": E(t["irpfTotal"]),
        "tp_gain_month": E(t["netMonth"] - e["netMonth"]), "tp_ss_year": E(t["annualSS"]),
        "regions": rows, "best": names.get(best["region"]), "worst": names.get(worst["region"]),
        "best_net": E(best["netYear"]), "worst_net": E(worst["netYear"]),
        "spread": E(best["netYear"] - worst["netYear"]), "ceuta_net": E(ceuta["netYear"]),
        "prev": neighbours[0], "next": neighbours[1],
    }
    if monthly:
        target = E(amount)
        ctx.update({
            "amount_label": per_month(target, lang),
            "crumb_label": f"Llevarte {target} al mes" if es else f"Take home {target} a month",
            "query": f"aut_r={revenue}", "target": target,
            "tp_needed": E(item["neededTarifaPlana"]), "tp_needed_month": E(item["neededTarifaPlana"] / 12),
            "tp_saving": E(item["needed"] - item["neededTarifaPlana"]),
            "example_costs": 500, "example_invoice": E(revenue / 12 + 500),
        })
        if es:
            title_core = f"Autónomo: cuánto facturar para ganar {target} al mes ({calc_year})"
            ctx["answer"] = (f"Para llevarte {target} al mes como autónomo consolidado en Madrid en {calc_year} necesitas unos "
                             f"{rev_label} de rendimiento neto al año ({rev_month} al mes), antes de {ctx['quota']} al mes de Seguridad Social y {ctx['irpf']} al año de IRPF.")
            ctx["description"] = (f"Para quedarte {target} al mes como autónomo necesitas unos {rev_label} al año de rendimiento neto ({rev_month} al mes) "
                                  f"tras cuota e IRPF ({calc_year}). Tarifa plana: {E(item['neededTarifaPlana'])}.")
        else:
            title_core = f"Take Home {target} a Month as an Autónomo (Spain {calc_year}): Earn {rev_label} a Year"
            ctx["answer"] = (f"To take home {target} a month as an established autónomo in Madrid in {calc_year}, you need about "
                             f"{rev_label} of annual net revenue ({rev_month} a month), before {ctx['quota']} a month of Social Security and {ctx['irpf']} a year of IRPF.")
            ctx["description"] = (f"A freelance autónomo needs about {rev_label} a year in net revenue ({rev_month} a month) to keep {target} a month after "
                                  f"Social Security and IRPF in Spain ({calc_year}). Tarifa plana first year: {eur(item['neededTarifaPlana'])}.")
    else:
        ctx.update({
            "amount_label": rev_label, "crumb_label": rev_label,
            "query": f"aut_r={revenue}",
        })
        if es:
            title_core = f"Autónomo con {rev_label} al año: {ctx['net_month']} netos al mes ({calc_year})"
            ctx["answer"] = (f"Un autónomo consolidado en Madrid con {rev_label} de rendimiento neto al año se queda unos {ctx['net_month']} al mes "
                             f"({ctx['net_year']} al año) en {calc_year}, después de {ctx['quota_year']} de Seguridad Social y {ctx['irpf']} de IRPF.")
            ctx["description"] = (f"{rev_label} de rendimiento neto al año dejan a un autónomo {ctx['net_month']} al mes ({calc_year}) tras "
                                  f"{ctx['quota']}/mes de cuota y {ctx['irpf']} de IRPF. Tarifa plana: {ctx['tp_net_month']} al mes.")
        else:
            title_core = f"Autónomo on {rev_label} a Year in Spain ({calc_year}): {ctx['net_month']}/month Net"
            ctx["answer"] = (f"An established autónomo in Madrid with {rev_label} of annual net revenue keeps about {ctx['net_month']} a month "
                             f"({ctx['net_year']} a year) in {calc_year}, after {ctx['quota_year']} of Social Security and {ctx['irpf']} of IRPF.")
            ctx["description"] = (f"{rev_label} of annual net revenue leaves a self-employed autónomo {ctx['net_month']} a month in Spain ({calc_year}) after "
                                  f"{ctx['quota']}/month Social Security and {ctx['irpf']} IRPF. First year on tarifa plana: {ctx['tp_net_month']} a month.")
    ctx["title"] = title_core + " | Spanified"
    ctx["h1"] = title_core
    ctx["faqs"] = autonomo_faqs_es(ctx) if es else autonomo_faqs(ctx)
    return ctx


def autonomo_faqs_es(c):
    r, y = c["revenue"], c["calc_year"]
    region_a = (f"Ceuta y Melilla son las que menos pagan, porque sus residentes solo tributan el 40 % del IRPF por lo que ganan allí ({c['ceuta_net']} netos al año con {r}). Entre las demás, "
                f"{es_region(c['best'])} es donde más te queda ({c['best_net']}) y {es_region(c['worst'])} donde menos ({c['worst_net']}), una diferencia de {c['spread']} al año. La Seguridad Social es igual en todas.")
    tp_a = (f"Los primeros 12 meses un autónomo nuevo paga la tarifa plana de 80 € más el MEI (unos 88,65 € al mes), así que la Seguridad Social es de {c['tp_ss_year']} al año en lugar de {c['quota_year']}. "
            f"Con {r} eso supone unos {c['tp_net_month']} netos al mes en lugar de {c['net_month']}, {c['tp_gain_month']} más cada mes. Pasado el primer año, la cuota va según tu tramo de rendimientos.")
    if c["kind"] == "monthly":
        return [
            (f"¿Cuánto tiene que ganar un autónomo para llevarse {c['target']} al mes en España?",
             f"Unos {r} al año ({c['revenue_month']} al mes) de rendimiento neto, es decir, ingresos menos gastos del negocio y antes de la Seguridad Social y el IRPF. "
             f"De ahí pagas {c['quota']} al mes de cuota (tramo {c['bracket']}) y {c['irpf']} al año de IRPF (normas de {y}, autónomo consolidado, Madrid, sin hijos)."),
            (f"¿Cuánto tengo que facturar para llevarme {c['target']} al mes?",
             f"Suma tus gastos del negocio a los {c['revenue_month']} al mes de rendimiento neto y añade el IVA si lo cobras. Por ejemplo, con {eur(c['example_costs'], 'es')} al mes de gastos "
             f"facturarías unos {c['example_invoice']} al mes sin IVA. La calculadora pide el rendimiento neto, así que resta los gastos antes de poner tu cifra."),
            (f"¿Es más fácil llegar a {c['target']} al mes con tarifa plana?",
             f"Sí. Durante los primeros 12 meses te bastan {c['tp_needed']} al año ({c['tp_needed_month']} al mes), {c['tp_saving']} menos que los {r} que necesita un autónomo consolidado, porque la cuota es de unos 88,65 € al mes (80 € más el MEI). "
             f"A partir del mes 13 se aplica la cuota normal."),
            (f"¿Cambia según la comunidad lo que me queda de {r} de rendimiento neto?",
             region_a),
        ]
    return [
        (f"¿Cuántos impuestos paga un autónomo con {r} en España?",
         f"Con {r} de rendimiento neto al año, un autónomo consolidado en Madrid paga {c['quota_year']} de Seguridad Social ({c['quota']} al mes, tramo {c['bracket']}) y {c['irpf']} de IRPF: "
         f"{c['burden']} en total, el {c['burden_rate']} del rendimiento (normas de {y}, sin hijos, 35 años)."),
        (f"¿Cuánto le queda a un autónomo de {r} al año?",
         f"Unos {c['net_year']} al año, o {c['net_month']} al mes, después de la Seguridad Social y el IRPF. Aquí el rendimiento neto son los ingresos menos los gastos del negocio, antes de la Seguridad Social y el IRPF. "
         f"El IRPF se calcula sobre {c['irpf_base']}, tras restar la Seguridad Social y una reducción de {c['irpf_deduction']}, menos el mínimo personal de {c['personal_minimum']}."),
        (f"¿Cambian las cifras con tarifa plana con {r}?", tp_a),
        (f"¿Qué comunidad sale más barata a un autónomo con {r}?", region_a),
    ]

def autonomo_faqs(c):
    r, y = c["revenue"], c["calc_year"]
    region_q = f"Which region is cheapest for an autónomo with {r}?"
    region_a = (f"Ceuta and Melilla pay least because residents owe only 40% of the IRPF on income earned there ({c['ceuta_net']} net a year at {r}). Among the other regions "
                f"{c['best']} leaves the most ({c['best_net']}) and {c['worst']} the least ({c['worst_net']}), a gap of {c['spread']} a year. Social Security is the same everywhere.")
    tp_a = (f"In the first 12 months a new autónomo pays the €80 tarifa plana plus the MEI levy (about €88.65 a month), so Social Security is {c['tp_ss_year']} a year instead of {c['quota_year']}. "
            f"At {r} that is about {c['tp_net_month']} a month net instead of {c['net_month']}, {c['tp_gain_month']} more each month. After the first year the quota follows your income bracket.")
    if c["kind"] == "monthly":
        return [
            (f"How much must an autónomo earn to take home {c['target']} a month in Spain?",
             f"About {r} a year ({c['revenue_month']} a month) of net revenue, meaning income after your business expenses and before Social Security and IRPF. "
             f"From that you pay {c['quota']} a month of quota (bracket {c['bracket']}) and {c['irpf']} a year of IRPF ({y} rules, established autónomo, Madrid, no dependants)."),
            (f"How much should I invoice to take home {c['target']} a month?",
             f"Add your business expenses to the {c['revenue_month']} a month of net revenue, then add IVA if you charge it. For example, with {eur(c['example_costs'])} a month of costs "
             f"you would invoice about {c['example_invoice']} a month before IVA. The calculator takes net revenue, so deduct expenses before you enter your own figure."),
            (f"Is it easier to reach {c['target']} a month on tarifa plana?",
             f"Yes. During the first 12 months you need only {c['tp_needed']} a year ({c['tp_needed_month']} a month), {c['tp_saving']} less than the {r} an established autónomo needs, because the quota is about €88.65 a month (€80 plus the MEI levy). "
             f"From month 13 the regular quota applies."),
            (f"Does the region change what I take home from {r} of net revenue?",
             region_a),
        ]
    return [
        (f"How much tax does an autónomo pay on {r} in Spain?",
         f"At {r} of annual net revenue an established autónomo in Madrid pays {c['quota_year']} of Social Security ({c['quota']} a month, bracket {c['bracket']}) and {c['irpf']} of IRPF, "
         f"{c['burden']} in total or {c['burden_rate']} of revenue ({y} rules, no dependants, age 35)."),
        (f"How much does an autónomo keep from {r} a year?",
         f"About {c['net_year']} a year, or {c['net_month']} a month, after Social Security and IRPF. Net revenue here means income after business expenses, before Social Security and IRPF. "
         f"IRPF is calculated on {c['irpf_base']} after Social Security and a {c['irpf_deduction']} allowance, less the {c['personal_minimum']} personal minimum."),
        (f"Does tarifa plana change the numbers at {r}?", tp_a),
        (region_q, region_a),
    ]


def render_autonomo_pages(env, grid=None, langs=("en", "es")):
    """Render calculators/autonomo-tax-{N}-euros.html and autonomo-take-home-{N}-euros-per-month.html.

    Figures come from scripts/autonomo-grid.mjs (the browser calculator modules run in node),
    so the tax engine stays a single source of truth. Raises when node is missing: the build
    must never silently drop these pages from the sitemap.
    Returns the English URL paths (e.g. "/calculators/autonomo-tax-30000-euros").
    """
    import glob

    calc_dir = os.path.join(OUT_DIR, "calculators")
    os.makedirs(calc_dir, exist_ok=True)
    # Clear stale pages so removed amounts don't linger.
    for path in glob.glob(os.path.join(calc_dir, "autonomo-*-euros*.html")):
        os.remove(path)

    grid = grid or compute_autonomo_grid()
    calc_year = CALC_YEAR
    template = env.get_template("calculator-autonomo-amount.html")
    urls = []
    for lang in langs:
        out_dir = lang_out_dir(lang, "calculators")
        os.makedirs(out_dir, exist_ok=True)
        if lang != "en":
            for path in glob.glob(os.path.join(out_dir, "autonomo-*-euros*.html")):
                os.remove(path)
        names = autonomo_region_names(lang)
        links = autonomo_links(lang=lang)
        count = 0
        for kind in ("revenue", "monthly"):
            items = grid[kind]
            for i, item in enumerate(items):
                def nb(j):
                    if 0 <= j < len(items):
                        label = eur(items[j]["amount"], lang)
                        return {"label": per_month(label, lang) if kind == "monthly" else label,
                                "slug": autonomo_slug(kind, items[j]["amount"])}
                    return None
                ctx = autonomo_page_context(kind, item, (nb(i - 1), nb(i + 1)), names, calc_year, lang)
                path = f"/calculators/{ctx['slug']}"
                crumbs = [
                    {"name": tr(lang, "Home"), "url": localize(lang, "/")},
                    {"name": tr(lang, "Autónomo Tax Calculator"), "url": localize(lang, "/calculators/autonomo-tax")},
                    {"name": ctx["crumb_label"], "url": lang_path(lang, path), "current": True},
                ]
                page_url = SITE_URL + lang_path(lang, path)
                og_summary = tr(lang, "Cuota {quota} a month  •  {rate} total burden",
                                quota=ctx["quota"], rate=ctx["burden_rate"])
                og_image = calculator_og_image(lang, ctx["slug"], ctx["h1"], og_summary)
                output = template.render(
                    p=ctx, crumbs=crumbs, js_version=js_version(), calc_year=calc_year, og_image=og_image,
                    page_lang=lang, page_url=page_url, alt_path=es_alt_path(path),
                    share=share_links(page_url, ctx["title"]), au_links=links, current_slug=ctx["slug"],
                    build_date=datetime.now().strftime("%Y-%m-%d"),
                )
                with open(os.path.join(out_dir, ctx["slug"] + ".html"), "w", encoding="utf-8") as fh:
                    fh.write(output)
                count += 1
                if lang == "en":
                    urls.append(path)
        print(f"  wrote {count} autónomo amount pages ({lang})")
    return urls


def render_quizzes(env, proof=None, latest_url=None, lang="en"):
    """Render quiz pages from load_quizzes(lang) (multi-quiz ready).

    ``proof`` is the social-proof dict from render_static (total_issues /
    first_issue, same data /subscribe shows) so the gate can render a live
    "N daily editions" line; pages fall back to a static default in the
    template when it is absent.

    Per quiz <slug>: quiz/<slug>.html (app), quiz/<slug>-subscribed.html
    (legacy Brevo confirmation snippet, kept for old links, noindex),
    quiz/<slug>-success.html (post double-opt-in page, noindex),
    quiz/<slug>-result-<persona>.html (per-persona share landing, noindex
    until launch). Only quiz/<slug> is indexable and in the sitemap.
    lang="es" writes the same set under es/quiz/ with page_lang="es";
    only quiz/<slug> has an hreflang pair (ES_PATHS), the flow pages are
    noindex and link their own language's pages.
    """
    import json as _json

    cards = load_quiz_cards(lang=lang)
    for quiz in load_quizzes(lang):
        slug = quiz["slug"]
        others = [c for c in cards if c.get("slug") != slug]
        quiz_json = _json.dumps(quiz)
        quiz_base = lang_path(lang, f"/quiz/{slug}")
        base = f"{SITE_URL}{quiz_base}"
        share = share_links(
            base,
            tr(lang, "{title} — Spanified", title=quiz["title"]),
            tr(lang, "{title} — 10 questions, 2 minutes, half of it really happened in Spain. Take the quiz:",
               title=quiz["title"]),
        )
        crumbs = [
            {"name": tr(lang, "Home"), "url": localize(lang, "/")},
            {"name": tr(lang, "Quiz"), "url": quiz_base, "current": True},
        ]
        ctx = dict(
            quiz=quiz, quiz_json=quiz_json, crumbs=crumbs,
            js_version=js_version(), share=share, proof=proof,
            other_quizzes=others, latest_digest_url=latest_url,
            page_lang=lang, quiz_base=quiz_base,
        )
        pages = [
            ("quiz.html", f"quiz/{slug}.html", es_alt_path(f"/quiz/{slug}")),
            ("quiz-subscribed.html", f"quiz/{slug}-subscribed.html", None),
            ("quiz-success.html", f"quiz/{slug}-success.html", None),
        ]
        for template_name, rel_dest, alt_path in pages:
            output = env.get_template(template_name).render(alt_path=alt_path, **ctx)
            dest = lang_out_dir(lang, rel_dest)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as out:
                out.write(output)
            print(f"  wrote {'es/' if lang == 'es' else ''}{rel_dest}")

        # Per-persona share landing pages (static, OG-scrapeable).
        result_template = env.get_template("quiz-result.html")
        for result in quiz.get("results", []):
            result_url = f"{base}-result-{result['slug']}"
            share_text = result.get('shareText', f"{result['title']} — {quiz['title']} — Spanified")
            first_para = (result.get('text') or '').split('\n\n')[0].strip()
            share_long = f"{share_text}\n\n{first_para}" if first_para else share_text
            result_share = share_links(result_url, share_text, share_long)
            result_ctx = dict(
                quiz=quiz,
                result=result,
                all_results=quiz.get("results", []),
                friend_score=None,
                share=result_share,
                crumbs=crumbs,
                other_quizzes=others,
                page_lang=lang,
                quiz_base=quiz_base,
            )
            dest_path = f"quiz/{slug}-result-{result['slug']}.html"
            output = result_template.render(**result_ctx)
            dest = lang_out_dir(lang, dest_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as out:
                out.write(output)
            print(f"  wrote {'es/' if lang == 'es' else ''}{dest_path}")


def attach_related(digests, limit=2):
    """Attach same-category 'More news' links to every story.

    Only stories from strictly older digests (newest first,
    /archive/<date>#news-N). Same-digest siblings are excluded.
    Within one digest, links are dealt out without repetition: if two
    stories share a category, the second one gets the next batch,
    reaching deeper into the archive.
    Stories with no same-category peers get an empty list (block not rendered).
    """
    for i, digest in enumerate(digests):
        stories = digest.get("stories", [])
        used = set()  # urls already dealt out within this digest
        for pos, item in enumerate(stories, start=1):
            cat = (item.get("category") or "").lower()
            if not cat:
                item["related"] = []
                continue
            related = []
            # Only older digests (list is newest-first), newest first.
            for older in digests[i + 1:]:
                for k, other in enumerate(older.get("stories", []), start=1):
                    if (other.get("category") or "").lower() != cat:
                        continue
                    title = other.get("title", "")
                    if not title:
                        continue
                    url = f"{older['url']}#news-{k}"
                    if url in used:
                        continue
                    related.append({"title": title, "url": url})
                    if len(related) >= limit:
                        break
                if len(related) >= limit:
                    break
            item["related"] = related[:limit]
            used.update(r["url"] for r in item["related"])


def attach_guides(digests, articles):
    """Attach an 'Explainer' link to stories that mention a guide's topic.

    Each article can list comma-separated `story_keywords` in its front
    matter; a story whose title or body contains one of them (whole
    words, case-insensitive) links to that article. Optional
    `story_categories` limits matching to stories in those categories.
    The article matching the most distinct keywords wins; ties go to the
    earlier one in `articles` order. Stories with no match get None.
    The link is the English path; digest.html localizes it (Spanish
    digests matched against Spanish articles link the /es/ twins).
    """
    patterns = _keyword_patterns(articles, "story_keywords", "story_categories")
    for digest in digests:
        for item in digest.get("stories", []):
            best = _best_matches(item, patterns)
            item["guide"] = ({"title": best[0]["title"], "url": best[0].get("path", best[0]["url"])}
                             if best else None)


def _keyword_patterns(entries, kw_key, cat_key):
    """(regex, categories, entry) for entries that list keywords."""
    return [
        (re.compile(r"\b(?:" + "|".join(re.escape(k) for k in e[kw_key]) + r")\b", re.I),
         [c.lower() for c in e.get(cat_key) or []], e)
        for e in entries if e.get(kw_key)
    ]


def _best_matches(item, patterns):
    """Entries whose keywords hit the story, most distinct hits first (stable)."""
    text = f"{item.get('title', '')} {item.get('body', '')}"
    cat = (item.get("category") or "").lower()
    scored = []
    for rx, cats, entry in patterns:
        if cats and cat not in cats:
            continue
        hits = {m.lower() for m in rx.findall(text)}
        if hits:
            scored.append((len(hits), entry))
    scored.sort(key=lambda s: -s[0])
    return [e for _, e in scored]


# Calculators linked from digest stories ("Calculator: …" line). Order breaks
# ties, so more specific tools come first. `anchors` vary the link text
# across editions; the choice is deterministic per (edition, tool).
STORY_TOOLS = [
    {"url": "/calculators/autonomo-tax",
     "keywords": ["autónomo", "autónomos", "autonomo", "autonomos", "self-employed", "freelancer",
                  "freelancers", "cuota de autónomos", "RETA", "tarifa plana"],
     "anchors": ["Autónomo tax calculator: your quota and IRPF",
                 "work out what you'd pay as an autónomo",
                 "self-employed in Spain: estimate your net income"]},
    {"url": "/calculators/electricity-bill",
     "keywords": ["electricity bill", "electricity bills", "power bill", "power bills", "electricity price",
                  "electricity prices", "price of electricity", "electricity tariff", "electricity tariffs",
                  "PVPC", "regulated tariff", "energy bill", "energy bills"],
     "anchors": ["Electricity bill calculator: PVPC vs fixed tariffs",
                 "check what your electricity bill should be",
                 "compare your power bill with the PVPC"]},
    {"url": "/calculators/rental-yield",
     "keywords": ["rental yield", "rental yields", "landlord", "landlords", "rental income", "buy-to-let",
                  "tourist flat", "tourist flats", "tourist rental", "tourist rentals", "holiday let",
                  "holiday lets", "rent prices", "rental prices", "rental market", "rent control"],
     "categories": ["property", "housing", "economy", "taxes"],
     "anchors": ["Rental yield calculator: net yield after tax",
                 "does a rental flat in Spain pay off?",
                 "work out net rental yield and cash flow"]},
    {"url": "/calculators/property-buying-cost",
     "keywords": ["house prices", "home prices", "housing prices", "property prices", "mortgage", "mortgages",
                  "homebuyers", "home buyers", "buying a home", "buy a home", "first home", "home purchase",
                  "home purchases", "ITP", "property transfer tax", "stamp duty", "notary fees"],
     "categories": ["property", "housing", "economy", "taxes"],
     "anchors": ["Property buying cost calculator: ITP, IVA and fees by region",
                 "what buying a home in Spain really costs",
                 "estimate taxes and fees on a home purchase"]},
    {"url": "/calculators/net-salary",
     "keywords": ["minimum wage", "SMI", "salary", "salaries", "wage", "wages", "net pay", "take-home pay",
                  "payslip", "payslips", "IRPF", "income tax", "pay rise", "pay rises", "gross salary"],
     "categories": ["work", "taxes", "economy"],
     "anchors": ["Spain net salary calculator: take-home pay after IRPF",
                 "work out your net salary in Spain",
                 "what a gross salary means after tax"]},
]


def attach_tools(digests, tools=STORY_TOOLS, per_digest=3, amount_pages=None):
    """Attach a 'Calculator' link to stories whose topic a calculator covers.

    Matching works like attach_guides (whole-word keywords, optional
    category filter, most distinct hits wins). Within one edition each
    calculator is linked at most once and at most `per_digest` stories get
    a link, in story order. Others get None.

    With `amount_pages` (see story_amount_pages), a story that quotes a
    euro amount in the right context links to the closest programmatic
    amount page (e.g. /calculators/net-salary-1200-euros-per-month)
    instead of the generic calculator.
    """
    patterns = _keyword_patterns(tools, "keywords", "categories")
    for digest in digests:
        used = set()
        for item in digest.get("stories", []):
            item["tool"] = None
            if len(used) >= per_digest:
                continue
            tool = next((t for t in _best_matches(item, patterns) if t["url"] not in used), None)
            if not tool:
                continue
            used.add(tool["url"])
            text = f"{item.get('title', '')} {item.get('body', '')}"
            amount_link = _amount_page_link(text, (amount_pages or {}).get(tool["url"]))
            if amount_link:
                item["tool"] = {**amount_link, "base": tool["url"]}
                continue
            anchors = tool["anchors"]
            n = int(hashlib.md5(f"{digest.get('date', '')}{tool['url']}".encode()).hexdigest(), 16)
            item["tool"] = {"url": tool["url"], "anchor": anchors[n % len(anchors)]}


# Euro amounts as written in digests: "€1,184", "€ 30,000", "16,576 euros".
# Millions/billions and "k" shorthands are skipped.
_EURO_AMOUNT_RE = re.compile(
    r"(?:€\s?(\d{1,3}(?:,\d{3})+|\d+)(?![\d,])(?:\.\d+)?(?![\d.])(?!\s?(?:bn|billion|million|mn|m\b|k\b))"
    r"|\b(\d{1,3}(?:,\d{3})+|\d+)(?![\d,])(?:\.\d+)?\s?euros?\b)",
    re.I,
)
_SALARY_CTX = r"\b(?:salary|salaries|wage|wages|SMI|earn|earns|earning|earnings|gross|paid|payslip|pay)\b"
_AUTONOMO_CTX = r"\b(?:revenue|turnover|invoic\w*|bill(?:s|ing)?|earn|earns|earning|earnings|income|take[- ]home)\b"
_PROPERTY_CTX = r"\b(?:flat|flats|home|homes|house|houses|property|properties|apartment|apartments|price|prices|costs?)\b"


def story_amount_pages(ns=None, au=None, ry=None):
    """Amount-page groups per calculator URL, for attach_tools.

    Each group: amounts with programmatic pages, the range of quoted
    amounts it accepts, a context regex that must appear near the amount,
    and how to build the URL and anchor text.
    """
    ns = ns or load_net_salary_pages()
    au = au or load_autonomo_pages()
    ry = ry or load_rental_yield_pages()
    calc = "/calculators/"
    return {
        "/calculators/net-salary": [
            {"amounts": ns["monthly"], "range": (600, 8000), "context": _SALARY_CTX,
             "url": lambda a: calc + net_salary_slug("monthly", a),
             "anchor": _amount_anchor("take-home pay on {amount} gross a month")},
            {"amounts": ns["annual"], "range": (9000, 150000), "context": _SALARY_CTX,
             "url": lambda a: calc + net_salary_slug("annual", a),
             "anchor": _amount_anchor("net pay on a {amount} gross salary in Spain")},
        ],
        "/calculators/autonomo-tax": [
            {"amounts": au["monthly"], "range": (800, 6000), "context": _AUTONOMO_CTX,
             "url": lambda a: calc + autonomo_slug("monthly", a),
             "anchor": _amount_anchor("what an autónomo must bill to take home {amount} a month")},
            {"amounts": au["revenue"], "range": (10000, 120000), "context": _AUTONOMO_CTX,
             "url": lambda a: calc + autonomo_slug("revenue", a),
             "anchor": _amount_anchor("autónomo net pay on {amount} a year")},
        ],
        "/calculators/rental-yield": [
            {"amounts": ry["prices"], "range": (90000, 1100000), "context": _PROPERTY_CTX,
             "url": lambda a: calc + rental_yield_slug(a),
             "anchor": _amount_anchor("rental yield on a {amount} property in Spain")},
        ],
    }


def _amount_anchor(key):
    """Amount-page anchor in `lang`: the English text is the ES_STRINGS key."""
    return lambda a, lang="en": tr(lang, key, amount=eur(a, lang))


def _amount_page_link(text, groups, tolerance=0.1, window=70, lang="en"):
    """Link to the amount page closest (within `tolerance`) to the first
    euro amount in `text` that falls in a group's range and has that
    group's context words within `window` characters. None otherwise.
    `lang` only picks the anchor's language (matching reads English text)."""
    if not groups:
        return None
    for m in _EURO_AMOUNT_RE.finditer(text):
        value = int((m.group(1) or m.group(2)).replace(",", ""))
        near = text[max(0, m.start() - window):m.end() + window]
        for g in groups:
            lo, hi = g["range"]
            if not lo <= value <= hi or not re.search(g["context"], near, re.I):
                continue
            best = min(g["amounts"], key=lambda a: abs(a - value))
            if abs(best - value) <= tolerance * value:
                return {"url": g["url"](best), "anchor": g["anchor"](best, lang)}
    return None


def attach_twin_links(es_digests, en_digests, es_articles, amount_pages=None):
    """Story lines of Spanish digests from their English twin stories.

    Stories pair by a shared source URL (their stable identity across
    languages). 'Calculadora:' lines copy the twin's calculator with a
    Spanish anchor: STORY_TOOLS keywords and the amount regexes read
    English text. 'Guía:' lines keep the Spanish keyword match
    (attach_guides) and fall back to the twin's guide, with the Spanish
    article title. digest.html localizes the URLs to the /es/ twins.
    Run after attach_guides/attach_tools on both languages."""
    es_by_path = articles_by_path(es_articles)
    by_date = {d["date"]: d for d in en_digests}
    for digest in es_digests:
        en = by_date.get(digest["date"]) or {}
        by_source = {s["url"]: item for item in en.get("stories", [])
                     for s in item.get("sources") or [] if s.get("url")}
        for item in digest.get("stories", []):
            twin = next((by_source[s["url"]] for s in item.get("sources") or []
                         if s.get("url") in by_source), None)
            guide = twin and twin.get("guide")
            if not item.get("guide") and guide and guide["url"] in es_by_path:
                item["guide"] = {"title": es_by_path[guide["url"]]["title"], "url": guide["url"]}
            tool = twin and twin.get("tool")
            if not tool:
                item["tool"] = None
            elif tool.get("base"):
                text = f"{twin.get('title', '')} {twin.get('body', '')}"
                link = _amount_page_link(text, (amount_pages or {}).get(tool["base"]), lang="es")
                item["tool"] = {**link, "base": tool["base"]}
            else:
                item["tool"] = {"url": tool["url"], "anchor": tr("es", tool["anchor"])}


ES_STRINGS.update({
    # STORY_TOOLS anchors ("Calculadora:" lines in Spanish digests)
    "Autónomo tax calculator: your quota and IRPF": "Calculadora de impuestos de autónomos: tu cuota y el IRPF",
    "work out what you'd pay as an autónomo": "calcula lo que pagarías como autónomo",
    "self-employed in Spain: estimate your net income": "autónomo en España: estima tus ingresos netos",
    "Electricity bill calculator: PVPC vs fixed tariffs": "Calculadora de la factura de la luz: PVPC frente a tarifa fija",
    "check what your electricity bill should be": "comprueba cuánto debería costar tu factura de la luz",
    "compare your power bill with the PVPC": "compara tu factura de la luz con el PVPC",
    "Rental yield calculator: net yield after tax": "Calculadora de rentabilidad del alquiler: rentabilidad neta tras impuestos",
    "does a rental flat in Spain pay off?": "¿sale a cuenta un piso de alquiler en España?",
    "work out net rental yield and cash flow": "calcula la rentabilidad neta y el flujo de caja de un alquiler",
    "Property buying cost calculator: ITP, IVA and fees by region":
        "Calculadora de gastos de compra de vivienda: ITP, IVA y gastos por comunidad",
    "what buying a home in Spain really costs": "lo que cuesta de verdad comprar una vivienda en España",
    "estimate taxes and fees on a home purchase": "estima los impuestos y gastos de comprar una vivienda",
    "Spain net salary calculator: take-home pay after IRPF": "Calculadora de sueldo neto: lo que cobras tras el IRPF",
    "work out your net salary in Spain": "calcula tu sueldo neto en España",
    "what a gross salary means after tax": "cuánto queda de un sueldo bruto tras impuestos",
    # story_amount_pages anchors
    "take-home pay on {amount} gross a month": "sueldo neto con {amount} brutos al mes",
    "net pay on a {amount} gross salary in Spain": "sueldo neto con {amount} brutos al año en España",
    "what an autónomo must bill to take home {amount} a month":
        "cuánto debe facturar un autónomo para ganar {amount} netos al mes",
    "autónomo net pay on {amount} a year": "ingresos netos de un autónomo que factura {amount} al año",
    "rental yield on a {amount} property in Spain": "rentabilidad del alquiler de una vivienda de {amount} en España",
})


# Calculator cards for the "Tools and guides" blocks on digests and
# category pages (same copy as the homepage cards).
CALCULATOR_CARDS = {
    "/calculators/net-salary": ("Net Salary Calculator", "Your payslip after IRPF and Social Security, and the Renta refund."),
    "/calculators/autonomo-tax": ("Autónomo Tax Calculator", "Social security quota and IRPF for the self-employed."),
    "/calculators/property-buying-cost": ("Property Buying Cost Calculator", "ITP, IVA/IGIC, AJD, notary and registry fees by region."),
    "/calculators/rental-yield": ("Rental Yield Calculator", "Net yield, cash flow and IRR with resident and non-resident taxes."),
    "/calculators/electricity-bill": ("Electricity Bill Calculator", "PVPC and tariff comparison for your monthly bill."),
}

# Calculators and guides that fit each story category, best first.
CATEGORY_HUBS = {
    "property": ["/calculators/property-buying-cost", "/articles/spain-property-guide", "/calculators/rental-yield"],
    "housing": ["/articles/spain-property-guide", "/calculators/rental-yield", "/calculators/property-buying-cost"],
    "work": ["/calculators/net-salary", "/calculators/autonomo-tax", "/articles/autonomo-taxes-spain"],
    "taxes": ["/calculators/net-salary", "/calculators/autonomo-tax", "/articles/autonomo-taxes-spain"],
    "economy": ["/calculators/net-salary", "/calculators/electricity-bill", "/articles/switching-electricity-provider-spain"],
    "politics": ["/articles/how-spain-is-governed", "/articles/how-spain-votes"],
    "visa": ["/calculators/autonomo-tax", "/articles/autonomo-taxes-spain", "/calculators/net-salary"],
    "migration": ["/calculators/net-salary", "/calculators/autonomo-tax", "/articles/autonomo-taxes-spain"],
}


def hub_card(url, articles_by_url, lang="en"):
    """Card dict for a calculator or article URL, or None if unknown.

    `kind` stays English (it is also a CSS class); templates translate it."""
    if url in CALCULATOR_CARDS:
        title, desc = CALCULATOR_CARDS[url]
        return {"url": localize(lang, url), "title": tr(lang, title), "desc": tr(lang, desc), "kind": "Calculator"}
    a = articles_by_url.get(url)
    if a:
        return {"url": localize(lang, url), "title": a["title"],
                "desc": tr(lang, "A {n}-minute read", n=a["reading_time"]), "kind": "Guide"}
    return None


def articles_by_path(articles):
    """Articles keyed by English path (/articles/<slug>), as hub_card expects.

    Spanish article dicts carry the English path in `path`; their cards get
    the Spanish title and localize() links the /es/ twin."""
    return {a.get("path", a["url"]): a for a in articles}


def category_hub_cards(slug, articles_by_url, lang="en"):
    return [c for c in (hub_card(u, articles_by_url, lang) for u in CATEGORY_HUBS.get(slug, [])) if c]


def article_hub_cards(article, articles_by_url, limit=3, lang="en"):
    """Calculator/guide cards for the end of an article.

    Uses the article's `related` URLs when set, else CATEGORY_HUBS for its
    story_categories in order. The article itself and unknown URLs are skipped.
    `articles_by_url` is keyed by English path (articles_by_path).
    """
    urls = article.get("related") or [u for cat in article.get("story_categories", [])
                                      for u in CATEGORY_HUBS.get(cat, [])]
    cards = []
    for url in dict.fromkeys(urls):
        if url == article.get("path", article["url"]):
            continue
        card = hub_card(url, articles_by_url, lang)
        if card:
            cards.append(card)
        if len(cards) >= limit:
            break
    return cards


def attach_digest_hubs(digests, articles, limit=3, lang="en"):
    """Pick up to `limit` calculator/guide cards for the end of each edition.

    Candidates come from CATEGORY_HUBS for the edition's categories, most
    frequent category first. Pages already linked from a story line
    (guide or tool) are skipped so the block adds new link targets.
    """
    by_url = articles_by_path(articles)
    for digest in digests:
        stories = digest.get("stories", [])
        linked = set()
        for item in stories:
            if item.get("guide"):
                linked.add(item["guide"]["url"])
            if item.get("tool"):
                # Amount pages count as their base calculator.
                linked.add(item["tool"].get("base") or item["tool"]["url"])
        counts = Counter((s.get("category") or "").lower() for s in stories)
        cards = []
        for cat, _ in counts.most_common():
            for url in CATEGORY_HUBS.get(cat, []):
                if len(cards) >= limit:
                    break
                if url in linked or any(c["url"] == localize(lang, url) for c in cards):
                    continue
                card = hub_card(url, by_url, lang)
                if card:
                    cards.append(card)
        digest["hub_cards"] = cards


def share_links(abs_url, text, long_text=None):
    """Build static share URLs (no JS SDKs) for X/TG/WA/FB/Threads + copy link.

    X keeps the short text (280-char limit); Telegram/WhatsApp/Threads get
    long_text when provided (falls back to text). Facebook ``quote``
    carries long_text — FB scrapes OG tags by default, but ``quote``
    sometimes surfaces as pre-filled text for manual posting."""
    u, t = quote(abs_url, safe=""), quote(text, safe="")
    tl = quote(long_text or text, safe="")
    return {
        "url": abs_url,
        "x": f"https://x.com/intent/tweet?text={t}&url={u}",
        "facebook": f"https://www.facebook.com/sharer/sharer.php?u={u}&quote={tl}",
        "telegram": f"https://t.me/share/url?url={u}&text={tl}",
        "whatsapp": f"https://wa.me/?text={tl}%20{u}",
        "threads": f"https://www.threads.com/intent/post?text={tl}&url={u}",
    }


def attach_share(digests):
    """Attach page-level + per-story share links (absolute URLs)."""
    for digest in digests:
        lang = digest.get("lang", "en")
        page_url = f"{SITE_URL}{digest['url']}"
        digest["share"] = share_links(
            page_url, tr(lang, "{headline} — Spain Daily Digest", headline=digest["headline"]))
        for pos, item in enumerate(digest.get("stories", []), start=1):
            abs_url = f"{page_url}#news-{pos}"
            item["share"] = share_links(
                abs_url, tr(lang, "{title} — via Spanified", title=item.get("title", "")))


def digest_podcast_context(ep):
    """Player data for digest.html; None when the day has no episode."""
    if not ep:
        return None
    date = ep["date"]
    duration = int(ep["duration"])
    m, sec = divmod(duration, 60)
    return {
        "audio_url": f"{PODCAST_MEDIA_URL}/episodes/{date}.mp3",
        "title": ep["title"],
        "duration": duration,
        "minutes": max(1, round(duration / 60)),
        "iso_duration": f"PT{m}M{sec}S",
        "chapters": [{"start": round(float(c["startTime"]), 3), "title": c["title"],
                      "label": f"{int(c['startTime']) // 60}:{int(c['startTime']) % 60:02d}"}
                     for c in ep.get("chapters", [])],
    }


def lang_out_dir(lang, *parts):
    """Output directory for a page section: <out>/<parts> or <out>/es/<parts>."""
    return os.path.join(OUT_DIR, *(("es",) if lang == "es" else ()), *parts)


def es_alt_path(path):
    """`alt_path` for partials/hreflang.html: the English path when it has a
    Spanish twin (ES_PATHS), else None (no hreflang)."""
    return path if path in ES_PATHS else None


def register_es_paths(es_digests, en_categories=None, es_articles=(), en_articles=()):
    """Add the Spanish digests, archive pages, categories and articles to ES_PATHS.

    Call before rendering: English pages need it for hreflang, Spanish pages
    for their links. Spanish digests are expected to have an English twin
    (same date); categories and articles only count when English has them too.
    """
    en_article_paths = {a["path"] for a in en_articles}
    es_article_paths = [a["path"] for a in es_articles if a["path"] in en_article_paths]
    ES_PATHS.update(es_article_paths)
    if es_article_paths:
        pages = (len(es_article_paths) + ARTICLES_PAGE_SIZE - 1) // ARTICLES_PAGE_SIZE
        ES_PATHS.update(articles_url(p) for p in range(1, pages + 1))

    ES_PATHS.update(f"/archive/{d['date']}" for d in es_digests)
    if es_digests:
        total_pages = (len(es_digests) + PAGE_SIZE - 1) // PAGE_SIZE
        ES_PATHS.update(archive_url(p) for p in range(1, total_pages + 1))
    es_cats = set(collect_categories(es_digests))
    if en_categories is not None:
        es_cats &= set(en_categories)
    ES_PATHS.update(f"/category/{slug}" for slug in es_cats)


def render_digests(env, digests, episodes_by_date=None, lang="en"):
    episodes_by_date = episodes_by_date or {}
    out_dir = ARCHIVE_DIR if lang == "en" else lang_out_dir(lang, "archive")
    os.makedirs(out_dir, exist_ok=True)
    # Clear previously generated HTML inside archive/ so removed digests don't linger.
    for filename in os.listdir(out_dir):
        if filename.endswith(".html"):
            os.remove(os.path.join(out_dir, filename))

    template = env.get_template("digest.html")
    rel_dir = lang_path(lang, "/archive")[1:]
    for i, digest in enumerate(digests):
        crumbs = [
            {"name": tr(lang, "Home"), "url": localize(lang, "/")},
            {"name": tr(lang, "Archive"), "url": localize(lang, "/archive/")},
            {"name": digest["date_display"], "url": digest["url"], "current": True},
        ]
        # digests is newest-first: i-1 is the newer day, i+1 the older day.
        older = digests[i + 1] if i + 1 < len(digests) else None
        newer = digests[i - 1] if i > 0 else None
        day_nav = {
            "older": {"url": older["url"], "date_display": older["date_display"]} if older else None,
            "newer": {"url": newer["url"], "date_display": newer["date_display"]} if newer else None,
        }
        # The podcast is English audio: Spanish pages leave the player out.
        podcast = digest_podcast_context(episodes_by_date.get(digest["date"])) if lang == "en" else None
        output = template.render(digest=digest, emoji=CATEGORY_EMOJI, crumbs=crumbs, day_nav=day_nav,
                                 podcast=podcast, js_version=js_version(), page_lang=lang,
                                 alt_path=es_alt_path(f"/archive/{digest['date']}"))
        dest = os.path.join(out_dir, f"{digest['date']}.html")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"  wrote {rel_dir}/{digest['date']}.html")


def render_archive(env, digests, lang="en"):
    total = len(digests)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE) if total else 1
    template = env.get_template("archive.html")
    out_dir = ARCHIVE_DIR if lang == "en" else lang_out_dir(lang, "archive")
    os.makedirs(out_dir, exist_ok=True)
    rel_dir = lang_path(lang, "/archive")[1:]

    for page in range(1, total_pages + 1):
        start = (page - 1) * PAGE_SIZE
        page_digests = digests[start:start + PAGE_SIZE]
        crumbs = [{"name": tr(lang, "Home"), "url": localize(lang, "/")}]
        if page == 1:
            crumbs.append({"name": tr(lang, "Archive"), "url": archive_url(1, lang), "current": True})
        else:
            crumbs.append({"name": tr(lang, "Archive"), "url": archive_url(1, lang)})
            crumbs.append({"name": tr(lang, "Page {n}", n=page), "url": archive_url(page, lang), "current": True})
        output = template.render(digests=page_digests, pagination=pagination(page, total_pages, lang), crumbs=crumbs,
                                 page_lang=lang, canonical_path=archive_url(page, lang),
                                 alt_path=es_alt_path(archive_url(page)))
        name = "index.html" if page == 1 else f"{page}.html"
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"  wrote {rel_dir}/{name}")


def render_articles_list(env, articles, lang="en"):
    total = len(articles)
    total_pages = max(1, (total + ARTICLES_PAGE_SIZE - 1) // ARTICLES_PAGE_SIZE) if total else 1
    template = env.get_template("articles.html")
    out_dir = ARTICLES_DIR if lang == "en" else lang_out_dir(lang, "articles")
    rel_dir = lang_path(lang, "/articles")[1:]
    os.makedirs(out_dir, exist_ok=True)
    # Clear previously generated listing pages so removed articles don't linger.
    for filename in os.listdir(out_dir):
        dest = os.path.join(out_dir, filename)
        if not os.path.isfile(dest):
            continue
        if filename == "index.html" or (filename[:-5].isdigit() and filename.endswith(".html")):
            os.remove(dest)

    for page in range(1, total_pages + 1):
        start = (page - 1) * ARTICLES_PAGE_SIZE
        page_articles = articles[start:start + ARTICLES_PAGE_SIZE]
        crumbs = [{"name": tr(lang, "Home"), "url": localize(lang, "/")}]
        if page == 1:
            crumbs.append({"name": tr(lang, "Articles"), "url": lang_path(lang, "/articles/"), "current": True})
        else:
            crumbs.append({"name": tr(lang, "Articles"), "url": lang_path(lang, "/articles/")})
            crumbs.append({"name": tr(lang, "Page {n}", n=page), "url": lang_path(lang, f"/articles/{page}"), "current": True})
        output = template.render(articles=page_articles, pagination=articles_pagination(page, total_pages, lang),
                                 crumbs=crumbs, page_lang=lang, canonical_path=lang_path(lang, articles_url(page)),
                                 alt_path=es_alt_path(articles_url(page)))
        name = "index.html" if page == 1 else f"{page}.html"
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"  wrote {rel_dir}/{name}")


def render_article_pages(env, articles, lang="en"):
    """Render /articles/<slug> (or /es/articles/<slug> from load_articles("es")).

    Spanish pages localize every internal link in the body and FAQ."""
    out_dir = ARTICLES_DIR if lang == "en" else lang_out_dir(lang, "articles")
    rel_dir = lang_path(lang, "/articles")[1:]
    os.makedirs(out_dir, exist_ok=True)
    # Clear previously generated article pages (slug files), keep listing files.
    for filename in os.listdir(out_dir):
        dest = os.path.join(out_dir, filename)
        if not os.path.isfile(dest) or not filename.endswith(".html"):
            continue
        if filename == "index.html" or filename[:-5].isdigit():
            continue
        os.remove(dest)

    template = env.get_template("article.html")
    by_path = articles_by_path(articles)
    for article in articles:
        crumbs = [
            {"name": tr(lang, "Home"), "url": localize(lang, "/")},
            {"name": tr(lang, "Articles"), "url": lang_path(lang, "/articles/")},
            {"name": article["title"], "url": article["url"], "current": True},
        ]
        if lang != "en":
            article = dict(article, body_html=localize_links(lang, article["body_html"]),
                           faq=[dict(f, a_html=localize_links(lang, f["a_html"])) for f in article["faq"]])
        output = template.render(article=article, crumbs=crumbs, js_version=js_version(),
                                 hub_cards=article_hub_cards(article, by_path, lang=lang),
                                 page_lang=lang, alt_path=es_alt_path(article["path"]))
        dest = os.path.join(out_dir, f"{article['slug']}.html")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"  wrote {rel_dir}/{article['slug']}.html")


def collect_categories(digests):
    """Group all stories by category slug (newest digest first)."""
    cats = {}
    for digest in digests:
        for item in digest.get("stories", []):
            slug = (item.get("category") or "news").lower()
            cats.setdefault(slug, []).append({**item, "date": digest["date"], "date_display": digest["date_display"]})
    return cats


def render_categories(env, digests, articles=(), lang="en"):
    """Render /category/<slug> (or /es/category/<slug>); returns the slugs.

    Spanish categories are rendered only when registered in ES_PATHS (an
    English twin exists)."""
    cats = collect_categories(digests)
    if lang == "es":
        cats = {slug: v for slug, v in cats.items() if f"/category/{slug}" in ES_PATHS}
    articles_by_url = articles_by_path(articles)
    cat_dir = lang_out_dir(lang, "category")
    os.makedirs(cat_dir, exist_ok=True)
    # Clear previously generated pages so removed categories don't linger.
    for filename in os.listdir(cat_dir):
        if filename.endswith(".html"):
            os.remove(os.path.join(cat_dir, filename))

    template = env.get_template("category.html")
    meta = CATEGORY_META_ES if lang == "es" else CATEGORY_META
    descriptions = CATEGORY_DESCRIPTIONS_ES if lang == "es" else CATEGORY_DESCRIPTIONS
    rel_dir = lang_path(lang, "/category")[1:]
    for slug, stories in sorted(cats.items()):
        name = category_name(slug, lang)
        path = f"/category/{slug}"
        crumbs = [
            {"name": tr(lang, "Home"), "url": localize(lang, "/")},
            {"name": name, "url": lang_path(lang, path), "current": True},
        ]
        meta_title, meta_desc = meta.get(slug, (tr(lang, "{name} News in Spain, in English — Spanified", name=name), ""))
        output = template.render(
            category_name=name,
            slug=slug,
            emoji=CATEGORY_EMOJI.get(slug, "\U0001F4F0"),
            category_description=descriptions.get(slug, ""),
            meta_title=meta_title,
            meta_description=meta_desc,
            stories=stories,
            hub_cards=category_hub_cards(slug, articles_by_url, lang),
            crumbs=crumbs,
            page_lang=lang,
            canonical_path=lang_path(lang, path),
            alt_path=es_alt_path(path),
        )
        dest = os.path.join(cat_dir, f"{slug}.html")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"  wrote {rel_dir}/{slug}.html ({len(stories)} stories)")
    return sorted(cats.keys())



# Source files (git pathspecs, repo-relative) behind each calculator page.
# Their newest commit date becomes the page's sitemap lastmod.
CALC_SOURCES = {
    "net-salary": ["templates/calculator-net-salary.html", "static/js/net-salary*.js", "data/videos.json"],
    "autonomo-tax": ["templates/calculator-autonomo.html", "static/js/autonomo*.js", "data/videos.json"],
    "property-buying-cost": ["templates/calculator-property-buying-cost.html", "static/js/property-buying-cost*.js"],
    "rental-yield": ["templates/calculator-rental-yield.html", "static/js/rental-yield*.js"],
    "electricity-bill": ["templates/calculator-electricity.html", "static/js/electricity*.js"],
}
# Amount pages also depend on their own template, page list and grid script.
CALC_AMOUNT_SOURCES = {
    "net-salary": ["templates/calculator-net-salary-amount.html", "data/net-salary-pages.json",
                   "scripts/net-salary-grid.mjs", "data/videos.json"],
    "autonomo-tax": ["templates/calculator-autonomo-amount.html", "data/autonomo-pages.json",
                     "scripts/autonomo-grid.mjs", "data/videos.json"],
    "rental-yield": ["templates/calculator-rental-yield-amount.html", "data/rental-yield-pages.json",
                     "scripts/rental-yield-grid.mjs"],
}

_git_lastmod_cache = {}


def git_lastmod(*pathspecs):
    """Date (YYYY-MM-DD) of the newest commit touching any of the pathspecs, or None
    when git or history is unavailable. CI must check out full history (fetch-depth: 0)."""
    import subprocess

    key = tuple(pathspecs)
    if key not in _git_lastmod_cache:
        try:
            res = subprocess.run(
                ["git", "log", "-1", "--format=%cs", "--", *pathspecs],
                check=True, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", cwd=SCRIPT_DIR,
            )
            _git_lastmod_cache[key] = res.stdout.strip() or None
        except (OSError, subprocess.CalledProcessError):
            _git_lastmod_cache[key] = None
    return _git_lastmod_cache[key]


def article_lastmod(article):
    """Newest of the article's publication date and its source file's last commit."""
    dates = [d for d in (article.get("date"), article.get("updated"), article.get("src_path") and git_lastmod(article["src_path"])) if d]
    return max(dates) if dates else None


def calc_lastmod(calc, amount_page=False):
    paths = CALC_SOURCES[calc] + (CALC_AMOUNT_SOURCES[calc] if amount_page else [])
    return git_lastmod(*paths)


def sitemap_hreflang(url):
    """xhtml:link alternates for an English page and its /es/ twin.

    Both URLs of a pair carry the same three links (en, es, x-default = en),
    matching partials/hreflang.html in the pages' <head>.
    """
    path = url[len(SITE_URL):]
    base = path[len("/es"):] if path.startswith("/es/") else path
    if base not in ES_PATHS:
        return ""
    links = (("en", SITE_URL + base), ("es", SITE_URL + "/es" + base), ("x-default", SITE_URL + base))
    return "".join(f'<xhtml:link rel="alternate" hreflang="{lang}" href="{href}"/>' for lang, href in links)


def digest_sitemap_urls(digests, lang="en"):
    """(url, lastmod) for the archive listing pages and every digest."""
    latest = digests[0]["date"] if digests else None
    total = len(digests)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total else 1
    urls = [(SITE_URL + archive_url(1, lang), latest)]
    for page in range(2, total_pages + 1):
        page_digests = digests[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]
        urls.append((SITE_URL + archive_url(page, lang), page_digests[0]["date"] if page_digests else None))
    for digest in digests:
        urls.append((SITE_URL + lang_path(lang, f"/archive/{digest['date']}"), digest["date"]))
    return urls


def article_sitemap_urls(articles, lang="en"):
    """(url, lastmod) for the articles listing (page 1 plus extra pages) and every article."""
    if lang != "en" and not articles:
        return []
    total = len(articles)
    total_pages = (total + ARTICLES_PAGE_SIZE - 1) // ARTICLES_PAGE_SIZE if total else 1
    urls = [(SITE_URL + lang_path(lang, "/articles/"), articles[0]["date"] if articles else None)]
    for page in range(2, total_pages + 1):
        urls.append((SITE_URL + lang_path(lang, f"/articles/{page}"), None))
    for article in articles:
        urls.append((SITE_URL + article["url"], article_lastmod(article)))
    return urls


def render_sitemap(
digests, categories=(), articles=(), salary_pages=(), autonomo_pages=(), rental_yield_pages=(), category_lastmod=None,
                   es_digests=(), es_categories=(), es_category_lastmod=None, es_articles=()):
    # lastmod only where it is real: the newest digest drives the home page,
    # archive and category pages; articles and calculators use the last git
    # commit of their sources. Static pages get none rather than a misleading
    # build date.
    latest = digests[0]["date"] if digests else None
    category_lastmod = category_lastmod or {}
    es_category_lastmod = es_category_lastmod or {}
    urls = [(SITE_URL + "/", latest)] + [
        (SITE_URL + "/" + name[:-len(".html")], None)
        for name in STATIC_PAGES
        if name.endswith(".html") and name != "index.html" and name not in NOINDEX_PAGES
    ]
    # Archive listing (page 1) plus extra pages, then every digest.
    urls.extend(digest_sitemap_urls(digests))
    urls.extend(article_sitemap_urls(articles))
    for slug in categories:
        urls.append((SITE_URL + f"/category/{slug}", category_lastmod.get(slug)))
    calc_urls = [("/calculators/net-salary", calc_lastmod("net-salary"))]
    calc_urls += [(path, calc_lastmod("net-salary", amount_page=True)) for path in salary_pages]
    calc_urls.append(("/calculators/autonomo-tax", calc_lastmod("autonomo-tax")))
    calc_urls += [(path, calc_lastmod("autonomo-tax", amount_page=True)) for path in autonomo_pages]
    calc_urls.append(("/calculators/property-buying-cost", calc_lastmod("property-buying-cost")))
    calc_urls.append(("/calculators/rental-yield", calc_lastmod("rental-yield")))
    calc_urls += [(path, calc_lastmod("rental-yield", amount_page=True)) for path in rental_yield_pages]
    calc_urls.append(("/calculators/electricity-bill", calc_lastmod("electricity-bill")))
    urls.extend((SITE_URL + path, lastmod) for path, lastmod in calc_urls)
    # Only the canonical quiz landing page is indexable (quiz.html ships
    # index,follow). The -success / -subscribed / -result-* variants stay
    # noindex,nofollow and must never enter the sitemap.
    urls.append((SITE_URL + "/quiz/ai-or-real", None))
    urls.append((SITE_URL + "/quiz/spanish-law-or-myth", None))
    # Spanish twins (/es/<page>) of indexable English pages.
    urls.append((SITE_URL + "/es/", es_digests[0]["date"] if es_digests else None))
    urls.extend((SITE_URL + "/es/" + name[:-len(".html")], None) for name in ES_PAGES if name in ES_INDEXED_PAGES)
    urls.extend(digest_sitemap_urls(es_digests, "es"))
    urls.extend(article_sitemap_urls(es_articles, "es"))
    for slug in es_categories:
        urls.append((SITE_URL + f"/es/category/{slug}", es_category_lastmod.get(slug)))
    # Spanish calculators share their English twin's lastmod (same sources).
    urls.extend((SITE_URL + "/es" + path, lastmod) for path, lastmod in calc_urls if path in ES_PATHS)
    urls.extend((SITE_URL + "/es" + path, None) for path in es_quiz_paths())

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
                 'xmlns:xhtml="http://www.w3.org/1999/xhtml">')
    for url, lastmod in urls:
        tag = f"<loc>{url}</loc>"
        if lastmod:
            tag += f"<lastmod>{lastmod}</lastmod>"
        tag += sitemap_hreflang(url)
        lines.append(f"  <url>{tag}</url>")
    lines.append("</urlset>")

    dest = os.path.join(OUT_DIR, "sitemap.xml")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"  wrote sitemap.xml ({len(urls)} urls)")


PODCAST_SRC_DIR = os.path.join(SCRIPT_DIR, "data", "podcast")
# MP3s live in Cloudflare R2 (bucket spanified-podcast), never in git.
PODCAST_MEDIA_URL = "https://media.spanified.com"
PODCAST_TITLE = "Spain Daily — Daily News Digest from Spain in English"
PODCAST_SUMMARY = (
    "Spain news in English, every day in a few minutes. A daily briefing for "
    "English speakers in Spain: immigrants and residents, Spaniards who "
    "follow the news in English, and foreigners with a holiday home here. "
    "New laws, taxes, housing and rent, visas and residency, NIE and "
    "paperwork, work, prices and travel, and what each change means for you."
)
PODCAST_OWNER_EMAIL = "support@spanified.com"
# Podcasting 2.0 GUID: uuidv5(podcast namespace, "spanified.com/podcast.xml").
# Must never change once the feed is submitted.
PODCAST_GUID = "b96af1a0-4554-50df-9ac5-f4542bce76ee"


def load_podcast_episodes():
    """data/podcast/YYYY-MM-DD.json, newest first (written by podcast_publish.py)."""
    if not os.path.isdir(PODCAST_SRC_DIR):
        return []
    episodes = []
    for name in sorted(os.listdir(PODCAST_SRC_DIR), reverse=True):
        if re.match(r"^\d{4}-\d{2}-\d{2}\.json$", name):
            with open(os.path.join(PODCAST_SRC_DIR, name), encoding="utf-8") as fh:
                episodes.append(json.load(fh))
    return episodes


def _rfc2822(date_str):
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(
        hour=8, tzinfo=ZoneInfo("Europe/Madrid"))
    return format_datetime(dt)


def _hms(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def podcast_episode_title(episode, number):
    """"#<n> <title> | Spain Daily News | <d Mon YYYY>"; any leading date in the stored title is dropped."""
    title = re.sub(r"^\d{4}-\d{2}-\d{2}\s*[:\-–—]\s*", "", episode["title"]).strip()
    dt = datetime.strptime(episode["date"], "%Y-%m-%d")
    return f"#{number} {title} | Spain Daily News | {dt.day} {dt:%b %Y}"


PODCAST_SUPPORT_URL = "https://buymeacoffee.com/spanified"


def podcast_episode_notes(episode, digest_dates=()):
    lines = []
    summary = (episode.get("summary") or "").strip()
    # The support line always goes last, so drop any copy the pipeline put in the summary.
    summary = "\n".join(l for l in summary.splitlines() if PODCAST_SUPPORT_URL not in l).strip()
    if summary:
        lines += [f"🇪🇸 {summary}", ""]
    if episode.get("chapters"):
        lines.append("⏱️ In this episode:")
        for ch in episode["chapters"]:
            lines.append(f"{_hms(ch['startTime'])} {ch['title']}")
        lines.append("")
    if episode["date"] in digest_dates:
        lines.append(f"📰 Read the full digest: {SITE_URL}/archive/{episode['date']}")
    lines.append(f"📬 Subscribe to the newsletter: {SITE_URL}/subscribe")
    lines += ["", f"☕ Enjoying Spain Daily? Support us: {PODCAST_SUPPORT_URL}"]
    return "\n".join(lines)


def _transcript_srt(segments):
    """Podcasting 2.0 JSON transcript segments -> SRT text."""
    def ts(t):
        ms = int(round(float(t) * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    blocks = []
    for i, seg in enumerate(segments, 1):
        text = seg["body"].strip()
        if seg.get("speaker"):
            text = f"{seg['speaker']}: {text}"
        blocks.append(f"{i}\n{ts(seg['startTime'])} --> {ts(seg['endTime'])}\n{text}\n")
    return "\n".join(blocks)


def render_podcast_feed(episodes, digest_dates=()):
    """podcast.xml (RSS 2.0 + itunes + podcast namespaces) and
    podcast/chapters/<date>.json for Apple / Spotify / YouTube."""
    esc = lambda s: html.escape(str(s), quote=True)
    cover = f"{SITE_URL}/static/podcast-cover.jpg"
    feed_url = f"{SITE_URL}/podcast.xml"
    chapters_dir = os.path.join(OUT_DIR, "podcast", "chapters")
    os.makedirs(chapters_dir, exist_ok=True)
    transcripts_dir = os.path.join(OUT_DIR, "podcast", "transcripts")
    os.makedirs(transcripts_dir, exist_ok=True)

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"'
        ' xmlns:podcast="https://podcastindex.org/namespace/1.0"'
        ' xmlns:atom="http://www.w3.org/2005/Atom"'
        ' xmlns:content="http://purl.org/rss/1.0/modules/content/">',
        "<channel>",
        f"  <title>{esc(PODCAST_TITLE)}</title>",
        f"  <link>{SITE_URL}/</link>",
        f'  <atom:link href="{feed_url}" rel="self" type="application/rss+xml"/>',
        "  <language>en</language>",
        f"  <description>{esc(PODCAST_SUMMARY)}</description>",
        f"  <copyright>© {datetime.now().year} Spanified</copyright>",
        "  <itunes:author>Spanified</itunes:author>",
        "  <itunes:owner>",
        "    <itunes:name>Spanified</itunes:name>",
        f"    <itunes:email>{PODCAST_OWNER_EMAIL}</itunes:email>",
        "  </itunes:owner>",
        f'  <itunes:image href="{cover}"/>',
        f"  <image><url>{cover}</url><title>{esc(PODCAST_TITLE)}</title><link>{SITE_URL}/</link></image>",
        '  <itunes:category text="News"><itunes:category text="Daily News"/></itunes:category>',
        "  <itunes:explicit>false</itunes:explicit>",
        "  <itunes:type>episodic</itunes:type>",
        f'  <podcast:locked owner="{PODCAST_OWNER_EMAIL}">yes</podcast:locked>',
        f"  <podcast:guid>{PODCAST_GUID}</podcast:guid>",
    ]
    valid = [e for e in episodes if re.match(r"^\d{4}-\d{2}-\d{2}$", e["date"])]
    numbers = {e["date"]: n for n, e in enumerate(sorted(valid, key=lambda e: e["date"]), 1)}
    for ep in episodes:
        date = ep["date"]
        if date not in numbers:
            continue
        notes = podcast_episode_notes(ep, digest_dates)
        audio = f"{PODCAST_MEDIA_URL}/episodes/{date}.mp3"
        link = f"{SITE_URL}/archive/{date}" if date in digest_dates else f"{SITE_URL}/"
        out += [
            "  <item>",
            f"    <title>{esc(podcast_episode_title(ep, numbers[date]))}</title>",
            f"    <itunes:episode>{numbers[date]}</itunes:episode>",
            f'    <guid isPermaLink="false">spanified-podcast-{date}</guid>',
            f"    <link>{link}</link>",
            f"    <pubDate>{_rfc2822(date)}</pubDate>",
            f"    <description>{esc(notes)}</description>",
            f"    <itunes:summary>{esc(notes)}</itunes:summary>",
            f"    <content:encoded>{esc('<p>' + notes.replace(chr(10), '<br>') + '</p>')}</content:encoded>",
            f'    <enclosure url="{audio}" length="{int(ep["length"])}" type="audio/mpeg"/>',
            f"    <itunes:duration>{int(ep['duration'])}</itunes:duration>",
            "    <itunes:author>Spanified</itunes:author>",
            "    <itunes:episodeType>full</itunes:episodeType>",
            "    <itunes:explicit>false</itunes:explicit>",
        ]
        if ep.get("chapters"):
            with open(os.path.join(chapters_dir, f"{date}.json"), "w", encoding="utf-8") as fh:
                json.dump({"version": "1.2.0", "chapters": ep["chapters"]}, fh, ensure_ascii=False)
            out.append(f'    <podcast:chapters url="{SITE_URL}/podcast/chapters/{date}.json"'
                       ' type="application/json+chapters"/>')
        segments = (ep.get("transcript") or {}).get("segments")
        if segments:
            base = f"{SITE_URL}/podcast/transcripts/{date}"
            with open(os.path.join(transcripts_dir, f"{date}.json"), "w", encoding="utf-8") as fh:
                json.dump(ep["transcript"], fh, ensure_ascii=False)
            with open(os.path.join(transcripts_dir, f"{date}.srt"), "w", encoding="utf-8") as fh:
                fh.write(_transcript_srt(segments))
            out += [
                f'    <podcast:transcript url="{base}.srt" type="application/x-subrip" language="en" rel="captions"/>',
                f'    <podcast:transcript url="{base}.json" type="application/json" language="en"/>',
            ]
        out.append("  </item>")
    out += ["</channel>", "</rss>"]

    with open(os.path.join(OUT_DIR, "podcast.xml"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"  wrote podcast.xml ({len(episodes)} episode(s))")


def parse_args():
    parser = argparse.ArgumentParser(description="Build the Spanified static site.")
    parser.add_argument(
        "--out",
        default=SCRIPT_DIR,
        help="Output directory (default: repo root, for local preview). "
        "CI uses --out dist.",
    )
    parser.add_argument(
        "--listmonk",
        default=os.environ.get("LISTMONK_URL", "prod"),
        help="Listmonk backend for the subscribe form: 'prod' (default, "
        "https://newsletter.spanified.com), 'local' (dev instance, "
        "https://listmonk.dslab.fyi), or a custom base URL. "
        "Env LISTMONK_URL overrides the default.",
    )
    parser.add_argument(
        "--list-uuid",
        default=os.environ.get("LISTMONK_LIST_UUID"),
        help="Listmonk list UUID for the subscribe form (default: prod "
        "Spain Daily list, or the dev list with --listmonk local). "
        "Env LISTMONK_LIST_UUID overrides.",
    )
    parser.add_argument(
        "--es-list-uuid",
        default=os.environ.get("LISTMONK_ES_LIST_UUID"),
        help="Listmonk list UUID for Spanish (lang=es) subscribe forms "
        "(default: prod Spanish list, or the dev Spanish list with "
        "--listmonk local). Env LISTMONK_ES_LIST_UUID overrides.",
    )
    parser.add_argument(
        "--analytics",
        choices=("on", "off", "auto"),
        default=_env_analytics(),
        help="Bake GA4 + Meta Pixel into the pages: 'auto' (default) = "
        "enabled only when --out is outside the repo root (CI builds to "
        "dist/), a local build into the repo root gets no analytics; "
        "'on'/'off' force it. Env ANALYTICS overrides the default.",
    )
    return parser.parse_args()


def _env_analytics():
    """Default for --analytics from env ANALYTICS (on/off/auto)."""
    value = (os.environ.get("ANALYTICS") or "auto").strip().lower()
    if value not in ("on", "off", "auto"):
        print(
            f"WARN: ignoring invalid ANALYTICS={value!r} (expected on/off/auto), "
            "using 'auto'",
            file=sys.stderr,
        )
        return "auto"
    return value


def analytics_enabled(args):
    """Whether GA4/Meta Pixel snippets are baked into the rendered pages.

    Explicit --analytics on/off wins; 'auto' enables analytics only for
    builds that output outside the repo root (CI: --out dist) so local
    builds into the repo root never ship tracking code."""
    if args.analytics != "auto":
        return args.analytics == "on"
    return os.path.abspath(args.out) != os.path.abspath(SCRIPT_DIR)


def listmonk_form_action(listmonk):
    """Resolve the --listmonk value to the Listmonk public API route."""
    base = {"prod": LISTMONK_PROD_URL, "local": LISTMONK_LOCAL_URL}.get(
        listmonk, listmonk)
    return base.rstrip("/") + "/api/public/subscription"


def listmonk_list_uuid(args):
    """Resolve the list UUID: explicit --list-uuid wins, otherwise per mode."""
    if args.list_uuid:
        return args.list_uuid
    if args.listmonk == "local":
        return LISTMONK_LOCAL_LIST_UUID
    return LISTMONK_PROD_LIST_UUID


def listmonk_es_list_uuid(args):
    """List UUID for Spanish forms: --es-list-uuid wins, otherwise per mode."""
    if args.es_list_uuid:
        return args.es_list_uuid
    if args.listmonk == "local":
        return LISTMONK_LOCAL_ES_LIST_UUID
    return LISTMONK_PROD_ES_LIST_UUID


def copy_static(out_dir):
    for name in STATIC_COPY:
        src = os.path.join(SCRIPT_DIR, name)
        if not os.path.exists(src):
            print(f"WARN: static asset missing, skipping: {name}", file=sys.stderr)
            continue
        dest = os.path.join(out_dir, name)
        if os.path.exists(dest) and os.path.samefile(src, dest):
            print(f"  kept {name} (build in place)")
            continue
        if os.path.isdir(src):
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            shutil.copy2(src, dest)
        print(f"  copied {name}")


def pub_date(date_str):
    """Full ISO 8601 with Europe/Madrid offset for schema.org datetimes.

    The digest goes out in the morning; DST offset resolves itself
    (+02:00 summer, +01:00 winter). Falls back to the raw string."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(
            hour=8, tzinfo=ZoneInfo("Europe/Madrid")
        ).isoformat()
    except (ValueError, TypeError):
        return date_str


def css_version():
    """Short content hash of main.css for cache-busting (?v=...)."""
    path = os.path.join(SCRIPT_DIR, "static", "css", "main.css")
    try:
        with open(path, "rb") as fh:
            return hashlib.md5(fh.read()).hexdigest()[:8]
    except OSError:
        return "dev"


def js_importmap():
    """Import map giving every static/js module a ?v=<content hash> URL.

    Entry scripts carry ?v={{ js_version }}, but the modules they import
    (`import './autonomo-calc.js'`) do not, so a browser could keep a stale
    module after a deploy. The map rewrites those nested imports per file."""
    js_dir = os.path.join(SCRIPT_DIR, "static", "js")
    imports = {}
    for name in sorted(os.listdir(js_dir)):
        if not name.endswith(".js"):
            continue
        with open(os.path.join(js_dir, name), "rb") as fh:
            digest = hashlib.md5(fh.read()).hexdigest()[:8]
        imports[f"/static/js/{name}"] = f"/static/js/{name}?v={digest}"
    return json.dumps({"imports": imports}, separators=(",", ":"))


def js_version():
    """Short content hash of calculator JS bundle for cache-busting."""
    h = hashlib.md5()
    for name in ("analytics.js",
                   "autonomo.js", "autonomo-calc.js", "autonomo-form.js",
                   "property-buying-cost.js", "property-buying-cost-calc.js",
                   "property-buying-cost-form.js",
                   "rental-yield.js", "rental-yield-calc.js", "rental-yield-form.js",
                   "net-salary.js", "net-salary-calc.js", "net-salary-form.js", "net-salary-data.js",
                   "net-salary-foral.js",
                   "quiz.js",
                   "quiz-logic.js", "subscribe-form.js", "subscription-store.js",
                   "electricity.js", "electricity-calc.js", "electricity-form.js",
                   "video-embed.js", "cookie-consent.js", "cookie-consent-logic.js",
                   "election-explorer.js", "election-filter.js", "election-compare.js",
                   "calc-i18n.js", "tooltips.js", "net-salary-es.js", "autonomo-es.js",
                   "property-buying-cost-es.js", "rental-yield-es.js", "electricity-es.js"):
        path = os.path.join(SCRIPT_DIR, "static", "js", name)
        try:
            with open(path, "rb") as fh:
                h.update(fh.read())
        except OSError:
            pass
    return h.hexdigest()[:8] or "dev"


def main():
    args = parse_args()
    out_dir = os.path.abspath(args.out)
    archive_dir = os.path.join(out_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    # Rebind module-level outputs when building into a custom dir.
    global OUT_DIR, ARCHIVE_DIR, ARTICLES_DIR
    OUT_DIR = out_dir
    ARCHIVE_DIR = archive_dir
    ARTICLES_DIR = os.path.join(out_dir, "articles")

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )
    register_i18n(env)
    env.globals["current_year"] = datetime.now().year
    env.globals["asset_version"] = css_version()
    # Default for templates not handed js_version explicitly (the cookie
    # banner included by base.html is on every page).
    env.globals["js_version"] = js_version()
    env.globals["js_importmap"] = js_importmap()
    env.globals["site_url"] = SITE_URL
    env.globals["listmonk_form_action"] = listmonk_form_action(args.listmonk)
    env.globals["listmonk_list_uuid"] = listmonk_list_uuid(args)
    env.globals["listmonk_es_list_uuid"] = listmonk_es_list_uuid(args)
    # Captcha (Cloudflare Turnstile via Worker) only exists in front of the
    # prod API. Local builds post straight at the dev Listmonk — no Worker,
    # so no widget is rendered and the JS token check is skipped.
    env.globals["turnstile_enabled"] = args.listmonk != "local"
    # Analytics (GA4 + Meta Pixel) are consent-gated: base.html only queues
    # gtag() calls and static/js/cookie-consent.js loads the vendor scripts
    # after opt-in. Local builds into the repo root stay tracking-free (see
    # analytics_enabled()) and load nothing even after "Accept".
    # The same value is exposed to every template as a JS global —
    # window.SPANIFIED_ANALYTICS in templates/base.html — because
    # static/js/*.js are copied verbatim (STATIC_COPY) and never rendered.
    env.globals["analytics_enabled"] = analytics_enabled(args)
    env.globals["pub_date"] = pub_date
    env.globals["video_embed"] = video_embed
    # Organization sameAs: every account of the brand, both editions.
    env.globals["site_socials"] = [url for accounts in SOCIALS.values() for url in accounts.values()]

    digests = dedupe_digest_titles([digest_context(d) for d in load_digests()])
    articles = load_articles()
    # Spanish twins (/es/articles/<slug>): only slugs English has too.
    en_slugs = {a["slug"] for a in articles}
    es_articles = [a for a in load_articles("es") if a["slug"] in en_slugs]
    amount_pages = story_amount_pages()
    attach_guides(digests, articles)
    attach_tools(digests, amount_pages=amount_pages)
    attach_digest_hubs(digests, articles)
    # Spanish twins (/es/archive/<date>): only dates English has too.
    # Guide lines match the Spanish articles' story_keywords and link their
    # /es/ twins (else the English twin story's guide); calculator lines copy
    # the twin's calculator (attach_twin_links) with Spanish anchors.
    en_dates = {d["date"] for d in digests}
    # Meta titles follow the English twin: subject-led only where English has a subject.
    en_subject_dates = {d["date"] for d in digests if d["subject"]}
    es_digests = dedupe_digest_titles([digest_context(d, "es", d["date"] in en_subject_dates)
                                       for d in load_digests(ES_DATA_DIR) if d["date"] in en_dates])
    register_es_paths(es_digests, collect_categories(digests), es_articles, articles)
    register_es_calculator_paths()
    register_es_quiz_paths()
    attach_guides(es_digests, es_articles)
    attach_twin_links(es_digests, digests, es_articles, amount_pages)
    attach_digest_hubs(es_digests, es_articles, lang="es")
    episodes = load_podcast_episodes()

    print("Copying static assets...")
    copy_static(out_dir)

    print("Building static pages...")
    render_static(env, digests, es_digests, es_articles)

    print(f"Building {len(digests)} digest page(s)...")
    attach_related(digests)
    attach_share(digests)
    render_digests(env, digests, {ep["date"]: ep for ep in episodes})
    print(f"Building {len(es_digests)} Spanish digest page(s)...")
    attach_related(es_digests)
    attach_share(es_digests)
    render_digests(env, es_digests, lang="es")

    print("Rendering OG images...")
    from og_images import render_og_images
    render_og_images(digests, articles, out_dir)
    render_og_images(es_digests, es_articles, out_dir, lang="es")

    print("Building archive listing...")
    render_archive(env, digests)
    render_archive(env, es_digests, lang="es")

    print("Building articles...")
    render_articles_list(env, articles)
    render_article_pages(env, articles)
    print(f"Building {len(es_articles)} Spanish article page(s)...")
    render_articles_list(env, es_articles, lang="es")
    render_article_pages(env, es_articles, lang="es")

    print("Building category pages...")
    categories = render_categories(env, digests, articles)
    es_categories = render_categories(env, es_digests, es_articles, lang="es")

    print("Building net salary amount pages...")
    salary_pages = render_net_salary_pages(env)

    print("Building autónomo amount pages...")
    autonomo_pages = render_autonomo_pages(env)

    print("Building rental yield amount pages...")
    rental_yield_pages = render_rental_yield_pages(env)

    print("Building sitemap...")
    category_lastmod = {slug: stories[0]["date"] for slug, stories in collect_categories(digests).items()}
    es_category_lastmod = {slug: stories[0]["date"] for slug, stories in collect_categories(es_digests).items()}
    render_sitemap(digests, categories, articles, salary_pages, autonomo_pages, rental_yield_pages, category_lastmod,
                   es_digests, es_categories, es_category_lastmod, es_articles)

    print("Writing llms.txt...")
    render_llms_txt(digests, articles, salary_pages, autonomo_pages, rental_yield_pages)

    print("Building podcast feed...")
    render_podcast_feed(episodes, {d["date"] for d in digests})

    if _untranslated:
        print(f"WARN: {len(_untranslated)} UI string(s) have no Spanish in ES_STRINGS: "
              + "; ".join(sorted(_untranslated)), file=sys.stderr)
    print("Done.")


if __name__ == "__main__":
    main()
