
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
import uvicorn
import socket
import csv
import secrets
from urllib.parse import quote

DB_FILE = "katlama_tam_sistem.db"
PORT = 10000

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
    except:
        return "0,00 ₺"

def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con

def rows(q, p=()):
    con = db()
    r = con.execute(q, p).fetchall()
    con.close()
    return r

def one(q, p=()):
    con = db()
    r = con.execute(q, p).fetchone()
    con.close()
    return r

def exec_db(q, p=()):
    con = db()
    cur = con.execute(q, p)
    con.commit()
    last = cur.lastrowid
    con.close()
    return last

def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def base_url():
    return f"http://{local_ip()}:{PORT}"

def init_db():
    con = db()
    c = con.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS workers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        phone TEXT,
        token TEXT UNIQUE,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        firm_price REAL NOT NULL DEFAULT 0,
        worker_price REAL NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS entries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        work_date TEXT NOT NULL,
        worker_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        qty INTEGER NOT NULL,
        firm_price REAL NOT NULL,
        worker_price REAL NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL,
        source TEXT DEFAULT 'telefon',
        FOREIGN KEY(worker_id) REFERENCES workers(id),
        FOREIGN KEY(product_id) REFERENCES products(id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pay_date TEXT NOT NULL,
        worker_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(worker_id) REFERENCES workers(id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS expenses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exp_date TEXT NOT NULL,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL
    )
    """)

    for name, firm_price, worker_price in [
        ("Eşarp", 0, 0),
        ("Şal", 0, 0),
        ("Tekstil Ürün", 0, 0),
    ]:
        c.execute(
            "INSERT OR IGNORE INTO products(name, firm_price, worker_price, active, created_at) VALUES(?,?,?,?,?)",
            (name, firm_price, worker_price, 1, now_iso())
        )

    for r in c.execute("SELECT id FROM workers WHERE token IS NULL OR token=''").fetchall():
        c.execute("UPDATE workers SET token=? WHERE id=?", (secrets.token_urlsafe(12), r[0]))

    con.commit()
    con.close()

CSS = """
<style>
:root{--bg:#08111f;--card:#121a2d;--line:#25314a;--text:#f8fafc;--muted:#aab3c5;--green:#22c55e;--red:#ef4444;--blue:#3b82f6;--yellow:#f59e0b;--purple:#8b5cf6}
*{box-sizing:border-box}
body{margin:0;font-family:Arial,Segoe UI,sans-serif;background:var(--bg);color:var(--text)}
.wrap{max-width:1250px;margin:0 auto;padding:14px 14px 90px}
.top{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:12px}
h1{font-size:24px;margin:8px 0} h2{margin:8px 0 14px}
a{color:white;text-decoration:none}
.nav{display:flex;gap:8px;flex-wrap:wrap}
.nav a,.btn{background:var(--blue);border:0;color:white;padding:11px 14px;border-radius:12px;font-weight:700;cursor:pointer;display:inline-block}
.btn.green{background:var(--green);color:#06130b}.btn.red{background:var(--red)}.btn.gray{background:#334155}.btn.yellow{background:var(--yellow);color:#1b1100}.btn.purple{background:var(--purple)}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px;margin:12px 0;box-shadow:0 12px 30px #0004}
.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
label{font-size:13px;color:var(--muted);display:block;margin-bottom:5px}
input,select,textarea{width:100%;padding:13px;border-radius:12px;border:1px solid var(--line);background:#0f172a;color:white;font-size:16px}
table{width:100%;border-collapse:collapse;background:var(--card);border-radius:14px;overflow:hidden}
th,td{border-bottom:1px solid var(--line);padding:10px;text-align:left;vertical-align:top}
th{color:#cbd5e1;background:#111827}
.right{text-align:right}.center{text-align:center}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
.kpi{background:#0f172a;border:1px solid var(--line);border-radius:14px;padding:14px}
.kpi b{font-size:22px;display:block;margin-top:5px}
.notice{background:#052e1a;border:1px solid #166534;color:#dcfce7;padding:10px;border-radius:12px;margin:10px 0}
.bad{background:#3b1111;border:1px solid #7f1d1d;color:#fee2e2;padding:10px;border-radius:12px;margin:10px 0}
.copy{font-size:12px;word-break:break-all;color:#dbeafe}
.small{font-size:12px;color:var(--muted)}
@media(max-width:900px){
 .grid,.kpis{grid-template-columns:1fr}
 h1{font-size:20px}
 table{font-size:13px}
 th,td{padding:8px}
 .nav a,.btn{width:100%;text-align:center}
}
</style>
"""

def page(title, body, nav=True):
    nav_html = ""
    if nav:
        nav_html = """<div class="nav">
<a href="/dashboard">Ana Panel</a>
<a href="/workers">Eleman Linkleri</a>
<a href="/products">Ürün/Fiyat</a>
<a href="/expenses">Masraflar</a>
<a href="/payments">Ödemeler</a>
<a href="/month">Ay Sonu</a>
</div>"""
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>{CSS}</head>
<body><div class="wrap"><div class="top"><h1>{title}</h1>{nav_html}</div>{body}</div></body></html>"""

@app.on_event("startup")
def startup():
    init_db()

@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/dashboard", status_code=303)

def month_summary(m):
    like = m + "%"
    s = one("""
    SELECT 
      COALESCE(SUM(qty),0) qty,
      COALESCE(SUM(qty*firm_price),0) revenue,
      COALESCE(SUM(qty*worker_price),0) labor_cost
    FROM entries WHERE work_date LIKE ?
    """, (like,))
    exp = one("SELECT COALESCE(SUM(amount),0) total FROM expenses WHERE exp_date LIKE ?", (like,))["total"] or 0
    paid = one("SELECT COALESCE(SUM(amount),0) total FROM payments WHERE pay_date LIKE ?", (like,))["total"] or 0
    revenue = s["revenue"] or 0
    labor = s["labor_cost"] or 0
    gross = revenue - labor
    net = revenue - labor - exp
    return {
        "qty": s["qty"] or 0,
        "revenue": revenue,
        "labor": labor,
        "expense": exp,
        "gross": gross,
        "net": net,
        "paid": paid,
        "labor_remaining": labor - paid
    }

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(m: Optional[str]=None):
    if not m:
        m = this_month()
    sm = month_summary(m)
    data = rows("""
    SELECT e.id,e.work_date,w.name worker,p.name product,e.qty,e.firm_price,e.worker_price,
           e.qty*e.firm_price revenue,e.qty*e.worker_price labor,e.qty*(e.firm_price-e.worker_price) gross,
           COALESCE(e.note,'') note,e.source
    FROM entries e
    JOIN workers w ON w.id=e.worker_id
    JOIN products p ON p.id=e.product_id
    ORDER BY e.work_date DESC,e.id DESC LIMIT 300
    """)
    trs = ""
    for r in data:
        trs += f"""
        <tr>
          <td>{r['id']}</td><td>{r['work_date']}</td><td>{r['worker']}</td><td>{r['product']}</td>
          <td class="right">{r['qty']}</td><td class="right">{money(r['revenue'])}</td>
          <td class="right">{money(r['labor'])}</td><td class="right">{money(r['gross'])}</td>
          <td>{r['note']}</td><td><a class="btn red" href="/delete-entry/{r['id']}">Sil</a></td>
        </tr>
        """
    body = f"""
    <div class="card">
      <form method="get" action="/dashboard">
        <label>Ay seç: YYYY-AA</label>
        <input name="m" value="{m}" style="max-width:180px;display:inline-block">
        <button class="btn green">Hesapla</button>
      </form>
    </div>
    <div class="kpis">
      <div class="kpi">Toplam Adet<b>{int(sm['qty'])}</b></div>
      <div class="kpi">Firmadan Alacak / Ciro<b>{money(sm['revenue'])}</b></div>
      <div class="kpi">Eleman Hak Edişi<b>{money(sm['labor'])}</b></div>
      <div class="kpi">Masraflar<b>{money(sm['expense'])}</b></div>
      <div class="kpi">Net Kazanç<b>{money(sm['net'])}</b></div>
    </div>
    <div class="card">
      <h2>Son Kayıtlar</h2>
      <table>
        <tr><th>ID</th><th>Tarih</th><th>Eleman</th><th>Ürün</th><th>Adet</th><th>Ciro</th><th>İşçilik</th><th>Brüt</th><th>Not</th><th>İşlem</th></tr>
        {trs}
      </table>
    </div>
    """
    return page("Katlama Atölyesi Ana Panel", body)

@app.get("/w/{token}", response_class=HTMLResponse)
def worker_page(token: str, saved: Optional[str]=None, error: Optional[str]=None):
    worker = one("SELECT * FROM workers WHERE token=? AND active=1", (token,))
    if not worker:
        return page("Link Geçersiz", "<div class='bad'>Bu eleman linki geçersiz veya pasif.</div>", nav=False)

    products = rows("SELECT id,name,worker_price FROM products WHERE active=1 ORDER BY name")
    product_opts = "".join([f"<option value='{p['id']}'>{p['name']}</option>" for p in products])
    like = this_month()+"%"
    total = one("SELECT COALESCE(SUM(qty),0) qty, COALESCE(SUM(qty*worker_price),0) earned FROM entries WHERE worker_id=? AND work_date LIKE ?", (worker["id"], like))
    today_total = one("SELECT COALESCE(SUM(qty),0) qty FROM entries WHERE worker_id=? AND work_date=?", (worker["id"], today()))
    msg = ""
    if saved:
        msg = "<div class='notice'>Adet kaydedildi.</div>"
    if error:
        msg = f"<div class='bad'>{error}</div>"

    last_rows = rows("""
    SELECT e.id,e.work_date,p.name product,e.qty,e.qty*e.worker_price earned,COALESCE(e.note,'') note
    FROM entries e JOIN products p ON p.id=e.product_id
    WHERE e.worker_id=?
    ORDER BY e.work_date DESC,e.id DESC LIMIT 20
    """, (worker["id"],))
    trs = "".join([f'''<tr>
    <td>{r['work_date']}</td>
    <td>{r['product']}</td>
    <td class='right'>{r['qty']}</td>
    <td class='right'>{money(r['earned'])}</td>
    <td>
      <a class="btn yellow" href="/w/{token}/edit/{r['id']}">Güncelle</a>
      <a class="btn red" href="/w/{token}/delete/{r['id']}" onclick="return confirm('Bu kayıt silinsin mi?')">Sil</a>
    </td>
</tr>''' for r in last_rows])

    body = f"""
    {msg}
    <div class="card">
      <h2>{worker['name']} - Katlama Girişi</h2>
      <div class="kpis">
        <div class="kpi">Bugünkü Adedim<b>{int(today_total['qty'] or 0)}</b></div>
        <div class="kpi">Bu Ay Toplam Adedim<b>{int(total['qty'] or 0)}</b></div>
        <div class="kpi">Bu Ay Hak Edişim<b>{money(total['earned'] or 0)}</b></div>
        <div class="kpi">Ay<b>{this_month()}</b></div>
        <div class="kpi">Durum<b>Aktif</b></div>
      </div>
    </div>
    <div class="card">
      <h2>Adet Gir</h2>
      <form method="post" action="/w/{token}/add">
        <div class="grid">
          <div><label>Tarih</label><input name="work_date" value="{today()}" required></div>
          <div><label>Ürün</label><select name="product_id" required>{product_opts}</select></div>
          <div><label>Adet</label><input name="qty" type="number" min="1" required autofocus></div>
          <div style="grid-column:span 2"><label>Not</label><input name="note" placeholder="İsteğe bağlı"></div>
        </div>
        <br><button class="btn green" type="submit">Kaydet</button>
      </form>
    </div>
    <div class="card">
      <h2>Son Kayıtlarım</h2>
      <table><tr><th>Tarih</th><th>Ürün</th><th>Adet</th><th>Hak Ediş</th><th>İşlem</th></tr>{trs}</table>
    </div>
    """
    return page("Benim Katlama Programım", body, nav=False)

@app.post("/w/{token}/add")
def worker_add(token: str, work_date: str=Form(...), product_id: int=Form(...), qty: int=Form(...), note: str=Form("")):
    worker = one("SELECT * FROM workers WHERE token=? AND active=1", (token,))
    if not worker:
        return RedirectResponse(f"/w/{token}?error=Link geçersiz", status_code=303)
    product = one("SELECT * FROM products WHERE id=? AND active=1", (product_id,))
    if not product:
        return RedirectResponse(f"/w/{token}?error=Ürün bulunamadı", status_code=303)
    try:
        datetime.strptime(work_date, "%Y-%m-%d")
        qty = int(qty)
        if qty <= 0:
            raise ValueError()
    except:
        return RedirectResponse(f"/w/{token}?error=Tarih veya adet hatalı", status_code=303)

    exec_db("""
    INSERT INTO entries(work_date, worker_id, product_id, qty, firm_price, worker_price, note, created_at, source)
    VALUES(?,?,?,?,?,?,?,?,?)
    """, (work_date, worker["id"], product_id, qty, float(product["firm_price"] or 0), float(product["worker_price"] or 0), note, now_iso(), "whatsapp-link"))
    return RedirectResponse(f"/w/{token}?saved=1", status_code=303)


@app.get("/w/{token}/edit/{entry_id}", response_class=HTMLResponse)
def worker_edit_page(token: str, entry_id: int):
    worker = one("SELECT * FROM workers WHERE token=? AND active=1", (token,))
    if not worker:
        return page("Link Geçersiz", "<div class='bad'>Bu eleman linki geçersiz veya pasif.</div>", nav=False)

    entry = one("""
    SELECT e.*, p.name product
    FROM entries e
    JOIN products p ON p.id=e.product_id
    WHERE e.id=? AND e.worker_id=?
    """, (entry_id, worker["id"]))

    if not entry:
        return page("Kayıt Bulunamadı", "<div class='bad'>Bu kayıt bulunamadı veya sana ait değil.</div>", nav=False)

    products = rows("SELECT id,name FROM products WHERE active=1 ORDER BY name")
    opts = ""
    for p in products:
        selected = "selected" if p["id"] == entry["product_id"] else ""
        opts += f"<option value='{p['id']}' {selected}>{p['name']}</option>"

    body = f"""
    <div class="card">
      <h2>Kayıt Güncelle</h2>
      <p class="small">Sadece kendi kaydını güncelleyebilirsin.</p>
      <form method="post" action="/w/{token}/edit/{entry_id}">
        <div class="grid">
          <div><label>Tarih</label><input name="work_date" value="{entry['work_date']}" required></div>
          <div><label>Ürün</label><select name="product_id" required>{opts}</select></div>
          <div><label>Adet</label><input name="qty" type="number" min="1" value="{entry['qty']}" required autofocus></div>
          <div style="grid-column:span 2"><label>Not</label><input name="note" value="{entry['note'] or ''}"></div>
        </div>
        <br>
        <button class="btn green" type="submit">Güncellemeyi Kaydet</button>
        <a class="btn gray" href="/w/{token}">Geri Dön</a>
      </form>
    </div>
    """
    return page("Kayıt Güncelle", body, nav=False)


@app.post("/w/{token}/edit/{entry_id}")
def worker_edit_save(token: str, entry_id: int, work_date: str=Form(...), product_id: int=Form(...), qty: int=Form(...), note: str=Form("")):
    worker = one("SELECT * FROM workers WHERE token=? AND active=1", (token,))
    if not worker:
        return RedirectResponse(f"/w/{token}?error=Link geçersiz", status_code=303)

    entry = one("SELECT * FROM entries WHERE id=? AND worker_id=?", (entry_id, worker["id"]))
    if not entry:
        return RedirectResponse(f"/w/{token}?error=Kayıt bulunamadı", status_code=303)

    product = one("SELECT * FROM products WHERE id=? AND active=1", (product_id,))
    if not product:
        return RedirectResponse(f"/w/{token}?error=Ürün bulunamadı", status_code=303)

    try:
        datetime.strptime(work_date, "%Y-%m-%d")
        qty = int(qty)
        if qty <= 0:
            raise ValueError()
    except:
        return RedirectResponse(f"/w/{token}?error=Tarih veya adet hatalı", status_code=303)

    exec_db("""
    UPDATE entries
    SET work_date=?, product_id=?, qty=?, firm_price=?, worker_price=?, note=?
    WHERE id=? AND worker_id=?
    """, (work_date, product_id, qty, float(product["firm_price"] or 0), float(product["worker_price"] or 0), note, entry_id, worker["id"]))

    return RedirectResponse(f"/w/{token}?saved=1", status_code=303)


@app.get("/w/{token}/delete/{entry_id}")
def worker_delete_entry(token: str, entry_id: int):
    worker = one("SELECT * FROM workers WHERE token=? AND active=1", (token,))
    if not worker:
        return RedirectResponse(f"/w/{token}?error=Link geçersiz", status_code=303)

    exec_db("DELETE FROM entries WHERE id=? AND worker_id=?", (entry_id, worker["id"]))
    return RedirectResponse(f"/w/{token}?saved=1", status_code=303)


@app.get("/workers", response_class=HTMLResponse)
def workers():
    data = rows("SELECT id,name,phone,token,active FROM workers ORDER BY active DESC,name")
    base = base_url()
    trs = ""
    for r in data:
        link = f"{base}/w/{r['token']}"
        # WhatsApp linki cümle içine gömülünce bazen tıklanabilir olmuyor.
        # Bu yüzden URL'yi ayrı satırda ve tek başına gönderiyoruz.
        wa_msg = f"Merhaba {r['name']}\n\nKatlama adet giriş linkin:\n{link}\n\nLinke tıkla, açılmazsa kopyalayıp Chrome'a yapıştır."
        wa_text = quote(wa_msg)
        trs += f"""
        <tr>
          <td>{r['id']}</td><td>{r['name']}</td><td>{r['phone'] or ''}</td><td>{'Aktif' if r['active'] else 'Pasif'}</td>
          <td>
            <span class="copy" id="link_{r['id']}">{link}</span><br>
            <button class="btn gray" type="button" onclick="copyLink('link_{r['id']}')">Linki Kopyala</button>
          </td>
          <td>
            <a class="btn green" target="_blank" href="https://wa.me/?text={wa_text}">WhatsApp'a At</a>
          </td>
          <td><a class="btn yellow" href="/worker-new-link/{r['id']}">Yeni Link</a></td>
          <td><a class="btn red" href="/worker-off/{r['id']}">Pasifleştir</a></td>
        </tr>
        """
    body = f"""
    <div class="card">
      <h2>Eleman Ekle</h2>
      <form method="post" action="/add-worker">
        <div class="grid">
          <div><label>Ad Soyad</label><input name="name" required></div>
          <div><label>Telefon</label><input name="phone" placeholder="05xx..."></div>
        </div>
        <br><button class="btn green">Eleman Ekle</button>
      </form>
    </div>
    <div class="card">
      <h2>WhatsApp Özel Linkleri</h2>
      <p class="small">Her elemana ayrı link gider. Eleman sadece kendi ekranını görür.</p>
      <table><tr><th>ID</th><th>Eleman</th><th>Telefon</th><th>Durum</th><th>Özel Link</th><th>WhatsApp</th><th>Link Yenile</th><th>İşlem</th></tr>{trs}</table>
    </div>
    <script>
      function copyLink(id) {
        const text = document.getElementById(id).innerText.trim();
        navigator.clipboard.writeText(text).then(function() {
          alert("Link kopyalandı. WhatsApp'a yapıştırıp gönderebilirsin.");
        }).catch(function() {
          prompt("Linki kopyala:", text);
        });
      }
    </script>
    """
    return page("Elemanlar ve WhatsApp Linkleri", body)

@app.post("/add-worker")
def add_worker(name:str=Form(...), phone:str=Form("")):
    name=name.strip()
    phone=phone.strip()
    if name:
        con=db()
        old=con.execute("SELECT id FROM workers WHERE name=?", (name,)).fetchone()
        if old:
            con.execute("UPDATE workers SET active=1, phone=COALESCE(NULLIF(?,''),phone) WHERE name=?", (phone,name))
        else:
            con.execute("INSERT INTO workers(name,phone,token,active,created_at) VALUES(?,?,?,?,?)", (name,phone,secrets.token_urlsafe(12),1,now_iso()))
        con.commit(); con.close()
    return RedirectResponse("/workers", status_code=303)

@app.get("/worker-new-link/{worker_id}")
def worker_new_link(worker_id:int):
    exec_db("UPDATE workers SET token=? WHERE id=?", (secrets.token_urlsafe(12), worker_id))
    return RedirectResponse("/workers", status_code=303)

@app.get("/worker-off/{worker_id}")
def worker_off(worker_id:int):
    exec_db("UPDATE workers SET active=0 WHERE id=?", (worker_id,))
    return RedirectResponse("/workers", status_code=303)

@app.get("/products", response_class=HTMLResponse)
def products():
    data = rows("SELECT id,name,firm_price,worker_price,active FROM products ORDER BY active DESC,name")
    trs = "".join([f"""
    <tr>
      <td>{r['id']}</td><td>{r['name']}</td>
      <td class='right'>{money(r['firm_price'])}</td>
      <td class='right'>{money(r['worker_price'])}</td>
      <td class='right'>{money((r['firm_price'] or 0)-(r['worker_price'] or 0))}</td>
      <td>{'Aktif' if r['active'] else 'Pasif'}</td>
      <td><a class='btn red' href='/product-off/{r['id']}'>Pasifleştir</a></td>
    </tr>""" for r in data])
    body = f"""
    <div class="card">
      <h2>Ürün ve Fiyatlar</h2>
      <form method="post" action="/add-product">
        <div class="grid">
          <div><label>Ürün adı</label><input name="name" required></div>
          <div><label>Firmadan Aldığın Ücret / Adet</label><input name="firm_price" type="number" step="0.01" min="0" required></div>
          <div><label>Elemana Verdiğin Ücret / Adet</label><input name="worker_price" type="number" step="0.01" min="0" required></div>
        </div>
        <br><button class="btn green">Kaydet / Güncelle</button>
      </form>
    </div>
    <div class="card">
      <table><tr><th>ID</th><th>Ürün</th><th>Firma Ücreti</th><th>Eleman Ücreti</th><th>Adet Başı Brüt</th><th>Durum</th><th>İşlem</th></tr>{trs}</table>
    </div>
    """
    return page("Ürün / Firma Ücreti / Eleman Ücreti", body)

@app.post("/add-product")
def add_product(name:str=Form(...), firm_price:float=Form(...), worker_price:float=Form(...)):
    name=name.strip()
    con=db()
    con.execute("""
    INSERT INTO products(name,firm_price,worker_price,active,created_at) VALUES(?,?,?,?,?)
    ON CONFLICT(name) DO UPDATE SET firm_price=excluded.firm_price, worker_price=excluded.worker_price, active=1
    """, (name, firm_price, worker_price, 1, now_iso()))
    con.commit(); con.close()
    return RedirectResponse("/products", status_code=303)

@app.get("/product-off/{product_id}")
def product_off(product_id:int):
    exec_db("UPDATE products SET active=0 WHERE id=?", (product_id,))
    return RedirectResponse("/products", status_code=303)

@app.get("/expenses", response_class=HTMLResponse)
def expenses():
    data = rows("SELECT * FROM expenses ORDER BY exp_date DESC,id DESC LIMIT 300")
    trs = "".join([f"<tr><td>{r['id']}</td><td>{r['exp_date']}</td><td>{r['category']}</td><td class='right'>{money(r['amount'])}</td><td>{r['note'] or ''}</td><td><a class='btn red' href='/delete-expense/{r['id']}'>Sil</a></td></tr>" for r in data])
    body = f"""
    <div class="card">
      <h2>Masraf Ekle</h2>
      <form method="post" action="/add-expense">
        <div class="grid">
          <div><label>Tarih</label><input name="exp_date" value="{today()}" required></div>
          <div><label>Kategori</label><input name="category" placeholder="Yemek, yol, kira..." required></div>
          <div><label>Tutar</label><input name="amount" type="number" step="0.01" min="0" required></div>
          <div style="grid-column:span 2"><label>Not</label><input name="note"></div>
        </div>
        <br><button class="btn green">Masraf Kaydet</button>
      </form>
    </div>
    <div class="card"><table><tr><th>ID</th><th>Tarih</th><th>Kategori</th><th>Tutar</th><th>Not</th><th>İşlem</th></tr>{trs}</table></div>
    """
    return page("Masraflar", body)

@app.post("/add-expense")
def add_expense(exp_date:str=Form(...), category:str=Form(...), amount:float=Form(...), note:str=Form("")):
    exec_db("INSERT INTO expenses(exp_date,category,amount,note,created_at) VALUES(?,?,?,?,?)", (exp_date, category, amount, note, now_iso()))
    return RedirectResponse("/expenses", status_code=303)

@app.get("/delete-expense/{eid}")
def delete_expense(eid:int):
    exec_db("DELETE FROM expenses WHERE id=?", (eid,))
    return RedirectResponse("/expenses", status_code=303)

@app.get("/payments", response_class=HTMLResponse)
def payments():
    workers=rows("SELECT id,name FROM workers WHERE active=1 ORDER BY name")
    opts="".join([f"<option value='{w['id']}'>{w['name']}</option>" for w in workers])
    data=rows("""
    SELECT p.id,p.pay_date,w.name worker,p.amount,COALESCE(p.note,'') note
    FROM payments p JOIN workers w ON w.id=p.worker_id
    ORDER BY p.pay_date DESC,p.id DESC LIMIT 300
    """)
    trs="".join([f"<tr><td>{r['id']}</td><td>{r['pay_date']}</td><td>{r['worker']}</td><td class='right'>{money(r['amount'])}</td><td>{r['note']}</td><td><a class='btn red' href='/delete-payment/{r['id']}'>Sil</a></td></tr>" for r in data])
    body=f"""
    <div class="card"><h2>Eleman Ödemesi</h2>
    <form method="post" action="/add-payment"><div class="grid">
    <div><label>Tarih</label><input name="pay_date" value="{today()}" required></div>
    <div><label>Eleman</label><select name="worker_id">{opts}</select></div>
    <div><label>Tutar</label><input name="amount" type="number" step="0.01" min="0" required></div>
    <div style="grid-column:span 2"><label>Not</label><input name="note"></div>
    </div><br><button class="btn green">Ödeme Kaydet</button></form></div>
    <div class="card"><table><tr><th>ID</th><th>Tarih</th><th>Eleman</th><th>Tutar</th><th>Not</th><th>İşlem</th></tr>{trs}</table></div>
    """
    return page("Ödemeler", body)

@app.post("/add-payment")
def add_payment(pay_date:str=Form(...), worker_id:int=Form(...), amount:float=Form(...), note:str=Form("")):
    exec_db("INSERT INTO payments(pay_date,worker_id,amount,note,created_at) VALUES(?,?,?,?,?)", (pay_date,worker_id,amount,note,now_iso()))
    return RedirectResponse("/payments", status_code=303)

@app.get("/delete-payment/{pid}")
def delete_payment(pid:int):
    exec_db("DELETE FROM payments WHERE id=?", (pid,))
    return RedirectResponse("/payments", status_code=303)

@app.get("/month", response_class=HTMLResponse)
def month(m: Optional[str]=None):
    if not m:
        m=this_month()
    like=m+"%"
    sm = month_summary(m)

    by_worker = rows("""
    SELECT w.id,w.name worker, COALESCE(SUM(e.qty),0) qty, COALESCE(SUM(e.qty*e.worker_price),0) earned
    FROM workers w
    LEFT JOIN entries e ON e.worker_id=w.id AND e.work_date LIKE ?
    WHERE w.active=1
    GROUP BY w.id,w.name
    ORDER BY w.name
    """, (like,))
    trs=""
    for r in by_worker:
        paid=one("SELECT COALESCE(SUM(amount),0) paid FROM payments WHERE worker_id=? AND pay_date LIKE ?", (r["id"], like))["paid"] or 0
        remain=(r["earned"] or 0)-paid
        trs += f"<tr><td>{r['worker']}</td><td class='right'>{int(r['qty'] or 0)}</td><td class='right'>{money(r['earned'] or 0)}</td><td class='right'>{money(paid)}</td><td class='right'>{money(remain)}</td></tr>"

    by_product = rows("""
    SELECT p.name product, COALESCE(SUM(e.qty),0) qty, COALESCE(SUM(e.qty*e.firm_price),0) revenue,
           COALESCE(SUM(e.qty*e.worker_price),0) labor,
           COALESCE(SUM(e.qty*(e.firm_price-e.worker_price)),0) gross
    FROM products p
    LEFT JOIN entries e ON e.product_id=p.id AND e.work_date LIKE ?
    GROUP BY p.id,p.name
    ORDER BY p.name
    """, (like,))
    ptrs = "".join([f"<tr><td>{r['product']}</td><td class='right'>{int(r['qty'] or 0)}</td><td class='right'>{money(r['revenue'] or 0)}</td><td class='right'>{money(r['labor'] or 0)}</td><td class='right'>{money(r['gross'] or 0)}</td></tr>" for r in by_product])

    body=f"""
    <div class="card">
      <form method="get" action="/month">
        <label>Ay seç: YYYY-AA</label>
        <input name="m" value="{m}" style="max-width:180px;display:inline-block">
        <button class="btn green">Hesapla</button>
        <a class="btn yellow" href="/export-month?m={m}">Excel/CSV Rapor Al</a>
      </form>
    </div>
    <div class="kpis">
      <div class="kpi">Toplam Adet<b>{int(sm['qty'])}</b></div>
      <div class="kpi">Ciro / Firmadan Alacak<b>{money(sm['revenue'])}</b></div>
      <div class="kpi">Eleman Hak Edişi<b>{money(sm['labor'])}</b></div>
      <div class="kpi">Masraflar<b>{money(sm['expense'])}</b></div>
      <div class="kpi">Net Kazanç<b>{money(sm['net'])}</b></div>
    </div>
    <div class="card"><h2>Eleman Bazlı Ay Sonu</h2><table><tr><th>Eleman</th><th>Toplam Adet</th><th>Hak Ediş</th><th>Ödenen</th><th>Kalan</th></tr>{trs}</table></div>
    <div class="card"><h2>Ürün Bazlı Özet</h2><table><tr><th>Ürün</th><th>Adet</th><th>Ciro</th><th>İşçilik</th><th>Brüt Kazanç</th></tr>{ptrs}</table></div>
    """
    return page("Ay Sonu Rapor ve Net Kazanç", body)

@app.get("/export-month")
def export_month(m: Optional[str]=None):
    if not m:
        m=this_month()
    like=m+"%"
    out=Path(f"katlama_tam_rapor_{m}.csv")
    sm = month_summary(m)

    with out.open("w", newline="", encoding="utf-8-sig") as f:
        wr=csv.writer(f, delimiter=";")
        wr.writerow(["AY SONU GENEL ÖZET"])
        wr.writerow(["Ay", m])
        wr.writerow(["Toplam Adet", int(sm["qty"])])
        wr.writerow(["Ciro / Firmadan Alacak", f"{sm['revenue']:.2f}"])
        wr.writerow(["Eleman Hak Edişi", f"{sm['labor']:.2f}"])
        wr.writerow(["Masraflar", f"{sm['expense']:.2f}"])
        wr.writerow(["Brüt Kazanç", f"{sm['gross']:.2f}"])
        wr.writerow(["Net Kazanç", f"{sm['net']:.2f}"])
        wr.writerow([])

        wr.writerow(["ELEMAN BAZLI ÖZET"])
        wr.writerow(["Eleman","Toplam Adet","Hak Ediş","Ödenen","Kalan"])
        by_worker = rows("""
        SELECT w.id,w.name worker, COALESCE(SUM(e.qty),0) qty, COALESCE(SUM(e.qty*e.worker_price),0) earned
        FROM workers w
        LEFT JOIN entries e ON e.worker_id=w.id AND e.work_date LIKE ?
        WHERE w.active=1
        GROUP BY w.id,w.name
        ORDER BY w.name
        """, (like,))
        for r in by_worker:
            paid=one("SELECT COALESCE(SUM(amount),0) paid FROM payments WHERE worker_id=? AND pay_date LIKE ?", (r["id"], like))["paid"] or 0
            remain=(r["earned"] or 0)-paid
            wr.writerow([r["worker"], int(r["qty"] or 0), f"{r['earned'] or 0:.2f}", f"{paid:.2f}", f"{remain:.2f}"])

        wr.writerow([])
        wr.writerow(["ÜRÜN BAZLI ÖZET"])
        wr.writerow(["Ürün","Adet","Ciro","İşçilik","Brüt Kazanç"])
        by_product = rows("""
        SELECT p.name product, COALESCE(SUM(e.qty),0) qty, COALESCE(SUM(e.qty*e.firm_price),0) revenue,
               COALESCE(SUM(e.qty*e.worker_price),0) labor,
               COALESCE(SUM(e.qty*(e.firm_price-e.worker_price)),0) gross
        FROM products p
        LEFT JOIN entries e ON e.product_id=p.id AND e.work_date LIKE ?
        GROUP BY p.id,p.name
        ORDER BY p.name
        """, (like,))
        for r in by_product:
            wr.writerow([r["product"], int(r["qty"] or 0), f"{r['revenue'] or 0:.2f}", f"{r['labor'] or 0:.2f}", f"{r['gross'] or 0:.2f}"])

        wr.writerow([])
        wr.writerow(["DETAY KAYITLAR"])
        wr.writerow(["Tarih","Eleman","Ürün","Adet","Firma Ücreti","Eleman Ücreti","Ciro","İşçilik","Brüt","Not"])
        details = rows("""
        SELECT e.work_date,w.name worker,p.name product,e.qty,e.firm_price,e.worker_price,
               e.qty*e.firm_price revenue,e.qty*e.worker_price labor,e.qty*(e.firm_price-e.worker_price) gross,COALESCE(e.note,'') note
        FROM entries e JOIN workers w ON w.id=e.worker_id JOIN products p ON p.id=e.product_id
        WHERE e.work_date LIKE ?
        ORDER BY e.work_date,e.id
        """, (like,))
        for r in details:
            wr.writerow([r["work_date"],r["worker"],r["product"],int(r["qty"]),f"{r['firm_price']:.2f}",f"{r['worker_price']:.2f}",f"{r['revenue']:.2f}",f"{r['labor']:.2f}",f"{r['gross']:.2f}",r["note"]])

        wr.writerow([])
        wr.writerow(["MASRAFLAR"])
        wr.writerow(["Tarih","Kategori","Tutar","Not"])
        exps = rows("SELECT * FROM expenses WHERE exp_date LIKE ? ORDER BY exp_date,id", (like,))
        for r in exps:
            wr.writerow([r["exp_date"],r["category"],f"{r['amount']:.2f}",r["note"] or ""])

    return FileResponse(out, filename=out.name)

@app.get("/delete-entry/{entry_id}")
def delete_entry(entry_id:int):
    exec_db("DELETE FROM entries WHERE id=?", (entry_id,))
    return RedirectResponse("/dashboard", status_code=303)

if __name__ == "__main__":
    init_db()
    print("="*70)
    print("KATLAMA ATÖLYESİ TAM SİSTEM BAŞLADI")
    print(f"Yönetim paneli: http://127.0.0.1:{PORT}/dashboard")
    print(f"Aynı Wi-Fi telefon: http://{local_ip()}:{PORT}")
    print(f"Farklı internet için ngrok: ngrok http {PORT}")
    print("="*70)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
