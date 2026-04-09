#!/usr/bin/env python3
"""
mussIchLos — Täglicher Vertretungsplan-Check
Läuft via GitHub Actions, täglich 17:00 UTC (= 19:00 CEST / 18:00 CET).

Ablauf:
  1. Alle verifizierten Registrierungen aus Supabase laden
  2. Pro Schule: Vertretungsplan-PDF herunterladen + parsen
  3. Pro Nutzer: prüfen ob seine Klasse im Plan steht
  4. Bei Vertretung: E-Mail via Resend schicken + last_notified_date setzen
"""

import os
import sys
import io
import re
import json
import datetime
import zoneinfo
import requests
import pdfplumber
import resend
from bs4 import BeautifulSoup
from supabase import create_client, Client
from collections import defaultdict
from urllib.parse import urljoin, urlparse

# ── Konfiguration aus GitHub Actions Secrets ─────────────────
SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_SERVICE_KEY = os.environ['SUPABASE_SERVICE_KEY']
RESEND_API_KEY = os.environ['RESEND_API_KEY']
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'alarm@mussichllos.de')
SITE_URL = os.environ.get('SITE_URL', 'https://mussichllos.de')

resend.api_key = RESEND_API_KEY
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# DST-Guard: Skript läuft zweimal täglich (17 + 18 Uhr UTC).
# Nur der Run zur richtigen Berliner Zeit wird ausgeführt.
# Bei manuellem Trigger (workflow_dispatch) wird der Guard übersprungen.
BERLIN = zoneinfo.ZoneInfo('Europe/Berlin')
now_berlin = datetime.datetime.now(BERLIN)
is_manual = os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
if not is_manual and not (18 <= now_berlin.hour <= 19):
    print(f"DST-Guard: Berliner Zeit ist {now_berlin.strftime('%H:%M')} — kein Benachrichtigungszeitfenster. Abbruch.")
    sys.exit(0)

today = datetime.date.today().isoformat()


# ── Hilfsfunktionen: PDF-Link finden ────────────────────────

def find_pdf_url(page_url: str) -> str | None:
    """Lädt die Schulseite und findet den aktuellsten Vertretungsplan-PDF-Link."""
    try:
        resp = requests.get(page_url, timeout=15, headers={'User-Agent': 'mussIchLos-Bot/1.0'})
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [FEHLER] Seite nicht erreichbar: {page_url} — {e}")
        return None

    base_origin = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    soup = BeautifulSoup(resp.text, 'html.parser')

    # Strategie 1: Link-href endet auf .pdf (zuverlässigste Methode)
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.lower().endswith('.pdf'):
            full_url = urljoin(page_url, href)
            if full_url.startswith(base_origin):
                print(f"  PDF-Link gefunden (via href): {full_url}")
                return full_url

    # Strategie 2: Linktext enthält "vertretungsplan" UND href enthält Dateiname
    for a in soup.find_all('a', href=True):
        href = a['href']
        link_text = a.get_text(strip=True).lower()
        if 'vertretungsplan' in link_text and '.' in href.split('/')[-1]:
            full_url = urljoin(page_url, href)
            if full_url.startswith(base_origin) and full_url != page_url:
                print(f"  PDF-Link gefunden (via Text): {full_url}")
                return full_url

    print(f"  [WARN] Kein PDF-Link gefunden auf {page_url}")
    return None


# ── Hilfsfunktionen: PDF parsen ──────────────────────────────

def download_pdf(pdf_url: str) -> bytes | None:
    """Lädt das PDF herunter und gibt den Inhalt als bytes zurück."""
    try:
        resp = requests.get(pdf_url, timeout=30, headers={'User-Agent': 'mussIchLos-Bot/1.0'})
        resp.raise_for_status()
        content_type = resp.headers.get('Content-Type', '')
        print(f"  Content-Type: {content_type} | Größe: {len(resp.content):,} Bytes | Anfang: {resp.content[:8]}")
        if b'%PDF' not in resp.content[:8]:
            print(f"  [WARN] Antwort beginnt nicht mit %PDF — kein echtes PDF!")
            print(f"  Inhalt-Anfang: {resp.content[:200]}")
            return None
        return resp.content
    except requests.RequestException as e:
        print(f"  [FEHLER] PDF nicht ladbar: {pdf_url} — {e}")
        return None


def extract_class_entries(pdf_bytes: bytes, klasse: str) -> list[str]:
    """
    Parst das PDF und gibt alle Vertretungs-Einträge für die Klasse zurück.

    Strategie:
    1. pdfplumber: Tabellen extrahieren (beste Methode)
    2. Fallback: Rohtext zeilenweise durchsuchen
    """
    klasse_lower = klasse.strip().lower()
    entries = []

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                # Methode 1: Tabellen-Extraktion
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        entries += _search_table(table, klasse_lower)
                    if entries:
                        return entries

                # Methode 2: Rohtext + Positionsdaten
                words = page.extract_words()
                entries += _search_words(words, klasse_lower)
                if entries:
                    return entries

                # Methode 3: Einfacher Rohtext-Fallback
                text = page.extract_text() or ''
                entries += _search_raw_text(text, klasse_lower)

    except Exception as e:
        print(f"  [FEHLER] PDF-Parsing fehlgeschlagen: {e}")

    return entries


def _search_table(table: list[list], klasse: str) -> list[str]:
    """Durchsucht eine extrahierte Tabelle nach der Klasse."""
    results = []
    for row in table:
        if not row:
            continue
        # Ersten Nicht-None-Wert als Klassen-Identifier prüfen
        first = (row[0] or '').strip().lower()
        if first == klasse or first.startswith(klasse + ' '):
            # Alle Zellen joinen
            row_text = ' | '.join(str(cell or '').strip() for cell in row if cell)
            if _has_substitution(row_text):
                results.append(row_text)
    return results


def _search_words(words: list[dict], klasse: str) -> list[str]:
    """
    Gruppiert PDF-Wörter nach y-Koordinate (±4pt Toleranz) und
    sucht Zeilen, die mit der Klasse beginnen.
    """
    if not words:
        return []

    # Wörter nach y-Position gruppieren
    rows: dict[int, list[dict]] = defaultdict(list)
    for word in words:
        y_bucket = round(word['top'] / 4) * 4
        rows[y_bucket].append(word)

    results = []
    for y in sorted(rows.keys()):
        row_words = sorted(rows[y], key=lambda w: w['x0'])
        texts = [w['text'] for w in row_words]
        if not texts:
            continue

        # Klasse am Zeilenanfang?
        first = texts[0].strip().lower()
        if first == klasse or first.startswith(klasse + ' '):
            row_text = ' '.join(texts)
            if _has_substitution(row_text):
                results.append(row_text)

    return results


def _search_raw_text(text: str, klasse: str) -> list[str]:
    """Einfachster Fallback: zeilenweise Suche im Rohtext."""
    results = []
    for line in text.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if lower.startswith(klasse) and _has_substitution(stripped):
            results.append(stripped)
    return results


def _has_substitution(text: str) -> bool:
    """Prüft ob ein Text auf Vertretung/Ausfall hindeutet."""
    keywords = ['ausfall', 'statt', 'vertretung', 'entfall', 'frei', 'selbst']
    t = text.lower()
    return any(kw in t for kw in keywords)


# ── E-Mail-Templates ─────────────────────────────────────────

def build_email_html(klasse: str, school_name: str, entries: list[str], unsubscribe_url: str) -> str:
    entries_html = ''.join(f'<li>{entry}</li>' for entry in entries)
    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8fafc;margin:0;padding:2rem 1rem;">
  <div style="max-width:520px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;">
    <div style="background:#0ea5e9;padding:1.5rem 2rem;">
      <span style="color:#fff;font-size:1.1rem;font-weight:800;">mussIchLos.</span>
    </div>
    <div style="padding:2rem;">
      <h1 style="font-size:1.4rem;font-weight:800;margin:0 0 .5rem;">Du hast morgen Vertretung!</h1>
      <p style="color:#64748b;margin:0 0 1.5rem;">
        Klasse <strong>{klasse.upper()}</strong> — {school_name}
      </p>
      <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:1rem 1.25rem;margin-bottom:1.5rem;">
        <p style="font-size:.85rem;color:#0369a1;font-weight:600;margin:0 0 .5rem;">Was im Plan steht:</p>
        <ul style="margin:0;padding-left:1.25rem;color:#0f172a;font-size:.95rem;">
          {entries_html}
        </ul>
      </div>
      <p style="color:#64748b;font-size:.9rem;margin:0;">
        Kein Stress — morgen weißt du Bescheid. 😎
      </p>
    </div>
    <div style="border-top:1px solid #e2e8f0;padding:1rem 2rem;text-align:center;">
      <a href="{unsubscribe_url}" style="color:#94a3b8;font-size:.8rem;text-decoration:none;">
        Abmelden
      </a>
    </div>
  </div>
</body>
</html>"""


def build_email_text(klasse: str, school_name: str, entries: list[str]) -> str:
    entries_text = '\n'.join(f'  • {e}' for e in entries)
    return (
        f"mussIchLos — Vertretungsplan-Alarm\n\n"
        f"Klasse {klasse.upper()} ({school_name}) hat morgen Vertretung:\n\n"
        f"{entries_text}\n\n"
        f"—\nNoch Fragen? hallo@mussichllos.de"
    )


# ── Hauptlogik ───────────────────────────────────────────────

def main():
    print(f"=== mussIchLos Plan-Check [{today}] ===")

    # Alle verifizierten Registrierungen laden (last_notified_date != heute)
    result = (
        supabase.table('registrations')
        .select('id, email, klasse, school_name, school_url, unsubscribe_token, last_notified_date')
        .eq('verified', True)
        .or_(f'last_notified_date.neq.{today},last_notified_date.is.null')
        .execute()
    )

    if not result.data:
        print("Keine aktiven Registrierungen. Fertig.")
        return

    print(f"{len(result.data)} aktive Registrierung(en) gefunden.")

    # Nach Schule gruppieren, um PDF nur einmal pro Schule zu laden
    by_school: dict[str, list[dict]] = defaultdict(list)
    for reg in result.data:
        by_school[reg['school_url']].append(reg)

    for school_url, regs in by_school.items():
        school_name = regs[0]['school_name']
        print(f"\n[Schule] {school_name}")

        pdf_url = find_pdf_url(school_url)
        if not pdf_url:
            continue
        print(f"  PDF: {pdf_url}")

        pdf_bytes = download_pdf(pdf_url)
        if not pdf_bytes:
            continue
        print(f"  PDF geladen ({len(pdf_bytes):,} Bytes)")

        for reg in regs:
            klasse = reg['klasse']
            email = reg['email']
            print(f"  → Klasse {klasse}: ", end='', flush=True)

            entries = extract_class_entries(pdf_bytes, klasse)

            if not entries:
                print("kein Eintrag gefunden.")
                continue

            print(f"{len(entries)} Eintrag/Einträge gefunden!")

            unsubscribe_url = f"{SITE_URL}/unsubscribe.html?token={reg['unsubscribe_token']}"

            try:
                resend.Emails.send({
                    'from': FROM_EMAIL,
                    'to': [email],
                    'subject': f"Morgen Vertretung — Klasse {klasse.upper()}",
                    'html': build_email_html(klasse, school_name, entries, unsubscribe_url),
                    'text': build_email_text(klasse, school_name, entries),
                })

                # last_notified_date aktualisieren
                supabase.table('registrations').update(
                    {'last_notified_date': today}
                ).eq('id', reg['id']).execute()

                print(f"    Mail gesendet an {email}")

            except Exception as e:
                print(f"    [FEHLER] Mail-Versand fehlgeschlagen: {e}")

    print("\n=== Fertig ===")


if __name__ == '__main__':
    main()
