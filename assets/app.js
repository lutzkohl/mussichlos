(() => {
  'use strict';

  // Supabase gibt manchmal einen "sb_publishable_..." Key zurück —
  // die REST API braucht nur den JWT-Teil (eyJ...)
  function extractJWT(key) {
    if (!key.startsWith('sb_publishable_')) return key;
    const idx = key.indexOf('eyJ');
    return idx !== -1 ? key.slice(idx) : key;
  }
  const SUPABASE_JWT = extractJWT(SUPABASE_ANON_KEY);

  const form = document.getElementById('registration-form');
  const submitBtn = document.getElementById('submit-btn');
  const btnText = document.getElementById('btn-text');
  const btnSpinner = document.getElementById('btn-spinner');
  const formCard = document.getElementById('form-card');
  const formSuccess = document.getElementById('form-success');
  const formError = document.getElementById('form-error');
  const errorText = document.getElementById('error-text');

  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const email = document.getElementById('email').value.trim();
    const klasseRaw = document.getElementById('klasse').value.trim();
    const schuleValue = document.getElementById('schule').value;

    // Basic validation
    if (!email || !klasseRaw || !schuleValue) {
      showError('Bitte füll alle Felder aus.');
      return;
    }

    if (!isValidEmail(email)) {
      showError('Das sieht nicht wie eine E-Mail-Adresse aus.');
      return;
    }

    // Parse school value: "KEY|Name|URL"
    const [, schoolName, schoolUrl] = schuleValue.split('|');
    const klasse = klasseRaw.toLowerCase();

    setLoading(true);
    hideError();

    try {
      // 1. Insert registration into Supabase
      const insertRes = await fetch(`${SUPABASE_URL}/rest/v1/registrations`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'apikey': SUPABASE_JWT,
          'Authorization': `Bearer ${SUPABASE_JWT}`,
          'Prefer': 'return=minimal',
        },
        body: JSON.stringify({ email, klasse, school_name: schoolName, school_url: schoolUrl }),
      });

      if (!insertRes.ok) {
        // 409 Conflict = already registered
        if (insertRes.status === 409) {
          showError('Diese E-Mail ist schon eingetragen. Check deinen Posteingang für die Bestätigung.');
          return;
        }
        throw new Error(`Insert failed: ${insertRes.status}`);
      }

      // 2. Trigger verification email via Edge Function
      await fetch(`${SUPABASE_URL}/functions/v1/send-verification`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'apikey': SUPABASE_JWT,
          'Authorization': `Bearer ${SUPABASE_JWT}`,
        },
        body: JSON.stringify({ email }),
      });

      // Show success (even if edge function had an issue — the cron job will retry)
      form.classList.add('hidden');
      formSuccess.classList.remove('hidden');

    } catch (err) {
      console.error(err);
      showError('Da ist leider was schiefgelaufen. Versuch es gleich nochmal.');
    } finally {
      setLoading(false);
    }
  });

  function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  function setLoading(loading) {
    submitBtn.disabled = loading;
    if (loading) {
      btnText.textContent = 'Einen Moment...';
      btnSpinner.classList.remove('hidden');
    } else {
      btnText.textContent = 'Loslegen';
      btnSpinner.classList.add('hidden');
    }
  }

  function showError(msg) {
    errorText.textContent = msg;
    formError.classList.remove('hidden');
  }

  function hideError() {
    formError.classList.add('hidden');
  }
})();
