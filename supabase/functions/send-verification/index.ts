/**
 * send-verification Edge Function
 * Wird direkt nach der Registrierung vom Frontend aufgerufen.
 * Schickt sofort die Bestätigungs-Mail via Resend.
 */
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const RESEND_API_KEY = Deno.env.get('RESEND_API_KEY')!;
const FROM_EMAIL = Deno.env.get('FROM_EMAIL') ?? 'alarm@mussichllos.de';
const SITE_URL = Deno.env.get('SITE_URL') ?? 'https://mussichllos.de';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  let email: string;
  try {
    const body = await req.json();
    email = body?.email?.trim()?.toLowerCase();
    if (!email) throw new Error('no email');
  } catch {
    return new Response(JSON.stringify({ error: 'email required' }), {
      status: 400,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }

  // Anon-Key aus dem Authorization-Header prüfen
  const authHeader = req.headers.get('Authorization') ?? '';
  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
  );

  // Frischeste unverifizierte Registrierung für diese E-Mail holen
  const { data: reg, error } = await supabase
    .from('registrations')
    .select('id, email, verification_token, verification_sent_at')
    .eq('email', email)
    .eq('verified', false)
    .order('created_at', { ascending: false })
    .limit(1)
    .single();

  if (error || !reg) {
    // Kein Eintrag → kein Fehler nach außen (verhindert E-Mail-Enumeration)
    return new Response(JSON.stringify({ ok: true }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }

  // Wenn bereits gesendet: nicht nochmal (Spam-Schutz)
  if (reg.verification_sent_at) {
    return new Response(JSON.stringify({ ok: true }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }

  const verifyUrl = `${Deno.env.get('SUPABASE_URL')}/functions/v1/verify-email?token=${reg.verification_token}`;

  const html = `<!DOCTYPE html>
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
        Klick auf den Button, um deine E-Mail zu bestätigen.
        Danach kriegst du jeden Abend Bescheid, wenn du Vertretung hast.
      </p>
      <a href="${verifyUrl}"
         style="display:inline-block;background:#0ea5e9;color:#fff;padding:.875rem 1.75rem;
                border-radius:8px;font-weight:700;font-size:1rem;text-decoration:none;">
        Jetzt bestätigen
      </a>
      <p style="color:#94a3b8;font-size:.8rem;margin-top:1.5rem;">
        Falls du das nicht warst, einfach ignorieren. Keine Kosten, kein Stress.
      </p>
    </div>
  </div>
</body>
</html>`;

  // Mail via Resend schicken
  const resendRes = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${RESEND_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      from: FROM_EMAIL,
      to: [email],
      subject: 'Bitte bestätige deine E-Mail — mussIchLos',
      html,
      text: `mussIchLos — Bestätigung\n\nKlick auf diesen Link:\n${verifyUrl}\n\nFalls du das nicht warst, einfach ignorieren.`,
    }),
  });

  if (resendRes.ok) {
    await supabase
      .from('registrations')
      .update({ verification_sent_at: new Date().toISOString() })
      .eq('id', reg.id);
  }

  return new Response(JSON.stringify({ ok: true }), {
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
});
