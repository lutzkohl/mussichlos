#!/usr/bin/env python3
"""
mussIchLos — Bestätigungs-Mails für neue Registrierungen
Backup-Cron: läuft stündlich und schickt Verifizierungsmails für
Einträge, bei denen die Edge Function nicht geklappt hat.
"""

import os
import datetime
import resend
from supabase import create_client, Client

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_SERVICE_KEY = os.environ['SUPABASE_SERVICE_KEY']
RESEND_API_KEY = os.environ['RESEND_API_KEY']
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'alarm@mussichllos.de')
SUPABASE_FUNCTIONS_URL = os.environ.get(
    'SUPABASE_FUNCTIONS_URL',
    SUPABASE_URL.replace('.supabase.co', '.supabase.co/functions/v1')
)
SITE_URL = os.environ.get('SITE_URL', 'https://mussichllos.de')

resend.api_key = RESEND_API_KEY
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Nur Einträge der letzten 24h, die noch nicht verifiziert sind
cutoff = (datetime.datetime.utcnow() - datetime.timedelta(hours=24)).isoformat()


def build_verification_html(email: str, verify_url: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8fafc;margin:0;padding:2rem 1rem;">
  <div style="max-width:520px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;">
    <div style="background:#0ea5e9;padding:1.5rem 2rem;">
      <span style="color:#fff;font-size:1.1rem;font-weight:800;">mussIchLos.</span>
    </div>
    <div style="padding:2rem;">
      <h1 style="font-size:1.4rem;font-weight:800;margin:0 0 .75rem;">Fast geschafft!</h1>
      <p style="color:#64748b;margin:0 0 1.5rem;">
        Klick auf den Button unten, damit wir wissen, dass die E-Mail-Adresse dir gehört.
        Danach kriegst du jeden Abend Bescheid, wenn du Vertretung hast.
      </p>
      <a href="{verify_url}"
         style="display:inline-block;background:#0ea5e9;color:#fff;padding:.875rem 1.75rem;
                border-radius:8px;font-weight:700;font-size:1rem;text-decoration:none;">
        Jetzt bestätigen
      </a>
      <p style="color:#94a3b8;font-size:.8rem;margin-top:1.5rem;">
        Falls du diesen Link nicht angefordert hast, kannst du diese Mail einfach ignorieren.
      </p>
    </div>
  </div>
</body>
</html>"""


def main():
    print("=== mussIchLos Verifizierungs-Check ===")

    result = (
        supabase.table('registrations')
        .select('id, email, verification_token, verification_sent_at')
        .eq('verified', False)
        .gte('created_at', cutoff)
        .is_('verification_sent_at', 'null')
        .execute()
    )

    if not result.data:
        print("Keine ausstehenden Verifizierungen. Fertig.")
        return

    print(f"{len(result.data)} ausstehende Verifizierung(en).")

    for reg in result.data:
        email = reg['email']
        token = reg['verification_token']
        verify_url = f"{SUPABASE_URL}/functions/v1/verify-email?token={token}"

        try:
            resend.Emails.send({
                'from': FROM_EMAIL,
                'to': [email],
                'subject': 'Bitte bestätige deine E-Mail — mussIchLos',
                'html': build_verification_html(email, verify_url),
                'text': (
                    f"mussIchLos — Bestätigung\n\n"
                    f"Klick auf diesen Link, um deine E-Mail zu bestätigen:\n{verify_url}\n\n"
                    f"Falls du das nicht warst, einfach ignorieren."
                ),
            })

            supabase.table('registrations').update(
                {'verification_sent_at': datetime.datetime.utcnow().isoformat()}
            ).eq('id', reg['id']).execute()

            print(f"  Verifizierungsmail gesendet an {email}")
        except Exception as e:
            print(f"  [FEHLER] {email}: {e}")

    print("=== Fertig ===")


if __name__ == '__main__':
    main()
