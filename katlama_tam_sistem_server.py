import os
import csv
import socket
from pathlib import Path
from datetime import datetime, date

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
import uvicorn

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
PORT = int(os.environ.get("PORT", "10000"))

app = FastAPI(title="Katlama Sistem (Temiz Versiyon)")


# ---------------- DB ----------------
def db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def rows(q, p=()):
    c = db(); cur = c.cursor(); cur.execute(q, p); r = cur.fetchall(); c.close(); return r

def one(q, p=()):
    c = db(); cur = c.cursor(); cur.execute(q, p); r = cur.fetchone(); c.close(); return r

def exec_db(q, p=()):
    c = db(); cur = c.cursor(); cur.execute(q, p); c.commit(); c.close()


# ---------------- HELPERS ----------------
def today():
    return date.today().strftime("%Y-%m-%d")

def money(v):
    try:
        return f"{float(v or 0):,.2f} ₺".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "0,00 ₺"


# ---------------- INIT ----------------
def init_db():
    con = db(); c = con.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS workers(
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE,
        active INT DEFAULT 1
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS products(
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE,
        worker_price FLOAT DEFAULT 0
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
        note TEXT
    )
    """)

    con.commit(); c.close(); con.close()


@app.on_event("startup")
def startup():
    init_db()


# ---------------- PAGE WRAPPER ----------------
def page(title, body):
    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <title>{title}</title>
        <style>
            body{{font-family:Arial;background:#0f172a;color:white;margin:0}}
            .wrap{{max-width:1200px;margin:auto;padding:20px}}
            .card{{background:#111827;padding:15px;margin:10px 0;border-radius:10px}}
            table{{width:100%;border-collapse:collapse}}
            th,td{{padding:8px;border-bottom:1px solid #333}}
            input,select{{padding:8px;width:100%}}
            .btn{{padding:8px 12px;border:0;cursor:pointer}}
            .green{{background:#22c55e}}
            .red{{background:#ef4444}}
            .yellow{{background:#f59e0b}}
        </style>
    </head>
    <body>
    <div class="wrap">
        <h2>{title}</h2>
        <a href="/dashboard">Dashboard</a> |
        <a href="/panel">Panel</a> |
        <a href="/workers">Workers</a> |
        <a href="/products">Products</a>

        {body}
    </div>
    </body>
    </html>
    """


# ---------------- DASHBOARD ----------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    sm = one("""
        SELECT
        COALESCE(SUM(qty),0) qty,
        COALESCE(SUM(qty*worker_price),0) total
        FROM entries
    """)

    body = f"""
    <div class="card">
        <h3>Toplam Adet: {sm['qty']}</h3>
        <h3>İşçilik Toplam: {money(sm['total'])}</h3>
    </div>
    """
    return page("Dashboard", body)


# ---------------- PANEL (TEK GİRİŞ) ----------------
@app.get("/panel", response_class=HTMLResponse)
def panel():
    workers = rows("SELECT * FROM workers WHERE active=1")
    products = rows("SELECT * FROM products")

    wopt = "".join([f"<option value='{w['id']}'>{w['name']}</option>" for w in workers])
    popt = "".join([f"<option value='{p['id']}'>{p['name']}</option>" for p in products])

    last = rows("""
        SELECT e.*, w.name worker, p.name product
        FROM entries e
        JOIN workers w ON w.id=e.worker_id
        JOIN products p ON p.id=e.product_id
        ORDER BY e.id DESC LIMIT 30
    """)

    trs = "".join([f"""
        <tr>
            <td>{r['id']}</td>
            <td>{r['work_date']}</td>
            <td>{r['worker']}</td>
            <td>{r['product']}</td>
            <td>{r['qty']}</td>
            <td>{r['qty']*r['worker_price']}</td>
            <td>{r['note'] or ''}</td>
        </tr>
    """ for r in last])

    body = f"""
    <div class="card">
        <form method="post" action="/panel/add">
            <label>Worker</label>
            <select name="worker_id">{wopt}</select>

            <label>Product</label>
            <select name="product_id">{popt}</select>

            <label>Qty</label>
            <input name="qty" type="number" required>

            <label>Date</label>
            <input name="work_date" value="{today()}">

            <label>Note</label>
            <input name="note">

            <br><br>
            <button class="btn green">Kaydet</button>
        </form>
    </div>

    <div class="card">
        <table>
        <tr><th>ID</th><th>Tarih</th><th>Çalışan</th><th>Ürün</th><th>Adet</th><th>Hakediş</th><th>Not</th></tr>
        {trs}
        </table>
    </div>
    """
    return page("Panel", body)


@app.post("/panel/add")
def panel_add(worker_id: int = Form(...),
              product_id: int = Form(...),
              qty: int = Form(...),
              work_date: str = Form(...),
              note: str = Form("")):

    product = one("SELECT * FROM products WHERE id=%s", (product_id,))

    exec_db("""
        INSERT INTO entries(work_date,worker_id,product_id,qty,worker_price,note)
        VALUES(%s,%s,%s,%s,%s,%s)
    """, (work_date, worker_id, product_id, qty, product["worker_price"], note))

    return RedirectResponse("/panel", status_code=303)


# ---------------- WORKERS ----------------
@app.get("/workers", response_class=HTMLResponse)
def workers():
    data = rows("""
        SELECT w.*,
        COALESCE(SUM(e.qty),0) qty,
        COALESCE(SUM(e.qty*e.worker_price),0) earned
        FROM workers w
        LEFT JOIN entries e ON e.worker_id=w.id
        WHERE w.active=1
        GROUP BY w.id
    """)

    trs = "".join([f"""
        <tr>
        <td>{r['id']}</td>
        <td>{r['name']}</td>
        <td>{r['qty']}</td>
        <td>{money(r['earned'])}</td>
        </tr>
    """ for r in data])

    return page("Workers", f"""
    <div class="card">
        <form method="post" action="/add-worker">
            <input name="name" placeholder="Worker name">
            <button class="btn green">Add</button>
        </form>
    </div>

    <div class="card">
        <table>
        <tr><th>ID</th><th>Name</th><th>Qty</th><th>Earned</th></tr>
        {trs}
        </table>
    </div>
    """)


@app.post("/add-worker")
def add_worker(name: str = Form(...)):
    exec_db("INSERT INTO workers(name) VALUES(%s) ON CONFLICT DO NOTHING", (name,))
    return RedirectResponse("/workers", status_code=303)


# ---------------- PRODUCTS ----------------
@app.get("/products", response_class=HTMLResponse)
def products():
    data = rows("SELECT * FROM products")

    trs = "".join([f"""
        <tr>
        <td>{p['id']}</td>
        <td>{p['name']}</td>
        <td>{p['worker_price']}</td>
        </tr>
    """ for p in data])

    return page("Products", f"""
    <div class="card">
        <form method="post" action="/add-product">
            <input name="name" placeholder="Product">
            <input name="worker_price" type="number">
            <button class="btn green">Add</button>
        </form>
    </div>

    <div class="card">
        <table>
        <tr><th>ID</th><th>Name</th><th>Price</th></tr>
        {trs}
        </table>
    </div>
    """)


@app.post("/add-product")
def add_product(name: str = Form(...), worker_price: float = Form(...)):
    exec_db("INSERT INTO products(name,worker_price) VALUES(%s,%s) ON CONFLICT DO NOTHING", (name, worker_price))
    return RedirectResponse("/products", status_code=303)


# ---------------- MAIN ----------------
@app.get("/")
def root():
    return RedirectResponse("/dashboard")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
