const $ = (id) => document.getElementById(id);
const stations = {
  sales: [184, 146, '#dc7b52', '#9d6246'],
  inventory: [426, 146, '#569c89', '#e0a97a'],
  finance: [306, 250, '#9b81bb', '#d09368'],
  support: [151, 341, '#4d8ab2', '#a96848'],
  marketing: [463, 341, '#d19c49', '#e4af80'],
};

let busy = false;

function drawFloor() {
  const ctx = $('floor').getContext('2d');
  function rect(x, y, w, h, color) {
    ctx.fillStyle = color;
    ctx.fillRect(x, y, w, h);
  }
  rect(0, 0, 640, 400, '#c0b39b');
  for (let y = 78; y < 400; y += 32) {
    for (let x = 0; x < 640; x += 32) {
      rect(x, y, 31, 31, (x + y) % 64 === 14 ? '#cdc2ad' : '#d1c6b1');
    }
  }
  rect(0, 0, 640, 74, '#5b716d');
  rect(0, 66, 640, 8, '#344c4a');
  rect(0, 74, 640, 5, '#a49c87');
  for (const x of [119, 274, 429]) {
    rect(x, 10, 99, 42, '#304953');
    rect(x + 4, 14, 91, 34, '#82adae');
    rect(x + 5, 15, 89, 4, '#a7cdca');
    rect(x + 46, 13, 4, 37, '#43676d');
    rect(x - 2, 51, 103, 4, '#d6caac');
  }
  function plant(x, y) {
    rect(x - 13, y + 10, 29, 5, '#a5987c');
    rect(x - 10, y, 21, 13, '#a66348');
    rect(x - 13, y - 3, 27, 5, '#d1835d');
    rect(x - 2, y - 29, 5, 26, '#38664f');
    rect(x - 16, y - 20, 18, 8, '#598f66');
    rect(x - 20, y - 25, 13, 7, '#73a678');
    rect(x + 1, y - 23, 18, 8, '#487b58');
    rect(x + 9, y - 28, 12, 7, '#69a16c');
  }
  for (const [x, y] of [[45, 70], [592, 72], [32, 242], [609, 240], [44, 371]]) plant(x, y);
  rect(18, 103, 58, 90, '#7d5a43');
  rect(22, 107, 50, 80, '#be8c62');
  for (const y of [111, 137, 163]) {
    rect(26, y, 42, 20, '#624d41');
    ['#d38d58', '#789690', '#b7655a', '#e0bc79', '#607a9d'].forEach((color, i) => {
      rect(28 + i * 8, y + 3 + i % 3, 6, 15 - i % 3, color);
    });
  }
  rect(535, 108, 83, 47, '#9b917b');
  rect(530, 102, 83, 46, '#3d6770');
  rect(534, 107, 75, 18, '#598f98');
  rect(536, 128, 71, 15, '#6fa2a5');
  rect(533, 126, 7, 21, '#345661');
  rect(604, 126, 7, 21, '#345661');
  rect(555, 305, 42, 20, '#776956');
  rect(559, 310, 34, 19, '#a88258');
  rect(559, 299, 34, 12, '#caab77');
  rect(572, 283, 8, 18, '#e4d9ad');
  rect(565, 278, 23, 8, '#a9724e');
  rect(561, 272, 31, 7, '#e1a85e');

  for (const [x, y, shirt, skin] of Object.values(stations)) {
    rect(x - 65, y + 19, 130, 30, '#aa9a80');
    rect(x + 15, y + 7, 34, 29, '#475456');
    rect(x + 19, y + 12, 26, 17, shirt);
    rect(x - 57, y - 19, 114, 58, '#715340');
    rect(x - 54, y - 17, 108, 49, '#ca9965');
    rect(x - 54, y - 17, 108, 4, '#ebbe83');
    rect(x - 49, y + 32, 7, 15, '#4a4943');
    rect(x + 44, y + 32, 7, 15, '#4a4943');
    rect(x + 9, y - 23, 34, 24, '#35383b');
    rect(x + 12, y - 20, 28, 16, '#578887');
    rect(x + 16, y - 17, 16, 2, '#b5d6b9');
    rect(x + 16, y - 12, 10, 2, '#7bc5a1');
    rect(x + 17, y + 2, 23, 4, '#554b43');
    rect(x - 38, y - 6, 26, 18, '#3d4746');
    rect(x - 34, y - 9, 18, 15, shirt);
    rect(x - 33, y - 25, 16, 16, '#312e2d');
    rect(x - 33, y - 19, 16, 10, skin);
    rect(x - 29, y - 16, 2, 3, '#252726');
    rect(x - 22, y - 16, 2, 3, '#252726');
    rect(x - 30, y - 29, 12, 5, '#312e2d');
  }
}

function renderTeam() {
  for (const [agent, [x, y, color]] of Object.entries(stations)) {
    const label = agent[0].toUpperCase() + agent.slice(1);
    const member = document.createElement('div');
    const desk = document.createElement('span');
    member.className = 'team-member';
    desk.className = 'desk';
    member.textContent = desk.textContent = label;
    member.style.setProperty('--agent', color);
    desk.style.left = x / 640 * 100 + '%';
    desk.style.top = (y + 20) / 400 * 100 + '%';
    member.dataset.agent = desk.dataset.agent = agent;
    $('team').append(member);
    $('desks').append(desk);
  }
}

function append(text, kind = '') {
  const item = document.createElement('p');
  item.className = 'message ' + kind;
  item.textContent = text;
  $('log').append(item);
  $('log').scrollTop = $('log').scrollHeight;
  return item;
}

function controls() {
  $('prompt').disabled = !session || busy;
  $('request').querySelector('button').disabled = !session || busy;
  $('workspace-account').disabled = busy;
  $('records-open').disabled = !session;
}

function displayStatus(run) {
  const assignments = run?.assignments ?? [];
  document.querySelectorAll('[data-agent]').forEach((element) => {
    const assignment = assignments.find(({agent}) => agent === element.dataset.agent);
    element.dataset.assigned = String(!!assignment);
    element.dataset.working = String(assignment?.status === 'working' && run.status === 'working');
  });
  const working = assignments.filter(({status}) => status === 'working').map(({agent}) => agent);
  $('work-status').textContent = {
    routing: 'Supervisor routing',
    working: working.length ? 'Working: ' + working.join(', ') : 'Supervisor preparing reply',
    complete: 'Request complete',
    failed: 'Request failed',
  }[run?.status] ?? 'Team available';
}

function showRun(run, includeRequest = true) {
  if (includeRequest) append(run.request, 'user');
  if (run.assignments.length) {
    append(run.assignments.map(({agent, task, status}) => agent + ' · ' + task
      + (status === 'failed' ? ' (could not finish)' : '')).join('\n'));
  }
  if (run.answer) append(run.answer, run.status === 'failed' ? 'error' : '');
  displayStatus(run);
}

async function followRun(id) {
  const shown = new Set();
  for (let attempt = 0; attempt < 65; attempt++) {
    const [run] = await getRuns(id);
    if (run) {
      displayStatus(run);
      for (const {agent, task} of run.assignments) {
        if (shown.has(agent)) continue;
        shown.add(agent);
        append('Supervisor assigned ' + agent + ' · ' + task);
      }
      if (run.status === 'complete' || run.status === 'failed') {
        if (run.answer) append(run.answer, run.status === 'failed' ? 'error' : '');
        return;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  throw new Error('The request is still pending. Sign in again later to check its saved status.');
}

async function restoreConversation() {
  const rows = (await getRuns()).reverse();
  $('log').replaceChildren();
  if (!rows.length) append('Ask the supervisor a question or assign a task. Add business information under Business records.');
  for (const row of rows) showRun(row);
  const latest = rows.at(-1);
  if (latest && ['routing', 'working'].includes(latest.status)
      && Date.now() - Date.parse(latest.created_at) < 105000) {
    try { await followRun(latest.id); }
    catch (error) { append(error.message, 'error'); }
  }
}

$('request').addEventListener('submit', async (event) => {
  event.preventDefault();
  const prompt = $('prompt');
  const message = prompt.value.trim();
  if (!session || !message || busy) return;
  busy = true;
  controls();
  prompt.value = '';
  append(message, 'user');
  displayStatus({status: 'routing'});
  try {
    const {id} = await cloudRequest('/functions/v1/office-chat', {
      method: 'POST', body: {id: crypto.randomUUID(), message},
    });
    await followRun(id);
  } catch (error) {
    displayStatus({status: 'failed'});
    append(error.message, 'error');
  } finally {
    busy = false;
    controls();
  }
});

$('workspace-account').addEventListener('click', () => {
  if (session) {
    session = null;
    $('log').replaceChildren();
    $('record-list').replaceChildren();
    append('Sign in to return to your workspace.');
    $('workspace-account').textContent = 'Sign in';
    displayStatus();
    controls();
    return;
  }
  $('account-status').textContent = '';
  $('account').showModal();
});
$('account-close').addEventListener('click', () => $('account').close());
$('account-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy) return;
  busy = true;
  controls();
  $('account-status').textContent = 'Connecting…';
  const password = $('password');
  try {
    const signedIn = await cloudAuth($('email').value, password.value, event.submitter?.value === 'register');
    if (!signedIn) {
      $('account-status').textContent = 'Confirm the address using the email, then return here to sign in.';
      return;
    }
    await restoreConversation();
    $('workspace-account').textContent = 'Sign out';
    $('account').close();
  } catch (error) {
    session = null;
    $('account-status').textContent = error.message;
  } finally {
    password.value = '';
    busy = false;
    controls();
  }
});

async function listRecords() {
  const records = await cloudRequest('/rest/v1/office_records?select=title,category,body&order=created_at.desc&limit=20');
  const list = $('record-list');
  list.replaceChildren();
  for (const {category, title, body} of records) {
    const detail = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = category + ' · ' + title;
    const content = document.createElement('p');
    content.textContent = body;
    detail.append(summary, content);
    list.append(detail);
  }
}
$('records-open').addEventListener('click', async () => {
  $('record-status').textContent = '';
  $('records').showModal();
  try { await listRecords(); }
  catch (error) { $('record-status').textContent = error.message; }
});
$('records-close').addEventListener('click', () => $('records').close());
$('records-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = event.submitter;
  if (!session || button.disabled) return;
  button.disabled = true;
  const title = $('record-title').value.trim();
  const body = $('record-body').value.trim();
  $('record-status').textContent = 'Saving…';
  try {
    if (!title || !body) throw new Error('Enter a title and business information.');
    await cloudRequest('/rest/v1/office_records', {
      method: 'POST', body: {category: $('category').value, title, body}, prefer: 'return=minimal',
    });
    $('records-form').reset();
    $('record-status').textContent = 'Record saved.';
    await listRecords();
  } catch (error) {
    $('record-status').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

drawFloor();
renderTeam();
controls();
