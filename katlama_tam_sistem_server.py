import os
import csv
import socket
import secrets
from pathlib import Path
from datetime import datetime, date
from typing import Optional
from urllib.parse import quote
from html import escape

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
import uvicorn

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
PORT = int(os.environ.get("PORT", "10000"))

app = FastAPI(title="Katlama Atölyesi Profesyonel Sistem")


@app.middleware("http")
async def disable_page_cache(request: Request, call_next):
    """Silinen veya güncellenen kayıtların telefonda eski haliyle kalmasını engeller."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Çalışan link sistemi:
# Her çalışan kendi tokenı ile kişiye özel link alır.
# Link formatı: https://katlama-sistem.onrender.com/w/<token>
LEGACY_WORKER_TOKENS = {}

DEFAULT_PUBLIC_BASE_URL = "https://katlama-sistem.onrender.com"


def public_base_url():
    """Çalışan linklerinde Render'in ozel 10.x adresinin kullanilmasini engeller."""
    value = (os.environ.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    invalid_values = ("http://10.", "https://10.", "http://127.", "https://127.",
                      "http://localhost", "https://localhost")
    if not value or value.lower().startswith(invalid_values):
        value = DEFAULT_PUBLIC_BASE_URL
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value.rstrip("/")


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def today():
    return date.today().strftime("%Y-%m-%d")


def this_month():
    return date.today().strftime("%Y-%m")


def display_date(value):
    """Veritabanındaki YYYY-AA-GG tarihini ekranda GG.AA.YYYY gösterir."""
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return str(value or "")


def normalize_date(value):
    """Kullanıcıdan gelen tarihleri veritabanında daima YYYY-AA-GG saklar."""
    raw = str(value or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return raw


def money(v):
    try:
        return f"{float(v or 0):,.2f} ₺".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00 ₺"


def num(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL yok. Render > Environment kısmına Supabase DATABASE_URL ekle.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def rows(q, p=()):
    con = db(); cur = con.cursor(); cur.execute(q, p); r = cur.fetchall(); cur.close(); con.close(); return r


def one(q, p=()):
    con = db(); cur = con.cursor(); cur.execute(q, p); r = cur.fetchone(); cur.close(); con.close(); return r


def exec_db(q, p=()):
    con = db(); cur = con.cursor(); cur.execute(q, p); out = None
    try:
        if cur.description:
            rr = cur.fetchone()
            if rr:
                out = list(rr.values())[0]
    except Exception:
        pass
    con.commit(); cur.close(); con.close(); return out


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        return "127.0.0.1"


def init_db():
    con = db(); c = con.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS workers(id SERIAL PRIMARY KEY,name TEXT NOT NULL UNIQUE,phone TEXT,token TEXT UNIQUE,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS firms(id SERIAL PRIMARY KEY,name TEXT NOT NULL UNIQUE,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL)""")
    c.execute("""UPDATE firms SET name='TEMA KONFEKSİYON' WHERE name='Genel Firma'
                 AND NOT EXISTS(SELECT 1 FROM firms WHERE name='TEMA KONFEKSİYON')""")
    c.execute("""INSERT INTO firms(name,active,created_at) VALUES('TEMA KONFEKSİYON',1,%s) ON CONFLICT(name) DO UPDATE SET active=1""", (now_iso(),))
    c.execute("""CREATE TABLE IF NOT EXISTS products(id SERIAL PRIMARY KEY,name TEXT NOT NULL,firm_id INTEGER REFERENCES firms(id),firm_price DOUBLE PRECISION NOT NULL DEFAULT 0,worker_price DOUBLE PRECISION NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL)""")
    c.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS firm_id INTEGER REFERENCES firms(id)")
    c.execute("UPDATE products SET firm_id=(SELECT id FROM firms WHERE name='TEMA KONFEKSİYON') WHERE firm_id IS NULL")
    c.execute("ALTER TABLE products ALTER COLUMN firm_id SET NOT NULL")
    c.execute("ALTER TABLE products DROP CONSTRAINT IF EXISTS products_name_key")
    c.execute("""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='products_firm_name_key') THEN
            ALTER TABLE products ADD CONSTRAINT products_firm_name_key UNIQUE(firm_id,name);
        END IF;
    END $$""")
    c.execute("""UPDATE products p SET firm_id=(SELECT id FROM firms WHERE name='TEMA KONFEKSİYON')
                 WHERE p.firm_id IN (SELECT id FROM firms WHERE name='Genel Firma')
                 AND NOT EXISTS(
                    SELECT 1 FROM products x
                    WHERE x.firm_id=(SELECT id FROM firms WHERE name='TEMA KONFEKSİYON') AND x.name=p.name AND x.id<>p.id
                 )""")
    c.execute("""UPDATE firms SET active=0 WHERE name='Genel Firma'
                 AND NOT EXISTS(SELECT 1 FROM products WHERE firm_id=firms.id)""")
    c.execute("""CREATE TABLE IF NOT EXISTS work_types(id SERIAL PRIMARY KEY,product_id INTEGER NOT NULL REFERENCES products(id),name TEXT NOT NULL,worker_price DOUBLE PRECISION NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,UNIQUE(product_id,name))""")
    c.execute("""CREATE TABLE IF NOT EXISTS entries(id SERIAL PRIMARY KEY,work_date TEXT NOT NULL,worker_id INTEGER NOT NULL REFERENCES workers(id),product_id INTEGER NOT NULL REFERENCES products(id),qty INTEGER NOT NULL,firm_price DOUBLE PRECISION NOT NULL,worker_price DOUBLE PRECISION NOT NULL,note TEXT,created_at TEXT NOT NULL,source TEXT DEFAULT 'telefon')""")
    c.execute("""CREATE TABLE IF NOT EXISTS payments(id SERIAL PRIMARY KEY,pay_date TEXT NOT NULL,worker_id INTEGER NOT NULL REFERENCES workers(id),amount DOUBLE PRECISION NOT NULL,note TEXT,created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS advances(id SERIAL PRIMARY KEY,adv_date TEXT NOT NULL,worker_id INTEGER NOT NULL REFERENCES workers(id),amount DOUBLE PRECISION NOT NULL,note TEXT,created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS expenses(id SERIAL PRIMARY KEY,exp_date TEXT NOT NULL,category TEXT NOT NULL,amount DOUBLE PRECISION NOT NULL,note TEXT,created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS deliveries(id SERIAL PRIMARY KEY,deliv_date TEXT NOT NULL,worker_id INTEGER REFERENCES workers(id),product_id INTEGER NOT NULL REFERENCES products(id),firm_qty INTEGER NOT NULL DEFAULT 0,worker_qty INTEGER NOT NULL DEFAULT 0,note TEXT,created_at TEXT NOT NULL)""")
    c.execute("ALTER TABLE entries ADD COLUMN IF NOT EXISTS work_type_id INTEGER REFERENCES work_types(id)")
    c.execute("ALTER TABLE work_types ADD COLUMN IF NOT EXISTS pay_basis TEXT NOT NULL DEFAULT 'piece'")
    c.execute("ALTER TABLE work_types ADD COLUMN IF NOT EXISTS counts_product INTEGER NOT NULL DEFAULT 0")
    c.execute("""UPDATE work_types wt SET counts_product=1
                 WHERE LOWER(wt.name) LIKE '%katlama%'
                   AND wt.id=(SELECT MIN(x.id) FROM work_types x WHERE x.product_id=wt.product_id AND LOWER(x.name) LIKE '%katlama%')
                   AND NOT EXISTS(SELECT 1 FROM work_types y WHERE y.product_id=wt.product_id AND y.counts_product=1)""")
    c.execute("ALTER TABLE entries ADD COLUMN IF NOT EXISTS package_size INTEGER NOT NULL DEFAULT 1")
    # Eski kayıtlarda GG.AA.YYYY / GG/AA/YYYY olarak kalmış tarihler ay sonu
    # filtresine girmiyordu. Hepsini tek seferde standart biçime dönüştür.
    for table_name, column_name in (
        ("entries", "work_date"),
        ("deliveries", "deliv_date"),
        ("expenses", "exp_date"),
        ("payments", "pay_date"),
        ("advances", "adv_date"),
    ):
        c.execute(f"""UPDATE {table_name}
                      SET {column_name}=SUBSTRING({column_name},7,4)||'-'||SUBSTRING({column_name},4,2)||'-'||SUBSTRING({column_name},1,2)
                      WHERE {column_name} ~ '^[0-9]{{2}}[./-][0-9]{{2}}[./-][0-9]{{4}}$'""")
    default_firm = c.execute("SELECT id FROM firms WHERE name='TEMA KONFEKSİYON'")
    default_firm_id = c.fetchone()["id"]
    for name in ["Şal", "Eşarp", "Tekstil Ürün"]:
        c.execute("INSERT INTO products(name,firm_id,firm_price,worker_price,active,created_at) VALUES(%s,%s,0,0,1,%s) ON CONFLICT(firm_id,name) DO NOTHING", (name, default_firm_id, now_iso()))
    c.execute("SELECT id FROM workers WHERE token IS NULL OR token='' OR token='None'")
    for r in c.fetchall():
        c.execute("UPDATE workers SET token=%s WHERE id=%s", (secrets.token_urlsafe(14), r["id"]))

    # Mevcut tokenlar korunur; tokenı boş olan eski çalışanlara yukarıda otomatik kişiye özel link tokenı verilir.

    con.commit(); c.close(); con.close()


CSS = """
<style>
:root{--bg:#08111f;--card:#121a2d;--card2:#0f172a;--line:#25314a;--text:#f8fafc;--muted:#aab3c5;--green:#22c55e;--red:#ef4444;--blue:#1d4ed8;--yellow:#f59e0b;--purple:#8b5cf6;--cyan:#06b6d4}
*{box-sizing:border-box}body{margin:0;font-family:Arial,Segoe UI,sans-serif;background:linear-gradient(135deg,#06101f,#111827 60%,#08111f);color:var(--text)}.wrap{max-width:1320px;margin:0 auto;padding:14px 14px 90px}.top{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:12px}h1{font-size:24px;margin:8px 0}h2{margin:8px 0 14px}a{color:white;text-decoration:none}.nav{display:flex;gap:8px;flex-wrap:wrap}.nav a,.btn{background:var(--blue);border:0;color:white;padding:11px 14px;border-radius:12px;font-weight:800;cursor:pointer;display:inline-block;box-shadow:0 8px 18px #0003}.btn.green{background:var(--green);color:#06130b}.btn.red{background:var(--red)}.btn.gray{background:#334155}.btn.yellow{background:var(--yellow);color:#1b1100}.btn.purple{background:var(--purple)}.btn.cyan{background:var(--cyan);color:#031014}.card{background:rgba(18,26,45,.94);border:1px solid var(--line);border-radius:18px;padding:15px;margin:12px 0;box-shadow:0 14px 34px #0005}.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}label{font-size:13px;color:var(--muted);display:block;margin-bottom:5px;font-weight:700}input,select,textarea{width:100%;padding:13px;border-radius:12px;border:1px solid var(--line);background:#0f172a;color:white;font-size:16px}table{width:100%;border-collapse:separate;border-spacing:0;background:var(--card);border-radius:14px;overflow:hidden;table-layout:fixed}th,td{border-bottom:1px solid var(--line);padding:8px 7px;vertical-align:middle;white-space:normal;overflow:hidden;text-overflow:ellipsis;word-break:break-word;line-height:1.25}th{color:#cbd5e1;background:#111827;text-align:left;font-size:12px}td{font-size:12px}.table-wrap{overflow-x:auto;max-width:100%}.link-cell{max-width:260px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.link-cell a{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.actions{display:flex;gap:5px;flex-wrap:nowrap;align-items:center}.actions .btn{padding:8px 9px;border-radius:10px;font-size:12px;white-space:nowrap}form.inline{display:inline-block;margin:0}.workers-table th:nth-child(1),.workers-table td:nth-child(1){width:42px}.workers-table th:nth-child(2),.workers-table td:nth-child(2){width:120px}.workers-table th:nth-child(3),.workers-table td:nth-child(3){width:95px}.workers-table th:nth-child(4),.workers-table td:nth-child(4){width:65px}.workers-table th:nth-child(5),.workers-table td:nth-child(5),.workers-table th:nth-child(6),.workers-table td:nth-child(6),.workers-table th:nth-child(7),.workers-table td:nth-child(7),.workers-table th:nth-child(8),.workers-table td:nth-child(8){width:88px}.workers-table th:nth-child(9),.workers-table td:nth-child(9){width:260px}.workers-table th:nth-child(10),.workers-table td:nth-child(10){width:250px}.right{text-align:right}.center{text-align:center}.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.kpis.three{grid-template-columns:repeat(3,1fr)}.kpi{background:linear-gradient(180deg,#111827,#0f172a);border:1px solid var(--line);border-radius:16px;padding:15px;min-height:82px}.kpi b{font-size:24px;display:block;margin-top:6px}.kpi span{color:var(--muted);font-size:13px;font-weight:700}.notice{background:#052e1a;border:1px solid #166534;color:#dcfce7;padding:10px;border-radius:12px;margin:10px 0}.bad{background:#3b1111;border:1px solid #7f1d1d;color:#fee2e2;padding:10px;border-radius:12px;margin:10px 0}.copy{font-size:12px;word-break:break-all;color:#dbeafe}.small{font-size:12px;color:var(--muted)}.worker-hero{background:linear-gradient(135deg,#172554,#0f172a 55%,#052e1a);border:1px solid #334155;border-radius:24px;padding:18px;box-shadow:0 18px 45px #0008}.worker-title{font-size:28px;font-weight:900;margin:0 0 8px}.worker-sub{color:#cbd5e1;margin-bottom:12px}.worker-form input,.worker-form select{font-size:20px;padding:16px}.worker-form button{font-size:20px;padding:16px 22px;width:100%}.diff-plus{color:#22c55e;font-weight:900}.diff-minus{color:#ef4444;font-weight:900}.diff-zero{color:#cbd5e1;font-weight:900}.table-wrap{overflow:auto}.muted{color:#aab3c5}@media(max-width:900px){.grid,.kpis,.kpis.three{grid-template-columns:1fr}h1{font-size:20px}.nav a,.btn{width:100%;text-align:center}.worker-title{font-size:24px}.table-wrap{overflow:auto}}
.nav a.delivery-link{background:var(--green);color:#06130b;box-shadow:0 8px 20px #22c55e55}
.diff-plus,.diff-minus{color:#ef4444}.diff-zero{color:#22c55e}
.record-list{display:grid;gap:12px}.record-card{background:#0f172a;border:1px solid var(--line);border-radius:16px;padding:14px}.record-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:10px}.record-head b{font-size:18px}.record-date{color:var(--muted);font-size:14px;white-space:nowrap}.record-values{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.record-value{background:#111827;border-radius:11px;padding:10px}.record-value span{display:block;color:var(--muted);font-size:12px;margin-bottom:5px}.record-value b{font-size:17px}.record-note{margin-top:10px;color:#cbd5e1}.record-actions{display:flex;gap:8px;margin-top:12px}.record-actions .btn,.record-actions form{flex:1}.record-actions button{width:100%}@media(max-width:600px){.record-values{grid-template-columns:1fr 1fr}.record-actions .btn{width:auto}.record-card{padding:12px}.record-head{display:block}.record-date{margin-top:5px}}
</style>
"""


def page(title, body, nav=True):
    nav_html = ""
    if nav:
        nav_html = """<div class="nav"><a href="/dashboard">Ana Panel</a><a class="delivery-link" href="/deliveries">Firmaya Gönderilen Adet</a><a href="/workers">Çalışan Linkleri</a><a href="/products">Firma / Ürün / Fiyat</a><a href="/expenses">Masraflar</a><a href="/payments">Ödemeler</a><a href="/month">Ay Sonu</a></div>"""
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>{CSS}</head><body><div class="wrap"><div class="top"><h1>{title}</h1>{nav_html}</div>{body}</div></body></html>"""


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/dashboard", status_code=303)


def calc_summary(month: Optional[str] = None):
    entry_where = "WHERE work_date LIKE %s" if month else ""
    deliv_where = "WHERE d.deliv_date LIKE %s" if month else ""
    exp_where = "WHERE exp_date LIKE %s" if month else ""
    p = (month + "%",) if month else ()

    firma = one(f"""SELECT COALESCE(SUM(d.firm_qty),0) qty,
                        COALESCE(SUM(d.firm_qty*p.firm_price),0) revenue
                 FROM deliveries d
                 JOIN products p ON p.id=d.product_id
                 {deliv_where}""", p)

    earned = one(f"SELECT COALESCE(SUM(qty*worker_price),0) total FROM entries {entry_where}", p)
    production_where = "WHERE e.work_date LIKE %s" if month else ""
    production = one(f"""SELECT COALESCE(SUM(e.qty),0) qty FROM entries e
                         JOIN work_types wt ON wt.id=e.work_type_id AND wt.counts_product=1
                         {production_where}""", p)
    exp = one(f"SELECT COALESCE(SUM(amount),0) total FROM expenses {exp_where}", p)
    advance_where = "WHERE adv_date LIKE %s" if month else ""
    payment_where = "WHERE pay_date LIKE %s" if month else ""
    advance_row = one(f"SELECT COALESCE(SUM(amount),0) total FROM advances {advance_where}", p)
    payment_row = one(f"SELECT COALESCE(SUM(amount),0) total FROM payments {payment_where}", p)

    hakedis = num(earned["total"] if earned else 0)
    advance = num(advance_row["total"] if advance_row else 0)
    paid = num(payment_row["total"] if payment_row else 0)
    labor = hakedis - advance - paid
    revenue = num(firma["revenue"] if firma else 0)
    expense = num(exp["total"] if exp else 0)

    return {
        "qty": num(firma["qty"] if firma else 0),
        "revenue": revenue,
        "worker_qty": num(production["qty"] if production else 0),
        "hakedis": hakedis,
        "advance": advance,
        "paid": paid,
        "labor": labor,
        "labor_remaining": labor,
        "expense": expense,
        "gross": revenue - hakedis,
        "net": revenue - labor - expense,
    }

def total_summary(): return calc_summary(None)
def month_summary(m): return calc_summary(m)


def diff_class(v):
    v = int(v or 0)
    return "diff-plus" if v > 0 else "diff-minus" if v < 0 else "diff-zero"


def last_entries(limit=300, month: Optional[str] = None):
    where = "WHERE e.work_date LIKE %s" if month else ""
    p = (month + "%", limit) if month else (limit,)
    return rows(f"""
    WITH ranked AS (
        SELECT e.*,ROW_NUMBER() OVER(PARTITION BY e.worker_id,e.work_date ORDER BY e.id) rn
        FROM entries e {where}
    )
    SELECT e.id,e.work_date,w.name worker,COALESCE(wt.name,pr.name) product,e.qty,
           e.qty*e.worker_price hakedis,
           CASE WHEN e.rn=1 THEN COALESCE(ad.avans,0) ELSE 0 END avans,
           CASE WHEN e.rn=1 THEN COALESCE(pa.odeme,0) ELSE 0 END odeme,
           (e.qty*e.worker_price)
             - CASE WHEN e.rn=1 THEN COALESCE(ad.avans,0) ELSE 0 END
             - CASE WHEN e.rn=1 THEN COALESCE(pa.odeme,0) ELSE 0 END net_kalan,
           COALESCE(e.note,'') note
    FROM ranked e
    JOIN workers w ON w.id=e.worker_id
    JOIN products pr ON pr.id=e.product_id
    LEFT JOIN work_types wt ON wt.id=e.work_type_id
    LEFT JOIN (SELECT worker_id,adv_date,SUM(amount) avans FROM advances GROUP BY worker_id,adv_date) ad ON ad.worker_id=e.worker_id AND ad.adv_date=e.work_date
    LEFT JOIN (SELECT worker_id,pay_date,SUM(amount) odeme FROM payments GROUP BY worker_id,pay_date) pa ON pa.worker_id=e.worker_id AND pa.pay_date=e.work_date
    ORDER BY e.work_date DESC,e.id DESC LIMIT %s
    """, p)


def entries_table(data):
    trs = "".join([f"""<tr><td>{r['id']}</td><td>{display_date(r['work_date'])}</td><td>{r['worker']}</td><td class='right'>{int(num(r['qty']))}</td><td class='right'>{money(r['hakedis'])}</td><td class='right'>{money(r['avans'])}</td><td class='right'>{money(r['odeme'])}</td><td class='right'>{money(r['net_kalan'])}</td><td>{r['note']}</td><td><a class='btn yellow' href='/edit-entry/{r['id']}'>Güncelle</a> <form method='post' action='/delete-entry/{r['id']}' style='display:inline'><button class='btn red' type='submit'>Sil</button></form></td></tr>""" for r in data]) or "<tr><td colspan='10' class='center small'>Kayıt yok.</td></tr>"
    return f"""<div class='table-wrap'><table class='workers-table'><tr><th>ID</th><th>TARİH</th><th>ÇALIŞAN</th><th class='right'>ADET</th><th class='right'>HAKEDİŞ</th><th class='right'>AVANS</th><th class='right'>ÖDEME</th><th class='right'>NET KALAN</th><th>NOT</th><th>İŞLEM</th></tr>{trs}</table></div>"""


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    sm = total_summary()
    compare = rows("""
    SELECT f.name firm_name,p.name product, COALESCE(fd.firm_qty,0) firm_qty,
           COALESCE(en.worker_qty,0) worker_qty,
           COALESCE(en.worker_qty,0)-COALESCE(fd.firm_qty,0) diff
    FROM products p
    JOIN firms f ON f.id=p.firm_id
    LEFT JOIN (SELECT product_id,SUM(firm_qty) firm_qty FROM deliveries GROUP BY product_id) fd ON fd.product_id=p.id
    LEFT JOIN (SELECT e.product_id,SUM(e.qty) worker_qty FROM entries e JOIN work_types wt ON wt.id=e.work_type_id WHERE wt.counts_product=1 GROUP BY e.product_id) en ON en.product_id=p.id
    WHERE p.active=1 AND (COALESCE(fd.firm_qty,0)>0 OR COALESCE(en.worker_qty,0)>0)
    ORDER BY f.name,p.name
    """)
    comp = "".join([f"<tr><td>{r['firm_name']}</td><td>{r['product']}</td><td class='right'>{int(num(r['firm_qty']))}</td><td class='right'>{int(num(r['worker_qty']))}</td><td class='right {diff_class(r['diff'])}'>{int(num(r['diff']))}</td></tr>" for r in compare]) or "<tr><td colspan='5' class='center small'>Henüz kayıt yok.</td></tr>"
    stage_compare = rows("""
    SELECT f.name firm_name,p.name product,wt.name work_type,
           COALESCE(k.folded_qty,0) folded_qty,
           COALESCE(en.stage_qty,0) stage_qty,
           COALESCE(en.stage_qty,0)-COALESCE(k.folded_qty,0) diff
    FROM work_types wt
    JOIN products p ON p.id=wt.product_id
    JOIN firms f ON f.id=p.firm_id
    LEFT JOIN (
        SELECT e.product_id,SUM(e.qty) folded_qty
        FROM entries e JOIN work_types x ON x.id=e.work_type_id
        WHERE x.counts_product=1 GROUP BY e.product_id
    ) k ON k.product_id=p.id
    LEFT JOIN (
        SELECT e.work_type_id,SUM(e.qty*e.package_size) stage_qty
        FROM entries e GROUP BY e.work_type_id
    ) en ON en.work_type_id=wt.id
    WHERE p.active=1 AND wt.active=1 AND wt.counts_product=0
      AND (COALESCE(k.folded_qty,0)>0 OR COALESCE(en.stage_qty,0)>0)
    ORDER BY f.name,p.name,wt.name
    """)
    stage_trs = "".join([f"<tr><td>{r['firm_name']}</td><td>{r['product']}</td><td>{r['work_type']}</td><td class='right'>{int(num(r['folded_qty']))}</td><td class='right'>{int(num(r['stage_qty']))}</td><td class='right {diff_class(r['diff'])}'>{int(num(r['diff']))}</td><td class='{diff_class(r['diff'])}'>{'DOĞRU' if int(num(r['diff']))==0 else 'FAZLA' if num(r['diff'])>0 else 'EKSİK'}</td></tr>" for r in stage_compare]) or "<tr><td colspan='7' class='center small'>Kontrol edilecek işçilik kaydı yok.</td></tr>"
    body = f"""
    <div class="card"><div class="notice">Ana panel tarih aralığı kullanmaz. İşçilik kutusu alttaki NET KALAN sütununun toplamıdır.</div></div>
    <div class="kpis"><div class="kpi"><span>Firma Teslim Adet</span><b>{int(num(sm['qty']))}</b></div><div class="kpi"><span>Firma Hak Ediş</span><b>{money(sm['revenue'])}</b></div><div class="kpi"><span>İşçilik</span><b>{money(sm['labor'])}</b></div><div class="kpi"><span>Masraflar</span><b>{money(sm['expense'])}</b></div><div class="kpi"><span>Net Kazanç</span><b>{money(sm['net'])}</b></div></div>
    <div class="card"><h2>Firma Teslimi ve Ana Ürün Adedi</h2><p class='small'>Her ürün için seçtiğiniz “Ana Adet” işi gerçek ürün adedi kabul edilir.</p><table><tr><th>Firma</th><th>Ürün</th><th class='right'>Firma Teslim Adet</th><th class='right'>Ana İş Adedi</th><th class='right'>Fark</th></tr>{comp}</table></div>
    <div class="card"><h2>İşçilik Adet Kontrolü</h2><p class='small'>Her işin adedi, o firma ve ürün için seçtiğiniz ana işin adediyle karşılaştırılır. Fark sıfırsa doğru, artıysa fazla, eksiyse eksik girilmiştir.</p><table><tr><th>Firma</th><th>Ürün</th><th>Yapılan İş</th><th class='right'>Ana İş Adedi</th><th class='right'>Girilen İş Adedi</th><th class='right'>Fark</th><th>Durum</th></tr>{stage_trs}</table></div>
    <div class="card"><h2>Son Çalışan Kayıtları</h2>{entries_table(last_entries())}</div>
    """
    return page("Katlama Atölyesi Ana Panel", body)


@app.get("/workers", response_class=HTMLResponse)
def workers():
    host = public_base_url()
    data = rows("""
    SELECT w.*, COALESCE(en.qty,0) qty, COALESCE(en.earned,0) earned, COALESCE(ad.amount,0) avans, COALESCE(pa.amount,0) odeme, COALESCE(en.earned,0)-COALESCE(ad.amount,0)-COALESCE(pa.amount,0) net
    FROM workers w
    LEFT JOIN (SELECT worker_id,SUM(qty) qty,SUM(qty*worker_price) earned FROM entries GROUP BY worker_id) en ON en.worker_id=w.id
    LEFT JOIN (SELECT worker_id,SUM(amount) amount FROM advances GROUP BY worker_id) ad ON ad.worker_id=w.id
    LEFT JOIN (SELECT worker_id,SUM(amount) amount FROM payments GROUP BY worker_id) pa ON pa.worker_id=w.id
    WHERE w.active=1
    ORDER BY w.name
    """)
    trs = ""
    for w in data:
        legacy_token = None
        for old_token, old_name in LEGACY_WORKER_TOKENS.items():
            if str(w['name']).strip().lower().startswith(old_name.strip().lower()):
                legacy_token = old_token
                break
        kullanilan_token = legacy_token or w['token']
        path = f"/w/{kullanilan_token}"
        link = host + path
        mesaj = f"Merhaba {w['name']} ……\n\nKatlama adet giriş linkin:\n{link}\n\nLinke tıkla, açılmazsa kopyalayıp Chrome'a yapıştır."
        wa = f"https://wa.me/?text={quote(mesaj)}"
        trs += f"<tr><td>{w['id']}</td><td>{w['name']}</td><td>{w.get('phone') or ''}</td><td class='right'>{int(num(w['qty']))}</td><td class='right'>{money(w['earned'])}</td><td class='right'>{money(w['avans'])}</td><td class='right'>{money(w['odeme'])}</td><td class='right'>{money(w['net'])}</td><td class='link-cell'><a class='copy' href='{link}' target='_blank' title='{link}'>{link}</a></td><td><div class='actions'><a class='btn cyan' href='{link}' target='_blank'>Aç</a><a class='btn green' href='{wa}' target='_blank'>WhatsApp</a><a class='btn yellow' href='/refresh-worker-token/{w['id']}'>Yeni Link</a><form class='inline' method='post' action='/delete-worker/{w['id']}'><button class='btn red' type='submit'>Sil</button></form></div></td></tr>"
    body = f"""
    <div class="card"><h2>Çalışan Ekle</h2><form method="post" action="/add-worker"><div class="grid"><div><label>Çalışan Adı</label><input name="name" required></div><div><label>Telefon</label><input name="phone" placeholder="05..."></div></div><br><button class="btn green">Çalışan Kaydet</button></form></div>
    <div class="card"><h2>Çalışan Linkleri</h2><div class='table-wrap'><table class='workers-table'><tr><th>ID</th><th>ÇALIŞAN</th><th>TELEFON</th><th class='right'>ADET</th><th class='right'>HAKEDİŞ</th><th class='right'>AVANS</th><th class='right'>ÖDEME</th><th class='right'>NET KALAN</th><th>LİNK</th><th>İŞLEM</th></tr>{trs or '<tr><td colspan="10" class="center small">Çalışan yok.</td></tr>'}</table></div></div>
    """
    return page("Çalışan Linkleri", body)


@app.post("/add-worker")
def add_worker(name: str = Form(...), phone: str = Form("")):
    name = " ".join(name.strip().split())
    if name:
        exec_db("INSERT INTO workers(name,phone,token,active,created_at) VALUES(%s,%s,%s,1,%s) ON CONFLICT(name) DO UPDATE SET phone=EXCLUDED.phone, active=1, token=COALESCE(NULLIF(workers.token,''), EXCLUDED.token)", (name, phone, secrets.token_urlsafe(14), now_iso()))
    return RedirectResponse("/workers", status_code=303)


@app.get("/refresh-worker-token/{wid}")
def refresh_worker_token(wid: int):
    # Bu buton sadece seçilen çalışanın linkini yeniler. Diğer çalışanların linkleri değişmez.
    exec_db("UPDATE workers SET token=%s WHERE id=%s", (secrets.token_urlsafe(14), wid))
    return RedirectResponse("/workers", status_code=303)


@app.post("/delete-worker/{wid}")
@app.get("/delete-worker/{wid}")
def delete_worker(wid: int):
    exec_db("UPDATE workers SET active=0 WHERE id=%s", (wid,))
    return RedirectResponse("/workers", status_code=303)


@app.get("/products", response_class=HTMLResponse)
def products(error: Optional[str] = None):
    firms = rows("SELECT * FROM firms WHERE active=1 ORDER BY name")
    data = rows("""SELECT p.*,f.name firm_name FROM products p JOIN firms f ON f.id=p.firm_id WHERE p.active=1 ORDER BY f.name,p.name""")
    deleted_products = rows("""SELECT p.id,p.name,f.name firm_name FROM products p JOIN firms f ON f.id=p.firm_id WHERE p.active=0 ORDER BY f.name,p.name""")
    deleted_work_types = rows("""SELECT wt.id,wt.name,p.name product_name,f.name firm_name FROM work_types wt JOIN products p ON p.id=wt.product_id JOIN firms f ON f.id=p.firm_id WHERE wt.active=0 ORDER BY f.name,p.name,wt.name""")
    work_types = rows("""SELECT wt.*,p.name product_name,p.firm_price,f.name firm_name,
                        (SELECT COALESCE(SUM(x.worker_price),0) FROM work_types x WHERE x.product_id=wt.product_id AND x.active=1) total_labor
                        FROM work_types wt JOIN products p ON p.id=wt.product_id JOIN firms f ON f.id=p.firm_id
                        WHERE wt.active=1 AND p.active=1 ORDER BY f.name,p.name,wt.name""")
    profit_data = rows("""SELECT f.name firm_name,p.name product_name,p.firm_price,
                          COALESCE(SUM(CASE WHEN wt.pay_basis='piece' AND wt.active=1 THEN wt.worker_price ELSE 0 END),0) piece_labor,
                          COALESCE(SUM(CASE WHEN wt.pay_basis='package' AND wt.active=1 THEN wt.worker_price ELSE 0 END),0) package_labor
                          FROM products p JOIN firms f ON f.id=p.firm_id
                          LEFT JOIN work_types wt ON wt.product_id=p.id
                          WHERE p.active=1 GROUP BY f.name,p.id,p.name,p.firm_price ORDER BY f.name,p.name""")
    def product_row(p):
        move_opts = "".join([f"<option value='{f['id']}' {'selected' if f['id']==p['firm_id'] else ''}>{f['name']}</option>" for f in firms])
        return f"<tr><td>{p['id']}</td><td>{p['firm_name']}</td><td>{p['name']}</td><td class='right'>{money(p['firm_price'])}</td><td><form method='post' action='/move-product-firm/{p['id']}'><select name='firm_id'>{move_opts}</select><button class='btn yellow' type='submit'>Firmayı Değiştir</button></form><form method='post' action='/delete-product/{p['id']}' style='display:inline'><button class='btn red' type='submit'>Sil</button></form></td></tr>"
    trs = "".join([product_row(p) for p in data]) or "<tr><td colspan='5' class='center small'>Ürün yok.</td></tr>"
    wt_trs = "".join([f"<tr><td>{w['firm_name']}</td><td>{w['product_name']}</td><td>{w['name']}</td><td>{'ANA ADET' if w['counts_product']==1 else ('Paket başına işçilik' if w['pay_basis']=='package' else 'Adet başına işçilik')}</td><td class='right'>{money(w['worker_price'])}</td><td>{'<span class=\"diff-zero\">ANA ADET SEÇİLİ</span>' if w['counts_product']==1 else f'<form method=\"post\" action=\"/set-main-work/{w["id"]}\" style=\"display:inline\"><button class=\"btn green\" type=\"submit\">Ana Adet Yap</button></form>'} <form method='post' action='/delete-work-type/{w['id']}' style='display:inline'><button class='btn red' type='submit'>Sil</button></form></td></tr>" for w in work_types]) or "<tr><td colspan='6' class='center small'>Henüz işçilik aşaması yok.</td></tr>"
    opts = "".join([f"<option value='{p['id']}'>{p['firm_name']} — {p['name']} — Firma fiyatı {money(p['firm_price'])}</option>" for p in data])
    firm_opts = "".join([f"<option value='{f['id']}'>{f['name']}</option>" for f in firms])
    firm_trs = "".join([f"<tr><td>{f['id']}</td><td>{f['name']}</td></tr>" for f in firms])
    profit_trs = ""
    for p in profit_data:
        pack_sizes = (3,6,7) if num(p['package_labor']) > 0 else (1,)
        for pack_size in pack_sizes:
            labor_per_piece = num(p['piece_labor']) + (num(p['package_labor']) / pack_size if pack_size > 1 else 0)
            profit_per_piece = num(p['firm_price']) - labor_per_piece
            package_text = f"{pack_size}'lü paket" if pack_size > 1 else "Paket işi yok"
            profit_trs += f"<tr><td>{p['firm_name']}</td><td>{p['product_name']}</td><td>{package_text}</td><td class='right'>{money(p['firm_price'])}</td><td class='right'>{money(labor_per_piece)}</td><td class='right'>{money(profit_per_piece)}</td></tr>"
    if not profit_trs:
        profit_trs = "<tr><td colspan='6' class='center small'>Ürün veya işçilik kaydı yok.</td></tr>"
    deleted_product_trs = "".join([f"<tr><td>{p['firm_name']}</td><td>Ürün</td><td>{p['name']}</td><td><form method='post' action='/restore-product/{p['id']}'><button class='btn green'>Geri Getir</button></form></td></tr>" for p in deleted_products])
    deleted_work_trs = "".join([f"<tr><td>{w['firm_name']}</td><td>İşçilik</td><td>{w['product_name']} — {w['name']}</td><td><form method='post' action='/restore-work-type/{w['id']}'><button class='btn green'>Geri Getir</button></form></td></tr>" for w in deleted_work_types])
    deleted_trs = deleted_product_trs + deleted_work_trs or "<tr><td colspan='4' class='center small'>Geri getirilecek silinmiş kayıt yok.</td></tr>"
    error_box = f"<div class='bad'>{error}</div>" if error else ""
    body = f"""{error_box}
    <div class="card"><h2>1. Firma Ekle</h2><form method="post" action="/save-firm"><div class="grid"><div><label>Firma Adı</label><input name="name" required></div></div><br><button class="btn green">Firmayı Kaydet</button></form><br><table><tr><th>ID</th><th>FİRMA</th></tr>{firm_trs}</table></div>
    <div class="card"><h2>2. Firmadan Alınan Ürün ve Fiyatı</h2><form method="post" action="/save-product"><div class="grid"><div><label>Firma</label><select name="firm_id" required>{firm_opts}</select></div><div><label>Ürün (örnek: Şal)</label><input name="name" required></div><div><label>Firmadan Alınan Birim Fiyat</label><input name="firm_price" type="number" step="0.01" min="0" required></div></div><br><button class="btn green">Ürünü Kaydet / Güncelle</button></form><p class='small'>Bu fiyat ürünün tamamı içindir; her işçilik aşamasında yeniden hesaplanmaz.</p></div>
    <div class="card"><table><tr><th>ID</th><th>FİRMA</th><th>ÜRÜN</th><th class='right'>FİRMADAN ALINAN FİYAT</th><th>İŞLEM</th></tr>{trs}</table></div>
    <div class="card"><h2>Adet Başı İşçilik ve Kâr Karşılaştırması</h2><p class='small'>Toplam işçilik, bütün adet başı işlerin toplamına paket ücretinin paket içindeki ürün sayısına düşen payı eklenerek hesaplanır.</p><table><tr><th>FİRMA</th><th>ÜRÜN</th><th>PAKET TÜRÜ</th><th class='right'>FİRMADAN ALINAN / ADET</th><th class='right'>ÇALIŞANA VERİLEN / ADET</th><th class='right'>SİZE KALAN / ADET</th></tr>{profit_trs}</table></div>
    <div class="card"><h2>3. Çalışana Verilen İşleri Bölüştür</h2><form method="post" action="/save-work-type"><div class="grid"><div><label>Hangi Firma / Ürün?</label><select name="product_id" required>{opts}</select></div><div><label>Yapılan İş</label><input name="name" placeholder="Örnek: Şal Çoklu Paketleme" required></div><div><label>Ücret Nasıl Hesaplansın?</label><select name="pay_basis"><option value="piece">Ürün adedi başına</option><option value="package">Paket başına</option></select></div><div><label>Çalışana Verilen Ücret</label><input name="worker_price" type="number" step="0.01" min="0" required></div></div><br><button class="btn green">İşçilik Aşamasını Kaydet</button></form><p class='small'>Çoklu paketlemede “Paket başına” seçin. Çalışan paket sayısını ve 3'lü, 6'lı veya 7'li olduğunu seçer.</p></div>
    <div class="card"><table><tr><th>FİRMA</th><th>ÜRÜN</th><th>İŞÇİLİK AŞAMASI</th><th>HESAPLAMA</th><th class='right'>ÇALIŞAN ÜCRETİ</th><th>İŞLEM</th></tr>{wt_trs}</table></div>
    <div class="card"><h2>Silinen Kayıtları Geri Getir</h2><p class='small'>Yanlışlıkla sildiğiniz kaydın karşısındaki yeşil “Geri Getir” düğmesine basın.</p><table><tr><th>FİRMA</th><th>TÜR</th><th>KAYIT</th><th>İŞLEM</th></tr>{deleted_trs}</table></div>
    """
    return page("Firma / Ürün / Fiyat", body)


@app.post("/save-product")
def save_product(firm_id: int = Form(...), name: str = Form(...), firm_price: float = Form(...)):
    name = " ".join(name.strip().split())
    if name:
        exec_db("""INSERT INTO products(firm_id,name,firm_price,worker_price,active,created_at) VALUES(%s,%s,%s,0,1,%s) ON CONFLICT(firm_id,name) DO UPDATE SET firm_price=EXCLUDED.firm_price, active=1""", (firm_id, name, firm_price, now_iso()))
    return RedirectResponse("/products", status_code=303)


@app.post("/save-firm")
def save_firm(name: str = Form(...)):
    name = " ".join(name.strip().split())
    if name:
        exec_db("INSERT INTO firms(name,active,created_at) VALUES(%s,1,%s) ON CONFLICT(name) DO UPDATE SET active=1", (name, now_iso()))
    return RedirectResponse("/products", status_code=303)


@app.post("/move-product-firm/{pid}")
def move_product_firm(pid: int, firm_id: int = Form(...)):
    exec_db("""UPDATE products p SET firm_id=%s WHERE p.id=%s
               AND NOT EXISTS(SELECT 1 FROM products x WHERE x.firm_id=%s AND x.name=p.name AND x.id<>p.id)""",
            (firm_id, pid, firm_id))
    return RedirectResponse("/products", status_code=303)


@app.post("/save-work-type")
def save_work_type(product_id: int = Form(...), name: str = Form(...), pay_basis: str = Form("piece"), worker_price: float = Form(...)):
    name = " ".join(name.strip().split())
    product = one("SELECT firm_price FROM products WHERE id=%s AND active=1", (product_id,))
    basis = "package" if pay_basis == "package" else "piece"
    current = one("SELECT COALESCE(SUM(worker_price),0) total FROM work_types WHERE product_id=%s AND active=1 AND pay_basis='piece' AND name<>%s", (product_id, name))
    price_is_valid = basis == "package" or num(current["total"]) + worker_price <= num(product["firm_price"] if product else 0)
    if product and name and price_is_valid:
        existing_main = one("SELECT id FROM work_types WHERE product_id=%s AND counts_product=1 LIMIT 1", (product_id,))
        counts_product = 1 if (not existing_main and "katlama" in name.lower()) else 0
        exec_db("""INSERT INTO work_types(product_id,name,worker_price,pay_basis,counts_product,active,created_at) VALUES(%s,%s,%s,%s,%s,1,%s)
                   ON CONFLICT(product_id,name) DO UPDATE SET worker_price=EXCLUDED.worker_price,pay_basis=EXCLUDED.pay_basis,counts_product=EXCLUDED.counts_product,active=1""",
                (product_id, name, worker_price, basis, counts_product, now_iso()))
        return RedirectResponse("/products", status_code=303)
    return RedirectResponse("/products?error=İşçilik toplamı firma fiyatını geçemez", status_code=303)


@app.post("/delete-work-type/{wid}")
@app.get("/delete-work-type/{wid}")
def delete_work_type(wid: int):
    exec_db("UPDATE work_types SET active=0 WHERE id=%s", (wid,))
    return RedirectResponse("/products", status_code=303)


@app.post("/set-main-work/{wid}")
def set_main_work(wid: int):
    selected = one("SELECT product_id FROM work_types WHERE id=%s AND active=1", (wid,))
    if selected:
        exec_db("UPDATE work_types SET counts_product=0 WHERE product_id=%s", (selected["product_id"],))
        exec_db("UPDATE work_types SET counts_product=1 WHERE id=%s", (wid,))
    return RedirectResponse("/products", status_code=303)


@app.post("/restore-work-type/{wid}")
def restore_work_type(wid: int):
    exec_db("UPDATE work_types SET active=1 WHERE id=%s", (wid,))
    return RedirectResponse("/products", status_code=303)


@app.post("/delete-product/{pid}")
@app.get("/delete-product/{pid}")
def delete_product(pid: int):
    exec_db("UPDATE products SET active=0 WHERE id=%s", (pid,))
    return RedirectResponse("/products", status_code=303)


@app.post("/restore-product/{pid}")
def restore_product(pid: int):
    exec_db("UPDATE products SET active=1 WHERE id=%s", (pid,))
    return RedirectResponse("/products", status_code=303)


@app.get("/deliveries", response_class=HTMLResponse)
def deliveries():
    products = rows("""SELECT p.id,p.name,f.name firm_name FROM products p JOIN firms f ON f.id=p.firm_id WHERE p.active=1 ORDER BY f.name,p.name""")
    opts = "".join([f"<option value='{p['id']}'>{p['firm_name']} — {p['name']}</option>" for p in products])
    data = rows("""SELECT d.id,d.deliv_date,f.name firm_name,p.name product,d.firm_qty,d.firm_qty*p.firm_price amount,COALESCE(d.note,'') note FROM deliveries d JOIN products p ON p.id=d.product_id JOIN firms f ON f.id=p.firm_id ORDER BY d.deliv_date DESC,d.id DESC LIMIT 500""")
    trs = "".join([f"<tr><td>{r['id']}</td><td>{display_date(r['deliv_date'])}</td><td>{r['firm_name']}</td><td>{r['product']}</td><td class='right'>{int(num(r['firm_qty']))}</td><td class='right'>{money(r['amount'])}</td><td>{r['note']}</td><td><form method='post' action='/delete-delivery/{r['id']}' style='display:inline'><button class='btn red' type='submit'>Sil</button></form></td></tr>" for r in data]) or "<tr><td colspan='8' class='center small'>Teslim kaydı yok.</td></tr>"
    body = f"""<div class="card"><h2>Firma Teslim Gir</h2><form method="post" action="/add-delivery"><div class="grid"><div><label>Tarih (Gün/Ay/Yıl)</label><input name="deliv_date" type="date" value="{today()}" required></div><div><label>Firma / Ürün</label><select name="product_id">{opts}</select></div><div><label>Firma Teslim Adet</label><input name="firm_qty" type="number" min="1" required></div><div style="grid-column:span 2"><label>Not</label><input name="note"></div></div><br><button class="btn green">Teslim Kaydet</button></form></div><div class="card"><table><tr><th>ID</th><th>TARİH</th><th>FİRMA</th><th>ÜRÜN</th><th class='right'>FİRMA TESLİM ADET</th><th class='right'>FİRMA HAKEDİŞ</th><th>NOT</th><th>İŞLEM</th></tr>{trs}</table></div>"""
    return page("Firma Teslim", body)


@app.post("/add-delivery")
def add_delivery(deliv_date: str = Form(...), product_id: int = Form(...), firm_qty: int = Form(...), note: str = Form("")):
    if int(firm_qty) > 0:
        exec_db("INSERT INTO deliveries(deliv_date,worker_id,product_id,firm_qty,worker_qty,note,created_at) VALUES(%s,NULL,%s,%s,0,%s,%s)", (normalize_date(deliv_date), product_id, firm_qty, note, now_iso()))
    return RedirectResponse("/deliveries", status_code=303)


@app.post("/delete-delivery/{did}")
@app.get("/delete-delivery/{did}")
def delete_delivery(did: int):
    exec_db("DELETE FROM deliveries WHERE id=%s", (did,)); return RedirectResponse("/deliveries", status_code=303)


def get_worker_by_token(token: str):
    # Her link token üzerinden ilgili kişiyi açar.
    return one("SELECT * FROM workers WHERE token=%s AND active=1", (token,))

@app.get("/w/{token}", response_class=HTMLResponse)
def worker_page(token: str, saved: Optional[str] = None, error: Optional[str] = None):
    worker = get_worker_by_token(token)
    if not worker: return page("Link Geçersiz", "<div class='bad'>Bu çalışan linki geçersiz veya pasif.</div>", nav=False)
    work_types = rows("""SELECT wt.id,wt.name,wt.worker_price,wt.pay_basis,p.name product_name,f.name firm_name
                        FROM work_types wt JOIN products p ON p.id=wt.product_id JOIN firms f ON f.id=p.firm_id
                        WHERE wt.active=1 AND p.active=1 ORDER BY f.name,p.name,wt.name""")
    product_opts = "".join([f"<option value='{w['id']}' data-basis='{w['pay_basis']}'>{w['firm_name']} — {w['product_name']} — {w['name']} ({money(w['worker_price'])} / {'paket' if w['pay_basis']=='package' else 'adet'})</option>" for w in work_types])
    total = one("SELECT COALESCE(SUM(qty),0) qty, COALESCE(SUM(qty*worker_price),0) earned FROM entries WHERE worker_id=%s", (worker["id"],))
    paid_total = num(one("SELECT COALESCE(SUM(amount),0) total FROM payments WHERE worker_id=%s", (worker["id"],))["total"])
    adv_total = num(one("SELECT COALESCE(SUM(amount),0) total FROM advances WHERE worker_id=%s", (worker["id"],))["total"])
    today_total = one("SELECT COALESCE(SUM(qty),0) qty FROM entries WHERE worker_id=%s AND work_date=%s", (worker["id"], today()))
    msg = "<div class='notice'>Adet kaydedildi.</div>" if saved else (f"<div class='bad'>{error}</div>" if error else "")
    last_rows = rows("""SELECT e.id,e.work_date,COALESCE(wt.name,p.name) product,e.qty,e.package_size,e.qty*e.package_size piece_qty,e.qty*e.worker_price earned,COALESCE(e.note,'') note FROM entries e JOIN products p ON p.id=e.product_id LEFT JOIN work_types wt ON wt.id=e.work_type_id WHERE e.worker_id=%s ORDER BY e.work_date DESC,e.id DESC LIMIT 30""", (worker["id"],))
    record_cards = ""
    for r in last_rows:
        is_package = int(num(r['package_size'])) > 1
        first_label = "Paket Sayısı" if is_package else "Yapılan Adet"
        package_value = f"{int(num(r['package_size']))}'li" if is_package else "Paket değil"
        record_cards += f"""<div class='record-card'><div class='record-head'><b>{r['product']}</b><div class='record-date'>{display_date(r['work_date'])}</div></div><div class='record-values'><div class='record-value'><span>{first_label}</span><b>{int(num(r['qty']))}</b></div><div class='record-value'><span>Paket Türü</span><b>{package_value}</b></div><div class='record-value'><span>Toplam Ürün</span><b>{int(num(r['piece_qty']))}</b></div><div class='record-value'><span>Hakediş</span><b>{money(r['earned'])}</b></div></div>{f"<div class='record-note'>Not: {r['note']}</div>" if r['note'] else ''}<div class='record-actions'><a class='btn yellow' href='/w/{token}/edit/{r['id']}'>Güncelle</a><form method='post' action='/w/{token}/delete/{r['id']}'><button class='btn red' type='submit'>Sil</button></form></div></div>"""
    if not record_cards:
        record_cards = "<div class='center small'>Henüz kayıt yok.</div>"
    kalan = num(total["earned"] if total else 0) - paid_total - adv_total
    body = f"""{msg}<div class="worker-hero"><div class="worker-title">{worker['name']} - İşçilik Paneli</div><div class="worker-sub">Yaptığın işi seç, adetini gir; yanlışsa güncelle veya sil.</div><div class="kpis three"><div class="kpi"><span>Bugünkü İş Adedim</span><b>{int(num(today_total['qty']))}</b></div><div class="kpi"><span>Genel Hak Edişim</span><b>{money(total['earned'] if total else 0)}</b></div><div class="kpi"><span>Net Kalan</span><b>{money(kalan)}</b></div></div></div><div class="card worker-form"><h2>Yapılan İşi Gir</h2><form method="post" action="/w/{token}/add"><div class="grid"><div><label>Tarih (Gün/Ay/Yıl)</label><input name="work_date" type="date" value="{today()}" required></div><div><label>Yapılan İş</label><select id="work_type_id" name="work_type_id" required onchange="paketAlani()">{product_opts}</select></div><div><label id="qty_label">Yapılan Adet / Paket Sayısı</label><input name="qty" type="number" min="1" required autofocus></div><div id="package_box"><label>Pakette Kaç Ürün Var?</label><select name="package_size"><option value="3">3'lü</option><option value="6">6'lı</option><option value="7">7'li</option></select></div><div><label>Not</label><input name="note" placeholder="İsteğe bağlı"></div></div><br><button class="btn green" type="submit">ADETİ KAYDET</button></form></div><div class="card"><h2>Son Kayıtlarım</h2><div class='record-list'>{record_cards}</div></div><script>function paketAlani(){{var s=document.getElementById('work_type_id');var b=s.options[s.selectedIndex]?.dataset.basis==='package';document.getElementById('package_box').style.display=b?'block':'none';document.getElementById('qty_label').textContent=b?'Yapılan Paket Sayısı':'Yapılan Ürün Adedi';}}paketAlani();</script>"""
    return page("Çalışan Paneli", body, nav=False)


@app.post("/w/{token}/add")
def worker_add(token: str, work_date: str = Form(...), work_type_id: int = Form(...), qty: int = Form(...), package_size: int = Form(1), note: str = Form("")):
    worker = get_worker_by_token(token)
    work_type = one("""SELECT wt.*,p.firm_price FROM work_types wt JOIN products p ON p.id=wt.product_id
                       WHERE wt.id=%s AND wt.active=1 AND p.active=1""", (work_type_id,))
    if not worker or not work_type or int(qty) <= 0:
        return RedirectResponse(f"/w/{token}?error=Kayıt yapılamadı", status_code=303)
    pack = max(1, int(package_size)) if work_type["pay_basis"] == "package" else 1
    exec_db("INSERT INTO entries(work_date,worker_id,product_id,work_type_id,qty,package_size,firm_price,worker_price,note,created_at,source) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'telefon')", (normalize_date(work_date), worker["id"], work_type["product_id"], work_type_id, qty, pack, work_type["firm_price"], work_type["worker_price"], note, now_iso()))
    return RedirectResponse(f"/w/{token}?saved=1", status_code=303)


@app.get("/w/{token}/edit/{eid}", response_class=HTMLResponse)
def worker_edit_form(token: str, eid: int):
    worker = get_worker_by_token(token)
    r = one("SELECT * FROM entries WHERE id=%s", (eid,))
    if not worker or not r or r["worker_id"] != worker["id"]: return RedirectResponse(f"/w/{token}", status_code=303)
    work_types = rows("""SELECT wt.id,wt.name,wt.pay_basis,p.name product_name FROM work_types wt JOIN products p ON p.id=wt.product_id WHERE wt.active=1 AND p.active=1 ORDER BY p.name,wt.name""")
    opts = "".join([f"<option value='{w['id']}' {'selected' if w['id']==r.get('work_type_id') else ''}>{w['product_name']} — {w['name']}</option>" for w in work_types])
    pack_opts = "".join([f"<option value='{n}' {'selected' if n==int(r.get('package_size') or 1) else ''}>{n}'lü</option>" for n in (1,3,6,7)])
    body = f"""<div class='card worker-form'><h2>Kayıt Güncelle</h2><form method='post' action='/w/{token}/edit/{eid}'><div class='grid'><div><label>Tarih (Gün/Ay/Yıl)</label><input name='work_date' type='date' value='{r['work_date']}'></div><div><label>Yapılan İş</label><select name='work_type_id'>{opts}</select></div><div><label>Adet / Paket Sayısı</label><input name='qty' type='number' min='1' value='{r['qty']}'></div><div><label>Paket İçi Adet</label><select name='package_size'>{pack_opts}</select></div><div><label>Not</label><input name='note' value='{r['note'] or ''}'></div></div><br><button class='btn green'>Güncelle</button></form></div>"""
    return page("Kayıt Güncelle", body, nav=False)


@app.post("/w/{token}/edit/{eid}")
def worker_edit(token: str, eid: int, work_date: str = Form(...), work_type_id: int = Form(...), qty: int = Form(...), package_size: int = Form(1), note: str = Form("")):
    worker = get_worker_by_token(token)
    work_type = one("""SELECT wt.*,p.firm_price FROM work_types wt JOIN products p ON p.id=wt.product_id WHERE wt.id=%s""", (work_type_id,))
    if worker and work_type and int(qty) > 0:
        pack = max(1, int(package_size)) if work_type["pay_basis"] == "package" else 1
        exec_db("UPDATE entries SET work_date=%s, product_id=%s, work_type_id=%s, qty=%s, package_size=%s, firm_price=%s, worker_price=%s, note=%s WHERE id=%s AND worker_id=%s", (normalize_date(work_date), work_type["product_id"], work_type_id, qty, pack, work_type["firm_price"], work_type["worker_price"], note, eid, worker["id"]))
    return RedirectResponse(f"/w/{token}", status_code=303)


@app.post("/w/{token}/delete/{eid}")
@app.get("/w/{token}/delete/{eid}")
def worker_delete(token: str, eid: int):
    worker = get_worker_by_token(token)
    if worker: exec_db("DELETE FROM entries WHERE id=%s AND worker_id=%s", (eid, worker["id"]))
    return RedirectResponse(f"/w/{token}", status_code=303)


@app.get("/edit-entry/{eid}", response_class=HTMLResponse)
def edit_entry_form(eid: int):
    r = one("SELECT * FROM entries WHERE id=%s", (eid,));
    if not r: return RedirectResponse("/dashboard", status_code=303)
    workers = rows("SELECT id,name FROM workers WHERE active=1 ORDER BY name")
    work_types = rows("""SELECT wt.id,wt.name,wt.pay_basis,p.name product_name FROM work_types wt JOIN products p ON p.id=wt.product_id WHERE wt.active=1 AND p.active=1 ORDER BY p.name,wt.name""")
    wopts = "".join([f"<option value='{w['id']}' {'selected' if w['id']==r['worker_id'] else ''}>{w['name']}</option>" for w in workers])
    popts = "".join([f"<option value='{w['id']}' {'selected' if w['id']==r.get('work_type_id') else ''}>{w['product_name']} — {w['name']}</option>" for w in work_types])
    pack_opts = "".join([f"<option value='{n}' {'selected' if n==int(r.get('package_size') or 1) else ''}>{n}'lü</option>" for n in (1,3,6,7)])
    body = f"""<div class='card'><h2>Çalışan Kaydı Güncelle</h2><form method='post' action='/edit-entry/{eid}'><div class='grid'><div><label>Tarih (Gün/Ay/Yıl)</label><input name='work_date' type='date' value='{r['work_date']}'></div><div><label>Çalışan</label><select name='worker_id'>{wopts}</select></div><div><label>Yapılan İş</label><select name='work_type_id'>{popts}</select></div><div><label>Adet / Paket Sayısı</label><input name='qty' type='number' min='1' value='{r['qty']}'></div><div><label>Paket İçi Adet</label><select name='package_size'>{pack_opts}</select></div><div><label>Not</label><input name='note' value='{r['note'] or ''}'></div></div><br><button class='btn green'>Güncelle</button></form></div>"""
    return page("Çalışan Kaydı Güncelle", body)


@app.post("/edit-entry/{eid}")
def edit_entry(eid: int, work_date: str = Form(...), worker_id: int = Form(...), work_type_id: int = Form(...), qty: int = Form(...), package_size: int = Form(1), note: str = Form("")):
    work_type = one("""SELECT wt.*,p.firm_price FROM work_types wt JOIN products p ON p.id=wt.product_id WHERE wt.id=%s""", (work_type_id,))
    if work_type and int(qty) > 0:
        pack = max(1, int(package_size)) if work_type["pay_basis"] == "package" else 1
        exec_db("UPDATE entries SET work_date=%s, worker_id=%s, product_id=%s, work_type_id=%s, qty=%s, package_size=%s, firm_price=%s, worker_price=%s, note=%s WHERE id=%s", (normalize_date(work_date), worker_id, work_type["product_id"], work_type_id, qty, pack, work_type["firm_price"], work_type["worker_price"], note, eid))
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/delete-entry/{entry_id}")
@app.get("/delete-entry/{entry_id}")
def delete_entry(entry_id: int):
    exec_db("DELETE FROM entries WHERE id=%s", (entry_id,)); return RedirectResponse("/dashboard", status_code=303)


@app.get("/expenses", response_class=HTMLResponse)
def expenses():
    total = one("SELECT COALESCE(SUM(amount),0) total FROM expenses")["total"] or 0
    data = rows("SELECT * FROM expenses ORDER BY exp_date DESC,id DESC LIMIT 500")
    trs = "".join([f"<tr><td>{r['id']}</td><td>{display_date(r['exp_date'])}</td><td>{r['category']}</td><td class='right'>{money(r['amount'])}</td><td>{r['note'] or ''}</td><td><form method='post' action='/delete-expense/{r['id']}' style='display:inline'><button class='btn red' type='submit'>Sil</button></form></td></tr>" for r in data]) or "<tr><td colspan='6' class='center small'>Masraf yok.</td></tr>"
    body = f"""<div class="kpis three"><div class="kpi"><span>Genel Masraf Toplamı</span><b>{money(total)}</b></div><div class="kpi"><span>Tarih Filtresi</span><b>Yok</b></div><div class="kpi"><span>Kayıt</span><b>Her Giriş Ayrı</b></div></div><div class="card"><h2>Masraf Ekle</h2><form method="post" action="/add-expense"><div class="grid"><div><label>Tarih (Gün/Ay/Yıl)</label><input name="exp_date" type="date" value="{today()}" required></div><div><label>Kategori</label><input name="category" required></div><div><label>Tutar</label><input name="amount" type="number" step="0.01" min="0" required></div><div style="grid-column:span 2"><label>Not</label><input name="note"></div></div><br><button class="btn green">Masraf Kaydet</button></form></div><div class="card"><table><tr><th>ID</th><th>TARİH</th><th>KATEGORİ</th><th class='right'>TUTAR</th><th>NOT</th><th>İŞLEM</th></tr>{trs}</table></div>"""
    return page("Masraflar", body)


@app.post("/add-expense")
def add_expense(exp_date: str = Form(...), category: str = Form(...), amount: float = Form(...), note: str = Form("")):
    exec_db("INSERT INTO expenses(exp_date,category,amount,note,created_at) VALUES(%s,%s,%s,%s,%s)", (normalize_date(exp_date), category, amount, note, now_iso())); return RedirectResponse("/expenses", status_code=303)


@app.post("/delete-expense/{eid}")
@app.get("/delete-expense/{eid}")
def delete_expense(eid: int):
    exec_db("DELETE FROM expenses WHERE id=%s", (eid,)); return RedirectResponse("/expenses", status_code=303)


@app.get("/payments", response_class=HTMLResponse)
def payments():
    workers = rows("SELECT id,name FROM workers WHERE active=1 ORDER BY name")
    opts = "".join([f"<option value='{w['id']}'>{w['name']}</option>" for w in workers])
    data = rows("""SELECT p.id,p.pay_date,w.name worker,p.amount,COALESCE(p.note,'') note FROM payments p JOIN workers w ON w.id=p.worker_id ORDER BY p.pay_date DESC,p.id DESC LIMIT 500""")
    trs = "".join([f"<tr><td>{r['id']}</td><td>{display_date(r['pay_date'])}</td><td>{r['worker']}</td><td class='right'>{money(r['amount'])}</td><td>{r['note']}</td><td><form method='post' action='/delete-payment/{r['id']}' style='display:inline'><button class='btn red' type='submit'>Sil</button></form></td></tr>" for r in data]) or "<tr><td colspan='6' class='center small'>Ödeme yok.</td></tr>"
    advdata = rows("""SELECT a.id,a.adv_date,w.name worker,a.amount,COALESCE(a.note,'') note FROM advances a JOIN workers w ON w.id=a.worker_id ORDER BY a.adv_date DESC,a.id DESC LIMIT 500""")
    advtrs = "".join([f"<tr><td>{r['id']}</td><td>{display_date(r['adv_date'])}</td><td>{r['worker']}</td><td class='right'>{money(r['amount'])}</td><td>{r['note']}</td><td><form method='post' action='/delete-advance/{r['id']}' style='display:inline'><button class='btn red' type='submit'>Sil</button></form></td></tr>" for r in advdata]) or "<tr><td colspan='6' class='center small'>Avans yok.</td></tr>"
    body = f"""<div class="card"><h2>Çalışan Ödemesi</h2><form method="post" action="/add-payment"><div class="grid"><div><label>Tarih (Gün/Ay/Yıl)</label><input name="pay_date" type="date" value="{today()}" required></div><div><label>Çalışan</label><select name="worker_id">{opts}</select></div><div><label>Ödeme Tutarı</label><input name="amount" type="number" step="0.01" min="0" required></div><div style="grid-column:span 2"><label>Not</label><input name="note"></div></div><br><button class="btn green">Ödeme Kaydet</button></form></div><div class="card"><h2>Çalışan Avansı</h2><form method="post" action="/add-advance"><div class="grid"><div><label>Tarih (Gün/Ay/Yıl)</label><input name="adv_date" type="date" value="{today()}" required></div><div><label>Çalışan</label><select name="worker_id">{opts}</select></div><div><label>Avans Tutarı</label><input name="amount" type="number" step="0.01" min="0" required></div><div style="grid-column:span 2"><label>Not</label><input name="note"></div></div><br><button class="btn yellow">Avans Kaydet</button></form></div><div class="card"><h2>Ödemeler</h2><table><tr><th>ID</th><th>TARİH</th><th>ÇALIŞAN</th><th class='right'>ÖDEME</th><th>NOT</th><th>İŞLEM</th></tr>{trs}</table></div><div class="card"><h2>Avanslar</h2><table><tr><th>ID</th><th>TARİH</th><th>ÇALIŞAN</th><th class='right'>AVANS</th><th>NOT</th><th>İŞLEM</th></tr>{advtrs}</table></div><div class="card"><h2>Çalışan Genel Özeti</h2>{entries_table(last_entries(500))}</div>"""
    return page("Ödemeler", body)


@app.post("/add-payment")
def add_payment(pay_date: str = Form(...), worker_id: int = Form(...), amount: float = Form(...), note: str = Form("")):
    exec_db("INSERT INTO payments(pay_date,worker_id,amount,note,created_at) VALUES(%s,%s,%s,%s,%s)", (normalize_date(pay_date), worker_id, amount, note, now_iso())); return RedirectResponse("/payments", status_code=303)


@app.post("/delete-payment/{pid}")
@app.get("/delete-payment/{pid}")
def delete_payment(pid: int): exec_db("DELETE FROM payments WHERE id=%s", (pid,)); return RedirectResponse("/payments", status_code=303)


@app.post("/add-advance")
def add_advance(adv_date: str = Form(...), worker_id: int = Form(...), amount: float = Form(...), note: str = Form("")):
    exec_db("INSERT INTO advances(adv_date,worker_id,amount,note,created_at) VALUES(%s,%s,%s,%s,%s)", (normalize_date(adv_date), worker_id, amount, note, now_iso())); return RedirectResponse("/payments", status_code=303)


@app.post("/delete-advance/{aid}")
@app.get("/delete-advance/{aid}")
def delete_advance(aid: int): exec_db("DELETE FROM advances WHERE id=%s", (aid,)); return RedirectResponse("/payments", status_code=303)


def firm_month_summary(m: str):
    return rows("""
        SELECT f.name firm_name,
               COALESCE(d.delivered_qty,0) delivered_qty,
               COALESCE(d.revenue,0) revenue,
               COALESCE(e.labor,0) labor,
               COALESCE(d.revenue,0)-COALESCE(e.labor,0) profit
        FROM firms f
        LEFT JOIN (
            SELECT p.firm_id,SUM(d.firm_qty) delivered_qty,SUM(d.firm_qty*p.firm_price) revenue
            FROM deliveries d JOIN products p ON p.id=d.product_id
            WHERE d.deliv_date LIKE %s GROUP BY p.firm_id
        ) d ON d.firm_id=f.id
        LEFT JOIN (
            SELECT p.firm_id,SUM(e.qty*e.worker_price) labor
            FROM entries e JOIN products p ON p.id=e.product_id
            WHERE e.work_date LIKE %s GROUP BY p.firm_id
        ) e ON e.firm_id=f.id
        WHERE f.active=1 AND (COALESCE(d.revenue,0)<>0 OR COALESCE(e.labor,0)<>0)
        ORDER BY f.name
    """, (m+"%",m+"%"))


def worker_month_detail(m: str, worker_id: Optional[int] = None):
    return rows("""
        SELECT e.work_date,w.id worker_id,w.name worker,f.name firm_name,p.name product,wt.name work_type,
               e.package_size,SUM(e.qty) qty,SUM(e.qty*e.package_size) product_qty,
               e.worker_price,SUM(e.qty*e.worker_price) earned
        FROM entries e
        JOIN workers w ON w.id=e.worker_id
        JOIN products p ON p.id=e.product_id
        JOIN firms f ON f.id=p.firm_id
        LEFT JOIN work_types wt ON wt.id=e.work_type_id
        WHERE e.work_date LIKE %s AND (%s IS NULL OR e.worker_id=%s)
        GROUP BY e.work_date,w.id,w.name,f.name,p.name,wt.name,e.package_size,e.worker_price
        ORDER BY w.name,e.work_date,wt.name
    """, (m+"%",worker_id,worker_id))


def worker_month_summary_rows(m: str, worker_id: Optional[int] = None):
    return rows("""
        SELECT w.id worker_id,w.name worker,COALESCE(e.earned,0) earned,COALESCE(a.advance,0) advance,
               COALESCE(py.paid,0) paid,
               COALESCE(e.earned,0)-COALESCE(a.advance,0)-COALESCE(py.paid,0) balance
        FROM workers w
        LEFT JOIN (SELECT worker_id,SUM(qty*worker_price) earned FROM entries WHERE work_date LIKE %s GROUP BY worker_id) e ON e.worker_id=w.id
        LEFT JOIN (SELECT worker_id,SUM(amount) advance FROM advances WHERE adv_date LIKE %s GROUP BY worker_id) a ON a.worker_id=w.id
        LEFT JOIN (SELECT worker_id,SUM(amount) paid FROM payments WHERE pay_date LIKE %s GROUP BY worker_id) py ON py.worker_id=w.id
        WHERE (%s IS NULL OR w.id=%s) AND (w.active=1 OR %s IS NOT NULL) AND (COALESCE(e.earned,0)<>0 OR COALESCE(a.advance,0)<>0 OR COALESCE(py.paid,0)<>0)
        ORDER BY w.name
    """, (m+"%",m+"%",m+"%",worker_id,worker_id,worker_id))


def firm_month_detail(m: str):
    return rows("""
        SELECT d.deliv_date,f.name firm_name,p.name product,SUM(d.firm_qty) qty,
               p.firm_price,SUM(d.firm_qty*p.firm_price) amount
        FROM deliveries d
        JOIN products p ON p.id=d.product_id
        JOIN firms f ON f.id=p.firm_id
        WHERE d.deliv_date LIKE %s
        GROUP BY d.deliv_date,f.name,p.name,p.firm_price
        ORDER BY f.name,d.deliv_date,p.name
    """, (m+"%",))


@app.get("/month", response_class=HTMLResponse)
def month(m: Optional[str] = None):
    m = m or this_month(); sm = month_summary(m)
    firm_rows = firm_month_summary(m)
    firm_trs = "".join([f"<tr><td>{r['firm_name']}</td><td class='right'>{int(num(r['delivered_qty']))}</td><td class='right'>{money(r['revenue'])}</td><td class='right'>{money(r['labor'])}</td><td class='right'>{money(r['profit'])}</td></tr>" for r in firm_rows]) or "<tr><td colspan='5' class='center small'>Bu ay firma kaydı yok.</td></tr>"
    worker_rows = worker_month_detail(m)
    worker_trs = "".join([f"<tr><td>{display_date(r['work_date'])}</td><td>{r['worker']}</td><td>{r['firm_name']}</td><td>{r['product']}</td><td>{r['work_type'] or r['product']}</td><td class='right'>{int(num(r['qty']))}</td><td class='right'>{int(num(r['package_size'])) if int(num(r['package_size']))>1 else '-'}</td><td class='right'>{int(num(r['product_qty']))}</td><td class='right'>{money(r['worker_price'])}</td><td class='right'>{money(r['earned'])}</td></tr>" for r in worker_rows]) or "<tr><td colspan='10' class='center small'>Bu ay çalışan işi yok.</td></tr>"
    worker_summary = worker_month_summary_rows(m)
    worker_summary_trs = "".join([f"<tr><td>{r['worker']}</td><td class='right'>{money(r['earned'])}</td><td class='right'>{money(r['advance'])}</td><td class='right'>{money(r['paid'])}</td><td class='right'>{money(r['balance'])}</td></tr>" for r in worker_summary]) or "<tr><td colspan='5' class='center small'>Bu ay çalışan hesabı yok.</td></tr>"
    firm_daily_rows = firm_month_detail(m)
    firm_daily_trs = "".join([f"<tr><td>{display_date(r['deliv_date'])}</td><td>{r['firm_name']}</td><td>{r['product']}</td><td class='right'>{int(num(r['qty']))}</td><td class='right'>{money(r['firm_price'])}</td><td class='right'>{money(r['amount'])}</td></tr>" for r in firm_daily_rows]) or "<tr><td colspan='6' class='center small'>Bu ay firma teslimi yok.</td></tr>"
    body = f"""<div class="card"><form method="get" action="/month"><label>Ay seç: YYYY-AA</label><input name="m" value="{m}" style="max-width:180px;display:inline-block"> <button class="btn green">Hesapla</button> <a class="btn yellow" href="/export-month?m={m}">CSV Rapor Al</a> <a class="btn cyan" href="/month/workers?m={m}">Çalışan Aylık Raporu</a> <a class="btn purple" href="/month/firms?m={m}">Firma Aylık Raporu</a></form></div><div class="kpis"><div class="kpi"><span>Firma Teslim Adet</span><b>{int(num(sm['qty']))}</b></div><div class="kpi"><span>Firma Hak Ediş</span><b>{money(sm['revenue'])}</b></div><div class="kpi"><span>İşçilik / Net Kalan</span><b>{money(sm['labor'])}</b></div><div class="kpi"><span>Masraflar</span><b>{money(sm['expense'])}</b></div><div class="kpi"><span>Net Kazanç</span><b>{money(sm['net'])}</b></div></div><div class="card"><h2>Firma Bazlı Aylık Kâr Özeti</h2><p class='small'>Firma brüt kârı = Firmadan alınacak ücret − o firmaya ait çalışan hakedişleri. Genel masraflar bu tabloda düşülmez.</p><table><tr><th>FİRMA</th><th class='right'>TESLİM ADET</th><th class='right'>FİRMA HAKEDİŞİ</th><th class='right'>ÇALIŞAN ÜCRETİ</th><th class='right'>SİZE KALAN BRÜT KÂR</th></tr>{firm_trs}</table></div><div class="card"><h2>Çalışan Bazlı Aylık Hesap Özeti</h2><table><tr><th>ÇALIŞAN</th><th class="right">TOPLAM HAKEDİŞ</th><th class="right">AVANS</th><th class="right">ÖDEME</th><th class="right">KALAN BAKİYE</th></tr>{worker_summary_trs}</table></div><div class="card"><h2>Çalışan Bazlı Gün Gün Aylık Döküm</h2><div class="table-wrap"><table><tr><th>TARİH</th><th>ÇALIŞAN</th><th>FİRMA</th><th>ÜRÜN</th><th>YAPILAN İŞ</th><th class="right">ADET / PAKET</th><th class="right">PAKET İÇİ</th><th class="right">ÜRÜN ADEDİ</th><th class="right">BİRİM ÜCRET</th><th class="right">HAKEDİŞ</th></tr>{worker_trs}</table></div></div><div class="card"><h2>Firma Bazlı Gün Gün Aylık Döküm</h2><div class="table-wrap"><table><tr><th>TARİH</th><th>FİRMA</th><th>ÜRÜN</th><th class="right">TESLİM ADET</th><th class="right">BİRİM FİYAT</th><th class="right">FİRMA HAKEDİŞİ</th></tr>{firm_daily_trs}</table></div></div>"""
    return page("Ay Sonu", body)


@app.get("/export-month")
def export_month(m: Optional[str] = None):
    m = m or this_month(); sm = month_summary(m); out = Path(f"katlama_rapor_{m}.csv")
    firm_data = firm_month_summary(m)
    worker_data = worker_month_detail(m)
    worker_summary_data = worker_month_summary_rows(m)
    firm_daily_data = firm_month_detail(m)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f, delimiter=";")
        wr.writerow(["Ay", m]); wr.writerow(["Firma Teslim Adet", int(num(sm["qty"]))]); wr.writerow(["Firma Hak Ediş", f"{sm['revenue']:.2f}"]); wr.writerow(["İşçilik Net Kalan", f"{sm['labor']:.2f}"]); wr.writerow(["Masraflar", f"{sm['expense']:.2f}"]); wr.writerow(["Net Kazanç", f"{sm['net']:.2f}"]); wr.writerow([])
        wr.writerow(["FİRMA BAZLI AYLIK KÂR ÖZETİ"])
        wr.writerow(["FİRMA","TESLİM ADET","FİRMA HAKEDİŞİ","ÇALIŞAN ÜCRETİ","SİZE KALAN BRÜT KÂR"])
        for r in firm_data: wr.writerow([r['firm_name'],int(num(r['delivered_qty'])),f"{num(r['revenue']):.2f}",f"{num(r['labor']):.2f}",f"{num(r['profit']):.2f}"])
        wr.writerow([])
        wr.writerow(["ÇALIŞAN BAZLI AYLIK HESAP ÖZETİ"])
        wr.writerow(["ÇALIŞAN","TOPLAM HAKEDİŞ","AVANS","ÖDEME","KALAN BAKİYE"])
        for r in worker_summary_data: wr.writerow([r['worker'],f"{num(r['earned']):.2f}",f"{num(r['advance']):.2f}",f"{num(r['paid']):.2f}",f"{num(r['balance']):.2f}"])
        wr.writerow([])
        wr.writerow(["ÇALIŞAN BAZLI GÜN GÜN AYLIK DÖKÜM"])
        wr.writerow(["TARİH","ÇALIŞAN","FİRMA","ÜRÜN","YAPILAN İŞ","ADET / PAKET","PAKET İÇİ","ÜRÜN ADEDİ","BİRİM ÜCRET","HAKEDİŞ"])
        for r in worker_data: wr.writerow([display_date(r['work_date']),r['worker'],r['firm_name'],r['product'],r['work_type'] or r['product'],int(num(r['qty'])),int(num(r['package_size'])) if int(num(r['package_size']))>1 else "",int(num(r['product_qty'])),f"{num(r['worker_price']):.2f}",f"{num(r['earned']):.2f}"])
        wr.writerow([])
        wr.writerow(["FİRMA BAZLI GÜN GÜN AYLIK DÖKÜM"])
        wr.writerow(["TARİH","FİRMA","ÜRÜN","TESLİM ADET","BİRİM FİYAT","FİRMA HAKEDİŞİ"])
        for r in firm_daily_data: wr.writerow([display_date(r['deliv_date']),r['firm_name'],r['product'],int(num(r['qty'])),f"{num(r['firm_price']):.2f}",f"{num(r['amount']):.2f}"])
    return FileResponse(out, filename=out.name)


@app.get("/month/workers", response_class=HTMLResponse)
def worker_month_report(m: Optional[str] = None, worker_id: Optional[int] = None):
    m = m or this_month()
    worker_id = worker_id or None
    summary = worker_month_summary_rows(m, worker_id)
    detail = worker_month_detail(m, worker_id)
    worker_options = "<option value='0'>Tüm çalışanlar</option>"
    for worker in rows("SELECT id,name FROM workers ORDER BY name,id"):
        selected = " selected" if worker["id"] == worker_id else ""
        worker_options += f"<option value='{worker['id']}'{selected}>{escape(worker['name'])}</option>"
    total_earned = sum(num(r["earned"]) for r in summary)
    total_advance = sum(num(r["advance"]) for r in summary)
    total_paid = sum(num(r["paid"]) for r in summary)
    total_balance = sum(num(r["balance"]) for r in summary)
    summary_trs = "".join([f"<tr><td>{r['worker']}</td><td class='right'>{money(r['earned'])}</td><td class='right'>{money(r['advance'])}</td><td class='right'>{money(r['paid'])}</td><td class='right'>{money(r['balance'])}</td></tr>" for r in summary]) or "<tr><td colspan='5' class='center small'>Bu ay çalışan hesabı yok.</td></tr>"
    detail_trs = "".join([f"<tr><td>{display_date(r['work_date'])}</td><td>{r['worker']}</td><td>{r['firm_name']}</td><td>{r['product']}</td><td>{r['work_type'] or r['product']}</td><td class='right'>{int(num(r['qty']))}</td><td class='right'>{int(num(r['package_size'])) if int(num(r['package_size']))>1 else '-'}</td><td class='right'>{int(num(r['product_qty']))}</td><td class='right'>{money(r['worker_price'])}</td><td class='right'>{money(r['earned'])}</td></tr>" for r in detail]) or "<tr><td colspan='10' class='center small'>Bu ay iş kaydı yok.</td></tr>"
    body = f"""<div class='card'><form method='get'><label>Ay seç: YYYY-AA</label><input name='m' value='{m}' style='max-width:180px;display:inline-block'> <label for='report-worker'>Çalışan seç</label><select id='report-worker' name='worker_id' style='max-width:280px;display:inline-block'>{worker_options}</select> <button class='btn green'>Göster</button> <a class='btn yellow' href='/export-workers?m={m}&amp;worker_id={worker_id or 0}'>Çalışan Raporunu İndir</a> <a class='btn gray' href='/month?m={m}'>Ay Sonuna Dön</a></form></div><div class='kpis'><div class='kpi'><span>Toplam Hakediş</span><b>{money(total_earned)}</b></div><div class='kpi'><span>Toplam Avans</span><b>{money(total_advance)}</b></div><div class='kpi'><span>Toplam Ödeme</span><b>{money(total_paid)}</b></div><div class='kpi'><span>Toplam Kalan</span><b>{money(total_balance)}</b></div></div><div class='card'><h2>Çalışan Aylık Hesap Toplamları</h2><table><tr><th>ÇALIŞAN</th><th class='right'>HAKEDİŞ</th><th class='right'>AVANS</th><th class='right'>ÖDEME</th><th class='right'>KALAN</th></tr>{summary_trs}<tr><th>GENEL TOPLAM</th><th class='right'>{money(total_earned)}</th><th class='right'>{money(total_advance)}</th><th class='right'>{money(total_paid)}</th><th class='right'>{money(total_balance)}</th></tr></table></div><div class='card'><h2>Gün Gün Yapılan İşler</h2><div class='table-wrap'><table><tr><th>TARİH</th><th>ÇALIŞAN</th><th>FİRMA</th><th>ÜRÜN</th><th>YAPILAN İŞ</th><th class='right'>ADET/PAKET</th><th class='right'>PAKET İÇİ</th><th class='right'>ÜRÜN ADEDİ</th><th class='right'>BİRİM TL</th><th class='right'>TOPLAM TL</th></tr>{detail_trs}</table></div></div>"""
    return page("Çalışan Aylık Raporu", body)


@app.get("/month/firms", response_class=HTMLResponse)
def firm_month_report(m: Optional[str] = None):
    m = m or this_month()
    summary = firm_month_summary(m)
    detail = firm_month_detail(m)
    total_qty = sum(num(r["delivered_qty"]) for r in summary)
    total_revenue = sum(num(r["revenue"]) for r in summary)
    total_labor = sum(num(r["labor"]) for r in summary)
    total_profit = sum(num(r["profit"]) for r in summary)
    summary_trs = "".join([f"<tr><td>{r['firm_name']}</td><td class='right'>{int(num(r['delivered_qty']))}</td><td class='right'>{money(r['revenue'])}</td><td class='right'>{money(r['labor'])}</td><td class='right'>{money(r['profit'])}</td></tr>" for r in summary]) or "<tr><td colspan='5' class='center small'>Bu ay firma hesabı yok.</td></tr>"
    detail_trs = "".join([f"<tr><td>{display_date(r['deliv_date'])}</td><td>{r['firm_name']}</td><td>{r['product']}</td><td class='right'>{int(num(r['qty']))}</td><td class='right'>{money(r['firm_price'])}</td><td class='right'>{money(r['amount'])}</td></tr>" for r in detail]) or "<tr><td colspan='6' class='center small'>Bu ay firma teslimi yok.</td></tr>"
    body = f"""<div class='card'><form method='get'><label>Ay seç: YYYY-AA</label><input name='m' value='{m}' style='max-width:180px;display:inline-block'> <button class='btn green'>Göster</button> <a class='btn yellow' href='/export-firms?m={m}'>Firma Raporunu İndir</a> <a class='btn gray' href='/month?m={m}'>Ay Sonuna Dön</a></form></div><div class='kpis'><div class='kpi'><span>Toplam Teslim Adedi</span><b>{int(total_qty)}</b></div><div class='kpi'><span>Firmalardan Alınacak</span><b>{money(total_revenue)}</b></div><div class='kpi'><span>Çalışan Ücretleri</span><b>{money(total_labor)}</b></div><div class='kpi'><span>Brüt Kâr</span><b>{money(total_profit)}</b></div></div><div class='card'><h2>Firma Aylık Hesap Toplamları</h2><table><tr><th>FİRMA</th><th class='right'>TESLİM ADET</th><th class='right'>FİRMA HAKEDİŞİ</th><th class='right'>ÇALIŞAN ÜCRETİ</th><th class='right'>BRÜT KÂR</th></tr>{summary_trs}<tr><th>GENEL TOPLAM</th><th class='right'>{int(total_qty)}</th><th class='right'>{money(total_revenue)}</th><th class='right'>{money(total_labor)}</th><th class='right'>{money(total_profit)}</th></tr></table></div><div class='card'><h2>Gün Gün Firmaya Teslim Edilen İşler</h2><div class='table-wrap'><table><tr><th>TARİH</th><th>FİRMA</th><th>ÜRÜN</th><th class='right'>ADET</th><th class='right'>BİRİM TL</th><th class='right'>TOPLAM TL</th></tr>{detail_trs}</table></div></div>"""
    return page("Firma Aylık Raporu", body)


@app.get("/export-workers")
def export_workers(m: Optional[str] = None, worker_id: Optional[int] = None):
    worker_id = worker_id or None
    m = m or this_month(); out = Path(f"calisan_aylik_rapor_{m}_{worker_id or 'tumu'}.csv")
    summary = worker_month_summary_rows(m, worker_id); detail = worker_month_detail(m, worker_id)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f, delimiter=";")
        wr.writerow(["ÇALIŞAN AYLIK HESAP TOPLAMLARI",m])
        wr.writerow(["ÇALIŞAN","HAKEDİŞ","AVANS","ÖDEME","KALAN"])
        for r in summary: wr.writerow([r['worker'],f"{num(r['earned']):.2f}",f"{num(r['advance']):.2f}",f"{num(r['paid']):.2f}",f"{num(r['balance']):.2f}"])
        wr.writerow(["GENEL TOPLAM",f"{sum(num(r['earned']) for r in summary):.2f}",f"{sum(num(r['advance']) for r in summary):.2f}",f"{sum(num(r['paid']) for r in summary):.2f}",f"{sum(num(r['balance']) for r in summary):.2f}"])
        wr.writerow([]); wr.writerow(["GÜN GÜN YAPILAN İŞLER"])
        wr.writerow(["TARİH","ÇALIŞAN","FİRMA","ÜRÜN","YAPILAN İŞ","ADET/PAKET","PAKET İÇİ","ÜRÜN ADEDİ","BİRİM TL","TOPLAM TL"])
        for r in detail: wr.writerow([display_date(r['work_date']),r['worker'],r['firm_name'],r['product'],r['work_type'] or r['product'],int(num(r['qty'])),int(num(r['package_size'])) if int(num(r['package_size']))>1 else "",int(num(r['product_qty'])),f"{num(r['worker_price']):.2f}",f"{num(r['earned']):.2f}"])
    return FileResponse(out,filename=out.name)


@app.get("/export-firms")
def export_firms(m: Optional[str] = None):
    m = m or this_month(); out = Path(f"firma_aylik_rapor_{m}.csv")
    summary = firm_month_summary(m); detail = firm_month_detail(m)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f, delimiter=";")
        wr.writerow(["FİRMA AYLIK HESAP TOPLAMLARI",m])
        wr.writerow(["FİRMA","TESLİM ADET","FİRMA HAKEDİŞİ","ÇALIŞAN ÜCRETİ","BRÜT KÂR"])
        for r in summary: wr.writerow([r['firm_name'],int(num(r['delivered_qty'])),f"{num(r['revenue']):.2f}",f"{num(r['labor']):.2f}",f"{num(r['profit']):.2f}"])
        wr.writerow(["GENEL TOPLAM",int(sum(num(r['delivered_qty']) for r in summary)),f"{sum(num(r['revenue']) for r in summary):.2f}",f"{sum(num(r['labor']) for r in summary):.2f}",f"{sum(num(r['profit']) for r in summary):.2f}"])
        wr.writerow([]); wr.writerow(["GÜN GÜN FİRMAYA TESLİM EDİLEN İŞLER"])
        wr.writerow(["TARİH","FİRMA","ÜRÜN","ADET","BİRİM TL","TOPLAM TL"])
        for r in detail: wr.writerow([display_date(r['deliv_date']),r['firm_name'],r['product'],int(num(r['qty'])),f"{num(r['firm_price']):.2f}",f"{num(r['amount']):.2f}"])
    return FileResponse(out,filename=out.name)


if __name__ == "__main__":
    init_db()
    print("="*70); print("KATLAMA ATÖLYESİ PROFESYONEL SİSTEM BAŞLADI"); print(f"Yönetim paneli: http://127.0.0.1:{PORT}/dashboard"); print(f"Aynı Wi-Fi telefon: http://{local_ip()}:{PORT}"); print("="*70)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
