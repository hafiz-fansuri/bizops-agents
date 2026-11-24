// The publishable key identifies the project. Supabase RLS authorizes each workspace request.
const api = 'https://zihupqxmwfxnndlquzte.supabase.co';
const publishable = 'sb_publishable_KQbHJAP6HHaGAIoS4C9YMA_4og2gefL';
let session;
let revision;

async function supabaseRequest(path, {method = 'GET', body, auth, prefer} = {}) {
  const headers = {apikey: publishable, 'Content-Type': 'application/json'};
  if (auth) headers.Authorization = 'Bearer ' + auth;
  if (prefer) headers.Prefer = prefer;
  const response = await fetch(api + path, {method, headers, body: body && JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.msg || data.message || 'Supabase could not complete the request.');
  return data;
}

async function cloudAuth(email, password, register) {
  const endpoint = register ? '/signup?redirect_to=' + encodeURIComponent(location.href.split('#')[0])
    : '/token?grant_type=password';
  const auth = await supabaseRequest('/auth/v1' + endpoint, {method: 'POST', body: {email, password}});
  if (!auth.access_token) return false;
  session = auth;
  try {
    return {workspace: await loadWorkspace()};
  } catch (error) {
    session = null;
    throw error;
  }
}

async function cloudToken() {
  if (session.expires_at && Date.now() / 1000 + 30 >= session.expires_at) {
    session = await supabaseRequest('/auth/v1/token?grant_type=refresh_token', {
      method: 'POST', body: {refresh_token: session.refresh_token},
    });
  }
  return session.access_token;
}

async function loadWorkspace() {
  const auth = await cloudToken();
  const rows = await supabaseRequest('/rest/v1/office_workspaces?select=payload,revision', {auth});
  revision = rows[0]?.revision ?? null;
  return rows[0]?.payload ?? null;
}

async function saveWorkspace(payload) {
  if (!session) return;
  const auth = await cloudToken();
  const creating = revision === null;
  const next = creating ? 0 : revision + 1;
  const suffix = creating ? '' : '?revision=eq.' + revision;
  const rows = await supabaseRequest('/rest/v1/office_workspaces' + suffix, {
    method: creating ? 'POST' : 'PATCH', auth, prefer: 'return=representation',
    body: {payload, revision: next},
  });
  if (!rows.length) throw new Error('This workspace changed in another tab. Sign in again to load the latest version.');
  revision = next;
}
