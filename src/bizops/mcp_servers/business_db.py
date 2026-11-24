"""MCP server exposing a generic small-business database (stdio).

    BIZOPS_DB=data/business.db python -m bizops.mcp_servers.business_db

Any MCP-capable client can use it (Claude Desktop, this project's agents, ...).
Read tools are free; write tools are listed in the profile's `approval_required` and gated by the agent runtime.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from bizops.db import connect, init_db, now

DB = os.getenv("BIZOPS_DB", "data/business.db")
init_db(DB)
mcp = FastMCP("business-db")


def _since(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")


def _rows(sql: str, args: tuple = ()) -> list[dict]:
    with connect(DB) as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


class OrderLine(BaseModel):
    sku: str = Field(description="Item SKU, e.g. P-001")
    qty: int = Field(gt=0, description="Quantity")


# ------------------------------- read -------------------------------
@mcp.tool()
def list_items(query: str = "", category: str = "") -> list[dict]:
    """List items/products with price and stock. Optional name/SKU `query` and `category` filters."""
    return _rows("SELECT sku,name,price,stock,reorder_level,category FROM items "
                 "WHERE (name LIKE ? OR sku LIKE ?) AND (?='' OR category=?) ORDER BY name",
                 (f"%{query}%", f"%{query}%", category, category))


@mcp.tool()
def low_stock() -> list[dict]:
    """Items whose stock is at or below their reorder level, with a suggested reorder quantity."""
    return _rows("SELECT sku,name,stock,reorder_level, MAX(reorder_level*2 - stock, 1) AS suggested_reorder_qty "
                 "FROM items WHERE reorder_level > 0 AND stock <= reorder_level ORDER BY stock - reorder_level")


@mcp.tool()
def list_customers(query: str = "") -> list[dict]:
    """Find customers by name/contact text (empty query = all, max 50)."""
    return _rows("SELECT id,name,contact,notes FROM customers WHERE name LIKE ? OR contact LIKE ? LIMIT 50",
                 (f"%{query}%", f"%{query}%"))


@mcp.tool()
def list_orders(days: int = 7, customer_id: int = 0, limit: int = 30) -> list[dict]:
    """Recent orders (default last 7 days), newest first. Optionally for one customer_id."""
    return _rows("SELECT o.id,o.created_at,o.status,o.total,c.name AS customer FROM orders o "
                 "LEFT JOIN customers c ON c.id=o.customer_id WHERE o.created_at>=? AND (?=0 OR o.customer_id=?) "
                 "ORDER BY o.created_at DESC LIMIT ?", (_since(days), customer_id, customer_id, limit))


@mcp.tool()
def sales_summary(days: int = 7) -> dict:
    """Revenue, order count, gross profit and top sellers for the last `days` days."""
    since = _since(days)
    tot = _rows("SELECT COUNT(*) AS orders, COALESCE(SUM(total),0) AS revenue FROM orders WHERE created_at>=?", (since,))[0]
    gp = _rows("SELECT COALESCE(SUM(l.qty*(l.unit_price-l.unit_cost)),0) AS gross_profit FROM order_lines l "
               "JOIN orders o ON o.id=l.order_id WHERE o.created_at>=?", (since,))[0]
    top = _rows("SELECT i.name, SUM(l.qty) AS units, SUM(l.qty*l.unit_price) AS revenue FROM order_lines l "
                "JOIN orders o ON o.id=l.order_id JOIN items i ON i.sku=l.sku WHERE o.created_at>=? "
                "GROUP BY i.name ORDER BY units DESC LIMIT 5", (since,))
    return {"days": days, **tot, **gp, "top_sellers": top}


@mcp.tool()
def list_expenses(days: int = 30) -> list[dict]:
    """Expenses in the last `days` days."""
    return _rows("SELECT id,created_at,category,amount,note FROM expenses WHERE created_at>=? ORDER BY created_at DESC", (_since(days),))


@mcp.tool()
def financial_summary(days: int = 30) -> dict:
    """Revenue, gross profit, expenses and net profit for the last `days` days."""
    s = sales_summary(days)
    exp = _rows("SELECT COALESCE(SUM(amount),0) AS expenses FROM expenses WHERE created_at>=?", (_since(days),))[0]["expenses"]
    return {"days": days, "revenue": s["revenue"], "gross_profit": s["gross_profit"], "expenses": exp,
            "net_profit": round(s["gross_profit"] - exp, 2)}


@mcp.tool()
def list_tickets(status: str = "open") -> list[dict]:
    """Support tickets by status (open/closed/all)."""
    return _rows("SELECT t.id,t.created_at,t.status,t.subject,t.body,t.reply_draft,c.name AS customer FROM tickets t "
                 "LEFT JOIN customers c ON c.id=t.customer_id WHERE ?='all' OR t.status=? ORDER BY t.created_at DESC",
                 (status, status))


# ------------------------------- write -------------------------------
@mcp.tool()
def create_order(customer_id: int, lines: list[OrderLine]) -> dict:
    """Create a paid order and decrement stock. Fails (no changes) if any item is missing or out of stock."""
    with connect(DB) as c:
        total, resolved = 0.0, []
        for ln in lines:
            r = c.execute("SELECT sku,name,price,cost,stock FROM items WHERE sku=?", (ln.sku,)).fetchone()
            if r is None:
                return {"ok": False, "error": f"unknown sku {ln.sku}"}
            if r["stock"] < ln.qty:
                return {"ok": False, "error": f"insufficient stock for {r['name']}: have {r['stock']}, need {ln.qty}"}
            resolved.append((r, ln.qty))
            total += r["price"] * ln.qty
        cur = c.execute("INSERT INTO orders(customer_id,status,total,created_at) VALUES(?,?,?,?)",
                        (customer_id, "paid", total, now()))
        for r, q in resolved:
            c.execute("INSERT INTO order_lines VALUES(?,?,?,?,?)", (cur.lastrowid, r["sku"], q, r["price"], r["cost"]))
            c.execute("UPDATE items SET stock=stock-? WHERE sku=?", (q, r["sku"]))
            c.execute("INSERT INTO stock_log(sku,delta,reason,created_at) VALUES(?,?,?,?)",
                      (r["sku"], -q, f"order {cur.lastrowid}", now()))
    return {"ok": True, "order_id": cur.lastrowid, "total": round(total, 2)}


@mcp.tool()
def adjust_stock(sku: str, delta: int, reason: str) -> dict:
    """Add (+) or remove (-) stock for an item, e.g. restock +20 or write-off -2. Stock cannot go negative."""
    with connect(DB) as c:
        r = c.execute("SELECT stock FROM items WHERE sku=?", (sku,)).fetchone()
        if r is None:
            return {"ok": False, "error": f"unknown sku {sku}"}
        if r["stock"] + delta < 0:
            return {"ok": False, "error": f"would go negative (current {r['stock']})"}
        c.execute("UPDATE items SET stock=stock+? WHERE sku=?", (delta, sku))
        c.execute("INSERT INTO stock_log(sku,delta,reason,created_at) VALUES(?,?,?,?)", (sku, delta, reason, now()))
    return {"ok": True, "sku": sku, "new_stock": r["stock"] + delta}


@mcp.tool()
def record_expense(category: str, amount: float, note: str = "") -> dict:
    """Record a business expense (amount > 0)."""
    if amount <= 0:
        return {"ok": False, "error": "amount must be > 0"}
    with connect(DB) as c:
        cur = c.execute("INSERT INTO expenses(category,amount,note,created_at) VALUES(?,?,?,?)", (category, amount, note, now()))
    return {"ok": True, "expense_id": cur.lastrowid}


@mcp.tool()
def create_ticket(customer_id: int, subject: str, body: str = "") -> dict:
    """Open a support ticket for a customer."""
    with connect(DB) as c:
        cur = c.execute("INSERT INTO tickets(customer_id,subject,body,created_at) VALUES(?,?,?,?)", (customer_id, subject, body, now()))
    return {"ok": True, "ticket_id": cur.lastrowid}


@mcp.tool()
def update_ticket(ticket_id: int, status: str = "", reply_draft: str = "") -> dict:
    """Update a ticket's status (open/closed) and/or store a reply draft."""
    with connect(DB) as c:
        if not c.execute("SELECT 1 FROM tickets WHERE id=?", (ticket_id,)).fetchone():
            return {"ok": False, "error": "no such ticket"}
        if status:
            c.execute("UPDATE tickets SET status=? WHERE id=?", (status, ticket_id))
        if reply_draft:
            c.execute("UPDATE tickets SET reply_draft=? WHERE id=?", (reply_draft, ticket_id))
    return {"ok": True}


@mcp.tool()
def draft_message(customer_id: int, channel: str, text: str) -> dict:
    """Save an outgoing message DRAFT (email/whatsapp/sms/social). Nothing is sent; the owner reviews the outbox."""
    with connect(DB) as c:
        cur = c.execute("INSERT INTO outbox(customer_id,channel,text,created_at) VALUES(?,?,?,?)", (customer_id, channel, text, now()))
    return {"ok": True, "draft_id": cur.lastrowid, "status": "draft"}


if __name__ == "__main__":
    mcp.run()
