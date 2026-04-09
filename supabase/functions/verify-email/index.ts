import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const SITE_URL = Deno.env.get('SITE_URL') ?? 'https://mussichllos.de';

Deno.serve(async (req: Request) => {
  const url = new URL(req.url);
  const token = url.searchParams.get('token');

  if (!token) {
    return new Response('Ungültiger Link.', { status: 400 });
  }

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
  );

  const { data, error } = await supabase
    .from('registrations')
    .update({ verified: true })
    .eq('verification_token', token)
    .eq('verified', false)
    .select('id')
    .single();

  if (error || !data) {
    // Möglicherweise schon verifiziert oder Token ungültig — trotzdem zur Success-Seite
    return Response.redirect(`${SITE_URL}/success.html`, 302);
  }

  return Response.redirect(`${SITE_URL}/success.html`, 302);
});
