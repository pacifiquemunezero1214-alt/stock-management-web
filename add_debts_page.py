import os
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL is not set.")
    input("Press Enter to exit...")
    raise SystemExit(1)

print("Connecting to PostgreSQL...")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

print("Connected successfully.")

# =========================
# CUSTOMERS
# =========================

cur.execute("""
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    phone VARCHAR(50),
    address VARCHAR(300),
    owner_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# =========================
# DEBTS
# =========================

cur.execute("""
CREATE TABLE IF NOT EXISTS debts (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    paid_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    balance NUMERIC(14,2) NOT NULL DEFAULT 0,
    due_date DATE,
    status VARCHAR(30) NOT NULL DEFAULT 'UNPAID',
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_debt_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
        ON DELETE CASCADE
)
""")

# =========================
# DEBT PAYMENTS
# =========================

cur.execute("""
CREATE TABLE IF NOT EXISTS debt_payments (
    id SERIAL PRIMARY KEY,
    debt_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_payment_debt
        FOREIGN KEY (debt_id)
        REFERENCES debts(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_payment_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
        ON DELETE CASCADE
)
""")

# =========================
# INDEXES
# =========================

cur.execute("""
CREATE INDEX IF NOT EXISTS idx_customers_owner
ON customers(owner_id)
""")

cur.execute("""
CREATE INDEX IF NOT EXISTS idx_debts_owner
ON debts(owner_id)
""")

cur.execute("""
CREATE INDEX IF NOT EXISTS idx_debts_customer
ON debts(customer_id)
""")

cur.execute("""
CREATE INDEX IF NOT EXISTS idx_debt_payments_debt
ON debt_payments(debt_id)
""")

cur.execute("""
CREATE INDEX IF NOT EXISTS idx_debt_payments_customer
ON debt_payments(customer_id)
""")

cur.execute("""
CREATE INDEX IF NOT EXISTS idx_debt_payments_owner
ON debt_payments(owner_id)
""")

conn.commit()

# =========================
# VERIFY
# =========================

cur.execute("""
SELECT table_name
FROM information_schema.tables
WHERE table_schema='public'
AND table_name IN (
    'customers',
    'debts',
    'debt_payments'
)
ORDER BY table_name
""")

tables = [row[0] for row in cur.fetchall()]

print("")
print("==============================================")
print("DATABASE TABLE CHECK")
print("==============================================")

for table in ["customers", "debts", "debt_payments"]:
    if table in tables:
        print(table + " : OK")
    else:
        print(table + " : MISSING")

print("==============================================")

cur.close()
conn.close()

input("Press Enter to close...")