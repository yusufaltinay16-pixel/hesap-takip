import os
import csv
import socket
import secrets
from pathlib import Path
from datetime import datetime, date
from typing import Optional
from urllib.parse import quote

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
import uvicorn

# ---------------------------
# CONFIG
# ---------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
PORT = int(os.environ.get("PORT", "10000"))

app = FastAPI(title="Katlama Atölyesi Stable Sistem")

DEFAULT_PUBLIC_BASE_URL = "https://katlama-sistem.onrender.com"

# ---------------------------
# HELPERS
# ---------------------------
def public_base_url():
    return (os.environ.get("PUBLIC_BASE_URL") or DEFAULT_PUBLIC_BASE_URL).strip().rstrip("/")

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def today():
    return date.today().strftime("%Y-%m-%d")

def money(v):
    try:
        return f"{float(v or 0):,.2f} ₺".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "0,00 ₺"

def num(v):
    try:
        return float(v or 0)
    except:
        return 0.0

# ---------------------------
# DB SAFE LAYER
# ---------------------------
def db():
    """DB yoksa sistemi çökertmez."""
    if not DATABASE_URL:
        return None
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        print("DB CONNECT ERROR:", e)
        return None

def rows(q, p=()):
    con = db()
    if not con:
        return []
    cur = con.cursor()
    cur.execute(q, p)
    r = cur.fetchall()
    cur.close()
    con.close()
    return r

def one(q, p=()):
    con = db()
    if not con:
        return None
    cur = con.cursor()
    cur.execute(q, p)
    r = cur.fetchone()
    cur.close()
    con.close()
    return r

def exec_db(q, p=()):
    con = db()
    if not con:
        return None
    cur = con.cursor()
    cur.execute(q, p)
    con.commit()
    cur.close()
    con.close()

# ---------------------------
# INIT DB SAFE
# ---------------------------
def init_db():
    con = db()
    if not con:
        print("DB yok → init_db skip")
        return

    c = con.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS workers(
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE,
        phone TEXT,
        token TEXT UNIQUE,
        active INTEGER DEFAULT 1,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS products(
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE,
        firm_price FLOAT DEFAULT 0,
        worker_price FLOAT DEFAULT 0,
        active INTEGER DEFAULT 1,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS entries(
        id SERIAL PRIMARY KEY,
        work_date TEXT,
        worker_id INT,
        product_id INT,
        qty INT,
        worker_price FLOAT,
        created_at TEXT
    )
    """)

    con.commit()
    c.close()
    con.close()
    print("DB INIT OK")

# ---------------------------
# STARTUP SAFE
# ---------------------------
@app.on_event("startup")
def startup():
    try:
        init_db()
    except Exception as e:
        print("STARTUP ERROR:", e)

# ---------------------------
# SIMPLE PAGE WRAPPER
# ---------------------------
def page(title, body):
    return f"""
    <html>
    <head><meta charset="utf-8"><title>{title}</title></head>
    <body style="font-family:Arial;background:#0f172a;color:white;padding:20px">
    <h1>{title}</h1>
    {body}
    </body></html>
    """

# ---------------------------
# HOME
# ---------------------------
@app.get("/")
def home():
    return RedirectResponse("/dashboard")

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    sm = rows("SELECT COUNT(*) as c FROM entries")
    count = sm[0]["c"] if sm else 0
    return page("Dashboard", f"<h2>Toplam Kayıt: {count}</h2>")

# ---------------------------
# WORKER SIMPLE
# ---------------------------
@app.get("/workers", response_class=HTMLResponse)
def workers():
    data = rows("SELECT * FROM workers WHERE active=1") or []
    html = "<h2>Workers</h2>"
    for w in data:
        html += f"<p>{w['name']}</p>"
    return page("Workers", html)

@app.post("/add-worker")
def add_worker(name: str = Form(...)):
    exec_db("INSERT INTO workers(name,created_at) VALUES(%s,%s) ON CONFLICT(name) DO NOTHING",
            (name, now_iso()))
    return RedirectResponse("/workers", status_code=303)

# ---------------------------
# PRODUCTS
# ---------------------------
@app.get("/products", response_class=HTMLResponse)
def products():
    data = rows("SELECT * FROM products WHERE active=1") or []
    html = "<h2>Products</h2>"
    for p in data:
        html += f"<p>{p['name']}</p>"
    return page("Products", html)

@app.post("/save-product")
def save_product(name: str = Form(...), firm_price: float = Form(0), worker_price: float = Form(0)):
    exec_db("""
    INSERT INTO products(name,firm_price,worker_price,created_at)
    VALUES(%s,%s,%s,%s)
    ON CONFLICT(name)
    DO UPDATE SET firm_price=EXCLUDED.firm_price, worker_price=EXCLUDED.worker_price
    """, (name, firm_price, worker_price, now_iso()))
    return RedirectResponse("/products", status_code=303)

# ---------------------------
# WORK ENTRY SAFE
# ---------------------------
@app.post("/add-entry")
def add_entry(work_date: str = Form(...), worker_id: int = Form(...), product_id: int = Form(...), qty: int = Form(...)):
    prod = one("SELECT * FROM products WHERE id=%s", (product_id,))
    if not prod:
        return RedirectResponse("/dashboard", status_code=303)

    exec_db("""
    INSERT INTO entries(work_date,worker_id,product_id,qty,worker_price,created_at)
    VALUES(%s,%s,%s,%s,%s,%s)
    """, (work_date, worker_id, product_id, qty, prod["worker_price"], now_iso()))

    return RedirectResponse("/dashboard", status_code=303)

# ---------------------------
# SAFE RUN
# ---------------------------
if __name__ == "__main__":
    print("SYSTEM STARTING...")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
