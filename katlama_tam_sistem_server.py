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
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
import uvicorn

# Render Environment içine DATABASE_URL olarak Supabase bağlantını yazmalısın.
# Örnek:
# postgresql://postgres.xxxxx:şifre@aws-0-eu-west-1.pooler.supabase.com:6543/postgres
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
PORT = int(os.environ.get("PORT", "10000"))

app = FastAPI(title="Katlama Atölyesi Tam Sistem")


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def today():
    return date.today().strftime("%Y-%m-%d")


def this_month():
    return date.today().strftime("%Y-%m")


def money(v):
    try:
        return f"{float(v):,.2f} ₺".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00 ₺"


def db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL yok. Render > Environment kısmına Supabase DATABASE_URL ekle.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def rows(q, p=()):
    con = db()
    cur = con.cursor()
    cur.execute(q, p)
    r = cur.fetchall()
    cur.close()
    con.close()
    return r


def one(q, p=()):
    con = db()
    cur = con.cursor()
    cur.execute(q, p)
    r = cur.fetchone()
    cur.close()
    con.close()
    return r


def exec_db(q, p=()):
    con = db()
    cur = con.cursor()
    cur.execute(q, p)
    last = None
    try:
        if cur.description:
            row = cur.fetchone()
            if row:
                last = list(row.values())[0]
    except Exception:
        last = None
    con.commit()
    cur.close()
    con.close()
    return last


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def product_key(name: str):
    return " ".join((name or "").strip().split()).casefold()


def init_db():
    con = db()
    c = con.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS workers(
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        phone TEXT,
        token TEXT UNIQUE,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS products(
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        firm_price DOUBLE PRECISION NOT NULL DEFAULT 0,
        worker_price DOUBLE PRECISION NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS entries(
        id SERIAL PRIMARY KEY,
        work_date TEXT NOT NULL,
        worker_id INTEGER NOT NULL REFERENCES workers(id),
        product_id INTEGER NOT NULL REFERENCES products(id),
        qty INTEGER NOT NULL,
        firm_price DOUBLE PRECISION NOT NULL,
        worker_price DOUBLE PRECISION NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL,
        source TEXT DEFAULT 'telefon'
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS payments(
        id SERIAL PRIMARY KEY,
        pay_date TEXT NOT NULL,
        worker_id INTEGER NOT NULL REFERENCES workers(id),
        amount DOUBLE PRECISION NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS advances(
        id SERIAL PRIMARY KEY,
        adv_date TEXT NOT NULL,
        worker_id INTEGER NOT NULL REFERENCES workers(id),
        amount DOUBLE PRECISION NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS partners(
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS partner_advances(
        id SERIAL PRIMARY KEY,
        adv_date TEXT NOT NULL,
        partner_id INTEGER NOT NULL REFERENCES partners(id),
        amount DOUBLE PRECISION NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS expenses(
        id SERIAL PRIMARY KEY,
        exp_date TEXT NOT NULL,
        category TEXT NOT NULL,
        amount DOUBLE PRECISION NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS deliveries(
        id SERIAL PRIMARY KEY,
        deliv_date TEXT NOT NULL,
        worker_id INTEGER REFERENCES workers(id),
        product_id INTEGER NOT NULL REFERENCES products(id),
        firm_qty INTEGER NOT NULL DEFAULT 0,
        worker_qty INTEGER NOT NULL DEFAULT 0,
        note TEXT,
        created_at TEXT NOT NULL
    )
    """)

    for name, firm_price, worker_price in [("Eşarp", 0, 0), ("Şal", 0, 0), ("Tekstil Ürün", 0, 0)]:
        c.execute("""
        INSERT INTO products(name, firm_price, worker_price, active, created_at)
        VALUES(%s,%s,%s,%s,%s)
        ON CONFLICT(name) DO NOTHING
        """, (name, firm_price, worker_price, 1, now_iso()))

    for pname in ["yusuf altınay", "mine ulu", "emine erol"]:
        c.execute("""
        INSERT INTO partners(name, active, created_at)
        VALUES(%s,%s,%s)
        ON CONFLICT(name) DO NOTHING
        """, (pname, 1, now_iso()))

    c.execute("SELECT id FROM workers WHERE token IS NULL OR token='' ")
    for r in c.fetchall():
        c.execute("UPDATE workers SET token=%s WHERE id=%s", (secrets.token_urlsafe(12), r["id"]))

    con.commit()
    c.close()
    con.close()


CSS = """
<style>
:root{--bg:#08111f;--card:#121a2d;--card2:#0f172a;--line:#25314a;--text:#f8fafc;--muted:#aab3c5;--green:#22c55e;--red:#ef4444;--blue:#3b82f6;--yellow:#f59e0b;--purple:#8b5cf6;--cyan:#06b6d4}
*{box-sizing:border-box}body{margin:0;font-family:Arial,Segoe UI,sans-serif;background:linear-gradient(135deg,#06101f,#111827 60%,#08111f);color:var(--text)}
.wrap{max-width:1280px;margin:0 auto;padding:14px 14px 90px}.top{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:12px}
h1{font-size:24px;margin:8px 0}h2{margin:8px 0 14px}a{color:white;text-decoration:none}.nav{display:flex;gap:8px;flex-wrap:wrap}
.nav a,.btn{background:var(--blue);border:0;color:white;padding:11px 14px;border-radius:12px;font-weight:800;cursor:pointer;display:inline-block;box-shadow:0 8px 18px #0003}
.btn.green{background:var(--green);color:#06130b}.btn.red{background:var(--red)}.btn.gray{background:#334155}.btn.yellow{background:var(--yellow);color:#1b1100}.btn.purple{background:var(--purple)}.btn.cyan{background:var(--cyan);color:#031014}
.card{background:rgba(18,26,45,.94);border:1px solid var(--line);border-radius:18px;padding:15px;margin:12px 0;box-shadow:0 14px 34px #0005}.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
label{font-size:13px;color:var(--muted);display:block;margin-bottom:5px;font-weight:700}input,select,textarea{width:100%;padding:13px;border-radius:12px;border:1px solid var(--line);background:#0f172a;color:white;font-size:16px}
table{width:100%;border-collapse:separate;border-spacing:0;background:var(--card);border-radius:14px;overflow:hidden;table-layout:fixed}
th,td{border-bottom:1px solid var(--line);padding:12px 14px;vertical-align:middle;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
th{color:#cbd5e1;background:#111827;text-align:left;font-size:14px}
td{font-size:15px}
th.right,td.right{text-align:right}
th.center,td.center{text-align:center}
.right{text-align:right}.center{text-align:center}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.kpis.three{grid-template-columns:repeat(3,1fr)}.kpi{background:linear-gradient(180deg,#111827,#0f172a);border:1px solid var(--line);border-radius:16px;padding:15px;min-height:82px}.kpi b{font-size:24px;display:block;margin-top:6px}.kpi span{color:var(--muted);font-size:13px;font-weight:700}
.notice{background:#052e1a;border:1px solid #166534;color:#dcfce7;padding:10px;border-radius:12px;margin:10px 0}.bad{background:#3b1111;border:1px solid #7f1d1d;color:#fee2e2;padding:10px;border-radius:12px;margin:10px 0}.copy{font-size:12px;word-break:break-all;color:#dbeafe}.small{font-size:12px;color:var(--muted)}
.worker-hero{background:linear-gradient(135deg,#172554,#0f172a 55%,#052e1a);border:1px solid #334155;border-radius:24px;padding:18px;box-shadow:0 18px 45px #0008}.worker-title{font-size:28px;font-weight:900;margin:0 0 8px}.worker-sub{color:#cbd5e1;margin-bottom:12px}.worker-form input,.worker-form select{font-size:20px;padding:16px}.worker-form button{font-size:20px;padding:16px 22px;width:100%}
.diff-plus{color:#22c55e;font-weight:900}.diff-minus{color:#ef4444;font-weight:900}.diff-zero{color:#cbd5e1;font-weight:900}
@media(max-width:900px){.grid,.kpis,.kpis.three{grid-template-columns:1fr}h1{font-size:20px}table{font-size:13px}th,td{padding:8px}.nav a,.btn{width:100%;text-align:center}.worker-title{font-size:24px}}
</style>
"""


def page(title, body, nav=True):
    nav_html = ""
    if nav:
        nav_html = """<div class="nav">
<a href="/dashboard">Ana Panel</a><a href="/workers">Eleman Linkleri</a><a href="/products">Ürün/Fiyat</a><a href="/deliveries">Firma Teslim</a><a href="/expenses">Masraflar</a><a href="/partners">Ortaklar Hesap</a><a href="/payments">Ödemeler</a><a href="/month">Ay Sonu</a>
</div>"""
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>{CSS}</head><body><div class="wrap"><div class="top"><h1>{title}</h1>{nav_html}</div>{body}</div></body></html>"""


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/dashboard", status_code=303)


def total_summary():
    """
    GENEL TOPLAM:
    Tarih filtresi yok.
    Firma hak edişi sadece firmaya teslim edilen adet üzerinden hesaplanır.
    İşçilik elemanların girdiği adet üzerinden hesaplanır.
    Masraf tüm masraflardan düşer.
    """
    firma = one("""
        SELECT 
            COALESCE(SUM(d.firm_qty),0) qty,
            COALESCE(SUM(d.firm_qty * p.firm_price),0) revenue
        FROM deliveries d
        JOIN products p ON p.id=d.product_id
    """)

    labor_row = one("""
        SELECT COALESCE(SUM(e.qty * e.worker_price),0) labor_cost
        FROM entries e
    """)

    exp = one("SELECT COALESCE(SUM(amount),0) total FROM expenses")["total"] or 0
    paid = one("SELECT COALESCE(SUM(amount),0) total FROM payments")["total"] or 0
    advance = one("SELECT COALESCE(SUM(amount),0) total FROM advances")["total"] or 0

    qty = firma["qty"] or 0
    revenue = firma["revenue"] or 0
    labor = labor_row["labor_cost"] or 0

    return {
        "qty": qty,
        "revenue": revenue,
        "labor": labor,
        "expense": exp,
        "gross": revenue - labor,
        "net": revenue - labor - exp,
        "paid": paid,
        "advance": advance,
        "labor_remaining": labor - paid - advance
    }


def month_summary(m):
    """
    Ay sonu sayfası için aylık rapor.
    Ana panel artık bunu kullanmaz.
    """
    like = m + "%"

    firma = one("""
        SELECT 
            COALESCE(SUM(d.firm_qty),0) qty,
            COALESCE(SUM(d.firm_qty * p.firm_price),0) revenue
        FROM deliveries d
        JOIN products p ON p.id=d.product_id
        WHERE d.deliv_date LIKE %s
    """, (like,))

    labor_row = one("""
        SELECT COALESCE(SUM(e.qty * e.worker_price),0) labor_cost
        FROM entries e
        WHERE e.work_date LIKE %s
    """, (like,))

    exp = one("SELECT COALESCE(SUM(amount),0) total FROM expenses WHERE exp_date LIKE %s", (like,))["total"] or 0
    paid = one("SELECT COALESCE(SUM(amount),0) total FROM payments WHERE pay_date LIKE %s", (like,))["total"] or 0
    advance = one("SELECT COALESCE(SUM(amount),0) total FROM advances WHERE adv_date LIKE %s", (like,))["total"] or 0

    qty = firma["qty"] or 0
    revenue = firma["revenue"] or 0
    labor = labor_row["labor_cost"] or 0

    return {
        "qty": qty,
        "revenue": revenue,
        "labor": labor,
        "expense": exp,
        "gross": revenue - labor,
        "net": revenue - labor - exp,
        "paid": paid,
        "advance": advance,
        "labor_remaining": labor - paid - advance
    }


def diff_class(v):
    v = int(v or 0)
    if v > 0:
        return "diff-plus"
    if v < 0:
        return "diff-minus"
    return "diff-zero"


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    sm = total_summary()

    data = rows("""
    SELECT e.id,e.work_date,w.name worker,p.name product,e.qty,e.firm_price,e.worker_price,
           e.qty*e.firm_price revenue,e.qty*e.worker_price labor,e.qty*(e.firm_price-e.worker_price) gross,
           COALESCE(e.note,'') note,e.source
    FROM entries e JOIN workers w ON w.id=e.worker_id JOIN products p ON p.id=e.product_id
    ORDER BY e.work_date DESC,e.id DESC LIMIT 300
    """)

    trs = "".join([
        f"""<tr><td>{r['id']}</td><td>{r['work_date']}</td><td>{r['worker']}</td><td>{r['product']}</td><td class="right">{r['qty']}</td><td class="right">{money(r['revenue'])}</td><td class="right">{money(r['labor'])}</td><td class="right">{money(r['gross'])}</td><td>{r['note']}</td><td><a class="btn red" href="/delete-entry/{r['id']}" onclick="return confirm('Bu kayıt silinsin mi?')">Sil</a></td></tr>"""
        for r in data
    ])

    compare = rows("""
    SELECT p.name product, 
           COALESCE(fd.firm_qty,0) firm_qty, 
           COALESCE(en.worker_qty,0) worker_qty,
           COALESCE(en.worker_qty,0)-COALESCE(fd.firm_qty,0) diff
    FROM products p
    LEFT JOIN (SELECT product_id,SUM(firm_qty) firm_qty FROM deliveries GROUP BY product_id) fd ON fd.product_id=p.id
    LEFT JOIN (SELECT product_id,SUM(qty) worker_qty FROM entries GROUP BY product_id) en ON en.product_id=p.id
    WHERE p.active=1 AND (COALESCE(fd.firm_qty,0)>0 OR COALESCE(en.worker_qty,0)>0)
    ORDER BY p.name
    """)

    comp_tr = "".join([
        f"<tr><td>{r['product']}</td><td class='right'>{int(r['firm_qty'] or 0)}</td><td class='right'>{int(r['worker_qty'] or 0)}</td><td class='right {diff_class(r['diff'])}'>{int(r['diff'] or 0)}</td></tr>"
        for r in compare
    ]) or "<tr><td colspan='4' class='center small'>Henüz kayıt yok.</td></tr>"

    body = f"""
    <div class="card">
        <div class="notice">
            Ana panel artık tarih aralığı kullanmaz. Buradaki rakamlar tüm kayıtların genel toplamıdır. Avanslar eleman alacağından düşer.
        </div>
    </div>

    <div class="kpis">
        <div class="kpi"><span>Firma Teslim Adet</span><b>{int(sm['qty'])}</b></div>
        <div class="kpi"><span>Firma Hak Ediş</span><b>{money(sm['revenue'])}</b></div>
        <div class="kpi"><span>İşçilik</span><b>{money(sm['labor'])}</b></div>
        <div class="kpi"><span>Masraflar</span><b>{money(sm['expense'])}</b></div>
        <div class="kpi"><span>Net Kazanç</span><b>{money(sm['net'])}</b></div>
    </div>

    <div class="card">
        <h2>Firma vs Eleman Genel Karşılaştırma</h2>
        <p class="small">Tarih fark etmeksizin tüm firma teslim kayıtları ve tüm eleman katlama adetleri karşılaştırılır.</p>
        <table>
            <colgroup>
                <col style="width:28%">
                <col style="width:24%">
                <col style="width:24%">
                <col style="width:24%">
            </colgroup>
            <tr>
                <th>Ürün</th>
                <th class="right">Firma Teslim Adet</th>
                <th class="right">Eleman Katlama Adet</th>
                <th class="right">Fark</th>
            </tr>
            {comp_tr}
        </table>
    </div>

    <div class="card">
        <h2>Son Eleman Kayıtları</h2>
        <table>
            <colgroup>
                <col style="width:6%">
                <col style="width:11%">
                <col style="width:13%">
                <col style="width:13%">
                <col style="width:8%">
                <col style="width:11%">
                <col style="width:11%">
                <col style="width:11%">
                <col style="width:10%">
                <col style="width:7%">
            </colgroup>
            <tr>
                <th>ID</th>
                <th>Tarih</th>
                <th>Eleman</th>
                <th>Ürün</th>
                <th class="right">Adet</th>
                <th class="right">Eski Ciro</th>
                <th class="right">İşçilik</th>
                <th class="right">Eski Brüt</th>
                <th>Not</th>
                <th>İşlem</th>
            </tr>
            {trs}
        </table>
        <p class="small">Not: Para hesabında firma hak edişi eleman adedinden değil, firma teslim adedinden hesaplanır.</p>
    </div>
    """
    return page("Katlama Atölyesi Ana Panel", body)


@app.get("/w/{token}", response_class=HTMLResponse)
def worker_page(token: str, saved: Optional[str] = None, error: Optional[str] = None):
    worker = one("SELECT * FROM workers WHERE token=%s AND active=1", (token,))
    if not worker:
        return page("Link Geçersiz", "<div class='bad'>Bu eleman linki geçersiz veya pasif.</div>", nav=False)
    products = rows("SELECT id,name,worker_price FROM products WHERE active=1 ORDER BY name")
    product_opts = "".join([f"<option value='{p['id']}'>{p['name']}</option>" for p in products])

    total = one("SELECT COALESCE(SUM(qty),0) qty, COALESCE(SUM(qty*worker_price),0) earned FROM entries WHERE worker_id=%s", (worker["id"],))
    adv_total = one("SELECT COALESCE(SUM(amount),0) total FROM advances WHERE worker_id=%s", (worker["id"],))["total"] or 0
    today_total = one("SELECT COALESCE(SUM(qty),0) qty FROM entries WHERE worker_id=%s AND work_date=%s", (worker["id"], today()))

    msg = "<div class='notice'>Adet kaydedildi.</div>" if saved else ""
    if error:
        msg = f"<div class='bad'>{error}</div>"
    last_rows = rows("""
    SELECT e.id,e.work_date,p.name product,e.qty,e.qty*e.worker_price earned,COALESCE(e.note,'') note
    FROM entries e JOIN products p ON p.id=e.product_id WHERE e.worker_id=%s ORDER BY e.work_date DESC,e.id DESC LIMIT 20
    """, (worker["id"],))
    trs = "".join([f"""<tr><td>{r['work_date']}</td><td>{r['product']}</td><td class='right'>{r['qty']}</td><td class='right'>{money(r['earned'])}</td><td><a class="btn yellow" href="/w/{token}/edit/{r['id']}">Güncelle</a> <a class="btn red" href="/w/{token}/delete/{r['id']}" onclick="return confirm('Bu kayıt silinsin mi?')">Sil</a></td></tr>""" for r in last_rows])
    body = f"""
    {msg}<div class="worker-hero"><div class="worker-title">{worker['name']} - Katlama Paneli</div><div class="worker-sub">Adetini gir, kendi kayıtlarını gör, yanlışsa güncelle veya sil.</div><div class="kpis three"><div class="kpi"><span>Bugünkü Adedim</span><b>{int(today_total['qty'] or 0)}</b></div><div class="kpi"><span>Genel Hak Edişim</span><b>{money(total['earned'] or 0)}</b></div><div class="kpi"><span>Avans Sonrası Kalan</span><b>{money((total['earned'] or 0) - adv_total)}</b></div></div></div>
    <div class="card worker-form"><h2>Adet Gir</h2><form method="post" action="/w/{token}/add"><div class="grid"><div><label>Tarih</label><input name="work_date" value="{today()}" required></div><div><label>Ürün</label><select name="product_id" required>{product_opts}</select></div><div><label>Adet</label><input name="qty" type="number" min="1" required autofocus></div><div style="grid-column:span 2"><label>Not</label><input name="note" placeholder="İsteğe bağlı"></div></div><br><button class="btn green" type="submit">ADETİ KAYDET</button></form></div>
    <div class="card"><h2>Son Kayıtlarım</h2><table><tr><th>Tarih</th><th>Ürün</th><th>Adet</th><th>Hak Ediş</th><th>İşlem</th></tr>{trs}</table></div>
    """
    return page("Benim Katlama Programım", body, nav=False)


@app.post("/w/{token}/add")
def worker_add(token: str, work_date: str = Form(...), product_id: int = Form(...), qty: int = Form(...), note: str = Form("")):
    worker = one("SELECT * FROM workers WHERE token=%s AND active=1", (token,))
    if not worker:
        return RedirectResponse(f"/w/{token}?error=Link geçersiz", status_code=303)
    product = one("SELECT * FROM products WHERE id=%s AND active=1", (product_id,))
    if not product:
        return RedirectResponse(f"/w/{token}?error=Ürün bulunamadı", status_code=303)
    try:
        datetime.strptime(work_date, "%Y-%m-%d")
        qty = int(qty)
        if qty <= 0:
            raise ValueError()
    except Exception:
        return RedirectResponse(f"/w/{token}?error=Tarih veya adet hatalı", status_code=303)
    exec_db("INSERT INTO entries(work_date,worker_id,product_id,qty,firm_price,worker_price,note,created_at,source) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)", (work_date, worker["id"], product_id, qty, float(product["firm_price"] or 0), float(product["worker_price"] or 0), note, now_iso(), "whatsapp-link"))
    return RedirectResponse(f"/w/{token}?saved=1", status_code=303)


@app.get("/w/{token}/edit/{entry_id}", response_class=HTMLResponse)
def worker_edit_page(token: str, entry_id: int):
    worker = one("SELECT * FROM workers WHERE token=%s AND active=1", (token,))
    if not worker:
        return page("Link Geçersiz", "<div class='bad'>Bu eleman linki geçersiz veya pasif.</div>", nav=False)
    entry = one("SELECT e.*, p.name product FROM entries e JOIN products p ON p.id=e.product_id WHERE e.id=%s AND e.worker_id=%s", (entry_id, worker["id"]))
    if not entry:
        return page("Kayıt Bulunamadı", "<div class='bad'>Bu kayıt bulunamadı veya sana ait değil.</div>", nav=False)
    products = rows("SELECT id,name FROM products WHERE active=1 ORDER BY name")
    opts = "".join([f"<option value='{p['id']}' {'selected' if p['id'] == entry['product_id'] else ''}>{p['name']}</option>" for p in products])
    body = f"""<div class="card"><h2>Kayıt Güncelle</h2><form method="post" action="/w/{token}/edit/{entry_id}"><div class="grid"><div><label>Tarih</label><input name="work_date" value="{entry['work_date']}" required></div><div><label>Ürün</label><select name="product_id" required>{opts}</select></div><div><label>Adet</label><input name="qty" type="number" min="1" value="{entry['qty']}" required autofocus></div><div style="grid-column:span 2"><label>Not</label><input name="note" value="{entry['note'] or ''}"></div></div><br><button class="btn green" type="submit">Güncellemeyi Kaydet</button> <a class="btn gray" href="/w/{token}">Geri Dön</a></form></div>"""
    return page("Kayıt Güncelle", body, nav=False)


@app.post("/w/{token}/edit/{entry_id}")
def worker_edit_save(token: str, entry_id: int, work_date: str = Form(...), product_id: int = Form(...), qty: int = Form(...), note: str = Form("")):
    worker = one("SELECT * FROM workers WHERE token=%s AND active=1", (token,))
    if not worker:
        return RedirectResponse(f"/w/{token}?error=Link geçersiz", status_code=303)
    product = one("SELECT * FROM products WHERE id=%s AND active=1", (product_id,))
    if not product:
        return RedirectResponse(f"/w/{token}?error=Ürün bulunamadı", status_code=303)
    try:
        datetime.strptime(work_date, "%Y-%m-%d")
        qty = int(qty)
        if qty <= 0:
            raise ValueError()
    except Exception:
        return RedirectResponse(f"/w/{token}?error=Tarih veya adet hatalı", status_code=303)
    exec_db("UPDATE entries SET work_date=%s, product_id=%s, qty=%s, firm_price=%s, worker_price=%s, note=%s WHERE id=%s AND worker_id=%s", (work_date, product_id, qty, float(product["firm_price"] or 0), float(product["worker_price"] or 0), note, entry_id, worker["id"]))
    return RedirectResponse(f"/w/{token}?saved=1", status_code=303)


@app.get("/w/{token}/delete/{entry_id}")
def worker_delete_entry(token: str, entry_id: int):
    worker = one("SELECT * FROM workers WHERE token=%s AND active=1", (token,))
    if worker:
        exec_db("DELETE FROM entries WHERE id=%s AND worker_id=%s", (entry_id, worker["id"]))
    return RedirectResponse(f"/w/{token}?saved=1", status_code=303)


@app.get("/workers", response_class=HTMLResponse)
def workers(request: Request):
    data = rows("SELECT id,name,phone,token,active FROM workers ORDER BY active DESC,name")
    base = str(request.base_url).rstrip("/")
    trs = ""
    for r in data:
        link = f"{base}/w/{r['token']}"
        wa_msg = f"""Merhaba {r['name']}

Katlama adet giriş linkin:
{link}

Linke tıkla, açılmazsa kopyalayıp Chrome'a yapıştır."""
        wa_text = quote(wa_msg)
        trs += f"""<tr><td>{r['id']}</td><td>{r['name']}</td><td>{r['phone'] or ''}</td><td>{'Aktif' if r['active'] else 'Pasif'}</td><td><span class="copy" id="link_{r['id']}">{link}</span><br><button class="btn gray" type="button" onclick="copyLink('link_{r['id']}')">Linki Kopyala</button></td><td><a class="btn green" target="_blank" href="https://wa.me/?text={wa_text}">WhatsApp'a At</a></td><td><a class="btn yellow" href="/worker-new-link/{r['id']}">Yeni Link</a></td><td><a class="btn red" href="/worker-off/{r['id']}">Pasifleştir</a></td></tr>"""
    body = f"""<div class="card"><h2>Eleman Ekle</h2><form method="post" action="/add-worker"><div class="grid"><div><label>Ad Soyad</label><input name="name" required></div><div><label>Telefon</label><input name="phone" placeholder="05xx..."></div></div><br><button class="btn green">Eleman Ekle</button></form></div><div class="card"><h2>WhatsApp Özel Linkleri</h2><p class="small">Her elemana ayrı link gider. Eleman sadece kendi ekranını görür.</p><table><tr><th>ID</th><th>Eleman</th><th>Telefon</th><th>Durum</th><th>Özel Link</th><th>WhatsApp</th><th>Link Yenile</th><th>İşlem</th></tr>{trs}</table></div><script>function copyLink(id){{const text=document.getElementById(id).innerText.trim();navigator.clipboard.writeText(text).then(function(){{alert('Link kopyalandı.')}}).catch(function(){{prompt('Linki kopyala:',text);}});}}</script>"""
    return page("Elemanlar ve WhatsApp Linkleri", body)


@app.post("/add-worker")
def add_worker(name: str = Form(...), phone: str = Form("")):
    name = name.strip(); phone = phone.strip()
    if name:
        old = one("SELECT id FROM workers WHERE name=%s", (name,))
        if old:
            exec_db("UPDATE workers SET active=1, phone=COALESCE(NULLIF(%s,''),phone) WHERE name=%s", (phone, name))
        else:
            exec_db("INSERT INTO workers(name,phone,token,active,created_at) VALUES(%s,%s,%s,%s,%s)", (name, phone, secrets.token_urlsafe(12), 1, now_iso()))
    return RedirectResponse("/workers", status_code=303)


@app.get("/worker-new-link/{worker_id}")
def worker_new_link(worker_id: int):
    exec_db("UPDATE workers SET token=%s WHERE id=%s", (secrets.token_urlsafe(12), worker_id))
    return RedirectResponse("/workers", status_code=303)


@app.get("/worker-off/{worker_id}")
def worker_off(worker_id: int):
    exec_db("UPDATE workers SET active=0 WHERE id=%s", (worker_id,))
    return RedirectResponse("/workers", status_code=303)


@app.get("/products", response_class=HTMLResponse)
def products():
    data = rows("SELECT id,name,firm_price,worker_price,active FROM products ORDER BY active DESC,name")
    trs = "".join([f"""<tr><td>{r['id']}</td><td>{r['name']}</td><td class='right'>{money(r['firm_price'])}</td><td class='right'>{money(r['worker_price'])}</td><td class='right'>{money((r['firm_price'] or 0)-(r['worker_price'] or 0))}</td><td>{'Aktif' if r['active'] else 'Pasif'}</td><td><a class='btn red' href='/delete-product/{r['id']}' onclick="return confirm('Bu ürün silinsin mi? Kayıtlarda kullanıldıysa sadece pasif yapılır.')">Sil</a></td></tr>""" for r in data])
    body = f"""<div class="card"><h2>Ürün ve Fiyatlar</h2><form method="post" action="/add-product"><div class="grid"><div><label>Ürün adı</label><input name="name" required></div><div><label>Firmadan Aldığın Ücret / Adet</label><input name="firm_price" type="number" step="0.01" min="0" required></div><div><label>Elemana Verdiğin Ücret / Adet</label><input name="worker_price" type="number" step="0.01" min="0" required></div></div><br><button class="btn green">Kaydet / Güncelle</button></form></div><div class="card"><table><tr><th>ID</th><th>Ürün</th><th>Firma Ücreti</th><th>Eleman Ücreti</th><th>Adet Başı Brüt</th><th>Durum</th><th>İşlem</th></tr>{trs}</table></div>"""
    return page("Ürün / Firma Ücreti / Eleman Ücreti", body)


@app.post("/add-product")
def add_product(name: str = Form(...), firm_price: float = Form(...), worker_price: float = Form(...)):
    name = " ".join(name.strip().split())
    if not name:
        return RedirectResponse("/products", status_code=303)
    all_products = rows("SELECT id,name FROM products")
    old_id = None
    for p in all_products:
        if product_key(p["name"]) == product_key(name):
            old_id = p["id"]
            break
    if old_id:
        exec_db("UPDATE products SET name=%s, firm_price=%s, worker_price=%s, active=1 WHERE id=%s", (name, firm_price, worker_price, old_id))
    else:
        exec_db("INSERT INTO products(name,firm_price,worker_price,active,created_at) VALUES(%s,%s,%s,%s,%s)", (name, firm_price, worker_price, 1, now_iso()))
    return RedirectResponse("/products", status_code=303)


@app.get("/delete-product/{product_id}")
def delete_product(product_id: int):
    used1 = one("SELECT id FROM entries WHERE product_id=%s LIMIT 1", (product_id,))
    used2 = one("SELECT id FROM deliveries WHERE product_id=%s LIMIT 1", (product_id,))
    if used1 or used2:
        exec_db("UPDATE products SET active=0 WHERE id=%s", (product_id,))
    else:
        exec_db("DELETE FROM products WHERE id=%s", (product_id,))
    return RedirectResponse("/products", status_code=303)


@app.get("/deliveries", response_class=HTMLResponse)
def deliveries():
    products = rows("SELECT id,name FROM products WHERE active=1 ORDER BY name")
    popts = "".join([f"<option value='{p['id']}'>{p['name']}</option>" for p in products])

    data = rows("""
    SELECT d.*, p.name product
    FROM deliveries d JOIN products p ON p.id=d.product_id
    ORDER BY d.deliv_date DESC,d.id DESC
    LIMIT 500
    """)

    trs = "".join([
        f"<tr><td>{r['id']}</td><td>{r['deliv_date']}</td><td>{r['product']}</td><td class='right'>{int(r['firm_qty'] or 0)}</td><td>{r['note'] or ''}</td><td><a class='btn red' href='/delete-delivery/{r['id']}' onclick=\"return confirm('Teslim kaydı silinsin mi?')\">Sil</a></td></tr>"
        for r in data
    ]) or "<tr><td colspan='6' class='center small'>Teslim kaydı yok.</td></tr>"

    summary = rows("""
    SELECT p.name product, COALESCE(fd.firm_qty,0) firm_qty, COALESCE(en.worker_qty,0) worker_qty, COALESCE(en.worker_qty,0)-COALESCE(fd.firm_qty,0) diff
    FROM products p
    LEFT JOIN (SELECT product_id,SUM(firm_qty) firm_qty FROM deliveries GROUP BY product_id) fd ON fd.product_id=p.id
    LEFT JOIN (SELECT product_id,SUM(qty) worker_qty FROM entries GROUP BY product_id) en ON en.product_id=p.id
    WHERE p.active=1 AND (COALESCE(fd.firm_qty,0)>0 OR COALESCE(en.worker_qty,0)>0)
    ORDER BY p.name
    """)

    sum_tr = "".join([
        f"<tr><td>{r['product']}</td><td class='right'>{int(r['firm_qty'] or 0)}</td><td class='right'>{int(r['worker_qty'] or 0)}</td><td class='right {diff_class(r['diff'])}'>{int(r['diff'] or 0)}</td></tr>"
        for r in summary
    ]) or "<tr><td colspan='4' class='center small'>Özet yok.</td></tr>"

    total_firm = one("SELECT COALESCE(SUM(firm_qty),0) total FROM deliveries")["total"] or 0

    body = f"""
    <div class="kpis three">
        <div class="kpi"><span>Genel Firma Teslim Adet</span><b>{int(total_firm)}</b></div>
        <div class="kpi"><span>Kayıt Sistemi</span><b>Her Giriş Ayrı</b></div>
        <div class="kpi"><span>Tarih Filtresi</span><b>Yok</b></div>
    </div>

    <div class="card">
        <h2>Firma Teslim Girişi</h2>
        <p class="small">Aynı tarih ve aynı ürün olsa bile her yazdığın adet ayrı kayıt olarak saklanır.</p>
        <form method="post" action="/add-delivery">
            <div class="grid">
                <div><label>Tarih</label><input name="deliv_date" value="{today()}" required></div>
                <div><label>Ürün</label><select name="product_id" required>{popts}</select></div>
                <div><label>Firmaya Teslim Edilen Adet</label><input name="firm_qty" type="number" min="1" required></div>
                <div style="grid-column:span 2"><label>Not</label><input name="note" placeholder="İsteğe bağlı"></div>
            </div>
            <br><button class="btn green">Firma Teslim Kaydet</button>
        </form>
    </div>

    <div class="card"><h2>Ürün Bazlı Genel Karşılaştırma</h2><table>
<colgroup>
    <col style="width:28%">
    <col style="width:24%">
    <col style="width:24%">
    <col style="width:24%">
</colgroup>
<tr>
    <th>Ürün</th>
    <th class="right">Firma Teslim Adet</th>
    <th class="right">Eleman Katlama Adet</th>
    <th class="right">Fark</th>
</tr>{sum_tr}</table></div>
    <div class="card"><h2>Tüm Teslim Kayıtları</h2><table>
<colgroup>
    <col style="width:8%">
    <col style="width:16%">
    <col style="width:24%">
    <col style="width:16%">
    <col style="width:24%">
    <col style="width:12%">
</colgroup>
<tr>
    <th>ID</th>
    <th>Tarih</th>
    <th>Ürün</th>
    <th class="right">Firma Adet</th>
    <th>Not</th>
    <th>İşlem</th>
</tr>{trs}</table></div>
    """
    return page("Firma Teslim ve Genel Karşılaştırma", body)


@app.post("/add-delivery")
def add_delivery(deliv_date: str = Form(...), product_id: int = Form(...), firm_qty: int = Form(...), note: str = Form("")):
    try:
        datetime.strptime(deliv_date, "%Y-%m-%d")
        firm_qty = int(firm_qty)
        if firm_qty <= 0:
            raise ValueError()
    except Exception:
        return RedirectResponse("/deliveries", status_code=303)

    # Aynı tarih + aynı ürün olsa bile yeni kayıt açar. Üstüne yazmaz.
    exec_db("""
        INSERT INTO deliveries(deliv_date,worker_id,product_id,firm_qty,worker_qty,note,created_at)
        VALUES(%s,%s,%s,%s,%s,%s,%s)
    """, (deliv_date, None, product_id, firm_qty, 0, note, now_iso()))
    return RedirectResponse("/deliveries", status_code=303)


@app.get("/delete-delivery/{did}")
def delete_delivery(did: int):
    exec_db("DELETE FROM deliveries WHERE id=%s", (did,))
    return RedirectResponse("/deliveries", status_code=303)


@app.get("/expenses", response_class=HTMLResponse)
def expenses():
    total = one("SELECT COALESCE(SUM(amount),0) total FROM expenses")["total"] or 0
    data = rows("SELECT * FROM expenses ORDER BY exp_date DESC,id DESC LIMIT 500")
    trs = "".join([f"<tr><td>{r['id']}</td><td>{r['exp_date']}</td><td>{r['category']}</td><td class='right'>{money(r['amount'])}</td><td>{r['note'] or ''}</td><td><a class='btn red' href='/delete-expense/{r['id']}'>Sil</a></td></tr>" for r in data])
    body = f"""<div class="kpis three"><div class="kpi"><span>Genel Masraf Toplamı</span><b>{money(total)}</b></div><div class="kpi"><span>Tarih Filtresi</span><b>Yok</b></div><div class="kpi"><span>Kayıt</span><b>Her Giriş Ayrı</b></div></div><div class="card"><h2>Masraf Ekle</h2><form method="post" action="/add-expense"><div class="grid"><div><label>Tarih</label><input name="exp_date" value="{today()}" required></div><div><label>Kategori</label><input name="category" placeholder="Yemek, yol, kira..." required></div><div><label>Tutar</label><input name="amount" type="number" step="0.01" min="0" required></div><div style="grid-column:span 2"><label>Not</label><input name="note"></div></div><br><button class="btn green">Masraf Kaydet</button></form></div><div class="card"><table><tr><th>ID</th><th>Tarih</th><th>Kategori</th><th>Tutar</th><th>Not</th><th>İşlem</th></tr>{trs}</table></div>"""
    return page("Masraflar", body)


@app.post("/add-expense")
def add_expense(exp_date: str = Form(...), category: str = Form(...), amount: float = Form(...), note: str = Form("")):
    exec_db("INSERT INTO expenses(exp_date,category,amount,note,created_at) VALUES(%s,%s,%s,%s,%s)", (exp_date, category, amount, note, now_iso()))
    return RedirectResponse("/expenses", status_code=303)


@app.get("/delete-expense/{eid}")
def delete_expense(eid: int):
    exec_db("DELETE FROM expenses WHERE id=%s", (eid,))
    return RedirectResponse("/expenses", status_code=303)




@app.get("/partners", response_class=HTMLResponse)
def partners(m: Optional[str] = None):
    if not m:
        m = this_month()

    sm = month_summary(m)
    net_kar = sm["net"] or 0
    ortak_pay = net_kar / 3

    partners_list = rows("SELECT id,name FROM partners WHERE active=1 ORDER BY id LIMIT 3")
    opts = "".join([f"<option value='{p['id']}'>{p['name']}</option>" for p in partners_list])

    # Eğer ortak adı değiştirmek istersen bu tabloda isim güncellenir.
    partner_rows = ""
    for p in partners_list:
        adv = one("""
            SELECT COALESCE(SUM(amount),0) total
            FROM partner_advances
            WHERE partner_id=%s AND adv_date LIKE %s
        """, (p["id"], m + "%"))["total"] or 0

        kalan = ortak_pay - adv
        partner_rows += (
            f"<tr>"
            f"<td>{p['name']}</td>"
            f"<td class='right'>{money(ortak_pay)}</td>"
            f"<td class='right'>{money(adv)}</td>"
            f"<td class='right'>{money(kalan)}</td>"
            f"</tr>"
        )

    adv_data = rows("""
        SELECT pa.id,pa.adv_date,p.name partner,pa.amount,COALESCE(pa.note,'') note
        FROM partner_advances pa
        JOIN partners p ON p.id=pa.partner_id
        WHERE pa.adv_date LIKE %s
        ORDER BY pa.adv_date DESC,pa.id DESC
        LIMIT 300
    """, (m + "%",))

    adv_rows = "".join([
        f"<tr><td>{r['id']}</td><td>{r['adv_date']}</td><td>{r['partner']}</td><td class='right'>{money(r['amount'])}</td><td>{r['note']}</td><td><a class='btn red' href='/delete-partner-advance/{r['id']}?m={m}' onclick=\"return confirm('Ortak avansı silinsin mi?')\">Sil</a></td></tr>"
        for r in adv_data
    ]) or "<tr><td colspan='6' class='center small'>Bu ay ortak avansı yok.</td></tr>"

    body = f"""
    <div class="card">
        <form method="get" action="/partners">
            <label>Ay seç: YYYY-AA</label>
            <input name="m" value="{m}" style="max-width:180px;display:inline-block">
            <button class="btn green">Hesapla</button>
        </form>
    </div>

    <div class="kpis three">
        <div class="kpi"><span>Net Kalan Toplam Kar</span><b>{money(net_kar)}</b></div>
        <div class="kpi"><span>Ortak Sayısı</span><b>3</b></div>
        <div class="kpi"><span>Kişi Başı Pay</span><b>{money(ortak_pay)}</b></div>
    </div>

    <div class="card">
        <h2>Ortak Avansı Gir</h2>
        <p class="small">Ortak ay içinde avans aldıysa burada yaz. Ay sonu ortak payından düşer.</p>
        <form method="post" action="/add-partner-advance">
            <input type="hidden" name="m" value="{m}">
            <div class="grid">
                <div><label>Tarih</label><input name="adv_date" value="{today()}" required></div>
                <div><label>Ortak</label><select name="partner_id" required>{opts}</select></div>
                <div><label>Avans Tutarı</label><input name="amount" type="number" step="0.01" min="0" required></div>
                <div style="grid-column:span 2"><label>Not</label><input name="note" placeholder="İsteğe bağlı"></div>
            </div>
            <br><button class="btn green">Ortak Avansı Kaydet</button>
        </form>
    </div>

    <div class="card">
        <h2>Ortaklar Hesap Özeti</h2>
        <table>
            <colgroup>
                <col style="width:25%">
                <col style="width:25%">
                <col style="width:25%">
                <col style="width:25%">
            </colgroup>
            <tr>
                <th>Ortak</th>
                <th class="right">Kar Payı</th>
                <th class="right">Ay İçinde Aldığı Avans</th>
                <th class="right">Net Kalan</th>
            </tr>
            {partner_rows}
        </table>
    </div>

    <div class="card">
        <h2>Bu Ay Ortak Avans Kayıtları</h2>
        <table>
            <colgroup>
                <col style="width:8%">
                <col style="width:16%">
                <col style="width:22%">
                <col style="width:18%">
                <col style="width:24%">
                <col style="width:12%">
            </colgroup>
            <tr>
                <th>ID</th>
                <th>Tarih</th>
                <th>Ortak</th>
                <th class="right">Avans</th>
                <th>Not</th>
                <th>İşlem</th>
            </tr>
            {adv_rows}
        </table>
    </div>
    """
    return page("Ortaklar Hesap", body)


@app.post("/add-partner-advance")
def add_partner_advance(
    adv_date: str = Form(...),
    partner_id: int = Form(...),
    amount: float = Form(...),
    note: str = Form(""),
    m: str = Form("")
):
    try:
        datetime.strptime(adv_date, "%Y-%m-%d")
        amount = float(amount)
        if amount <= 0:
            raise ValueError()
    except Exception:
        return RedirectResponse(f"/partners?m={m or this_month()}", status_code=303)

    exec_db("""
        INSERT INTO partner_advances(adv_date,partner_id,amount,note,created_at)
        VALUES(%s,%s,%s,%s,%s)
    """, (adv_date, partner_id, amount, note, now_iso()))

    return RedirectResponse(f"/partners?m={m or adv_date[:7]}", status_code=303)


@app.get("/delete-partner-advance/{aid}")
def delete_partner_advance(aid: int, m: Optional[str] = None):
    exec_db("DELETE FROM partner_advances WHERE id=%s", (aid,))
    return RedirectResponse(f"/partners?m={m or this_month()}", status_code=303)


@app.get("/partner-name-edit", response_class=HTMLResponse)
def partner_name_edit():
    data = rows("SELECT id,name FROM partners ORDER BY id LIMIT 3")
    trs = "".join([
        f"<tr><td>{r['id']}</td><td><form method='post' action='/partner-name-edit' style='display:flex;gap:8px'><input type='hidden' name='partner_id' value='{r['id']}'><input name='name' value='{r['name']}' required><button class='btn green'>Kaydet</button></form></td></tr>"
        for r in data
    ])
    body = f"<div class='card'><h2>Ortak İsimlerini Düzenle</h2><table><tr><th>ID</th><th>Ortak Adı</th></tr>{trs}</table></div>"
    return page("Ortak İsimleri", body)


@app.post("/partner-name-edit")
def partner_name_edit_save(partner_id: int = Form(...), name: str = Form(...)):
    name = " ".join(name.strip().split())
    if name:
        exec_db("UPDATE partners SET name=%s WHERE id=%s", (name, partner_id))
    return RedirectResponse("/partner-name-edit", status_code=303)


@app.get("/advances", response_class=HTMLResponse)
def advances():
    total = one("SELECT COALESCE(SUM(amount),0) total FROM advances")["total"] or 0
    workers = rows("SELECT id,name FROM workers WHERE active=1 ORDER BY name")
    opts = "".join([f"<option value='{w['id']}'>{w['name']}</option>" for w in workers])

    data = rows("""
    SELECT a.id,a.adv_date,w.name worker,a.amount,COALESCE(a.note,'') note
    FROM advances a
    JOIN workers w ON w.id=a.worker_id
    ORDER BY a.adv_date DESC,a.id DESC
    LIMIT 500
    """)

    trs = "".join([
        f"<tr><td>{r['id']}</td><td>{r['adv_date']}</td><td>{r['worker']}</td><td class='right'>{money(r['amount'])}</td><td>{r['note']}</td><td><a class='btn red' href='/delete-advance/{r['id']}' onclick=\"return confirm('Avans kaydı silinsin mi?')\">Sil</a></td></tr>"
        for r in data
    ]) or "<tr><td colspan='6' class='center small'>Avans kaydı yok.</td></tr>"

    by_worker = rows("""
    SELECT w.id,w.name worker,
           COALESCE(en.earned,0) earned,
           COALESCE(ad.amount,0) advance,
           COALESCE(pa.amount,0) paid,
           COALESCE(en.earned,0)-COALESCE(ad.amount,0)-COALESCE(pa.amount,0) remaining
    FROM workers w
    LEFT JOIN (
        SELECT worker_id,SUM(qty*worker_price) earned
        FROM entries
        GROUP BY worker_id
    ) en ON en.worker_id=w.id
    LEFT JOIN (
        SELECT worker_id,SUM(amount) amount
        FROM advances
        GROUP BY worker_id
    ) ad ON ad.worker_id=w.id
    LEFT JOIN (
        SELECT worker_id,SUM(amount) amount
        FROM payments
        GROUP BY worker_id
    ) pa ON pa.worker_id=w.id
    WHERE w.active=1
    ORDER BY w.name
    """)

    sum_tr = "".join([
        f"<tr><td>{r['worker']}</td><td class='right'>{money(r['earned'])}</td><td class='right'>{money(r['advance'])}</td><td class='right'>{money(r['paid'])}</td><td class='right'>{money(r['remaining'])}</td></tr>"
        for r in by_worker
    ]) or "<tr><td colspan='5' class='center small'>Eleman yok.</td></tr>"

    body = f"""
    <div class="kpis three">
        <div class="kpi"><span>Genel Avans Toplamı</span><b>{money(total)}</b></div>
        <div class="kpi"><span>Hesap Mantığı</span><b>Hak Edişten Düşer</b></div>
        <div class="kpi"><span>Kayıt</span><b>Her Giriş Ayrı</b></div>
    </div>

    <div class="card">
        <h2>Avans Ekle</h2>
        <form method="post" action="/add-advance">
            <div class="grid">
                <div><label>Tarih</label><input name="adv_date" value="{today()}" required></div>
                <div><label>Eleman</label><select name="worker_id">{opts}</select></div>
                <div><label>Avans Tutarı</label><input name="amount" type="number" step="0.01" min="0" required></div>
                <div style="grid-column:span 2"><label>Not</label><input name="note" placeholder="İsteğe bağlı"></div>
            </div>
            <br><button class="btn green">Avans Kaydet</button>
        </form>
    </div>

    <div class="card">
        <h2>Eleman Avans Özeti</h2>
        <table>
            <colgroup>
                <col style="width:24%">
                <col style="width:19%">
                <col style="width:19%">
                <col style="width:19%">
                <col style="width:19%">
            </colgroup>
            <tr>
                <th>Eleman</th>
                <th class="right">Hak Ediş</th>
                <th class="right">Avans</th>
                <th class="right">Ödenen</th>
                <th class="right">Kalan</th>
            </tr>
            {sum_tr}
        </table>
    </div>

    <div class="card">
        <h2>Tüm Avans Kayıtları</h2>
        <table>
            <colgroup>
                <col style="width:8%">
                <col style="width:16%">
                <col style="width:24%">
                <col style="width:18%">
                <col style="width:22%">
                <col style="width:12%">
            </colgroup>
            <tr>
                <th>ID</th>
                <th>Tarih</th>
                <th>Eleman</th>
                <th class="right">Tutar</th>
                <th>Not</th>
                <th>İşlem</th>
            </tr>
            {trs}
        </table>
    </div>
    """
    return page("Avanslar", body)


@app.post("/add-advance")
def add_advance(adv_date: str = Form(...), worker_id: int = Form(...), amount: float = Form(...), note: str = Form("")):
    try:
        datetime.strptime(adv_date, "%Y-%m-%d")
        amount = float(amount)
        if amount <= 0:
            raise ValueError()
    except Exception:
        return RedirectResponse("/advances", status_code=303)

    exec_db("""
        INSERT INTO advances(adv_date,worker_id,amount,note,created_at)
        VALUES(%s,%s,%s,%s,%s)
    """, (adv_date, worker_id, amount, note, now_iso()))
    return RedirectResponse("/advances", status_code=303)


@app.get("/delete-advance/{aid}")
def delete_advance(aid: int):
    exec_db("DELETE FROM advances WHERE id=%s", (aid,))
    return RedirectResponse("/advances", status_code=303)


@app.get("/payments", response_class=HTMLResponse)
def payments():
    total = one("SELECT COALESCE(SUM(amount),0) total FROM payments")["total"] or 0
    workers = rows("SELECT id,name FROM workers WHERE active=1 ORDER BY name")
    opts = "".join([f"<option value='{w['id']}'>{w['name']}</option>" for w in workers])

    data = rows("""
    SELECT p.id,p.pay_date,w.name worker,p.amount,COALESCE(p.note,'') note
    FROM payments p
    JOIN workers w ON w.id=p.worker_id
    ORDER BY p.pay_date DESC,p.id DESC
    LIMIT 500
    """)

    trs = "".join([
        f"<tr><td>{r['id']}</td><td>{r['pay_date']}</td><td>{r['worker']}</td><td class='right'>{money(r['amount'])}</td><td>{r['note']}</td><td><a class='btn red' href='/delete-payment/{r['id']}' onclick=\"return confirm('Ödeme kaydı silinsin mi?')\">Sil</a></td></tr>"
        for r in data
    ]) or "<tr><td colspan='6' class='center small'>Ödeme kaydı yok.</td></tr>"

    by_worker = rows("""
    SELECT w.id,w.name worker,
           COALESCE(en.qty,0) qty,
           COALESCE(en.earned,0) earned,
           COALESCE(ad.amount,0) advance,
           COALESCE(pa.amount,0) paid,
           COALESCE(en.earned,0)-COALESCE(ad.amount,0)-COALESCE(pa.amount,0) remaining
    FROM workers w
    LEFT JOIN (
        SELECT worker_id,
               SUM(qty) qty,
               SUM(qty*worker_price) earned
        FROM entries
        GROUP BY worker_id
    ) en ON en.worker_id=w.id
    LEFT JOIN (
        SELECT worker_id,SUM(amount) amount
        FROM advances
        GROUP BY worker_id
    ) ad ON ad.worker_id=w.id
    LEFT JOIN (
        SELECT worker_id,SUM(amount) amount
        FROM payments
        GROUP BY worker_id
    ) pa ON pa.worker_id=w.id
    WHERE w.active=1
    ORDER BY w.name
    """)

    worker_rows = "".join([
        f"<tr><td>{r['worker']}</td><td class='right'>{int(r['qty'] or 0)}</td><td class='right'>{money(r['earned'])}</td><td class='right'>{money(r['advance'])}</td><td class='right'>{money(r['paid'])}</td><td class='right'>{money(r['remaining'])}</td></tr>"
        for r in by_worker
    ]) or "<tr><td colspan='6' class='center small'>Eleman yok.</td></tr>"

    body = f"""
    <div class="kpis three">
        <div class="kpi"><span>Genel Ödeme Toplamı</span><b>{money(total)}</b></div>
        <div class="kpi"><span>Hesap</span><b>Hak Ediş - Avans - Ödeme</b></div>
        <div class="kpi"><span>Kayıt</span><b>Her Giriş Ayrı</b></div>
    </div>

    <div class="card">
        <h2>Eleman Ödemesi</h2>
        <form method="post" action="/add-payment">
            <div class="grid">
                <div><label>Tarih</label><input name="pay_date" value="{today()}" required></div>
                <div><label>Eleman</label><select name="worker_id">{opts}</select></div>
                <div><label>Ödeme Tutarı</label><input name="amount" type="number" step="0.01" min="0" required></div>
                <div style="grid-column:span 2"><label>Not</label><input name="note" placeholder="İsteğe bağlı"></div>
            </div>
            <br><button class="btn green">Ödeme Kaydet</button>
        </form>
    </div>

    <div class="card">
        <h2>Eleman Ödeme Özeti</h2>
        <table>
            <colgroup>
                <col style="width:22%">
                <col style="width:14%">
                <col style="width:16%">
                <col style="width:16%">
                <col style="width:16%">
                <col style="width:16%">
            </colgroup>
            <tr>
                <th>Eleman</th>
                <th class="right">Toplam Adet</th>
                <th class="right">Hak Ediş</th>
                <th class="right">Avans</th>
                <th class="right">Ödenen</th>
                <th class="right">Kalan</th>
            </tr>
            {worker_rows}
        </table>
    </div>

    <div class="card">
        <h2>Tüm Ödeme Kayıtları</h2>
        <table>
            <colgroup>
                <col style="width:8%">
                <col style="width:16%">
                <col style="width:24%">
                <col style="width:18%">
                <col style="width:22%">
                <col style="width:12%">
            </colgroup>
            <tr>
                <th>ID</th>
                <th>Tarih</th>
                <th>Eleman</th>
                <th class="right">Tutar</th>
                <th>Not</th>
                <th>İşlem</th>
            </tr>
            {trs}
        </table>
    </div>
    """
    return page("Ödemeler", body)


@app.post("/add-payment")
def add_payment(pay_date: str = Form(...), worker_id: int = Form(...), amount: float = Form(...), note: str = Form("")):
    exec_db("INSERT INTO payments(pay_date,worker_id,amount,note,created_at) VALUES(%s,%s,%s,%s,%s)", (pay_date, worker_id, amount, note, now_iso()))
    return RedirectResponse("/payments", status_code=303)


@app.get("/delete-payment/{pid}")
def delete_payment(pid: int):
    exec_db("DELETE FROM payments WHERE id=%s", (pid,))
    return RedirectResponse("/payments", status_code=303)


@app.get("/month", response_class=HTMLResponse)
def month(m: Optional[str] = None):
    if not m:
        m = this_month()
    like = m + "%"
    sm = month_summary(m)
    by_worker = rows("""
    SELECT w.id,w.name worker, COALESCE(SUM(e.qty),0) qty, COALESCE(SUM(e.qty*e.worker_price),0) earned
    FROM workers w LEFT JOIN entries e ON e.worker_id=w.id AND e.work_date LIKE %s WHERE w.active=1 GROUP BY w.id,w.name ORDER BY w.name
    """, (like,))
    trs = ""
    for r in by_worker:
        paid = one("SELECT COALESCE(SUM(amount),0) paid FROM payments WHERE worker_id=%s AND pay_date LIKE %s", (r["id"], like))["paid"] or 0
        advance = one("SELECT COALESCE(SUM(amount),0) advance FROM advances WHERE worker_id=%s AND adv_date LIKE %s", (r["id"], like))["advance"] or 0
        remain = (r["earned"] or 0) - paid - advance
        trs += f"<tr><td>{r['worker']}</td><td class='right'>{int(r['qty'] or 0)}</td><td class='right'>{money(r['earned'] or 0)}</td><td class='right'>{money(advance)}</td><td class='right'>{money(paid)}</td><td class='right'>{money(remain)}</td></tr>"
    by_product = rows("""
    SELECT p.name product, 
           COALESCE(fd.firm_qty,0) qty,
           COALESCE(fd.firm_qty*p.firm_price,0) revenue,
           COALESCE(en.worker_labor,0) labor,
           COALESCE(fd.firm_qty*p.firm_price,0)-COALESCE(en.worker_labor,0) gross
    FROM products p 
    LEFT JOIN (SELECT product_id,SUM(firm_qty) firm_qty FROM deliveries WHERE deliv_date LIKE %s GROUP BY product_id) fd ON fd.product_id=p.id
    LEFT JOIN (SELECT product_id,SUM(qty*worker_price) worker_labor FROM entries WHERE work_date LIKE %s GROUP BY product_id) en ON en.product_id=p.id
    WHERE p.active=1
    ORDER BY p.name
    """, (like, like))
    ptrs = "".join([f"<tr><td>{r['product']}</td><td class='right'>{int(r['qty'] or 0)}</td><td class='right'>{money(r['revenue'] or 0)}</td><td class='right'>{money(r['labor'] or 0)}</td><td class='right'>{money(r['gross'] or 0)}</td></tr>" for r in by_product])
    body = f"""<div class="card"><form method="get" action="/month"><label>Ay seç: YYYY-AA</label><input name="m" value="{m}" style="max-width:180px;display:inline-block"><button class="btn green">Hesapla</button><a class="btn yellow" href="/export-month?m={m}">CSV Rapor Al</a></form></div><div class="kpis"><div class="kpi"><span>Firma Teslim Adet</span><b>{int(sm['qty'])}</b></div><div class="kpi"><span>Firma Hak Ediş</span><b>{money(sm['revenue'])}</b></div><div class="kpi"><span>İşçilik</span><b>{money(sm['labor'])}</b></div><div class="kpi"><span>Masraflar</span><b>{money(sm['expense'])}</b></div><div class="kpi"><span>Net Kazanç</span><b>{money(sm['net'])}</b></div></div><div class="card"><h2>Eleman Bazlı Ay Sonu</h2><table><tr><th>Eleman</th><th class="right">Toplam Adet</th><th class="right">Hak Ediş</th><th class="right">Avans</th><th class="right">Ödenen</th><th class="right">Kalan</th></tr>{trs}</table></div><div class="card"><h2>Ürün Bazlı Özet</h2><table><tr><th>Ürün</th><th>Firma Teslim Adet</th><th>Firma Hak Ediş</th><th>İşçilik</th><th>Brüt Kazanç</th></tr>{ptrs}</table></div>"""
    return page("Ay Sonu Rapor ve Net Kazanç", body)


@app.get("/export-month")
def export_month(m: Optional[str] = None):
    if not m:
        m = this_month()
    sm = month_summary(m)
    out = Path(f"katlama_tam_rapor_{m}.csv")
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f, delimiter=";")
        wr.writerow(["AY SONU GENEL ÖZET"])
        wr.writerow(["Ay", m])
        wr.writerow(["Firma Teslim Adet", int(sm["qty"])])
        wr.writerow(["Firma Hak Ediş", f"{sm['revenue']:.2f}"])
        wr.writerow(["İşçilik", f"{sm['labor']:.2f}"])
        wr.writerow(["Avanslar", f"{sm.get('advance', 0):.2f}"])
        wr.writerow(["Masraflar", f"{sm['expense']:.2f}"])
        wr.writerow(["Brüt Kazanç", f"{sm['gross']:.2f}"])
        wr.writerow(["Net Kazanç", f"{sm['net']:.2f}"])
    return FileResponse(out, filename=out.name)


@app.get("/delete-entry/{entry_id}")
def delete_entry(entry_id: int):
    exec_db("DELETE FROM entries WHERE id=%s", (entry_id,))
    return RedirectResponse("/dashboard", status_code=303)


if __name__ == "__main__":
    init_db()
    print("=" * 70)
    print("KATLAMA ATÖLYESİ TAM SİSTEM BAŞLADI - SUPABASE KALICI VERİ")
    print(f"Yönetim paneli: http://127.0.0.1:{PORT}/dashboard")
    print(f"Aynı Wi-Fi telefon: http://{local_ip()}:{PORT}")
    print("=" * 70)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
