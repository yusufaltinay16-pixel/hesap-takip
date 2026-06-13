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

# -----------------------
# CONFIG
# -----------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
PORT = int(os.environ.get("PORT", "10000"))

app = FastAPI(title="Katlama FULL STABLE SYSTEM")

# -----------------------
# SAFE DB LAYER
# -----------------------
def db():
    if not DATABASE_URL:
        return None
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        print("DB ERROR:", e)
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
        return
    cur = con.cursor()
    cur.execute(q, p)
    con.commit()
    cur.close()
    con.close()

# -----------------------
# CORE HELPERS
# -----------------------
def now():
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

# -----------------------
# INIT DB (SAFE)
# -----------------------
def init_db():
    con = db()
    if not con:
        print("DB yok → init skip")
        return

    c = con.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS workers(
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE,
        phone TEXT,
        token TEXT UNIQUE,
        active INT DEFAULT 1,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS products(
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE,
        firm_price FLOAT DEFAULT 0,
        worker_price FLOAT DEFAULT 0,
        active INT DEFAULT 1,
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

    c.execute("""
    CREATE TABLE IF NOT EXISTS payments(
        id SERIAL PRIMARY KEY,
        worker_id INT,
        amount FLOAT,
        pay_date TEXT,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS advances(
        id SERIAL PRIMARY KEY,
        worker_id INT,
        amount FLOAT,
        adv_date TEXT,
        created_at TEXT
    )
    """)

    con.commit()
    c.close()
    con.close()
    print("DB READY")

@app.on_event("startup")
def startup():
    try:
        init_db()
    except Exception as e:
        print("STARTUP FAIL SAFE:", e)

# -----------------------
# SIMPLE PAGE
# -----------------------
def page(title, body):
    return f"""
    <html>
    <head><meta charset="utf-8"><title>{title}</title></head>
    <body style="background:#0f172a;color:white;font-family:Arial;padding:20px">
    <h1>{title}</h1>
    {body}
    </body></html>
    """

# -----------------------
# DASHBOARD
# -----------------------
@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/dashboard")

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    c = one("SELECT COUNT(*) c FROM entries")
    count = c["c"] if c else 0
    return page("Dashboard", f"<h2>Toplam kayıt: {count}</h2>")

# -----------------------
# WORKERS FULL
# -----------------------
@app.get("/workers", response_class=HTMLResponse)
def workers():
    data = rows("SELECT * FROM workers WHERE active=1")
    html = "<h2>Çalışanlar</h2>"

    html += """
    <form method='post' action='/add-worker'>
        <input name='name' placeholder='İsim'>
        <button>Kaydet</button>
    </form>
    <hr>
    """

    for w in data:
        html += f"""
        <p>
        {w['name']}
        </p>
        """

    return page("Workers", html)

@app.post("/add-worker")
def add_worker(name: str = Form(...)):
    exec_db("""
    INSERT INTO workers(name,created_at)
    VALUES(%s,%s)
    ON CONFLICT(name) DO NOTHING
    """, (name, now()))
    return RedirectResponse("/workers", status_code=303)

# -----------------------
# PRODUCTS FULL
# -----------------------
@app.get("/products", response_class=HTMLResponse)
def products():
    data = rows("SELECT * FROM products WHERE active=1")
    html = """
    <h2>Ürünler</h2>
    <form method='post' action='/save-product'>
        <input name='name' placeholder='Ürün'>
        <input name='firm_price' type='number' placeholder='Firma'>
        <input name='worker_price' type='number' placeholder='İşçilik'>
        <button>Kaydet</button>
    </form>
    <hr>
    """

    for p in data:
        html += f"<p>{p['name']} | {p['worker_price']}</p>"

    return page("Products", html)

@app.post("/save-product")
def save_product(name: str = Form(...), firm_price: float = Form(0), worker_price: float = Form(0)):
    exec_db("""
    INSERT INTO products(name,firm_price,worker_price,created_at)
    VALUES(%s,%s,%s,%s)
    ON CONFLICT(name)
    DO UPDATE SET firm_price=EXCLUDED.firm_price,
                  worker_price=EXCLUDED.worker_price
    """, (name, firm_price, worker_price, now()))
    return RedirectResponse("/products", status_code=303)

# -----------------------
# ENTRY SYSTEM FULL CORE
# -----------------------
@app.post("/add-entry")
def add_entry(work_date: str = Form(...), worker_id: int = Form(...), product_id: int = Form(...), qty: int = Form(...)):
    p = one("SELECT * FROM products WHERE id=%s", (product_id,))
    if not p:
        return RedirectResponse("/dashboard")

    exec_db("""
    INSERT INTO entries(work_date,worker_id,product_id,qty,worker_price,created_at)
    VALUES(%s,%s,%s,%s,%s,%s)
    """, (work_date, worker_id, product_id, qty, p["worker_price"], now()))

    return RedirectResponse("/dashboard")

# -----------------------
# PAYMENTS / ADVANCES
# -----------------------
@app.get("/payments", response_class=HTMLResponse)
def payments():
    html = """
    <h2>Ödemeler</h2>

    <form method='post' action='/add-payment'>
        <input name='worker_id' placeholder='worker id'>
        <input name='amount' type='number'>
        <button>Ödeme</button>
    </form>

    <form method='post' action='/add-advance'>
        <input name='worker_id' placeholder='worker id'>
        <input name='amount' type='number'>
        <button>Avans</button>
    </form>
    """

    return page("Payments", html)

@app.post("/add-payment")
def add_payment(worker_id: int = Form(...), amount: float = Form(...)):
    exec_db("INSERT INTO payments(worker_id,amount,pay_date,created_at) VALUES(%s,%s,%s,%s)",
            (worker_id, amount, today(), now()))
    return RedirectResponse("/payments", status_code=303)

@app.post("/add-advance")
def add_advance(worker_id: int = Form(...), amount: float = Form(...)):
    exec_db("INSERT INTO advances(worker_id,amount,adv_date,created_at) VALUES(%s,%s,%s,%s)",
            (worker_id, amount, today(), now()))
    return RedirectResponse("/payments", status_code=303)

# -----------------------
# RUN SAFE
# -----------------------
if __name__ == "__main__":
    print("FULL SYSTEM STARTING")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
