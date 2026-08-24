import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set.")

conn = psycopg2.connect(DATABASE_URL)

try:
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            # ============================================================
            # CUSTOMERS
            # ============================================================
            cur.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    phone TEXT,
                    address TEXT,
                    owner_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ============================================================
            # DEBTS
            # ============================================================
            cur.execute("""
                CREATE TABLE IF NOT EXISTS debts (
                    id SERIAL PRIMARY KEY,
                    customer_id INTEGER NOT NULL,
                    owner_id INTEGER NOT NULL,
                    amount NUMERIC(14,2) NOT NULL DEFAULT 0,
                    paid_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
                    remaining_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
                    description TEXT,
                    due_date DATE,
                    status TEXT NOT NULL DEFAULT 'UNPAID',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    CONSTRAINT fk_debt_customer
                    FOREIGN KEY (customer_id)
                    REFERENCES customers(id)
                    ON DELETE CASCADE
                )
            """)

            # ============================================================
            # DEBT PAYMENTS
            # ============================================================
            cur.execute("""
                CREATE TABLE IF NOT EXISTS debt_payments (
                    id SERIAL PRIMARY KEY,
                    debt_id INTEGER NOT NULL,
                    owner_id INTEGER NOT NULL,
                    amount NUMERIC(14,2) NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    CONSTRAINT fk_payment_debt
                    FOREIGN KEY (debt_id)
                    REFERENCES debts(id)
                    ON DELETE CASCADE
                )
            """)

            # ============================================================
            # INDEXES
            # ============================================================
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
                CREATE INDEX IF NOT EXISTS idx_debt_payments_owner
                ON debt_payments(owner_id)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_debt_payments_debt
                ON debt_payments(debt_id)
            """)

            # ============================================================
            # UPDATE REMAINING AMOUNTS
            # ============================================================
            cur.execute("""
                UPDATE debts
                SET remaining_amount = GREATEST(
                    amount - paid_amount,
                    0
                )
                WHERE remaining_amount IS NULL
                   OR remaining_amount <> GREATEST(amount - paid_amount, 0)
            """)

            # ============================================================
            # UPDATE STATUS
            # ============================================================
            cur.execute("""
                UPDATE debts
                SET status = CASE
                    WHEN remaining_amount <= 0 THEN 'PAID'
                    WHEN paid_amount > 0 THEN 'PARTIAL'
                    ELSE 'UNPAID'
                END
            """)

            # ============================================================
            # CHECK TABLES
            # ============================================================
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'customers',
                      'debts',
                      'debt_payments'
                  )
                ORDER BY table_name
            """)

            tables = cur.fetchall()

            print("")
            print("==============================================")
            print("       DEBT TABLES CREATED SUCCESSFULLY")
            print("==============================================")

            for table in tables:
                print("OK:", table["table_name"])

            print("")
            print("Customers table:     READY")
            print("Debts table:         READY")
            print("Debt payments table: READY")
            print("")
            print("Database:", "PostgreSQL")
            print("==============================================")

finally:
    conn.close()