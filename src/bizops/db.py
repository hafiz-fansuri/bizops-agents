"""Generic small-business schema (SQLite). Any business maps onto: items, customers, orders, expenses, tickets."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items(sku TEXT PRIMARY KEY, name TEXT NOT NULL, price REAL NOT NULL, cost REAL DEFAULT 0,
  stock INTEGER DEFAULT 0, reorder_level INTEGER DEFAULT 0, category TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, contact TEXT DEFAULT '', notes TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, status TEXT DEFAULT 'paid',
  total REAL NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_lines(order_id INTEGER, sku TEXT, qty INTEGER, unit_price REAL, unit_cost REAL);
CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, amount REAL NOT NULL, note TEXT DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, subject TEXT, body TEXT DEFAULT '',
  status TEXT DEFAULT 'open', reply_draft TEXT DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, channel TEXT, text TEXT, status TEXT DEFAULT 'draft', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS stock_log(id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT, delta INTEGER, reason TEXT, created_at TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect(path: str | Path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(path))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init_db(path: str | Path, seed: dict | None = None, demo_history: bool = True) -> None:
    with closing(connect(path)) as c, c:
        c.executescript(SCHEMA)
        if seed and c.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0:
            for it in seed.get("items", []):
                c.execute("INSERT INTO items(sku,name,price,cost,stock,reorder_level,category) VALUES(?,?,?,?,?,?,?)",
                          (it["sku"], it["name"], it["price"], it.get("cost", 0), it.get("stock", 0),
                           it.get("reorder_level", 0), it.get("category", "")))
            for cu in seed.get("customers", []):
                c.execute("INSERT INTO customers(name,contact,notes) VALUES(?,?,?)",
                          (cu["name"], cu.get("contact", ""), cu.get("notes", "")))
            if demo_history:
                _demo_history(c)


def _demo_history(c: sqlite3.Connection) -> None:
    """A few days of fake orders/expenses/tickets so the agents have something to talk about."""
    items = c.execute("SELECT sku,price,cost FROM items WHERE price > 0 AND category != 'other'").fetchall()
    custs = [r[0] for r in c.execute("SELECT id FROM customers")]
    if not items or not custs:
        return
    for d in range(14, 0, -1):
        for k in range(2 + d % 3):
            it = items[(d + k) % len(items)]
            qty = 1 + (d + k) % 3
            ts = (datetime.now() - timedelta(days=d, hours=k)).isoformat(timespec="seconds")
            cur = c.execute("INSERT INTO orders(customer_id,status,total,created_at) VALUES(?,?,?,?)",
                            (custs[(d + k) % len(custs)], "paid", it["price"] * qty, ts))
            c.execute("INSERT INTO order_lines VALUES(?,?,?,?,?)", (cur.lastrowid, it["sku"], qty, it["price"], it["cost"]))
        if d % 5 == 0:
            c.execute("INSERT INTO expenses(category,amount,note,created_at) VALUES(?,?,?,?)",
                      ("supplies", 40.0 + d, "restock", (datetime.now() - timedelta(days=d)).isoformat(timespec="seconds")))
    c.execute("INSERT INTO tickets(customer_id,subject,body,created_at) VALUES(?,?,?,?)",
              (custs[0], "Wrong item delivered", "I ordered 2 but got 1. Can you fix this?", now()))
