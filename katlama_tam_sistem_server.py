
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
