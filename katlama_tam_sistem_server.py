from datetime import datetime, date
from typing import Optional
from urllib.parse import quote
import os, secrets
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
import uvicorn

PORT = int(os.environ.get('PORT', '10000'))
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
app = FastAPI(title='Katlama Atolyesi')

def db_url():
    u = DATABASE_URL.strip()
    if u.startswith('postgres://'):
        u = 'postgresql://' + u[len('postgres://'):]
    if u and 'sslmode=' not in u:
        u += ('&' if '?' in u else '?') + 'sslmode=require'
    return u

def conn():
    if not DATABASE_URL:
        raise RuntimeError('DATABASE_URL bos. Render Environment alanina Supabase linkini ekle.')
    return psycopg2.connect(db_url(), cursor_factory=RealDictCursor)

def q_all(sql, p=()):
    c = conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql, p)
            return cur.fetchall()
    finally:
        c.close()

def q_one(sql, p=()):
    c = conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql, p)
            return cur.fetchone()
    finally:
        c.close()

def run(sql, p=()):
    c = conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql, p)
            c.commit()
    finally:
        c.close()

def now(): return datetime.now().isoformat(timespec='seconds')
def today(): return date.today().strftime('%Y-%m-%d')
def month_now(): return date.today().strftime('%Y-%m')
def money(v):
    try: return ('{:,.2f} TL'.format(float(v))).replace(',', 'X').replace('.', ',').replace('X', '.')
    except Exception: return '0,00 TL'

def init_db():
    c = conn()
    try:
        with c.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS workers(id SERIAL PRIMARY KEY,name TEXT NOT NULL UNIQUE,phone TEXT,token TEXT UNIQUE,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL)")
            cur.execute("CREATE TABLE IF NOT EXISTS products(id SERIAL PRIMARY KEY,name TEXT NOT NULL UNIQUE,firm_price NUMERIC NOT NULL DEFAULT 0,worker_price NUMERIC NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL)")
            cur.execute("CREATE TABLE IF NOT EXISTS entries(id SERIAL PRIMARY KEY,work_date TEXT NOT NULL,worker_id INTEGER NOT NULL REFERENCES workers(id) ON DELETE CASCADE,product_id INTEGER NOT NULL REFERENCES products(id),qty INTEGER NOT NULL,firm_price NUMERIC NOT NULL,worker_price NUMERIC NOT NULL,note TEXT,created_at TEXT NOT NULL,source TEXT DEFAULT 'telefon')")
            cur.execute("CREATE TABLE IF NOT EXISTS expenses(id SERIAL PRIMARY KEY,exp_date TEXT NOT NULL,category TEXT NOT NULL,amount NUMERIC NOT NULL,note TEXT,created_at TEXT NOT NULL)")
            for n in ['Esarp','Sal','Tekstil Urun']:
                cur.execute("INSERT INTO products(name,firm_price,worker_price,active,created_at) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(name) DO NOTHING", (n,0,0,1,now()))
            c.commit()
    finally:
        c.close()

CSS = """
<style>
body{font-family:Arial;background:#08111f;color:white;margin:0}.wrap{max-width:1100px;margin:auto;padding:15px}.nav a,.btn{display:inline-block;margin:4px;padding:10px 12px;border-radius:10px;background:#2563eb;color:white;text-decoration:none;border:0}.green{background:#22c55e!important;color:#06210f!important}.red{background:#dc2626!important}.card{background:#121a2d;border:1px solid #25314a;border-radius:14px;padding:14px;margin:12px 0}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}input,select{width:100%;padding:12px;border-radius:10px;background:#0f172a;color:white;border:1px solid #334155}table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #334155;padding:8px;text-align:left}.right{text-align:right}.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.kpi{background:#0f172a;border-radius:12px;padding:12px}.kpi b{display:block;font-size:22px}@media(max-width:800px){.grid,.kpis{grid-template-columns:1fr}.btn,.nav a{width:100%;text-align:center}}
</style>
"""

def page(title, body, nav=True):
    n = ""
    if nav:
        n = "<div class='nav'><a href='/dashboard'>Ana Panel</a><a href='/workers'>Eleman Linkleri</a><a href='/products'>Urun/Fiyat</a><a href='/expenses'>Masraflar</a></div>"
    return "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{}</title>{}</head><body><div class='wrap'><h1>{}</h1>{}{}</div></body></html>".format(title, CSS, title, n, body)

@app.on_event('startup')
def startup(): init_db()
@app.get('/')
def root(): return RedirectResponse('/dashboard', 303)
@app.get('/health', response_class=PlainTextResponse)
def health():
    init_db()
    return 'OK - Supabase/PostgreSQL veritabani bagli'

@app.get('/dashboard', response_class=HTMLResponse)
def dashboard(m: Optional[str]=None):
    m = m or month_now(); like = m + '%'
    s = q_one("SELECT COALESCE(SUM(qty),0) qty,COALESCE(SUM(qty*firm_price),0) revenue,COALESCE(SUM(qty*worker_price),0) labor FROM entries WHERE work_date LIKE %s", (like,))
    exp = q_one("SELECT COALESCE(SUM(amount),0) total FROM expenses WHERE exp_date LIKE %s", (like,))['total'] or 0
    revenue=float(s['revenue'] or 0); labor=float(s['labor'] or 0); exp=float(exp or 0)
    rows = q_all("SELECT e.id,e.work_date,w.name worker,p.name product,e.qty,e.qty*e.firm_price revenue,e.qty*e.worker_price labor,COALESCE(e.note,'') note FROM entries e JOIN workers w ON w.id=e.worker_id JOIN products p ON p.id=e.product_id ORDER BY e.id DESC LIMIT 300")
    trs = ''.join("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td class='right'>{}</td><td class='right'>{}</td><td class='right'>{}</td><td>{}</td><td><a class='btn red' href='/delete-entry/{}'>Sil</a></td></tr>".format(r['id'],r['work_date'],r['worker'],r['product'],r['qty'],money(r['revenue']),money(r['labor']),r['note'],r['id']) for r in rows)
    body = "<div class='card'><form><input name='m' value='{}'><button class='btn green'>Hesapla</button></form></div>".format(m)
    body += "<div class='kpis'><div class='kpi'>Adet<b>{}</b></div><div class='kpi'>Ciro<b>{}</b></div><div class='kpi'>Isçilik<b>{}</b></div><div class='kpi'>Masraf<b>{}</b></div><div class='kpi'>Net<b>{}</b></div></div>".format(int(s['qty'] or 0), money(revenue), money(labor), money(exp), money(revenue-labor-exp))
    body += "<div class='card'><table><tr><th>ID</th><th>Tarih</th><th>Eleman</th><th>Urun</th><th>Adet</th><th>Ciro</th><th>Isçilik</th><th>Not</th><th>Islem</th></tr>{}</table></div>".format(trs)
    return page('Katlama Atolyesi Ana Panel', body)

@app.get('/workers', response_class=HTMLResponse)
def workers(request: Request):
    data = q_all("SELECT * FROM workers ORDER BY active DESC,name")
    base = str(request.base_url).rstrip('/')
    trs = ''
    for r in data:
        link = base + '/w/' + r['token']
        wa = quote('Merhaba {}\nKatlama adet giris linkin:\n{}'.format(r['name'], link))
        trs += "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td style='word-break:break-all'>{}</td><td><a class='btn green' target='_blank' href='https://wa.me/?text={}'>WhatsApp</a></td><td><a class='btn red' href='/worker-off/{}'>Pasif</a></td></tr>".format(r['id'],r['name'],r['phone'] or '', 'Aktif' if r['active'] else 'Pasif', link, wa, r['id'])
    body = "<div class='card'><form method='post' action='/add-worker'><div class='grid'><input name='name' placeholder='Ad soyad' required><input name='phone' placeholder='Telefon'></div><button class='btn green'>Eleman Ekle</button></form></div>"
    body += "<div class='card'><table><tr><th>ID</th><th>Eleman</th><th>Tel</th><th>Durum</th><th>Link</th><th>WhatsApp</th><th>Islem</th></tr>{}</table></div>".format(trs)
    return page('Elemanlar ve WhatsApp Linkleri', body)

@app.post('/add-worker')
def add_worker(name: str=Form(...), phone: str=Form('')):
    old = q_one("SELECT id FROM workers WHERE name=%s", (name.strip(),))
    if old: run("UPDATE workers SET active=1, phone=COALESCE(NULLIF(%s,''),phone) WHERE name=%s", (phone.strip(), name.strip()))
    else: run("INSERT INTO workers(name,phone,token,active,created_at) VALUES(%s,%s,%s,%s,%s)", (name.strip(), phone.strip(), secrets.token_urlsafe(12), 1, now()))
    return RedirectResponse('/workers', 303)
@app.get('/worker-off/{wid}')
def worker_off(wid:int): run("UPDATE workers SET active=0 WHERE id=%s", (wid,)); return RedirectResponse('/workers',303)

@app.get('/products', response_class=HTMLResponse)
def products():
    data=q_all("SELECT * FROM products ORDER BY active DESC,name")
    trs=''.join("<tr><td>{}</td><td>{}</td><td class='right'>{}</td><td class='right'>{}</td><td>{}</td></tr>".format(r['id'],r['name'],money(r['firm_price']),money(r['worker_price']),'Aktif' if r['active'] else 'Pasif') for r in data)
    body="<div class='card'><form method='post' action='/add-product'><div class='grid'><input name='name' placeholder='Urun' required><input name='firm_price' type='number' step='0.01' placeholder='Firmadan aldigin'><input name='worker_price' type='number' step='0.01' placeholder='Elemana verilen'></div><button class='btn green'>Kaydet</button></form></div><div class='card'><table><tr><th>ID</th><th>Urun</th><th>Firma</th><th>Eleman</th><th>Durum</th></tr>{}</table></div>".format(trs)
    return page('Urun ve Fiyat', body)
@app.post('/add-product')
def add_product(name:str=Form(...), firm_price:float=Form(...), worker_price:float=Form(...)):
    run("INSERT INTO products(name,firm_price,worker_price,active,created_at) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(name) DO UPDATE SET firm_price=EXCLUDED.firm_price, worker_price=EXCLUDED.worker_price, active=1", (name.strip(), firm_price, worker_price, 1, now()))
    return RedirectResponse('/products',303)

@app.get('/w/{token}', response_class=HTMLResponse)
def worker_page(token:str, saved:Optional[str]=None):
    w=q_one("SELECT * FROM workers WHERE token=%s AND active=1", (token,))
    if not w: return page('Link Gecersiz', "<div class='card'>Link geçersiz veya pasif.</div>", False)
    opts=''.join("<option value='{}'>{}</option>".format(p['id'],p['name']) for p in q_all("SELECT id,name FROM products WHERE active=1 ORDER BY name"))
    like=month_now()+'%'
    total=q_one("SELECT COALESCE(SUM(qty),0) qty,COALESCE(SUM(qty*worker_price),0) earned FROM entries WHERE worker_id=%s AND work_date LIKE %s", (w['id'],like))
    last=q_all("SELECT e.id,e.work_date,p.name product,e.qty,e.qty*e.worker_price earned FROM entries e JOIN products p ON p.id=e.product_id WHERE e.worker_id=%s ORDER BY e.id DESC LIMIT 30", (w['id'],))
    trs=''.join("<tr><td>{}</td><td>{}</td><td class='right'>{}</td><td class='right'>{}</td><td><a class='btn red' href='/w/{}/delete/{}'>Sil</a></td></tr>".format(r['work_date'],r['product'],r['qty'],money(r['earned']),token,r['id']) for r in last)
    body=("<div class='card'><h2>{}</h2><div class='kpis'><div class='kpi'>Bu Ay Adet<b>{}</b></div><div class='kpi'>Bu Ay Hak Edis<b>{}</b></div></div></div>".format(w['name'], int(total['qty'] or 0), money(total['earned'] or 0)))
    body += "<div class='card'><form method='post' action='/w/{}/add'><div class='grid'><input name='work_date' value='{}'><select name='product_id'>{}</select><input name='qty' type='number' min='1' required><input name='note' placeholder='Not'></div><button class='btn green'>Kaydet</button></form></div>".format(token,today(),opts)
    body += "<div class='card'><table><tr><th>Tarih</th><th>Urun</th><th>Adet</th><th>Hak</th><th>Islem</th></tr>{}</table></div>".format(trs)
    return page('Benim Katlama Programim', body, False)
@app.post('/w/{token}/add')
def worker_add(token:str, work_date:str=Form(...), product_id:int=Form(...), qty:int=Form(...), note:str=Form('')):
    w=q_one("SELECT * FROM workers WHERE token=%s AND active=1", (token,)); p=q_one("SELECT * FROM products WHERE id=%s AND active=1", (product_id,))
    if w and p: run("INSERT INTO entries(work_date,worker_id,product_id,qty,firm_price,worker_price,note,created_at,source) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)", (work_date,w['id'],product_id,int(qty),float(p['firm_price']),float(p['worker_price']),note,now(),'telefon'))
    return RedirectResponse('/w/'+token+'?saved=1',303)
@app.get('/w/{token}/delete/{eid}')
def worker_delete(token:str,eid:int):
    w=q_one("SELECT id FROM workers WHERE token=%s", (token,))
    if w: run("DELETE FROM entries WHERE id=%s AND worker_id=%s", (eid,w['id']))
    return RedirectResponse('/w/'+token+'?saved=1',303)

@app.get('/expenses', response_class=HTMLResponse)
def expenses():
    data=q_all("SELECT * FROM expenses ORDER BY id DESC LIMIT 200")
    trs=''.join("<tr><td>{}</td><td>{}</td><td class='right'>{}</td><td>{}</td><td><a class='btn red' href='/delete-expense/{}'>Sil</a></td></tr>".format(r['exp_date'],r['category'],money(r['amount']),r['note'] or '',r['id']) for r in data)
    body="<div class='card'><form method='post' action='/add-expense'><div class='grid'><input name='exp_date' value='{}'><input name='category' placeholder='Kategori'><input name='amount' type='number' step='0.01'><input name='note' placeholder='Not'></div><button class='btn green'>Masraf Kaydet</button></form></div><div class='card'><table><tr><th>Tarih</th><th>Kategori</th><th>Tutar</th><th>Not</th><th>Islem</th></tr>{}</table></div>".format(today(),trs)
    return page('Masraflar', body)
@app.post('/add-expense')
def add_expense(exp_date:str=Form(...), category:str=Form(...), amount:float=Form(...), note:str=Form('')):
    run("INSERT INTO expenses(exp_date,category,amount,note,created_at) VALUES(%s,%s,%s,%s,%s)",(exp_date,category,amount,note,now()))
    return RedirectResponse('/expenses',303)
@app.get('/delete-expense/{eid}')
def delete_expense(eid:int): run("DELETE FROM expenses WHERE id=%s", (eid,)); return RedirectResponse('/expenses',303)
@app.get('/payments')
def payments(): return RedirectResponse('/month',303)
@app.get('/month')
def month(): return RedirectResponse('/dashboard',303)
@app.get('/delete-entry/{eid}')
def delete_entry(eid:int): run("DELETE FROM entries WHERE id=%s", (eid,)); return RedirectResponse('/dashboard',303)

if __name__ == '__main__': uvicorn.run(app, host='0.0.0.0', port=PORT)
