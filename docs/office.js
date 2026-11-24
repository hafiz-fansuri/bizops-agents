const $ = (id) => document.getElementById(id);
const stations = {
  sales: [184, 146, '#dc7b52', '#9d6246'],
  inventory: [426, 146, '#569c89', '#e0a97a'],
  finance: [306, 250, '#9b81bb', '#d09368'],
  support: [151, 341, '#4d8ab2', '#a96848'],
  marketing: [463, 341, '#d19c49', '#e4af80'],
};

let workspace;
let pending = null;
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

function button(label, className, action) {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = className;
  el.textContent = label;
  el.addEventListener('click', action);
  return el;
}

function indicateAssignments(agents) {
  document.querySelectorAll('[data-agent]').forEach((el) => {
    el.dataset.assigned = String(agents.includes(el.dataset.agent));
  });
}

function workStatus(state, agent) {
  document.querySelectorAll('[data-agent]').forEach((element) => {
    element.dataset.working = String(state === 'Working' && element.dataset.agent === agent);
  });
  $('work-status').textContent = agent ? agent[0].toUpperCase() + agent.slice(1) + ' · ' + state : state;
}

async function startWork(agent) {
  workStatus('Working', agent);
  if (!document.hidden) await new Promise((resolve) => {
    const timer = setTimeout(resolve, 100);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      clearTimeout(timer);
      resolve();
    }));
  });
}

function render(data) {
  workspace = data;
  $('business').textContent = data.business.name;
  for (const id of ['team', 'desks', 'scenarios']) $(id).replaceChildren();
  for (const agent of Object.keys(data.agents)) {
    const [x, y, color] = stations[agent];
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
  for (const scenario of data.scenarios) {
    const card = button(scenario.label, 'scenario', () => {
      run({kind: 'demo', scenario: scenario.id}, scenario.label);
    });
    const role = document.createElement('small');
    role.textContent = scenario.agent;
    card.prepend(role);
    $('scenarios').append(card);
  }
  indicateAssignments(data.approval ? [data.approval.agent] : []);
  showApproval(data.approval);
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
  $('reset').disabled = busy || !workspace;
  $('workspace-account').disabled = busy;
  document.querySelectorAll('.scenario').forEach((el) => {
    el.disabled = busy || !!pending || !workspace;
  });
  document.querySelectorAll('#request input, #request button').forEach((el) => {
    el.disabled = busy || !!pending || !workspace;
  });
  document.querySelectorAll('#approval button').forEach((el) => { el.disabled = busy; });
}

function showApproval(approval) {
  pending = approval || null;
  $('approval').hidden = !pending;
  $('approval').replaceChildren();
  if (!pending) return;
  workStatus('Waiting for approval', approval.agent);
  const title = document.createElement('strong');
  title.textContent = 'Review proposed changes';
  const details = document.createElement('pre');
  details.textContent = approval.actions.map(({tool, args}) => tool + '\n' + JSON.stringify(args, null, 2)).join('\n\n');
  $('approval').append(title, details,
    button('Approve', 'action', () => run({kind: 'decision', id: approval.id, approve: true})),
    button('Reject', 'action reject', () => run({kind: 'decision', id: approval.id, approve: false})));
}

function formatResult(value) {
  if (typeof value === 'string') return value;
  if (Array.isArray(value) && value.every((item) => item?.type === 'text')) {
    return value.map((item) => {
      try { return JSON.stringify(JSON.parse(item.text), null, 2); }
      catch { return item.text; }
    }).join('\n');
  }
  return JSON.stringify(value, null, 2);
}

async function run(body, label) {
  if (busy) return;
  busy = true;
  controls();
  const before = structuredClone(demoState);
  const previousMessages = messages();
  workStatus(body.kind === 'chat' ? 'Supervisor routing' : 'Team available');
  if (label) append(label, 'user');
  const status = body.kind === 'info' ? null : append('Working…');
  try {
    const data = await hostedDemo(body, startWork);
    if (data.agents) {
      if (body.kind === 'reset') {
        $('log').replaceChildren();
        append('Demo reset. The original sample records are ready.');
      }
      render(data);
    } else {
      showApproval(data.approval);
      if (data.routes) indicateAssignments(data.routes);
      if (data.routes?.length) {
        append('Supervisor assigned: ' + data.routes.map((agent) =>
          agent[0].toUpperCase() + agent.slice(1)).join(', '));
      }
      if (data.message !== undefined) append(formatResult(data.message));
      if (data.result !== undefined) append(formatResult(data.result));
    }
    status?.remove();
    if (body.kind !== 'info') await saveWorkspace({demo: demoState, messages: messages()});
    if (!pending) workStatus(body.kind === 'reset' || body.kind === 'info' ? 'Team available' : 'Request complete');
  } catch (error) {
    demoState = before;
    restoreMessages(previousMessages);
    showApproval(before.approval?.details);
    if (!pending) workStatus('Request failed');
    append(error.message, 'error');
  } finally {
    status?.remove();
    busy = false;
    controls();
  }
}

function messages() {
  return Array.from($('log').children, (item) => ({
    text: item.textContent,
    kind: item.classList.contains('user') ? 'user' : '',
  })).slice(-40);
}

function restoreMessages(history) {
  $('log').replaceChildren();
  for (const {text, kind} of history) append(text, kind === 'user' ? 'user' : '');
}

const welcome = messages();
$('workspace-account').addEventListener('click', () => {
  if (session) {
    session = null;
    revision = null;
    demoState = freshDemo();
    restoreMessages(welcome);
    $('workspace-account').textContent = 'Save workspace';
    run({kind: 'info'});
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
    const result = await cloudAuth($('email').value, password.value, event.submitter?.value === 'register');
    if (!result) {
      $('account-status').textContent = 'Check your email to confirm the account, then return here and sign in.';
      return;
    }
    const saved = result.workspace;
    if (saved?.demo && Array.isArray(saved.messages)) {
      demoState = saved.demo;
      restoreMessages(saved.messages);
    } else {
      await saveWorkspace({demo: demoState, messages: messages()});
    }
    $('workspace-account').textContent = 'Sign out';
    $('account').close();
    render(await hostedDemo({kind: 'info'}, startWork));
  } catch (error) {
    session = null;
    revision = null;
    $('account-status').textContent = error.message;
  } finally {
    password.value = '';
    busy = false;
    controls();
  }
});

$('request').addEventListener('submit', (event) => {
  event.preventDefault();
  const prompt = $('prompt');
  const message = prompt.value.trim();
  if (!message || busy || pending) return;
  prompt.value = '';
  run({kind: 'chat', message}, message);
});
$('reset').addEventListener('click', () => {
  if (window.confirm('Reset the sample records, conversation, and pending approval?')) run({kind: 'reset'});
});
drawFloor();
run({kind: 'info'});
