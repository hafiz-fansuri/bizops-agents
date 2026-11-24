// The publishable key identifies the project. Supabase RLS authorizes each workspace request.
const api = 'https://zihupqxmwfxnndlquzte.supabase.co';
const publishable = 'sb_publishable_KQbHJAP6HHaGAIoS4C9YMA_4og2gefL';
let session;

async function supabaseRequest(path, {method = 'GET', body, auth, prefer} = {}) {
  const headers = {apikey: publishable, 'Content-Type': 'application/json'};
  if (auth) headers.Authorization = 'Bearer ' + auth;
  if (prefer) headers.Prefer = prefer;
  const response = await fetch(api + path, {method, headers, body: body && JSON.stringify(body)});
  if (response.ok && response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error_description || data.msg || data.message || data.error
    || 'Supabase could not complete the request.');
  return data;
}

async function cloudAuth(email, password, register) {
  const endpoint = register ? '/signup?redirect_to=' + encodeURIComponent(location.href.split('#')[0])
    : '/token?grant_type=password';
  const auth = await supabaseRequest('/auth/v1' + endpoint, {method: 'POST', body: {email, password}});
  if (!auth.access_token) return false;
  session = auth;
  return true;
}

async function cloudToken() {
  if (session.expires_at && Date.now() / 1000 + 30 >= session.expires_at) {
    session = await supabaseRequest('/auth/v1/token?grant_type=refresh_token', {
      method: 'POST', body: {refresh_token: session.refresh_token},
    });
  }
  return session.access_token;
}

async function cloudRequest(path, options = {}) {
  return supabaseRequest(path, {...options, auth: await cloudToken()});
}

function getRuns(id) {
  const filter = id ? '&id=eq.' + encodeURIComponent(id) : '&order=created_at.desc&limit=30';
  return cloudRequest('/rest/v1/office_runs?select=id,request,status,assignments,answer,created_at' + filter);
}
