import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")

# ---------------- DB ----------------
def db():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL eksik")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    con = db()
    c = con.cursor()

    # tek sistem tablo mantığı (ERP core)
    c.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL
    );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id SERIAL PRIMARY KEY,
        employee_name TEXT,
        type TEXT,
        amount NUMERIC,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS cash (
        id SERIAL PRIMARY KEY,
        description TEXT,
        amount NUMERIC,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    con.commit()
    con.close()

@app.on_event("startup")
def startup():
    init_db()

# ---------------- MODELS ----------------
class Employee(BaseModel):
    name: str

class Transaction(BaseModel):
    employee_name: str | None = None
    type: str
    amount: float

class Cash(BaseModel):
    description: str
    amount: float

# ---------------- API ----------------

@app.get("/dashboard")
def dashboard():
    con = db()
    c = con.cursor()

    c.execute("SELECT COUNT(*) as total FROM transactions;")
    total = c.fetchone()["total"]

    con.close()

    return {"toplam_kayit": total}

@app.post("/employee")
def add_employee(e: Employee):
    con = db()
    c = con.cursor()

    c.execute("INSERT INTO employees (name) VALUES (%s)", (e.name,))
    con.commit()
    con.close()

    return {"status": "ok"}

@app.post("/transaction")
def add_transaction(t: Transaction):
    con = db()
    c = con.cursor()

    c.execute("""
        INSERT INTO transactions (employee_name, type, amount)
        VALUES (%s, %s, %s)
    """, (t.employee_name, t.type, t.amount))

    con.commit()
    con.close()

    return {"status": "ok"}

@app.post("/cash")
def add_cash(cash: Cash):
    con = db()
    c = con.cursor()

    c.execute("""
        INSERT INTO cash (description, amount)
        VALUES (%s, %s)
    """, (cash.description, cash.amount))

    con.commit()
    con.close()

    return {"status": "ok"}
