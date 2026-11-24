function freshDemo() {
  const records = structuredClone(demoSeed.records);
  const shift = Date.now() - Math.max(...records.tickets.map(({created_at}) => new Date(created_at).getTime()));
  for (const table of [records.orders, records.expenses, records.tickets]) {
    for (const row of table) row.created_at = new Date(new Date(row.created_at).getTime() + shift).toISOString();
  }
  return {records, approval: null};
}

let demoState = freshDemo();

async function hostedDemo(request, work) {
  if (request.kind === 'reset') {
    demoState = freshDemo();
  }
  if (request.kind === 'info' || request.kind === 'reset') {
    return {...demoSeed.info, approval: demoState.approval?.details};
  }
  if (request.kind === 'decision') {
    const proposal = demoState.approval;
    if (proposal?.details.id !== request.id) throw new Error('This approval is no longer pending.');
    demoState.approval = null;
    if (!request.approve) return {message: 'Rejected. No records changed.'};
    await work(proposal.details.agent);
    return {result: applyScenario(proposal.tool, proposal.args)};
  }
  if (demoState.approval) throw new Error('Decide the pending approval first.');
  if (request.kind === 'chat') return supervise(request.message, work);
  const [agent, , tool, args] = demoSeed.actions[request.scenario];
  if (!demoSeed.writes.includes(tool)) {
    await work(agent);
    return {routes: [agent], result: applyScenario(tool, args)};
  }
  return {...propose(agent, tool, args), routes: [agent]};
}

function propose(agent, tool, args) {
  const details = {id: crypto.randomUUID(), agent, actions: [{tool, args}]};
  demoState.approval = {details, tool, args};
  return {approval: details};
}

async function supervise(message, work) {
  const text = message.toLowerCase().replace(/[’‘]/g, "'");
  const db = demoState.records;
  let match;
  // Propose writes only when the request supplies the values used in the tool call.
  if ((match = text.match(/^(?:please )?(?:create an order for alex(?: tan)? (?:for |of )?|order )(\d{1,6}) starter packs?(?: for alex(?: tan)?)?[.!]?$/))) {
    if (!/\balex\b/.test(text) || Number(match[1]) < 1) {
      return {message: 'Specify Alex Tan and a positive quantity of Starter Packs.'};
    }
    return {...propose('sales', 'create_order', {
      customer_id: 1, lines: [{sku: 'P-001', qty: Number(match[1])}],
    }), routes: ['sales']};
  }
  if ((match = text.match(/^(?:please )?(?:restock|add) (\d{1,6}) standard widgets?[.!]?$/))) {
    if (Number(match[1]) < 1) return {message: 'Enter a positive restock quantity.'};
    return {...propose('inventory', 'adjust_stock', {
      sku: 'P-002', delta: Number(match[1]), reason: 'Requested in Office HQ',
    }), routes: ['inventory']};
  }
  if (/^(?:please )?(?:close|resolve) (?:support )?(?:ticket #?1|alex(?: tan)?'s (?:delivery )?ticket)[.!]?$/.test(text)) {
    return {...propose('support', 'update_ticket', {ticket_id: 1, status: 'closed'}), routes: ['support']};
  }
  if ((match = message.match(/^(?:please )?record (?:a |an )?\$?(\d{1,6}(?:\.\d{1,2})?) (.+?) expense[.!]?$/i))) {
    const amount = Number(match[1]);
    if (!amount) return {message: 'Enter an expense amount greater than zero.'};
    return {...propose('finance', 'record_expense', {category: match[2].trim(), amount, note: 'Requested in Office HQ'}),
      routes: ['finance']};
  }
  if ((match = message.match(/^draft (?:an )?(email|sms) for (.+?):\s*(.+)$/i))) {
    const customer = db.customers.find(({name}) => name.toLowerCase() === match[2].trim().toLowerCase());
    if (!customer) return {message: 'Use the full name of a sample customer, such as Alex Tan.'};
    return {...propose('marketing', 'draft_message', {customer_id: customer.id, channel: match[1].toLowerCase(), text: match[3]}),
      routes: ['marketing']};
  }
  if ((match = message.match(/^(?:open|create) (?:a )?(?:support )?ticket for (.+?):\s*(.+)$/i))) {
    const customer = db.customers.find(({name}) => name.toLowerCase() === match[1].trim().toLowerCase());
    if (!customer) return {message: 'Use the full name of a sample customer, such as Alex Tan.'};
    return {...propose('support', 'create_ticket', {customer_id: customer.id, subject: match[2]}), routes: ['support']};
  }
  const routes = [];
  const reports = [];
  const period = /\b(\d{1,2})[- ]days?\b/.exec(text);
  const days = period ? Math.max(1, Number(period[1])) : /\b(?:week|weekly)\b/.test(text) ? 7 : 30;
  const money = new Intl.NumberFormat('en-US', {style: 'currency', currency: demoSeed.info.business.currency});
  const brief = /\b(?:business|operations|daily|weekly|morning) (?:brief(?:ing)?|update|summary)\b/.test(text);
  const report = async (agent, produce) => {
    routes.push(agent);
    await work(agent);
    reports.push(produce());
  };
  if (brief || /\b(sales|orders?|best sellers?|top sellers?)\b/.test(text)) {
    await report('sales', () => {
      const cutoff = new Date(Date.now() - days * 86400000);
      const orders = db.orders.filter(({created_at}) => new Date(created_at) >= cutoff);
      const total = orders.reduce((sum, order) => sum + order.total, 0);
      const customer = db.customers.find(({name}) => text.includes(name.toLowerCase()));
      const relevant = customer ? orders.filter(({customer_id}) => customer_id === customer.id) : orders;
      if (customer || /\brecent orders\b/.test(text)) {
        const details = relevant.slice(-5).reverse().map(({id, total}) => `#${id} ${money.format(total)}`);
        return `Sales · ${customer ? customer.name + ' · ' : ''}Recent orders: ${details.join(', ') || 'none'}.`;
      }
      return `Sales · Last ${days} days: ${orders.length} orders totaling ${money.format(total)}.`;
    });
  }
  if (brief || /\b(stock|inventory|widgets?|starter packs?|restock|reorder)\b/.test(text)) {
    await report('inventory', () => {
      const named = db.items.find(({name, sku}) => text.includes(name.toLowerCase()) || text.includes(sku.toLowerCase()));
      const items = named ? [named] : /\b(?:all|list)\b/.test(text) && !/\blow\b/.test(text)
        ? db.items : applyScenario('low_stock', {});
      return items.length
      ? 'Inventory · ' + items.map((row) => {
        const restock = row.suggested_reorder_qty ?? (row.stock <= row.reorder_level ? row.reorder_level * 2 - row.stock : 0);
        return `${row.name} (${row.sku}): ${row.stock} in stock, reorder level ${row.reorder_level}${restock ? `, suggested reorder ${restock}` : ''}.`;
      }).join(' ')
      : 'Inventory · Nothing is at or below its reorder level.';
    });
  }
  if (brief || /\b(finance|financial|expenses?|profit|revenue|cash flow)\b/.test(text)) {
    await report('finance', () => {
      const summary = applyScenario('financial_summary', {days});
      return `Finance · Last ${days} days: revenue ${money.format(summary.revenue)}, expenses ${money.format(summary.expenses)}, net profit ${money.format(summary.net_profit)}.`;
    });
  }
  if (brief || /\b(support|tickets?|complaints?|delivery issue)\b/.test(text)) {
    await report('support', () => {
      const statusFilter = /\bclosed\b/.test(text) ? 'closed' : /\ball\b/.test(text) ? null : 'open';
      const tickets = applyScenario('list_tickets', {}).filter(({status}) => !statusFilter || status === statusFilter);
      return tickets.length
      ? 'Support · ' + tickets.map((ticket) => `#${ticket.id} ${ticket.subject} (${ticket.status}, ${ticket.customer})`).join('; ')
      : 'Support · No matching tickets.';
    });
  }
  if (/\b(marketing|promotions?|campaigns?|newsletters?|email drafts?)\b/.test(text)) {
    await report('marketing', () => {
      const draft = db.outbox.at(-1);
      return draft
      ? `Marketing · Latest ${draft.channel} draft: ${draft.text}`
      : 'Marketing · No saved drafts. Try “Draft an email for Alex Tan: Our Starter Packs are in stock”.';
    });
  }
  return {
    routes,
    message: reports.join('\n\n') || 'I can route demo requests about sales, stock, finances, support tickets, and marketing. Try “Check stock and open tickets” or “Order 2 Starter Packs for Alex”.',
  };
}

function applyScenario(tool, args) {
  const db = demoState.records;
  const add = (table, row) => {
    const id = 1 + Math.max(0, ...db[table].map((item) => item.id));
    db[table].push({...row, id, created_at: new Date().toISOString()});
    return id;
  };
  let result;
  switch (tool) {
    case 'low_stock':
      return db.items.filter(({stock, reorder_level}) => reorder_level > 0 && stock <= reorder_level)
        .map(({sku, name, stock, reorder_level}) => ({
          sku, name, stock, reorder_level, suggested_reorder_qty: reorder_level * 2 - stock,
        }));
    case 'list_tickets':
      return db.tickets.map(({customer_id, ...ticket}) => ({
        ...ticket, customer: db.customers.find(({id}) => id === customer_id).name,
      }));
    case 'financial_summary': {
      const cutoff = new Date(Date.now() - args.days * 86400000);
      const orders = db.orders.filter(({created_at}) => new Date(created_at) >= cutoff);
      const ids = new Set(orders.map(({id}) => id));
      const revenue = orders.reduce((sum, {total}) => sum + total, 0);
      const gross_profit = db.order_lines.filter(({order_id}) => ids.has(order_id))
        .reduce((sum, line) => sum + line.qty * (line.unit_price - line.unit_cost), 0);
      const expenses = db.expenses.filter(({created_at}) => new Date(created_at) >= cutoff)
        .reduce((sum, {amount}) => sum + amount, 0);
      const round = (value) => Number(value.toFixed(2));
      return {days: args.days, revenue: round(revenue), gross_profit: round(gross_profit),
        expenses: round(expenses), net_profit: round(gross_profit - expenses)};
    }
    case 'create_order': {
      const lines = args.lines.map(({sku, qty}) => ({item: db.items.find((row) => row.sku === sku), qty}));
      if (lines.some(({item, qty}) => item.stock < qty)) return {ok: false, error: 'Insufficient stock'};
      const total = lines.reduce((sum, {item, qty}) => sum + item.price * qty, 0);
      const order_id = add('orders', {customer_id: args.customer_id, status: 'paid', total});
      for (const {item, qty} of lines) {
        item.stock -= qty;
        db.order_lines.push({order_id, sku: item.sku, qty, unit_price: item.price, unit_cost: item.cost});
      }
      result = {ok: true, order_id, total};
      break;
    }
    case 'adjust_stock': {
      const item = db.items.find(({sku}) => sku === args.sku);
      item.stock += args.delta;
      result = {ok: true, sku: item.sku, new_stock: item.stock};
      break;
    }
    case 'record_expense':
      result = {ok: true, expense_id: add('expenses', args)};
      break;
    case 'update_ticket': {
      const ticket = db.tickets.find(({id}) => id === args.ticket_id);
      ticket.status = args.status;
      if (args.reply_draft) ticket.reply_draft = args.reply_draft;
      result = {ok: true};
      break;
    }
    case 'create_ticket':
      result = {ok: true, ticket_id: add('tickets', {...args, status: 'open', reply_draft: ''})};
      break;
    case 'draft_message':
      result = {ok: true, draft_id: add('outbox', {...args, status: 'draft'}), status: 'draft'};
      break;
    default:
      throw new Error('Unknown scenario.');
  }
  return result;
}
