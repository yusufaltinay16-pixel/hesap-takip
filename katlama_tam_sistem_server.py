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

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
PORT = int(os.environ.get("PORT", "10000"))

app = FastAPI(title="Katlama Atölyesi Profesyonel Sistem")

# Eleman link sistemi:
# Her çalışan kendi tokenı ile kişiye özel link alır.
# Link formatı: https://katlama-sistem.onrender.com/w/<token>
LEGACY_WORKER_TOKENS = {}

DEFAULT_PUBLIC_BASE_URL = "https://katlama-sistem.onrender.com"


def public_base_url():
    """Eleman linklerini her zaman tıklanabilir tam URL olarak üretir."""
    return (os.environ.get("PUBLIC_BASE_URL") or DEFAULT_PUBLIC_BASE_URL).strip().rstrip("/")


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def today():
    return date.today().strftime("%Y-%m-%d")


def this_month():
    return date.today().strftime("%Y-%m")


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
    c.execute("""CREATE TABLE IF NOT EXISTS products(id SERIAL PRIMARY KEY,name TEXT NOT NULL UNIQUE,firm_price DOUBLE PRECISION NOT NULL DEFAULT 0,worker_price DOUBLE PRECISION NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS entries(id SERIAL PRIMARY KEY,work_date TEXT NOT NULL,worker_id INTEGER NOT NULL REFERENCES workers(id),product_id INTEGER NOT NULL REFERENCES products(id),qty INTEGER NOT NULL,firm_price DOUBLE PRECISION NOT NULL,worker_price DOUBLE PRECISION NOT NULL,note TEXT,created_at TEXT NOT NULL,source TEXT DEFAULT 'telefon')""")
    c.execute("""CREATE TABLE IF NOT EXISTS payments(id SERIAL PRIMARY KEY,pay_date TEXT NOT NULL,worker_id INTEGER NOT NULL REFERENCES workers(id),amount DOUBLE PRECISION NOT NULL,note TEXT,created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS advances(id SERIAL PRIMARY KEY,adv_date TEXT NOT NULL,worker_id INTEGER NOT NULL REFERENCES workers(id),amount DOUBLE PRECISION NOT NULL,note TEXT,created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS expenses(id SERIAL PRIMARY KEY,exp_date TEXT NOT NULL,category TEXT NOT NULL,amount DOUBLE PRECISION NOT NULL,note TEXT,created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS deliveries(id SERIAL PRIMARY KEY,deliv_date TEXT NOT NULL,worker_id INTEGER REFERENCES workers(id),product_id INTEGER NOT NULL REFERENCES products(id),firm_qty INTEGER NOT NULL DEFAULT 0,worker_qty INTEGER NOT NULL DEFAULT 0,note TEXT,created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS partners(id SERIAL PRIMARY KEY,name TEXT NOT NULL UNIQUE,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS partner_advances(id SERIAL PRIMARY KEY,adv_date TEXT NOT NULL,partner_id INTEGER NOT NULL REFERENCES partners(id),amount DOUBLE PRECISION NOT NULL,note TEXT,created_at TEXT NOT NULL)""")
    for name in ["Şal", "Eşarp", "Tekstil Ürün"]:
        c.execute("INSERT INTO products(name,firm_price,worker_price,active,created_at) VALUES(%s,0,0,1,%s) ON CONFLICT(name) DO NOTHING", (name, now_iso()))
    for pname in ["yusuf altınay", "mine ulu", "emine erol"]:
        c.execute("INSERT INTO partners(name,active,created_at) VALUES(%s,1,%s) ON CONFLICT(name) DO UPDATE SET active=1", (pname, now_iso()))
    c.execute("UPDATE partners SET active=0 WHERE name NOT IN ('yusuf altınay','mine ulu','emine erol')")
    c.execute("SELECT id FROM workers WHERE token IS NULL OR token='' OR token='None'")
    for r in c.fetchall():
        c.execute("UPDATE workers SET token=%s WHERE id=%s", (secrets.token_urlsafe(14), r["id"]))

    # Mevcut tokenlar korunur; tokenı boş olan eski elemanlara yukarıda otomatik kişiye özel link tokenı verilir.

    con.commit(); c.close(); con.close()


CSS = """
<style>
:root{--bg:#08111f;--card:#121a2d;--card2:#0f172a;--line:#25314a;--text:#f8fafc;--muted:#aab3c5;--green:#22c55e;--red:#ef4444;--blue:#1d4ed8;--yellow:#f59e0b;--purple:#8b5cf6;--cyan:#06b6d4}
*{box-sizing:border-box}body{margin:0;font-family:Arial,Segoe UI,sans-serif;background:linear-gradient(135deg,#06101f,#111827 60%,#08111f);color:var(--text)}.wrap{max-width:1320px;margin:0 auto;padding:14px 14px 90px}.top{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:12px}h1{font-size:24px;margin:8px 0}h2{margin:8px 0 14px}a{color:white;text-decoration:none}.nav{display:flex;gap:8px;flex-wrap:wrap}.nav a,.btn{background:var(--blue);border:0;color:white;padding:11px 14px;border-radius:12px;font-weight:800;cursor:pointer;display:inline-block;box-shadow:0 8px 18px #0003}.btn.green{background:var(--green);color:#06130b}.btn.red{background:var(--red)}.btn.gray{background:#334155}.btn.yellow{background:var(--yellow);color:#1b1100}.btn.purple{background:var(--purple)}.btn.cyan{background:var(--cyan);color:#031014}.card{background:rgba(18,26,45,.94);border:1px solid var(--line);border-radius:18px;padding:15px;margin:12px 0;box-shadow:0 14px 34px #0005}.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}label{font-size:13px;color:var(--muted);display:block;margin-bottom:5px;font-weight:700}input,select,textarea{width:100%;padding:13px;border-radius:12px;border:1px solid var(--line);background:#0f172a;color:white;font-size:16px}table{width:100%;border-collapse:separate;border-spacing:0;background:var(--card);border-radius:14px;overflow:hidden;table-layout:fixed}th,td{border-bottom:1px solid var(--line);padding:8px 7px;vertical-align:middle;white-space:normal;overflow:hidden;text-overflow:ellipsis;word-break:break-word;line-height:1.25}th{color:#cbd5e1;background:#111827;text-align:left;font-size:12px}td{font-size:12px}.table-wrap{overflow-x:auto;max-width:100%}.link-cell{max-width:260px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.link-cell a{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.actions{display:flex;gap:5px;flex-wrap:nowrap;align-items:center}.actions .btn{padding:8px 9px;border-radius:10px;font-size:12px;white-space:nowrap}form.inline{display:inline-block;margin:0}.workers-table th:nth-child(1),.workers-table td:nth-child(1){width:42px}.workers-table th:nth-child(2),.workers-table td:nth-child(2){width:120px}.workers-table th:nth-child(3),.workers-table td:nth-child(3){width:95px}.workers-table th:nth-child(4),.workers-table td:nth-child(4){width:65px}.workers-table th:nth-child(5),.workers-table td:nth-child(5),.workers-table th:nth-child(6),.workers-table td:nth-child(6),.workers-table th:nth-child(7),.workers-table td:nth-child(7),.workers-table th:nth-child(8),.workers-table td:nth-child(8){width:88px}.workers-table th:nth-child(9),.workers-table td:nth-child(9){width:260px}.workers-table th:nth-child(10),.workers-table td:nth-child(10){width:250px}.right{text-align:right}.center{text-align:center}.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.kpis.three{grid-template-columns:repeat(3,1fr)}.kpi{background:linear-gradient(180deg,#111827,#0f172a);border:1px solid var(--line);border-radius:16px;padding:15px;min-height:82px}.kpi b{font-size:24px;display:block;margin-top:6px}.kpi span{color:var(--muted);font-size:13px;font-weight:700}.notice{background:#052e1a;border:1px solid #166534;color:#dcfce7;padding:10px;border-radius:12px;margin:10px 0}.bad{background:#3b1111;border:1px solid #7f1d1d;color:#fee2e2;padding:10px;border-radius:12px;margin:10px 0}.copy{font-size:12px;word-break:break-all;color:#dbeafe}.small{font-size:12px;color:var(--muted)}.worker-hero{background:linear-gradient(135deg,#172554,#0f172a 55%,#052e1a);border:1px solid #334155;border-radius:24px;padding:18px;box-shadow:0 18px 45px #0008}.worker-title{font-size:28px;font-weight:900;margin:0 0 8px}.worker-sub{color:#cbd5e1;margin-bottom:12px}.worker-form input,.worker-form select{font-size:20px;padding:16px}.worker-form button{font-size:20px;padding:16px 22px;width:100%}.diff-plus{color:#22c55e;font-weight:900}.diff-minus{color:#ef4444;font-weight:900}.diff-zero{color:#cbd5e1;font-weight:900}.table-wrap{overflow:auto}.muted{color:#aab3c5}@media(max-width:900px){.grid,.kpis,.kpis.three{grid-template-columns:1fr}h1{font-size:20px}.nav a,.btn{width:100%;text-align:center}.worker-title{font-size:24px}.table-wrap{overflow:auto}}
</style>
"""


def page(title, body, nav=True):
    nav_html = ""
    if nav:
        nav_html = """<div class="nav"><a href="/dashboard">Ana Panel</a><a href="/workers">Eleman Linkleri</a><a href="/products">Ürün/Fiyat</a><a href="/deliveries">Firma Teslim</a><a href="/expenses">Masraflar</a><a href="/partners">Ortaklar Hesap</a><a href="/payments">Ödemeler</a><a href="/month">Ay Sonu</a></div>"""
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
    pay_where = "WHERE pay_date LIKE %s" if month else ""
    adv_where = "WHERE adv_date LIKE %s" if month else ""
    p = (month + "%",) if month else ()
    firma = one(f"""SELECT COALESCE(SUM(d.firm_qty),0) qty, COALESCE(SUM(d.firm_qty*p.firm_price),0) revenue FROM deliveries d JOIN products p ON p.id=d.product_id {deliv_where}""", p)
    earned = one(f"SELECT COALESCE(SUM(qty*worker_price),0) total, COALESCE(SUM(qty),0) qty FROM entries {entry_where}", p)
    exp = one(f"SELECT COALESCE(SUM(amount),0) total FROM expenses {exp_where}", p)
    paid = one(f"SELECT COALESCE(SUM(amount),0) total FROM payments {pay_where}", p)
    adv = one(f"SELECT COALESCE(SUM(amount),0) total FROM advances {adv_where}", p)
    hakedis = num(earned["total"] if earned else 0)
    odeme = num(paid["total"] if paid else 0)
    avans = num(adv["total"] if adv else 0)
    net_kalan = hakedis - avans - odeme
    revenue = num(firma["revenue"] if firma else 0)
    expense = num(exp["total"] if exp else 0)
    return {"qty": num(firma["qty"] if firma else 0), "revenue": revenue, "worker_qty": num(earned["qty"] if earned else 0), "hakedis": hakedis, "advance": avans, "paid": odeme, "labor": net_kalan, "labor_remaining": net_kalan, "expense": expense, "gross": revenue - hakedis, "net": revenue - net_kalan - expense}


def total_summary(): return calc_summary(None)
def month_summary(m): return calc_summary(m)


def diff_class(v):
    v = int(v or 0)
    return "diff-plus" if v > 0 else "diff-minus" if v < 0 else "diff-zero"


def last_entries(limit=300, month: Optional[str] = None):
    where = "WHERE e.work_date LIKE %s" if month else ""
    p = (month + "%", limit) if month else (limit,)
    return rows(f"""
    SELECT e.id,e.work_date,w.name worker,p.name product,e.qty,
           e.qty*e.worker_price hakedis,
           COALESCE(ad.avans,0) avans,
           COALESCE(pa.odeme,0) odeme,
           (e.qty*e.worker_price)-COALESCE(ad.avans,0)-COALESCE(pa.odeme,0) net_kalan,
           COALESCE(e.note,'') note
    FROM entries e
    JOIN workers w ON w.id=e.worker_id
    JOIN products p ON p.id=e.product_id
    LEFT JOIN (SELECT worker_id,adv_date,SUM(amount) avans FROM advances GROUP BY worker_id,adv_date) ad ON ad.worker_id=e.worker_id AND ad.adv_date=e.work_date
    LEFT JOIN (SELECT worker_id,pay_date,SUM(amount) odeme FROM payments GROUP BY worker_id,pay_date) pa ON pa.worker_id=e.worker_id AND pa.pay_date=e.work_date
    {where}
    ORDER BY e.work_date DESC,e.id DESC LIMIT %s
    """, p)


def entries_table(data):
    trs = "".join([f"""<tr><td>{r['id']}</td><td>{r['work_date']}</td><td>{r['worker']}</td><td class='right'>{int(num(r['qty']))}</td><td class='right'>{money(r['hakedis'])}</td><td class='right'>{money(r['avans'])}</td><td class='right'>{money(r['odeme'])}</td><td class='right'>{money(r['net_kalan'])}</td><td>{r['note']}</td><td><a class='btn yellow' href='/edit-entry/{r['id']}'>Güncelle</a> <form method='post' action='/delete-entry/{r['id']}' style='display:inline'><button class='btn red' type='submit'>Sil</button></form></td></tr>""" for r in data]) or "<tr><td colspan='10' class='center small'>Kayıt yok.</td></tr>"
    return f"""<div class='table-wrap'><table class='workers-table'><tr><th>ID</th><th>TARİH</th><th>ÇALIŞAN</th><th class='right'>ADET</th><th class='right'>HAKEDİŞ</th><th class='right'>AVANS</th><th class='right'>ÖDEME</th><th class='right'>NET KALAN</th><th>NOT</th><th>İŞLEM</th></tr>{trs}</table></div>"""


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    sm = total_summary()
    compare = rows("""
    SELECT p.name product, COALESCE(fd.firm_qty,0) firm_qty, COALESCE(en.worker_qty,0) worker_qty, COALESCE(en.worker_qty,0)-COALESCE(fd.firm_qty,0) diff
    FROM products p
    LEFT JOIN (SELECT product_id,SUM(firm_qty) firm_qty FROM deliveries GROUP BY product_id) fd ON fd.product_id=p.id
    LEFT JOIN (SELECT product_id,SUM(qty) worker_qty FROM entries GROUP BY product_id) en ON en.product_id=p.id
    WHERE p.active=1 AND (COALESCE(fd.firm_qty,0)>0 OR COALESCE(en.worker_qty,0)>0)
    ORDER BY p.name
    """)
    comp = "".join([f"<tr><td>{r['product']}</td><td class='right'>{int(num(r['firm_qty']))}</td><td class='right'>{int(num(r['worker_qty']))}</td><td class='right {diff_class(r['diff'])}'>{int(num(r['diff']))}</td></tr>" for r in compare]) or "<tr><td colspan='4' class='center small'>Henüz kayıt yok.</td></tr>"
    body = f"""
    <div class="card"><div class="notice">Ana panel tarih aralığı kullanmaz. İşçilik kutusu alttaki NET KALAN sütununun toplamıdır.</div></div>
    <div class="kpis"><div class="kpi"><span>Firma Teslim Adet</span><b>{int(num(sm['qty']))}</b></div><div class="kpi"><span>Firma Hak Ediş</span><b>{money(sm['revenue'])}</b></div><div class="kpi"><span>İşçilik</span><b>{money(sm['labor'])}</b></div><div class="kpi"><span>Masraflar</span><b>{money(sm['expense'])}</b></div><div class="kpi"><span>Net Kazanç</span><b>{money(sm['net'])}</b></div></div>
    <div class="card"><h2>Firma vs Eleman Genel Karşılaştırma</h2><table><tr><th>Ürün</th><th class='right'>Firma Teslim Adet</th><th class='right'>Eleman Katlama Adet</th><th class='right'>Fark</th></tr>{comp}</table></div>
    <div class="card"><h2>Son Eleman Kayıtları</h2>{entries_table(last_entries())}</div>
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
    <div class="card"><h2>Eleman Ekle</h2><form method="post" action="/add-worker"><div class="grid"><div><label>Çalışan Adı</label><input name="name" required></div><div><label>Telefon</label><input name="phone" placeholder="05..."></div></div><br><button class="btn green">Eleman Kaydet</button></form></div>
    <div class="card"><h2>Eleman Linkleri</h2><div class='table-wrap'><table class='workers-table'><tr><th>ID</th><th>ÇALIŞAN</th><th>TELEFON</th><th class='right'>ADET</th><th class='right'>HAKEDİŞ</th><th class='right'>AVANS</th><th class='right'>ÖDEME</th><th class='right'>NET KALAN</th><th>LİNK</th><th>İŞLEM</th></tr>{trs or '<tr><td colspan="10" class="center small">Eleman yok.</td></tr>'}</table></div></div>
    """
    return page("Eleman Linkleri", body)


@app.post("/add-worker")
def add_worker(name: str = Form(...), phone: str = Form("")):
    name = " ".join(name.strip().split())
    if name:
        exec_db("INSERT INTO workers(name,phone,token,active,created_at) VALUES(%s,%s,%s,1,%s) ON CONFLICT(name) DO UPDATE SET phone=EXCLUDED.phone, active=1, token=COALESCE(NULLIF(workers.token,''), EXCLUDED.token)", (name, phone, secrets.token_urlsafe(14), now_iso()))
    return RedirectResponse("/workers", status_code=303)


@app.get("/refresh-worker-token/{wid}")
def refresh_worker_token(wid: int):
    # Bu buton sadece seçilen elemanın linkini yeniler. Diğer elemanların linkleri değişmez.
    exec_db("UPDATE workers SET token=%s WHERE id=%s", (secrets.token_urlsafe(14), wid))
    return RedirectResponse("/workers", status_code=303)


@app.post("/delete-worker/{wid}")
@app.get("/delete-worker/{wid}")
def delete_worker(wid: int):
    exec_db("UPDATE workers SET active=0 WHERE id=%s", (wid,))
    return RedirectResponse("/workers", status_code=303)


@app.get("/products", response_class=HTMLResponse)
def products():
    data = rows("SELECT * FROM products WHERE active=1 ORDER BY name")
    trs = "".join([f"<tr><td>{p['id']}</td><td>{p['name']}</td><td class='right'>{money(p['firm_price'])}</td><td class='right'>{money(p['worker_price'])}</td><td><form method='post' action='/delete-product/{p['id']}' style='display:inline'><button class='btn red' type='submit'>Sil</button></form></td></tr>" for p in data]) or "<tr><td colspan='5' class='center small'>Ürün yok.</td></tr>"
    body = f"""<div class="card"><h2>Ürün / Fiyat Kaydet</h2><form method="post" action="/save-product"><div class="grid"><div><label>Ürün</label><input name="name" required></div><div><label>Firma Birim Fiyat</label><input name="firm_price" type="number" step="0.01" min="0" required></div><div><label>Eleman Birim İşçilik</label><input name="worker_price" type="number" step="0.01" min="0" required></div></div><br><button class="btn green">Kaydet / Güncelle</button></form><p class='small'>Aynı ürün adını yazarsan yeni ürün açmaz, fiyatı günceller.</p></div><div class="card"><table><tr><th>ID</th><th>ÜRÜN</th><th class='right'>FİRMA FİYAT</th><th class='right'>İŞÇİLİK FİYAT</th><th>İŞLEM</th></tr>{trs}</table></div>"""
    return page("Ürün/Fiyat", body)


@app.post("/save-product")
def save_product(name: str = Form(...), firm_price: float = Form(...), worker_price: float = Form(...)):
    name = " ".join(name.strip().split())
    if name:
        exec_db("""INSERT INTO products(name,firm_price,worker_price,active,created_at) VALUES(%s,%s,%s,1,%s) ON CONFLICT(name) DO UPDATE SET firm_price=EXCLUDED.firm_price, worker_price=EXCLUDED.worker_price, active=1""", (name, firm_price, worker_price, now_iso()))
    return RedirectResponse("/products", status_code=303)


@app.post("/delete-product/{pid}")
@app.get("/delete-product/{pid}")
def delete_product(pid: int):
    exec_db("UPDATE products SET active=0 WHERE id=%s", (pid,))
    return RedirectResponse("/products", status_code=303)


@app.get("/deliveries", response_class=HTMLResponse)
def deliveries():
    products = rows("SELECT id,name FROM products WHERE active=1 ORDER BY name")
    opts = "".join([f"<option value='{p['id']}'>{p['name']}</option>" for p in products])
    data = rows("""SELECT d.id,d.deliv_date,p.name product,d.firm_qty,d.firm_qty*p.firm_price amount,COALESCE(d.note,'') note FROM deliveries d JOIN products p ON p.id=d.product_id ORDER BY d.deliv_date DESC,d.id DESC LIMIT 500""")
    trs = "".join([f"<tr><td>{r['id']}</td><td>{r['deliv_date']}</td><td>{r['product']}</td><td class='right'>{int(num(r['firm_qty']))}</td><td class='right'>{money(r['amount'])}</td><td>{r['note']}</td><td><form method='post' action='/delete-delivery/{r['id']}' style='display:inline'><button class='btn red' type='submit'>Sil</button></form></td></tr>" for r in data]) or "<tr><td colspan='7' class='center small'>Teslim kaydı yok.</td></tr>"
    body = f"""<div class="card"><h2>Firma Teslim Gir</h2><form method="post" action="/add-delivery"><div class="grid"><div><label>Tarih</label><input name="deliv_date" value="{today()}" required></div><div><label>Ürün</label><select name="product_id">{opts}</select></div><div><label>Firma Teslim Adet</label><input name="firm_qty" type="number" min="1" required></div><div style="grid-column:span 2"><label>Not</label><input name="note"></div></div><br><button class="btn green">Teslim Kaydet</button></form></div><div class="card"><table><tr><th>ID</th><th>TARİH</th><th>ÜRÜN</th><th class='right'>FİRMA TESLİM ADET</th><th class='right'>FİRMA HAKEDİŞ</th><th>NOT</th><th>İŞLEM</th></tr>{trs}</table></div>"""
    return page("Firma Teslim", body)


@app.post("/add-delivery")
def add_delivery(deliv_date: str = Form(...), product_id: int = Form(...), firm_qty: int = Form(...), note: str = Form("")):
    if int(firm_qty) > 0:
        exec_db("INSERT INTO deliveries(deliv_date,worker_id,product_id,firm_qty,worker_qty,note,created_at) VALUES(%s,NULL,%s,%s,0,%s,%s)", (deliv_date, product_id, firm_qty, note, now_iso()))
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
    if not worker: return page("Link Geçersiz", "<div class='bad'>Bu eleman linki geçersiz veya pasif.</div>", nav=False)
    products = rows("SELECT id,name,worker_price FROM products WHERE active=1 ORDER BY name")
    product_opts = "".join([f"<option value='{p['id']}'>{p['name']}</option>" for p in products])
    total = one("SELECT COALESCE(SUM(qty),0) qty, COALESCE(SUM(qty*worker_price),0) earned FROM entries WHERE worker_id=%s", (worker["id"],))
    paid_total = num(one("SELECT COALESCE(SUM(amount),0) total FROM payments WHERE worker_id=%s", (worker["id"],))["total"])
    adv_total = num(one("SELECT COALESCE(SUM(amount),0) total FROM advances WHERE worker_id=%s", (worker["id"],))["total"])
    today_total = one("SELECT COALESCE(SUM(qty),0) qty FROM entries WHERE worker_id=%s AND work_date=%s", (worker["id"], today()))
    msg = "<div class='notice'>Adet kaydedildi.</div>" if saved else (f"<div class='bad'>{error}</div>" if error else "")
    last_rows = rows("""SELECT e.id,e.work_date,p.name product,e.qty,e.qty*e.worker_price earned,COALESCE(e.note,'') note FROM entries e JOIN products p ON p.id=e.product_id WHERE e.worker_id=%s ORDER BY e.work_date DESC,e.id DESC LIMIT 30""", (worker["id"],))
    trs = "".join([f"<tr><td>{r['id']}</td><td>{r['work_date']}</td><td>{r['product']}</td><td class='right'>{int(num(r['qty']))}</td><td class='right'>{money(r['earned'])}</td><td>{r['note']}</td><td><a class='btn yellow' href='/w/{token}/edit/{r['id']}'>Güncelle</a> <form method='post' action='/w/{token}/delete/{r['id']}' style='display:inline'><button class='btn red' type='submit'>Sil</button></form></td></tr>" for r in last_rows]) or "<tr><td colspan='7' class='center small'>Kayıt yok.</td></tr>"
    kalan = num(total["earned"] if total else 0) - paid_total - adv_total
    body = f"""{msg}<div class="worker-hero"><div class="worker-title">{worker['name']} - Katlama Paneli</div><div class="worker-sub">Adetini gir, kendi kayıtlarını gör, yanlışsa güncelle veya sil.</div><div class="kpis three"><div class="kpi"><span>Bugünkü Adedim</span><b>{int(num(today_total['qty']))}</b></div><div class="kpi"><span>Genel Hak Edişim</span><b>{money(total['earned'] if total else 0)}</b></div><div class="kpi"><span>Net Kalan</span><b>{money(kalan)}</b></div></div></div><div class="card worker-form"><h2>Adet Gir</h2><form method="post" action="/w/{token}/add"><div class="grid"><div><label>Tarih</label><input name="work_date" value="{today()}" required></div><div><label>Ürün</label><select name="product_id" required>{product_opts}</select></div><div><label>Adet</label><input name="qty" type="number" min="1" required autofocus></div><div style="grid-column:span 2"><label>Not</label><input name="note" placeholder="İsteğe bağlı"></div></div><br><button class="btn green" type="submit">ADETİ KAYDET</button></form></div><div class="card"><h2>Son Kayıtlarım</h2><table><tr><th>ID</th><th>TARİH</th><th>ÜRÜN</th><th class='right'>ADET</th><th class='right'>HAKEDİŞ</th><th>NOT</th><th>İŞLEM</th></tr>{trs}</table></div>"""
    return page("Eleman Paneli", body, nav=False)


@app.post("/w/{token}/add")
def worker_add(token: str, work_date: str = Form(...), product_id: int = Form(...), qty: int = Form(...), note: str = Form("")):
    worker = get_worker_by_token(token)
    product = one("SELECT * FROM products WHERE id=%s AND active=1", (product_id,))
    if not worker or not product or int(qty) <= 0:
        return RedirectResponse(f"/w/{token}?error=Kayıt yapılamadı", status_code=303)
    exec_db("INSERT INTO entries(work_date,worker_id,product_id,qty,firm_price,worker_price,note,created_at,source) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'telefon')", (work_date, worker["id"], product_id, qty, product["firm_price"], product["worker_price"], note, now_iso()))
    return RedirectResponse(f"/w/{token}?saved=1", status_code=303)


@app.get("/w/{token}/edit/{eid}", response_class=HTMLResponse)
def worker_edit_form(token: str, eid: int):
    worker = get_worker_by_token(token)
    r = one("SELECT * FROM entries WHERE id=%s", (eid,))
    if not worker or not r or r["worker_id"] != worker["id"]: return RedirectResponse(f"/w/{token}", status_code=303)
    products = rows("SELECT id,name FROM products WHERE active=1 ORDER BY name")
    opts = "".join([f"<option value='{p['id']}' {'selected' if p['id']==r['product_id'] else ''}>{p['name']}</option>" for p in products])
    body = f"""<div class='card worker-form'><h2>Kayıt Güncelle</h2><form method='post' action='/w/{token}/edit/{eid}'><div class='grid'><div><label>Tarih</label><input name='work_date' value='{r['work_date']}'></div><div><label>Ürün</label><select name='product_id'>{opts}</select></div><div><label>Adet</label><input name='qty' type='number' min='1' value='{r['qty']}'></div><div style='grid-column:span 2'><label>Not</label><input name='note' value='{r['note'] or ''}'></div></div><br><button class='btn green'>Güncelle</button></form></div>"""
    return page("Kayıt Güncelle", body, nav=False)


@app.post("/w/{token}/edit/{eid}")
def worker_edit(token: str, eid: int, work_date: str = Form(...), product_id: int = Form(...), qty: int = Form(...), note: str = Form("")):
    worker = get_worker_by_token(token); product = one("SELECT * FROM products WHERE id=%s", (product_id,))
    if worker and product and int(qty) > 0:
        exec_db("UPDATE entries SET work_date=%s, product_id=%s, qty=%s, firm_price=%s, worker_price=%s, note=%s WHERE id=%s AND worker_id=%s", (work_date, product_id, qty, product["firm_price"], product["worker_price"], note, eid, worker["id"]))
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
    workers = rows("SELECT id,name FROM workers WHERE active=1 ORDER BY name"); products = rows("SELECT id,name FROM products WHERE active=1 ORDER BY name")
    wopts = "".join([f"<option value='{w['id']}' {'selected' if w['id']==r['worker_id'] else ''}>{w['name']}</option>" for w in workers])
    popts = "".join([f"<option value='{p['id']}' {'selected' if p['id']==r['product_id'] else ''}>{p['name']}</option>" for p in products])
    body = f"""<div class='card'><h2>Eleman Kaydı Güncelle</h2><form method='post' action='/edit-entry/{eid}'><div class='grid'><div><label>Tarih</label><input name='work_date' value='{r['work_date']}'></div><div><label>Çalışan</label><select name='worker_id'>{wopts}</select></div><div><label>Ürün</label><select name='product_id'>{popts}</select></div><div><label>Adet</label><input name='qty' type='number' min='1' value='{r['qty']}'></div><div><label>Not</label><input name='note' value='{r['note'] or ''}'></div></div><br><button class='btn green'>Güncelle</button></form></div>"""
    return page("Eleman Kaydı Güncelle", body)


@app.post("/edit-entry/{eid}")
def edit_entry(eid: int, work_date: str = Form(...), worker_id: int = Form(...), product_id: int = Form(...), qty: int = Form(...), note: str = Form("")):
    product = one("SELECT * FROM products WHERE id=%s", (product_id,))
    if product and int(qty) > 0:
        exec_db("UPDATE entries SET work_date=%s, worker_id=%s, product_id=%s, qty=%s, firm_price=%s, worker_price=%s, note=%s WHERE id=%s", (work_date, worker_id, product_id, qty, product["firm_price"], product["worker_price"], note, eid))
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/delete-entry/{entry_id}")
@app.get("/delete-entry/{entry_id}")
def delete_entry(entry_id: int):
    exec_db("DELETE FROM entries WHERE id=%s", (entry_id,)); return RedirectResponse("/dashboard", status_code=303)


@app.get("/expenses", response_class=HTMLResponse)
def expenses():
    total = one("SELECT COALESCE(SUM(amount),0) total FROM expenses")["total"] or 0
    data = rows("SELECT * FROM expenses ORDER BY exp_date DESC,id DESC LIMIT 500")
    trs = "".join([f"<tr><td>{r['id']}</td><td>{r['exp_date']}</td><td>{r['category']}</td><td class='right'>{money(r['amount'])}</td><td>{r['note'] or ''}</td><td><form method='post' action='/delete-expense/{r['id']}' style='display:inline'><button class='btn red' type='submit'>Sil</button></form></td></tr>" for r in data]) or "<tr><td colspan='6' class='center small'>Masraf yok.</td></tr>"
    body = f"""<div class="kpis three"><div class="kpi"><span>Genel Masraf Toplamı</span><b>{money(total)}</b></div><div class="kpi"><span>Tarih Filtresi</span><b>Yok</b></div><div class="kpi"><span>Kayıt</span><b>Her Giriş Ayrı</b></div></div><div class="card"><h2>Masraf Ekle</h2><form method="post" action="/add-expense"><div class="grid"><div><label>Tarih</label><input name="exp_date" value="{today()}" required></div><div><label>Kategori</label><input name="category" required></div><div><label>Tutar</label><input name="amount" type="number" step="0.01" min="0" required></div><div style="grid-column:span 2"><label>Not</label><input name="note"></div></div><br><button class="btn green">Masraf Kaydet</button></form></div><div class="card"><table><tr><th>ID</th><th>TARİH</th><th>KATEGORİ</th><th class='right'>TUTAR</th><th>NOT</th><th>İŞLEM</th></tr>{trs}</table></div>"""
    return page("Masraflar", body)


@app.post("/add-expense")
def add_expense(exp_date: str = Form(...), category: str = Form(...), amount: float = Form(...), note: str = Form("")):
    exec_db("INSERT INTO expenses(exp_date,category,amount,note,created_at) VALUES(%s,%s,%s,%s,%s)", (exp_date, category, amount, note, now_iso())); return RedirectResponse("/expenses", status_code=303)


@app.post("/delete-expense/{eid}")
@app.get("/delete-expense/{eid}")
def delete_expense(eid: int):
    exec_db("DELETE FROM expenses WHERE id=%s", (eid,)); return RedirectResponse("/expenses", status_code=303)


@app.get("/payments", response_class=HTMLResponse)
def payments():
    workers = rows("SELECT id,name FROM workers WHERE active=1 ORDER BY name")
    opts = "".join([f"<option value='{w['id']}'>{w['name']}</option>" for w in workers])
    data = rows("""SELECT p.id,p.pay_date,w.name worker,p.amount,COALESCE(p.note,'') note FROM payments p JOIN workers w ON w.id=p.worker_id ORDER BY p.pay_date DESC,p.id DESC LIMIT 500""")
    trs = "".join([f"<tr><td>{r['id']}</td><td>{r['pay_date']}</td><td>{r['worker']}</td><td class='right'>{money(r['amount'])}</td><td>{r['note']}</td><td><form method='post' action='/delete-payment/{r['id']}' style='display:inline'><button class='btn red' type='submit'>Sil</button></form></td></tr>" for r in data]) or "<tr><td colspan='6' class='center small'>Ödeme yok.</td></tr>"
    advdata = rows("""SELECT a.id,a.adv_date,w.name worker,a.amount,COALESCE(a.note,'') note FROM advances a JOIN workers w ON w.id=a.worker_id ORDER BY a.adv_date DESC,a.id DESC LIMIT 500""")
    advtrs = "".join([f"<tr><td>{r['id']}</td><td>{r['adv_date']}</td><td>{r['worker']}</td><td class='right'>{money(r['amount'])}</td><td>{r['note']}</td><td><form method='post' action='/delete-advance/{r['id']}' style='display:inline'><button class='btn red' type='submit'>Sil</button></form></td></tr>" for r in advdata]) or "<tr><td colspan='6' class='center small'>Avans yok.</td></tr>"
    body = f"""<div class="card"><h2>Eleman Ödemesi</h2><form method="post" action="/add-payment"><div class="grid"><div><label>Tarih</label><input name="pay_date" value="{today()}" required></div><div><label>Eleman</label><select name="worker_id">{opts}</select></div><div><label>Ödeme Tutarı</label><input name="amount" type="number" step="0.01" min="0" required></div><div style="grid-column:span 2"><label>Not</label><input name="note"></div></div><br><button class="btn green">Ödeme Kaydet</button></form></div><div class="card"><h2>Eleman Avansı</h2><form method="post" action="/add-advance"><div class="grid"><div><label>Tarih</label><input name="adv_date" value="{today()}" required></div><div><label>Eleman</label><select name="worker_id">{opts}</select></div><div><label>Avans Tutarı</label><input name="amount" type="number" step="0.01" min="0" required></div><div style="grid-column:span 2"><label>Not</label><input name="note"></div></div><br><button class="btn yellow">Avans Kaydet</button></form></div><div class="card"><h2>Ödemeler</h2><table><tr><th>ID</th><th>TARİH</th><th>ÇALIŞAN</th><th class='right'>ÖDEME</th><th>NOT</th><th>İŞLEM</th></tr>{trs}</table></div><div class="card"><h2>Avanslar</h2><table><tr><th>ID</th><th>TARİH</th><th>ÇALIŞAN</th><th class='right'>AVANS</th><th>NOT</th><th>İŞLEM</th></tr>{advtrs}</table></div><div class="card"><h2>Eleman Genel Özeti</h2>{entries_table(last_entries(500))}</div>"""
    return page("Ödemeler", body)


@app.post("/add-payment")
def add_payment(pay_date: str = Form(...), worker_id: int = Form(...), amount: float = Form(...), note: str = Form("")):
    exec_db("INSERT INTO payments(pay_date,worker_id,amount,note,created_at) VALUES(%s,%s,%s,%s,%s)", (pay_date, worker_id, amount, note, now_iso())); return RedirectResponse("/payments", status_code=303)


@app.post("/delete-payment/{pid}")
@app.get("/delete-payment/{pid}")
def delete_payment(pid: int): exec_db("DELETE FROM payments WHERE id=%s", (pid,)); return RedirectResponse("/payments", status_code=303)


@app.post("/add-advance")
def add_advance(adv_date: str = Form(...), worker_id: int = Form(...), amount: float = Form(...), note: str = Form("")):
    exec_db("INSERT INTO advances(adv_date,worker_id,amount,note,created_at) VALUES(%s,%s,%s,%s,%s)", (adv_date, worker_id, amount, note, now_iso())); return RedirectResponse("/payments", status_code=303)


@app.post("/delete-advance/{aid}")
@app.get("/delete-advance/{aid}")
def delete_advance(aid: int): exec_db("DELETE FROM advances WHERE id=%s", (aid,)); return RedirectResponse("/payments", status_code=303)


@app.get("/partners", response_class=HTMLResponse)
def partners(m: Optional[str] = None):
    m = m or this_month(); sm = month_summary(m); net_kar = num(sm["net"]); ortak_pay = net_kar / 3.0
    plist = rows("""SELECT id,name FROM partners WHERE active=1 AND name IN ('yusuf altınay','mine ulu','emine erol') ORDER BY CASE name WHEN 'yusuf altınay' THEN 1 WHEN 'mine ulu' THEN 2 WHEN 'emine erol' THEN 3 ELSE 4 END""")
    opts = "".join([f"<option value='{p['id']}'>{p['name']}</option>" for p in plist])
    partner_rows = ""
    for p in plist:
        adv = num(one("SELECT COALESCE(SUM(amount),0) total FROM partner_advances WHERE partner_id=%s AND adv_date LIKE %s", (p["id"], m+"%"))["total"])
        partner_rows += f"<tr><td>{p['name']}</td><td class='right'>{money(ortak_pay)}</td><td class='right'>{money(adv)}</td><td class='right'>{money(ortak_pay-adv)}</td></tr>"
    advdata = rows("""SELECT pa.id,pa.adv_date,p.name partner,pa.amount,COALESCE(pa.note,'') note FROM partner_advances pa JOIN partners p ON p.id=pa.partner_id WHERE pa.adv_date LIKE %s ORDER BY pa.adv_date DESC,pa.id DESC""", (m+"%",))
    adv_rows = "".join([f"<tr><td>{r['id']}</td><td>{r['adv_date']}</td><td>{r['partner']}</td><td class='right'>{money(r['amount'])}</td><td>{r['note']}</td><td><form method='post' action='/delete-partner-advance/{r['id']}?m={m}' style='display:inline'><button class='btn red' type='submit'>Sil</button></form></td></tr>" for r in advdata]) or "<tr><td colspan='6' class='center small'>Avans yok.</td></tr>"
    body = f"""<div class="card"><form method="get" action="/partners"><label>Ay seç: YYYY-AA</label><input name="m" value="{m}" style="max-width:180px;display:inline-block"> <button class="btn green">Hesapla</button></form></div><div class="kpis three"><div class="kpi"><span>Net Kalan Toplam Kar</span><b>{money(net_kar)}</b></div><div class="kpi"><span>Ortak Sayısı</span><b>3</b></div><div class="kpi"><span>Kişi Başı Pay</span><b>{money(ortak_pay)}</b></div></div><div class="card"><h2>Ortak Avansı Gir</h2><form method="post" action="/add-partner-advance"><input type="hidden" name="m" value="{m}"><div class="grid"><div><label>Tarih</label><input name="adv_date" value="{today()}" required></div><div><label>Ortak</label><select name="partner_id">{opts}</select></div><div><label>Avans</label><input name="amount" type="number" step="0.01" min="0" required></div><div style="grid-column:span 2"><label>Not</label><input name="note"></div></div><br><button class="btn green">Kaydet</button></form></div><div class="card"><h2>Ortaklar Hesap Özeti</h2><table><tr><th>ORTAK</th><th class='right'>PAY</th><th class='right'>AVANS</th><th class='right'>NET KALAN</th></tr>{partner_rows}</table></div><div class="card"><h2>Ortak Avans Kayıtları</h2><table><tr><th>ID</th><th>TARİH</th><th>ORTAK</th><th class='right'>AVANS</th><th>NOT</th><th>İŞLEM</th></tr>{adv_rows}</table></div>"""
    return page("Ortaklar Hesap", body)


@app.post("/add-partner-advance")
def add_partner_advance(m: str = Form(...), adv_date: str = Form(...), partner_id: int = Form(...), amount: float = Form(...), note: str = Form("")):
    exec_db("INSERT INTO partner_advances(adv_date,partner_id,amount,note,created_at) VALUES(%s,%s,%s,%s,%s)", (adv_date, partner_id, amount, note, now_iso())); return RedirectResponse(f"/partners?m={m}", status_code=303)


@app.post("/delete-partner-advance/{aid}")
@app.get("/delete-partner-advance/{aid}")
def delete_partner_advance(aid: int, m: Optional[str] = None):
    exec_db("DELETE FROM partner_advances WHERE id=%s", (aid,)); return RedirectResponse(f"/partners?m={m or this_month()}", status_code=303)


@app.get("/month", response_class=HTMLResponse)
def month(m: Optional[str] = None):
    m = m or this_month(); sm = month_summary(m)
    body = f"""<div class="card"><form method="get" action="/month"><label>Ay seç: YYYY-AA</label><input name="m" value="{m}" style="max-width:180px;display:inline-block"> <button class="btn green">Hesapla</button> <a class="btn yellow" href="/export-month?m={m}">CSV Rapor Al</a></form></div><div class="kpis"><div class="kpi"><span>Firma Teslim Adet</span><b>{int(num(sm['qty']))}</b></div><div class="kpi"><span>Firma Hak Ediş</span><b>{money(sm['revenue'])}</b></div><div class="kpi"><span>İşçilik / Net Kalan</span><b>{money(sm['labor'])}</b></div><div class="kpi"><span>Masraflar</span><b>{money(sm['expense'])}</b></div><div class="kpi"><span>Net Kazanç</span><b>{money(sm['net'])}</b></div></div><div class="card"><h2>Ayın Eleman Kayıtları</h2>{entries_table(last_entries(1000, m))}</div>"""
    return page("Ay Sonu", body)


@app.get("/export-month")
def export_month(m: Optional[str] = None):
    m = m or this_month(); sm = month_summary(m); out = Path(f"katlama_rapor_{m}.csv")
    data = last_entries(10000, m)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f, delimiter=";")
        wr.writerow(["Ay", m]); wr.writerow(["Firma Teslim Adet", int(num(sm["qty"]))]); wr.writerow(["Firma Hak Ediş", f"{sm['revenue']:.2f}"]); wr.writerow(["İşçilik Net Kalan", f"{sm['labor']:.2f}"]); wr.writerow(["Masraflar", f"{sm['expense']:.2f}"]); wr.writerow(["Net Kazanç", f"{sm['net']:.2f}"]); wr.writerow([])
        wr.writerow(["ID","TARİH","ÇALIŞAN","ADET","HAKEDİŞ","AVANS","ÖDEME","NET KALAN","NOT"])
        for r in data: wr.writerow([r['id'],r['work_date'],r['worker'],r['qty'],r['hakedis'],r['avans'],r['odeme'],r['net_kalan'],r['note']])
    return FileResponse(out, filename=out.name)


if __name__ == "__main__":
    init_db()
    print("="*70); print("KATLAMA ATÖLYESİ PROFESYONEL SİSTEM BAŞLADI"); print(f"Yönetim paneli: http://127.0.0.1:{PORT}/dashboard"); print(f"Aynı Wi-Fi telefon: http://{local_ip()}:{PORT}"); print("="*70)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
