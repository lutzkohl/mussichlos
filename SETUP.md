# mussIchLos — Setup-Anleitung

GitHub-Account: **lutzkohl**
GitHub Pages URL: **https://lutzkohl.github.io/mussichlos/**

---

## 1. Supabase einrichten

1. Account erstellen: https://supabase.com (kostenlos)
2. Neues Projekt anlegen (Region: **EU West** wegen DSGVO)
3. Im SQL Editor: Inhalt von `supabase/schema.sql` ausführen
4. Unter **Settings → API** folgende Werte notieren:
   - **Project URL** → `SUPABASE_URL`
   - **anon key** → `SUPABASE_ANON_KEY` (für `assets/config.js`)
   - **service_role key** → `SUPABASE_SERVICE_KEY` (für GitHub Secrets)

## 2. Resend einrichten

1. Account erstellen: https://resend.com (kostenlos)
2. Domain verifizieren (oder `@resend.dev` für den Start nutzen)
3. API Key erstellen → notieren als `RESEND_API_KEY`
4. Absender-E-Mail notieren (z.B. `alarm@mussichllos.de`) → `FROM_EMAIL`

## 3. assets/config.js anpassen

```js
const SUPABASE_URL = 'https://DEIN-PROJEKT.supabase.co';
const SUPABASE_ANON_KEY = 'DEIN-ANON-KEY';
```

## 4. GitHub Repository erstellen

1. Neues Repository erstellen: `lutzkohl/mussichlos` (public)
2. Dateien hochladen (oder `git push`)
3. **Settings → Pages → Source:** `Deploy from a branch`, Branch `main`, Ordner `/`
4. Die Seite ist dann erreichbar unter: **https://lutzkohl.github.io/mussichlos/**

## 5. GitHub Secrets setzen

**Settings → Secrets and variables → Actions → New repository secret:**

| Name | Wert |
|------|------|
| `SUPABASE_URL` | `https://xyz.supabase.co` |
| `SUPABASE_SERVICE_KEY` | service_role key aus Schritt 1 |
| `RESEND_API_KEY` | aus Schritt 2 |
| `FROM_EMAIL` | z.B. `alarm@mussichllos.de` |
| `SITE_URL` | `https://lutzkohl.github.io/mussichlos` |

## 6. Supabase Edge Functions deployen

Supabase CLI installieren: https://supabase.com/docs/guides/cli

```bash
supabase login
supabase link --project-ref DEIN-PROJEKT-ID
supabase secrets set RESEND_API_KEY=... FROM_EMAIL=... SITE_URL=https://lutzkohl.github.io/mussichlos
supabase functions deploy verify-email
supabase functions deploy send-verification
supabase functions deploy unsubscribe
```

## 7. Testen

1. Auf https://lutzkohl.github.io/mussichlos/ gehen
2. Mit echter E-Mail registrieren
3. Bestätigungsmail abwarten (kommt innerhalb von Sekunden)
4. Link klicken → success.html
5. GitHub Actions manuell auslösen:
   **Actions → Vertretungsplan-Check → Run workflow**
6. Logs prüfen ob PDF geladen + Klasse gefunden wird

## Fertig!

Ab sofort läuft der Check automatisch jeden Abend um 19 Uhr.

---

## Später: Custom Domain mussichllos.de einbinden

1. Bei deinem Domain-Anbieter einen CNAME-Eintrag setzen:
   - Name: `@` (oder `www`)
   - Wert: `lutzkohl.github.io`
2. In GitHub: **Settings → Pages → Custom domain:** `mussichllos.de` eintragen
3. HTTPS aktivieren (GitHub macht das automatisch via Let's Encrypt)
4. `SITE_URL` Secret in GitHub und Supabase auf `https://mussichllos.de` updaten
