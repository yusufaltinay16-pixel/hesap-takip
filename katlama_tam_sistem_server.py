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
    """Eleman linklerinde Render'in ozel 10.x adresinin kullanilmasini engeller."""
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
