-- mussIchLos — Datenbankschema
-- Ausführen in: Supabase → SQL Editor

-- Tabelle erstellen
CREATE TABLE IF NOT EXISTS public.registrations (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email                 TEXT NOT NULL,
  klasse                TEXT NOT NULL,
  school_name           TEXT NOT NULL,
  school_url            TEXT NOT NULL,
  verified              BOOLEAN NOT NULL DEFAULT FALSE,
  verification_token    UUID NOT NULL DEFAULT gen_random_uuid(),
  verification_sent_at  TIMESTAMPTZ,
  unsubscribe_token     UUID NOT NULL DEFAULT gen_random_uuid(),
  last_notified_date    DATE,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Eindeutigkeit: eine E-Mail pro Schule + Klasse
CREATE UNIQUE INDEX IF NOT EXISTS registrations_email_school_unique
  ON public.registrations (email, school_url, klasse);

-- Index für schnelle Lookups
CREATE INDEX IF NOT EXISTS registrations_email_idx       ON public.registrations (email);
CREATE INDEX IF NOT EXISTS registrations_verified_idx    ON public.registrations (verified);
CREATE INDEX IF NOT EXISTS registrations_created_at_idx  ON public.registrations (created_at);

-- ────────────────────────────────────────────────────────────
-- Row Level Security
-- ────────────────────────────────────────────────────────────
ALTER TABLE public.registrations ENABLE ROW LEVEL SECURITY;

-- Anon-Nutzer dürfen NUR neue Einträge einfügen (kein SELECT, UPDATE, DELETE)
CREATE POLICY "anon_insert_only"
  ON public.registrations
  FOR INSERT
  TO anon
  WITH CHECK (true);

-- Authenticated und Service Role haben vollen Zugriff (für Edge Functions + Actions)
-- Service Role umgeht RLS automatisch — kein explizites Policy nötig.

-- Notification-Log (für saubere Deduplizierung)
CREATE TABLE IF NOT EXISTS public.notification_log (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  registration_id UUID REFERENCES public.registrations(id) ON DELETE CASCADE,
  plan_date       DATE NOT NULL,
  sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status          TEXT NOT NULL DEFAULT 'sent',  -- 'sent', 'failed'
  resend_id       TEXT
);

CREATE INDEX IF NOT EXISTS notification_log_reg_date_idx
  ON public.notification_log (registration_id, plan_date);

ALTER TABLE public.notification_log ENABLE ROW LEVEL SECURITY;
-- Kein Anon-Zugriff auf Logs
CREATE POLICY "no_anon_log" ON public.notification_log FOR ALL TO anon USING (false);

-- Automatisches Bereinigen unverifizierter Einträge nach 48h
-- Aktiviert pg_cron Extension falls noch nicht aktiv:
-- CREATE EXTENSION IF NOT EXISTS pg_cron;
-- SELECT cron.schedule('cleanup-unverified', '0 3 * * *',
--   $$DELETE FROM public.registrations WHERE verified = false AND created_at < now() - interval '48 hours'$$);

-- ────────────────────────────────────────────────────────────
-- Kommentar zur Sicherheit:
-- Der anon key im Frontend-JS erlaubt AUSSCHLIESSLICH INSERT.
-- E-Mail-Adressen sind für niemanden über die öffentliche API lesbar.
-- Nur GitHub Actions (service key) kann die Daten lesen und bearbeiten.
-- ────────────────────────────────────────────────────────────
