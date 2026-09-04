from flask import Flask, request, jsonify, session, redirect, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "CHANGE-THIS-STOCK-SECRET-KEY"
)

DATABASE_URL = os.getenv("DATABASE_URL", "")


# ============================================================
# DATABASE
# ============================================================

def get_db():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. Set your PostgreSQL connection string first."
        )

    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )


def init_database():
    conn = get_db()

    try:
        with conn.cursor() as cur:

            # USERS
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role VARCHAR(20) NOT NULL DEFAULT 'user',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # PRODUCTS
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0
                        CHECK (quantity >= 0),
                    purchase_price NUMERIC(14,2) NOT NULL DEFAULT 0
                        CHECK (purchase_price >= 0),
                    selling_price NUMERIC(14,2) NOT NULL DEFAULT 0
                        CHECK (selling_price >= 0),
                    owner_id INTEGER NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(owner_id, name)
                )
            """)
            # PRODUCT UNIT COST
            cur.execute("""
                ALTER TABLE products
                ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(14,2) NOT NULL DEFAULT 0
            """)

            # CASH
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cash_account (
                    id SERIAL PRIMARY KEY,
                    balance NUMERIC(16,2) NOT NULL DEFAULT 0,
                    owner_id INTEGER UNIQUE NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE
                )
            """)
# TRANSACTIONS
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    transaction_type VARCHAR(50) NOT NULL,
                    product_id INTEGER
                        REFERENCES products(id) ON DELETE SET NULL,
                    product_name VARCHAR(200),
                    quantity INTEGER,
                    purchase_price NUMERIC(14,2) DEFAULT 0,
                    selling_price NUMERIC(14,2) DEFAULT 0,
                    amount NUMERIC(16,2) DEFAULT 0,
                    cost_amount NUMERIC(16,2) DEFAULT 0,
                    profit NUMERIC(16,2) DEFAULT 0,
                    cash_before NUMERIC(16,2) DEFAULT 0,
                    cash_after NUMERIC(16,2) DEFAULT 0,
                    stock_before INTEGER,
                    stock_after INTEGER,
                    username VARCHAR(100),
                    description TEXT,
                    owner_id INTEGER NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # DEBIT & CREDIT
            cur.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    phone VARCHAR(50),
                    address VARCHAR(300),
                    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS debts (
                    id SERIAL PRIMARY KEY,
                    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
                    product_name VARCHAR(200),
                    quantity INTEGER NOT NULL DEFAULT 0,
                    total_amount NUMERIC(16,2) NOT NULL DEFAULT 0,
                    amount_paid NUMERIC(16,2) NOT NULL DEFAULT 0,
                    amount_remaining NUMERIC(16,2) NOT NULL DEFAULT 0,
                    due_date DATE,
                    status VARCHAR(20) NOT NULL DEFAULT 'UNPAID',
                    description TEXT,
                    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS debt_payments (
                    id SERIAL PRIMARY KEY,
                    debt_id INTEGER NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
                    amount NUMERIC(16,2) NOT NULL,
                    payment_method VARCHAR(50) DEFAULT 'CASH',
                    description TEXT,
                    username VARCHAR(100),
                    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # HISTORY
            cur.execute("""
                CREATE TABLE IF NOT EXISTS approval_requests (
                    id SERIAL PRIMARY KEY,
                    requester_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    requester_username VARCHAR(100) NOT NULL,
                    action_type VARCHAR(100) NOT NULL,
                    description TEXT NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT PENDING,
                    approved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    approved_by_username VARCHAR(100),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id SERIAL PRIMARY KEY,
                    product_id INTEGER
                        REFERENCES products(id) ON DELETE SET NULL,
                    product_name VARCHAR(200) NOT NULL,
                    action VARCHAR(50) NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    previous_quantity INTEGER NOT NULL DEFAULT 0,
                    new_quantity INTEGER NOT NULL DEFAULT 0,
                    username VARCHAR(100) NOT NULL,
                    owner_id INTEGER NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

        conn.commit()
        create_default_admin(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users")
            existing_users=cur.fetchall()
        for u in existing_users:
            ensure_default_accounts(conn,u["id"])
        conn.commit()

    finally:
        conn.close()


def ensure_default_accounts(conn, owner_id):
    accounts = [
        ("1000", "Cash", "ASSET"),
        ("1010", "Bank", "ASSET"),
        ("1020", "Mobile Money", "ASSET"),
        ("1100", "Accounts Receivable", "ASSET"),
        ("1200", "Inventory", "ASSET"),
        ("4000", "Sales Revenue", "REVENUE"),
        ("5000", "Cost of Goods Sold", "EXPENSE"),
        ("3000", "Owner Capital", "EQUITY"),
        ("6000", "Operating Expenses", "EXPENSE")
    ]

    with conn.cursor() as cur:
        for account_code, account_name, account_type in accounts:
            cur.execute("""
                INSERT INTO accounts(
                    account_code,
                    account_name,
                    account_type,
                    owner_id
                )
                VALUES(%s,%s,%s,%s)
                ON CONFLICT(owner_id, account_code) DO NOTHING
            """, (
                account_code,
                account_name,
                account_type,
                owner_id
            ))

def get_account_id(conn, owner_id, account_code):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM accounts WHERE owner_id=%s AND account_code=%s", (owner_id, account_code))
        row = cur.fetchone()
    if not row:
        raise ValueError(f"Accounting account {account_code} was not found for this user.")
    return row["id"]


def create_journal_entry(conn, owner_id, reference_type, reference_id, description, lines, username=None):
    if not lines:
        raise ValueError("Journal entry must contain at least one line.")

    total_debit = sum(float(line.get("debit", 0) or 0) for line in lines)
    total_credit = sum(float(line.get("credit", 0) or 0) for line in lines)

    if abs(total_debit - total_credit) > 0.005:
        raise ValueError(f"Unbalanced journal entry. Debit={total_debit:.2f}, Credit={total_credit:.2f}")

    if total_debit <= 0:
        raise ValueError("Journal entry amount must be greater than zero.")

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO journal_entries(reference_type, reference_id, description, username, owner_id)
            VALUES(%s,%s,%s,%s,%s)
            RETURNING id
        """, (reference_type, reference_id, description, username, owner_id))
        journal_entry_id = cur.fetchone()["id"]

        for line in lines:
            account_code = str(line.get("account_code", "")).strip()
            debit = float(line.get("debit", 0) or 0)
            credit = float(line.get("credit", 0) or 0)
            line_description = line.get("description")

            if not account_code:
                raise ValueError("Every journal line must have an account code.")
            if debit < 0 or credit < 0:
                raise ValueError("Debit and credit amounts cannot be negative.")
            if debit > 0 and credit > 0:
                raise ValueError("A journal line cannot contain both debit and credit.")
            if debit == 0 and credit == 0:
                raise ValueError("A journal line must contain either debit or credit.")

            account_id = get_account_id(conn, owner_id, account_code)

            cur.execute("""
                INSERT INTO journal_entry_lines(journal_entry_id, account_id, debit, credit, description)
                VALUES(%s,%s,%s,%s,%s)
            """, (journal_entry_id, account_id, debit, credit, line_description))

    return journal_entry_id

BASE_CSS = """
*{box-sizing:border-box}body{font-family:Arial,sans-serif;background:linear-gradient(rgba(15,23,42,.72),rgba(15,23,42,.72)),url("/static/stockbackground.jpg") center/cover fixed no-repeat;color:#0f172a;margin:0}.nav{background:#020617;color:#fff;padding:16px 28px;display:flex;justify-content:space-between;align-items:center;gap:12px}.brand{font-size:21px;font-weight:700}.nav a{color:#fff;text-decoration:none}.container{max-width:1500px;margin:auto;padding:28px 20px}.top{display:flex;justify-content:space-between;align-items:center;gap:15px;margin-bottom:24px}.muted{color:#64748b}.btn{display:inline-block;border:0;border-radius:8px;padding:11px 16px;background:#2563eb;color:#fff;text-decoration:none;cursor:pointer;font-weight:700}.green{background:#16a34a}.red{background:#ef4444}.purple{background:#7c3aed}.dark{background:#0f172a}.box,.card,.section{background:#fff;padding:22px;border-radius:15px;box-shadow:0 5px 25px rgba(0,0,0,.06)}.box{margin-bottom:22px}.cards{display:grid;grid-template-columns:repeat(5,1fr);gap:18px}.card .title{color:#64748b;font-size:13px;font-weight:bold}.num{font-size:27px;font-weight:700;margin-top:10px}.form-grid{display:grid;grid-template-columns:2fr 1fr 1fr 1fr auto;gap:12px}.input,select{width:100%;padding:12px;border:1px solid #cbd5e1;border-radius:8px;font-size:15px}label{font-weight:700;display:block;margin:10px 0 7px}table{width:100%;border-collapse:collapse;background:#fff}th,td{padding:12px;border-bottom:1px solid #e2e8f0;text-align:left;white-space:nowrap}th{background:#020617;color:#fff}.table-wrap{overflow-x:auto}.profit{color:#16a34a;font-weight:700}.loss{color:#dc2626;font-weight:700}.menu{display:grid;grid-template-columns:repeat(6,1fr);gap:16px;margin-top:25px}.menu a{background:#fff;padding:20px;border-radius:14px;text-decoration:none;color:#0f172a;font-weight:700;text-align:center;box-shadow:0 5px 20px rgba(0,0,0,.06)}.menu a:hover{background:#2563eb;color:#fff}.search{margin-bottom:18px}.auth{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;background:linear-gradient(135deg,#020617,#2563eb)}.auth-box{width:100%;max-width:440px;background:#fff;padding:32px;border-radius:18px;box-shadow:0 15px 45px rgba(0,0,0,.2)}.auth-box h1{text-align:center}.auth-box .input{margin:8px 0 12px}.auth-box button{width:100%;margin-top:8px}.message{padding:10px;border-radius:8px;margin:10px 0;display:none}.small{font-size:13px}.warning{background:#fee2e2;color:#991b1b;padding:16px;border-radius:12px;margin-bottom:20px}@media(max-width:1100px){.cards{grid-template-columns:repeat(3,1fr)}.menu{grid-template-columns:repeat(3,1fr)}.form-grid{grid-template-columns:1fr 1fr}}@media(max-width:650px){.cards,.menu,.form-grid{grid-template-columns:1fr}.nav{padding:14px;flex-wrap:wrap}.container{padding:18px 12px}}
"""

AUTH_HTML = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Stock Management</title><style>{{ css }}</style></head><body style="background-image:url(/static/pc.jpeg);background-size:cover;background-position:center;background-attachment:fixed;background-repeat:no-repeat;">
<div class="auth"><div class="auth-box"><h1> Stock Management</h1><p class="muted" style="text-align:center">Login or create your account</p><div id="msg" class="message"></div>
<input id="username" class="input" placeholder="Username" autocomplete="username"><input id="password" class="input" type="password" placeholder="Password" autocomplete="current-password"><button class="btn" onclick="login()">LOGIN</button>
<hr style="margin:25px 0;border:0;border-top:1px solid #e2e8f0"><h3>Create account</h3><input id="rusername" class="input" placeholder="New username"><input id="rpassword" class="input" type="password" placeholder="New password"><button class="btn green" onclick="register()">REGISTER</button><p class="small muted">Password must contain at least 4 characters.</p>
</div></div><script>
function show(t,ok=false){const m=document.getElementById('msg');m.textContent=t;m.style.display='block';m.style.background=ok?'#dcfce7':'#fee2e2';m.style.color=ok?'#166534':'#991b1b'}
async function login(){const r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:username.value.trim(),password:password.value})});const d=await r.json();if(d.success){alert("Murakaza neza, "+username.value.trim()+"!");location.href=d.redirect}else show(d.message)}
async function register(){const r=await fetch('/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:rusername.value.trim(),password:rpassword.value})});const d=await r.json();show(d.message,d.success);if(d.success){username.value=rusername.value.trim();password.value=rpassword.value;rusername.value='';rpassword.value=''}}
</script></body></html>
"""

DASHBOARD_HTML = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dashboard</title><style>{{ css }}</style></head><body style="background-image:url(/static/pc.jpeg);background-size:cover;background-position:center;background-attachment:fixed;background-repeat:no-repeat;">
<div class="nav"><div class="brand"> Stock Management</div><div> {{ username }} <a class="btn red" href="/logout">LOGOUT</a></div></div>
<div class="container"><div class="top"><div><h1 id="welcomeText">&#128075; Welcome, {{ username }} </h1><style>#welcomeText{animation:welcomeFade 3s ease-in-out infinite;}@keyframes welcomeFade{0%,100%{opacity:1;transform:translateY(0);}50%{opacity:0;transform:translateY(-12px);}}</style><p class="muted">Manage stock, cash, sales and profit.</p></div></div>
<div class="cards"><div class="card"><div class="title">PRODUCTS</div><div id="products" class="num">0</div></div><div class="card"><div class="title">TOTAL STOCK</div><div id="stock" class="num">0</div></div><div class="card"><div class="title">STOCK VALUE</div><div id="stockValue" class="num">0</div></div><div class="card"><div class="title">CASH BALANCE</div><div id="cash" class="num">0</div></div><div class="card"><div class="title">POTENTIAL PROFIT</div><div id="potential" class="num">0</div></div><div class="card"><div class="title">TOTAL SALES</div><div id="sales" class="num">0</div></div><div class="card"><div class="title">TOTAL PROFIT</div><div id="profit" class="num">0</div></div><div class="card"><div class="title">LOW STOCK</div><div id="low" class="num">0</div></div></div>
<div class="menu"><a href="/products"> Products</a><a href="/stock-in"> Stock In</a><a href="/stock-out"> Stock Out</a><a href="/cash"> Cash</a><a href="/history"> History</a><a href="/debts"> Debts/Credit</a><a href="/invoice-history"> Invoice History</a><a href="/invoice"> Invoice</a></div></div>
<script>
async function loadDashboard(){
 try{
  const response=await fetch('/dashboard-data',{cache:'no-store'});
  const d=await response.json();
  if(!d.success){console.error('Dashboard error:',d);return;}
  document.getElementById('products').textContent=Number(d.total_products||0).toLocaleString();
  document.getElementById('stock').textContent=Number(d.total_stock||0).toLocaleString();
  document.getElementById('stockValue').textContent=Number(d.stock_value||0).toLocaleString();
  document.getElementById('cash').textContent=Number(d.cash_balance||0).toLocaleString();
  document.getElementById('potential').textContent=Number(d.potential_profit||0).toLocaleString();
  document.getElementById('sales').textContent=Number(d.total_sales||0).toLocaleString();
  document.getElementById('profit').textContent=Number(d.total_profit||0).toLocaleString();
  document.getElementById('low').textContent=Number(d.low_stock||0).toLocaleString();
 }catch(e){console.error('Dashboard loading error:',e);}
}
loadDashboard();
setInterval(loadDashboard,5000);
</script></body></html>
"""

PRODUCTS_HTML = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Products</title><style>{{ css }}</style></head><body>
<div class="nav"><div class="brand"> Products</div><a class="btn" href="/dashboard"> Dashboard</a></div><div class="container"><div class="box"><h2> Add Product</h2><div class="form-grid"><input id="name" class="input" placeholder="Product name"><input id="qty" class="input" type="number" min="0" placeholder="Initial stock"><input id="purchase" class="input" type="number" min="0" step="0.01" placeholder="Purchase price"><input id="unitCost" class="input" type="number" min="0" step="0.01" placeholder="Unit cost"><input id="selling" class="input" type="number" min="0" step="0.01" placeholder="Selling price"><button class="btn green" onclick="addProduct()">ADD</button></div><p class="muted">Initial stock does not change cash. Use Stock In when purchasing stock.</p></div><input id="search" class="input search" placeholder=" Search..." oninput="filterRows()"><div class="table-wrap"><table><thead><tr><th>ID</th><th>Product</th><th>Stock</th><th>Purchase</th><th>Unit Cost</th><th>Selling</th><th>Profit/Unit</th><th>Action</th></tr></thead><tbody id="rows"></tbody></table></div></div>
<script>let products=[];async function load(){const r=await fetch('/api/products');const d=await r.json();if(!d.success)return alert(d.message);products=d.products;render(products)}function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function render(a){rows.innerHTML=a.map(p=>{const profit=Number(p.selling_price)-Number(p.purchase_price);return `<tr><td>${p.id}</td><td>${esc(p.name)}</td><td>${p.quantity}</td><td>${Number(p.purchase_price).toLocaleString()}</td><td>${Number(p.unit_cost).toLocaleString()}</td><td>${Number(p.selling_price).toLocaleString()}</td><td class="${profit>=0?'profit':'loss'}">${profit.toLocaleString()}</td><td><button class="btn" onclick="edit(${p.id})">EDIT</button> <button class="btn purple" onclick="editStock(${p.id},${p.quantity})">STOCK</button> <button class="btn red" onclick="del(${p.id})">DELETE</button></td></tr>`}).join('')}function filterRows(){const q=search.value.toLowerCase();render(products.filter(p=>(p.name+' '+p.id).toLowerCase().includes(q)))}async function addProduct(){const body={name:document.getElementById("name").value.trim(),quantity:Number(document.getElementById("qty").value),purchase_price:Number(document.getElementById("purchase").value),unit_cost:Number(document.getElementById("unitCost").value),selling_price:Number(document.getElementById("selling").value)};if(!body.name||!Number.isInteger(body.quantity)||body.quantity<0||!Number.isFinite(body.purchase_price)||body.purchase_price<0||!Number.isFinite(body.unit_cost)||body.unit_cost<0||!Number.isFinite(body.selling_price)||body.selling_price<0)return alert('Enter valid values.');const r=await fetch('/api/products',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();alert(d.message);if(d.success){document.getElementById('name').value='';document.getElementById('qty').value='';document.getElementById('purchase').value='';document.getElementById('unitCost').value='';document.getElementById('selling').value='';load()}}async function edit(id){const p=products.find(x=>x.id===id);const n=prompt('Product name:',p.name);if(n===null)return;const pp=prompt('Purchase price:',p.purchase_price);if(pp===null)return;const sp=prompt('Selling price:',p.selling_price);if(sp===null)return;const r=await fetch('/api/products/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n,purchase_price:Number(pp),selling_price:Number(sp)})});const d=await r.json();alert(d.message);if(d.success)load()}async function editStock(id,current){const q=prompt('Current stock: '+current+'\\nEnter correct total stock:',current);if(q===null)return;const quantity=Number(q);if(!Number.isInteger(quantity)||quantity<0)return alert('Enter a valid whole number.');const reason=prompt('Reason for correction:','Stock correction');if(reason===null)return;const r=await fetch('/api/products/'+id+'/stock',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({quantity,reason})});const d=await r.json();alert(d.message);if(d.success)load()}async function del(id){if(!confirm('Delete this product? Stock must be zero.'))return;const r=await fetch('/api/products/'+id,{method:'DELETE'});const d=await r.json();alert(d.message);if(d.success)load()}load()</script></body></html>
"""

MOVEMENT_HTML = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }}</title><style>{{ css }}</style></head><body><div class="nav"><div class="brand"> Stock Management</div><a class="btn" href="/dashboard"> Dashboard</a></div><div class="container"><div class="box" style="max-width:700px;margin:auto"><h1>{{ icon }} {{ title }}</h1><label>Product</label><select id="product" class="input"></select><label>Quantity</label><input id="quantity" class="input" type="number" min="1"><div id="priceBox"></div><button class="btn {{ color }}" style="width:100%;margin-top:20px" onclick="submitMove()">{{ button }}</button></div></div><script>async function load(){const r=await fetch('/api/products');const d=await r.json();product.innerHTML='<option value="">Select product</option>'+d.products.map(p=>`<option value="${p.id}" data-price="${p.purchase_price}">${p.name}  Stock: ${p.quantity}  Buy: ${Number(p.purchase_price).toLocaleString()}</option>`).join('')}async function submitMove(){const product_id=Number(product.value),quantity=Number(document.getElementById('quantity').value);if(!product_id||!Number.isInteger(quantity)||quantity<=0)return alert('Enter valid information.');const r=await fetch('{{ endpoint }}',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_id,quantity})});const d=await r.json();alert(d.message);if(d.success){document.getElementById('quantity').value='';load()}}load()</script></body></html>
"""

INVOICE_HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Create Invoice</title>
<style>
{{ css }}

.invoice-wrap{max-width:1100px;margin:auto}
.invoice-header{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:20px}
.invoice-title{font-size:30px;font-weight:800}
.invoice-subtitle{color:#777;margin-top:5px}
.invoice-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.invoice-box{background:#fff;border-radius:14px;padding:20px;box-shadow:0 4px 18px rgba(0,0,0,.08);margin-bottom:20px}
.invoice-box h2{margin-top:0}
.invoice-table{width:100%;border-collapse:collapse;margin-top:15px}
.invoice-table th,.invoice-table td{padding:12px;border-bottom:1px solid #eee;text-align:left}
.invoice-table th{background:#f7f7f7}
.invoice-total{margin-left:auto;max-width:400px}
.total-row{display:flex;justify-content:space-between;padding:8px 0}
.grand-total{font-size:22px;font-weight:800;border-top:2px solid #222;margin-top:8px;padding-top:12px}
.balance{font-size:20px;font-weight:800}
.status{display:inline-block;padding:7px 12px;border-radius:20px;font-weight:700}
.status.paid{background:#dcfce7;color:#166534}
.status.partial{background:#fef3c7;color:#92400e}
.status.unpaid{background:#fee2e2;color:#991b1b}
.item-form{display:grid;grid-template-columns:2fr 1fr 1fr auto;gap:10px;align-items:end}
.small-label{font-size:13px;font-weight:600;display:block;margin-bottom:5px}
.remove-btn{background:#dc2626;color:white;border:0;padding:9px 12px;border-radius:7px;cursor:pointer}
.summary-box{background:#f8fafc;border-radius:10px;padding:15px;margin-top:15px}
@media(max-width:800px){
 .invoice-grid{grid-template-columns:1fr}
 .item-form{grid-template-columns:1fr}
 .invoice-header{flex-direction:column;align-items:flex-start}
}
</style>
</head>
<body>

<div class="nav">
    <div class="brand">Invoice</div>
    <div>
        <a class="btn" href="/dashboard">Dashboard</a>
    </div>
</div>

<div class="container invoice-wrap">

<div class="invoice-header">
    <div>
        <div class="invoice-title">Create Invoice</div>
        <div class="invoice-subtitle">Create a sale and automatically update stock and accounting.</div>
    </div>
</div>

<div class="invoice-grid">

<div class="invoice-box">
<h2>Customer Information</h2>

<label class="small-label">Customer Name *</label>
<input id="customerName" class="input" placeholder="Customer name">

<label class="small-label">Phone</label>
<input id="customerPhone" class="input" placeholder="Phone number">

<label class="small-label">Address</label>
<input id="customerAddress" class="input" placeholder="Customer address">
</div>

<div class="invoice-box">
<h2>Payment</h2>

<label class="small-label">Amount Paid</label>
<input id="amountPaid" class="input" type="number" min="0" step="0.01" value="0" oninput="calculate()">

<label class="small-label">Payment Method</label>
<select id="paymentMethod" class="input">
    <option value="CASH">CASH</option>
    <option value="BANK">BANK</option>
    <option value="MOBILE MONEY">MOBILE MONEY</option>
</select>

<label class="small-label">Payment Reference</label>
<input id="paymentReference" class="input" placeholder="Optional reference">

<div class="summary-box">
    <div class="total-row">
        <span>Status</span>
        <span id="paymentStatus" class="status unpaid">UNPAID</span>
    </div>
    <div class="total-row">
        <span>Balance</span>
        <strong id="balance">0 Frw</strong>
    </div>
</div>
</div>

</div>

<div class="invoice-box">
<h2>Products</h2>

<div class="item-form">
<div>
<label class="small-label">Product</label>
<select id="product" class="input" onchange="setPrice()">
<option value="">Select product</option>
</select>
</div>

<div>
<label class="small-label">Quantity</label>
<input id="quantity" class="input" type="number" min="1" value="1">
</div>

<div>
<label class="small-label">Unit Price</label>
<input id="unitPrice" class="input" type="number" min="0" step="0.01">
</div>

<div>
<button class="btn green" onclick="addItem()">ADD</button>
</div>
</div>

<div class="table-wrap">
<table class="invoice-table">
<thead>
<tr>
<th>Product</th>
<th>Qty</th>
<th>Unit Price</th>
<th>Total</th>
<th>Action</th>
</tr>
</thead>
<tbody id="itemRows">
<tr>
<td colspan="5" style="text-align:center;color:#777">No products added.</td>
</tr>
</tbody>
</table>
</div>
</div>

<div class="invoice-box">

<div class="invoice-total">

<div class="total-row">
<span>Subtotal</span>
<strong id="subtotal">0 Frw</strong>
</div>

<div class="total-row">
<span>Discount</span>
<input id="discount" class="input" type="number" min="0" step="0.01" value="0" style="max-width:180px" oninput="calculate()">
</div>

<div class="total-row">
<span>Tax</span>
<input id="tax" class="input" type="number" min="0" step="0.01" value="0" style="max-width:180px" oninput="calculate()">
</div>

<div class="total-row grand-total">
<span>GRAND TOTAL</span>
<strong id="grandTotal">0 Frw</strong>
</div>

<div class="total-row">
<span>AMOUNT PAID</span>
<strong id="paidDisplay">0 Frw</strong>
</div>

<div class="total-row balance">
<span>BALANCE</span>
<strong id="balanceBottom">0 Frw</strong>
</div>

<div style="margin-top:20px">
<button class="btn green" style="width:100%;font-size:17px;padding:14px" onclick="createInvoice()">
CREATE INVOICE
</button>
</div>

</div>
</div>

</div>

<script>
let products=[];
let items=[];

function money(n){
    return Number(n||0).toLocaleString(undefined,{
        minimumFractionDigits:2,
        maximumFractionDigits:2
    }) + ' Frw';
}

function esc(s){
    return String(s??'').replace(/[&<>"']/g,c=>({
        '&':'&amp;',
        '<':'&lt;',
        '>':'&gt;',
        '"':'&quot;',
        "'":'&#39;'
    }[c]));
}

async function loadProducts(){
    const r=await fetch('/api/products');
    const d=await r.json();

    if(!d.success){
        alert(d.message||'Could not load products.');
        return;
    }

    products=d.products;

    product.innerHTML='<option value="">Select product</option>'+
        products.map(p=>
            '<option value="'+p.id+'">'+
            esc(p.name)+
            ' | Stock: '+p.quantity+
            ' | Price: '+Number(p.selling_price).toLocaleString()+
            '</option>'
        ).join('');
}

function setPrice(){
    const p=products.find(x=>Number(x.id)===Number(product.value));

    if(p){
        unitPrice.value=Number(p.selling_price);
    }else{
        unitPrice.value='';
    }
}

function addItem(){
    const productId=Number(product.value);
    const qty=Number(quantity.value);
    const price=Number(unitPrice.value);

    if(!productId){
        alert('Please select a product.');
        return;
    }

    if(!Number.isInteger(qty)||qty<=0){
        alert('Enter a valid quantity.');
        return;
    }

    if(!Number.isFinite(price)||price<0){
        alert('Enter a valid unit price.');
        return;
    }

    const p=products.find(x=>Number(x.id)===productId);

    if(!p){
        alert('Product not found.');
        return;
    }

    const existing=items.find(x=>x.product_id===productId);

    const newQty=(existing?existing.quantity:0)+qty;

    if(newQty>Number(p.quantity)){
        alert('Not enough stock. Available: '+p.quantity);
        return;
    }

    if(existing){
        existing.quantity=newQty;
        existing.unit_price=price;
    }else{
        items.push({
            product_id:productId,
            product_name:p.name,
            quantity:qty,
            unit_price:price
        });
    }

    renderItems();

    product.value='';
    quantity.value=1;
    unitPrice.value='';
}

function removeItem(index){
    items.splice(index,1);
    renderItems();
}

function renderItems(){
    if(items.length===0){
        itemRows.innerHTML=
            '<tr><td colspan="5" style="text-align:center;color:#777">No products added.</td></tr>';
        calculate();
        return;
    }

    itemRows.innerHTML=items.map((item,index)=>{
        const total=Number(item.quantity)*Number(item.unit_price);

        return `
        <tr>
            <td>${esc(item.product_name)}</td>
            <td>${item.quantity}</td>
            <td>${money(item.unit_price)}</td>
            <td>${money(total)}</td>
            <td>
                <button class="remove-btn" onclick="removeItem(${index})">REMOVE</button>
            </td>
        </tr>`;
    }).join('');

    calculate();
}

function calculate(){
    let subtotalValue=0;

    items.forEach(item=>{
        subtotalValue += Number(item.quantity)*Number(item.unit_price);
    });

    const discountValue=Math.max(0,Number(discount.value)||0);
    const taxValue=Math.max(0,Number(tax.value)||0);

    let total=subtotalValue-discountValue+taxValue;

    if(total<0) total=0;

    const paid=Math.max(0,Number(amountPaid.value)||0);
    const balanceValue=Math.max(0,total-paid);

    subtotal.textContent=money(subtotalValue);
    grandTotal.textContent=money(total);
    paidDisplay.textContent=money(paid);

    balance.textContent=money(balanceValue);
    balanceBottom.textContent=money(balanceValue);

    const status=paymentStatus;

    status.className='status';

    if(paid>=total && total>0){
        status.textContent='PAID';
        status.classList.add('paid');
    }else if(paid>0){
        status.textContent='PARTIALLY PAID';
        status.classList.add('partial');
    }else{
        status.textContent='UNPAID';
        status.classList.add('unpaid');
    }
}

async function createInvoice(){

    const customer_name=customerName.value.trim();
    const customer_phone=customerPhone.value.trim();
    const customer_address=customerAddress.value.trim();

    if(!customer_name){
        alert('Customer name is required.');
        return;
    }

    if(items.length===0){
        alert('Add at least one product.');
        return;
    }

    const discountValue=Math.max(0,Number(discount.value)||0);
    const taxValue=Math.max(0,Number(tax.value)||0);
    const paid=Math.max(0,Number(amountPaid.value)||0);

    let subtotalValue=0;

    items.forEach(item=>{
        subtotalValue += Number(item.quantity)*Number(item.unit_price);
    });

    const total=subtotalValue-discountValue+taxValue;

    if(discountValue>subtotalValue){
        alert('Discount cannot exceed subtotal.');
        return;
    }

    if(paid>total){
        alert('Amount paid cannot exceed invoice total.');
        return;
    }

    const body={
        customer_name,
        customer_phone,
        customer_address,
        items:items.map(item=>({
            product_id:item.product_id,
            quantity:item.quantity,
            unit_price:item.unit_price
        })),
        discount:discountValue,
        tax:taxValue,
        amount_paid:paid,
        payment_method:paymentMethod.value,
        payment_reference:paymentReference.value.trim()
    };

    const button=document.querySelector('button[onclick="createInvoice()"]');

    button.disabled=true;
    button.textContent='CREATING...';

    try{
        const r=await fetch('/api/invoices',{
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(body)
        });

        const d=await r.json();

        if(d.success){
            alert(
                'Invoice '+d.invoice.invoice_number+
                ' created successfully!\\n\\n'+
                'Total: '+money(d.invoice.total_amount)+'\\n'+
                'Paid: '+money(d.invoice.amount_paid)+'\\n'+
                'Balance: '+money(d.invoice.balance)+'\\n'+
                'Status: '+d.invoice.payment_status
            );

            items=[];
            customerName.value='';
            customerPhone.value='';
            customerAddress.value='';
            amountPaid.value=0;
            paymentReference.value='';
            discount.value=0;
            tax.value=0;

            renderItems();
            calculate();
            await loadProducts();

        }else{
            alert(d.message||'Invoice creation failed.');
        }

    }catch(e){
        alert('Invoice creation failed: '+e.message);
    }finally{
        button.disabled=false;
        button.textContent='CREATE INVOICE';
    }
}

loadProducts();
calculate();
</script>

</body>
</html>
"""

INVOICE_HISTORY_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Invoice History</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f4f7fb;
            margin: 0;
            padding: 20px;
        }

        .invoice-history {
            max-width: 1200px;
            margin: auto;
        }

        .topbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }

        h1 {
            margin: 0;
            color: #1f2937;
        }

        .back-btn {
            text-decoration: none;
            background: #2563eb;
            color: white;
            padding: 10px 16px;
            border-radius: 8px;
            font-weight: bold;
        }

        .search-box {
            background: white;
            padding: 15px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,.08);
            margin-bottom: 20px;
        }

        .search-box input {
            width: 100%;
            box-sizing: border-box;
            padding: 12px;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            font-size: 15px;
        }

        .table-wrap {
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,.08);
            overflow-x: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            min-width: 900px;
        }

        th, td {
            padding: 13px 12px;
            border-bottom: 1px solid #e5e7eb;
            text-align: left;
        }

        th {
            background: #f8fafc;
            color: #374151;
        }

        .status {
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            display: inline-block;
        }

        .paid {
            background: #dcfce7;
            color: #166534;
        }

        .partial {
            background: #fef3c7;
            color: #92400e;
        }

        .unpaid {
            background: #fee2e2;
            color: #991b1b;
        }

        .view-btn {
            border: none;
            background: #111827;
            color: white;
            padding: 8px 12px;
            border-radius: 7px;
            cursor: pointer;
            font-weight: bold;
        }

        .empty {
            text-align: center;
            padding: 30px;
            color: #6b7280;
        }

        .loading {
            text-align: center;
            padding: 30px;
        }
    </style>
</head>

<body>

<div class="invoice-history">

    <div class="topbar">
        <h1>?? Invoice History</h1>
        <a href="/invoice" class="back-btn">+ New Invoice</a>
    </div>

    <div class="search-box">
        <input
            type="text"
            id="searchInput"
            placeholder="Search invoice number, customer, phone, cashier or status..."
            oninput="filterInvoices()"
        >
    </div>

    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Invoice No.</th>
                    <th>Date</th>
                    <th>Customer</th>
                    <th>Cashier</th>
                    <th>Total</th>
                    <th>Paid</th>
                    <th>Balance</th>
                    <th>Status</th>
                    <th>Action</th>
                </tr>
            </thead>

            <tbody id="invoiceTableBody">
                <tr>
                    <td colspan="9" class="loading">Loading invoices...</td>
                </tr>
            </tbody>
        </table>
    </div>

</div>

<script>
let invoices = [];

async function loadInvoices() {
    const body = document.getElementById("invoiceTableBody");

    try {
        const response = await fetch("/api/invoices");
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || "Failed to load invoices.");
        }

        invoices = data.invoices || [];
        renderInvoices(invoices);

    } catch (error) {
        body.innerHTML = `
            <tr>
                <td colspan="9" class="empty">
                    ? ${escapeHtml(error.message)}
                </td>
            </tr>
        `;
    }
}

function renderInvoices(list) {
    const body = document.getElementById("invoiceTableBody");

    if (!list.length) {
        body.innerHTML = `
            <tr>
                <td colspan="9" class="empty">
                    No invoices found.
                </td>
            </tr>
        `;
        return;
    }

    body.innerHTML = list.map(inv => {

        const status = String(inv.payment_status || "UNPAID").toUpperCase();

        let statusClass = "unpaid";

        if (status === "PAID") {
            statusClass = "paid";
        } else if (status === "PARTIALLY PAID") {
            statusClass = "partial";
        }

        return `
            <tr>
                <td><strong>${escapeHtml(inv.invoice_number)}</strong></td>

                <td>
                    ${formatDate(inv.created_at)}
                </td>

                <td>
                    ${escapeHtml(inv.customer_name || "Walk-in Customer")}
                    ${inv.customer_phone
                        ? "<br><small>" + escapeHtml(inv.customer_phone) + "</small>"
                        : ""}
                </td>

                <td>
                    ${escapeHtml(inv.cashier || "-")}
                </td>

                <td>
                    ${money(inv.total_amount)}
                </td>

                <td>
                    ${money(inv.amount_paid)}
                </td>

                <td>
                    ${money(inv.balance)}
                </td>

                <td>
                    <span class="status ${statusClass}">
                        ${escapeHtml(status)}
                    </span>
                </td>

                <td>
                    <button
                        class="view-btn"
                        onclick="viewInvoice(${Number(inv.id)})"
                    >
                        View
                    </button>
                </td>
            </tr>
        `;
    }).join("");
}

function filterInvoices() {
    const search = document
        .getElementById("searchInput")
        .value
        .toLowerCase()
        .trim();

    const filtered = invoices.filter(inv => {

        const text = [
            inv.invoice_number,
            inv.customer_name,
            inv.customer_phone,
            inv.cashier,
            inv.payment_status
        ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

        return text.includes(search);
    });

    renderInvoices(filtered);
}

function viewInvoice(id) {
    window.location.href = "/invoice/" + id;
}

function money(value) {
    return Number(value || 0).toLocaleString(
        undefined,
        {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }
    );
}

function formatDate(value) {
    if (!value) return "-";

    const date = new Date(value);

    if (isNaN(date.getTime())) {
        return escapeHtml(String(value));
    }

    return date.toLocaleString();
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

loadInvoices();
</script>

</body>
</html>
"""

CASH_HTML = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cash</title><style>{{ css }}</style></head><body><div class="nav"><div class="brand"> Cash Management</div><a class="btn" href="/dashboard"> Dashboard</a></div><div class="container"><div class="cards"><div class="card"><div class="title">CURRENT CASH</div><div id="balance" class="num">0</div></div></div><div class="box" style="max-width:700px;margin-top:25px"><h2>Cash Transaction</h2><select id="type" class="input"><option value="CASH IN">CASH IN</option><option value="CASH OUT">CASH OUT</option></select><label>Amount</label><input id="amount" class="input" type="number" min="0.01" step="0.01"><label>Description</label><input id="description" class="input" placeholder="Reason / description"><button class="btn green" onclick="save()">SAVE TRANSACTION</button></div></div><script>async function load(){const r=await fetch('/api/cash');const d=await r.json();balance.textContent=Number(d.balance||0).toLocaleString()}async function save(){const r=await fetch('/api/cash',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({transaction_type:type.value,amount:Number(amount.value),description:description.value})});const d=await r.json();alert(d.message);if(d.success){amount.value='';description.value='';load()}}load()</script></body></html>
"""

HISTORY_HTML = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>History</title><style>{{ css }}</style></head><body><div class="nav"><div class="brand"> Transaction History</div><a class="btn" href="/dashboard"> Dashboard</a></div><div class="container"><input id="search" class="input search" placeholder=" Search history..." oninput="filterRows()"><div class="table-wrap"><table><thead><tr><th>ID</th><th>Type</th><th>Product</th><th>Qty</th><th>Amount</th><th>Cost</th><th>Profit</th><th>Stock Before</th><th>Stock After</th><th>Cash Before</th><th>Cash After</th><th>User</th><th>Description</th><th>Date</th></tr></thead><tbody id="rows"></tbody></table></div></div><script>let items=[];async function load(){const r=await fetch('/api/transactions');const d=await r.json();if(!d.success)return alert(d.message);items=d.transactions;render(items)}function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function render(a){rows.innerHTML=a.map(t=>`<tr><td>${t.id}</td><td class="${String(t.transaction_type).includes('IN')?'profit':'loss'}">${esc(t.transaction_type)}</td><td>${esc(t.product_name||'-')}</td><td>${t.quantity??'-'}</td><td>${Number(t.amount||0).toLocaleString()}</td><td>${Number(t.cost_amount||0).toLocaleString()}</td><td class="profit">${Number(t.profit||0).toLocaleString()}</td><td>${t.stock_before??'-'}</td><td>${t.stock_after??'-'}</td><td>${Number(t.cash_before||0).toLocaleString()}</td><td>${Number(t.cash_after||0).toLocaleString()}</td><td>${esc(t.username||'-')}</td><td>${esc(t.description||'-')}</td><td>${t.created_at}</td></tr>`).join('')}function filterRows(){const q=search.value.toLowerCase();render(items.filter(t=>(String(t.transaction_type)+' '+String(t.product_name)+' '+String(t.username)+' '+String(t.description)).toLowerCase().includes(q)))}load()</script></body></html>
"""

ADMIN_HTML = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Admin Dashboard</title><style>{{ css }}</style></head><body><div class="nav"><div class="brand"> Admin Dashboard</div><div>ADMIN ONLY  {{ username }} <a class="btn red" href="/logout">LOGOUT</a></div></div><div class="container"><div class="warning"><b> PRIVATE ADMIN AREA</b><br><br>Only the administrator can access this dashboard. Normal users and their activities are monitored here.</div><div class="cards"><div class="card"><div class="title">USERS</div><div id="usersCount" class="num">0</div></div><div class="card"><div class="title">PRODUCTS</div><div id="productsCount" class="num">0</div></div><div class="card"><div class="title">STOCK</div><div id="stockCount" class="num">0</div></div><div class="card"><div class="title">USERS CASH</div><div id="cash" class="num">0</div></div><div class="card"><div class="title">SALES</div><div id="sales" class="num">0</div></div><div class="card"><div class="title">PROFIT</div><div id="profit" class="num">0</div></div><div class="card"><div class="title">STOCK IN</div><div id="stockIn" class="num">0</div></div><div class="card"><div class="title">STOCK OUT</div><div id="stockOut" class="num">0</div></div></div><div class="section" style="margin-top:25px"><h2> LIVE ACTIVITY <span style="font-size:12px;color:#16a34a"> LIVE</span></h2><div id="liveActivity" style="max-height:420px;overflow-y:auto"></div></div><script>let lastLiveId=0;async function loadLiveActivity(){try{const r=await fetch('/api/admin-dashboard');const d=await r.json();if(!d.success)return;const box=document.getElementById('liveActivity');if(!box)return;const acts=(d.activities||[]).slice(0,30);if(acts.length===0){box.innerHTML='<div style="padding:20px;color:#777">No activity yet.</div>';return;}box.innerHTML=acts.map(a=>{const type=(a.transaction_type||'ACTIVITY').toUpperCase();let icon='';if(type==='STOCK OUT')icon='';else if(type==='STOCK IN')icon='';else if(type.includes('CASH'))icon='';return `<div style="padding:14px;border-bottom:1px solid #eee;display:flex;gap:12px;align-items:flex-start"><div style="font-size:24px">${icon}</div><div style="flex:1"><b>${a.username||'User'}</b> <span style="color:#555">performed</span> <b>${type}</b><br><span style="color:#555">${a.product_name||a.description||'Transaction'}</span>${a.quantity!=null?`  Qty: <b>${a.quantity}</b>`:''}${a.amount?`  Amount: <b>${Number(a.amount).toLocaleString()} Frw</b>`:''}${a.profit?`  Profit: <b>${Number(a.profit).toLocaleString()} Frw</b>`:''}<br><small style="color:#888">${a.created_at||''}</small></div></div>`}).join('');if(acts[0]&&acts[0].id>lastLiveId){lastLiveId=acts[0].id;}}catch(e){console.error('Live activity error:',e);}}loadLiveActivity();setInterval(loadLiveActivity,2000);</script><div class="section" style="margin-top:25px"><h2> Registered Users</h2><div class="table-wrap"><table><thead><tr><th>ID</th><th>Username</th><th>Role</th><th>Created</th><th>Status</th><th>Action</th></tr></thead><tbody id="userRows"></tbody></table></div></div><div class="section" style="margin-top:25px"><h2> User Activity</h2><div class="table-wrap"><table><thead><tr><th>ID</th><th>User</th><th>Action</th><th>Product</th><th>Qty</th><th>Amount</th><th>Profit</th><th>Description</th><th>Date</th></tr></thead><tbody id="activity"></tbody></table></div></div></div><script>async function toggleUser(id,activate){const action=activate?'activate':'deactivate';if(!confirm('Are you sure you want to '+action+' this account?'))return;try{const r=await fetch('/api/admin/users/'+id+'/'+action,{method:'POST'});const d=await r.json();alert(d.message||'Request completed.');if(d.success)load()}catch(e){console.error(e);alert('Request failed: '+e.message)}}async function load(){const r=await fetch('/api/admin-dashboard');const d=await r.json();if(!d.success)return alert(d.message);usersCount.textContent=d.total_users;productsCount.textContent=d.total_products;stockCount.textContent=d.total_stock;cash.textContent=Number(d.total_cash).toLocaleString();sales.textContent=Number(d.total_sales).toLocaleString();profit.textContent=Number(d.total_profit).toLocaleString();stockIn.textContent=d.stock_in;stockOut.textContent=d.stock_out;userRows.innerHTML=d.users.map(u=>{const secs=Number(u.last_seen_seconds);const diff=Number.isFinite(secs)?Math.max(0,secs*1000):999999999;const mins=Math.floor(diff/60000);const online=diff<120000;const status=online?" Online":mins<60?" Last seen "+mins+" minute"+(mins===1?"":"s")+" ago":" Last seen "+Math.floor(mins/60)+" hour"+(Math.floor(mins/60)===1?"":"s")+" ago";const active=Boolean(u.is_active);const action=active?`<button class="btn red" onclick="toggleUser(${u.id},false)">DEACTIVATE</button>`:`<button class="btn green" onclick="toggleUser(${u.id},true)">ACTIVATE</button>`;return `<tr><td>${u.id}</td><td><b>${u.username}</b></td><td>${u.role}</td><td>${u.created_at}</td><td>${status}<br><small>${active?"ACTIVE":"INACTIVE"}</small></td><td>${action}</td></tr>`}).join("");activity.innerHTML=d.activities.map(a=>`<tr><td>${a.id}</td><td><b>${a.username}</b></td><td>${a.transaction_type}</td><td>${a.product_name||'-'}</td><td>${a.quantity??'-'}</td><td>${Number(a.amount||0).toLocaleString()}</td><td>${Number(a.profit||0).toLocaleString()}</td><td>${a.description||'-'}</td><td>${a.created_at}</td></tr>`).join('')}load();setInterval(load,5000);setInterval(()=>fetch("/api/heartbeat",{method:"POST"}),30000);fetch("/api/heartbeat",{method:"POST"})</script></body></html>
"""

def money(value):
    return Decimal(str(value or 0)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )
def logged_in():
    return bool(session.get("user_id"))


def current_user_id():
    return session.get("user_id")


def current_username():
    return session.get("username", "")


def is_admin():
    return session.get("role") == "admin"


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not logged_in():
            return jsonify(
                success=False,
                message="Login required."
            ), 401
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not logged_in():
            return jsonify(
                success=False,
                message="Login required."
            ), 401

        if not is_admin():
            return jsonify(
                success=False,
                message="Admin access required."
            ), 403

        return view(*args, **kwargs)
    return wrapped

def ensure_cash_account(conn, user_id):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO cash_account(balance, owner_id)
            VALUES(0,%s)
            ON CONFLICT(owner_id) DO NOTHING
        """, (user_id,))
        cur.execute("""
            SELECT id,balance,owner_id
            FROM cash_account
            WHERE owner_id=%s
        """, (user_id,))
        row = cur.fetchone()
    return row
def create_default_admin(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE username=%s", ("admin",))
        row = cur.fetchone()
        if row:
            admin_id = row["id"]
            cur.execute("UPDATE users SET role='admin' WHERE id=%s", (admin_id,))
        else:
            cur.execute("""
                INSERT INTO users(username,password,role)
                VALUES(%s,%s,'admin') RETURNING id
            """, ("admin", generate_password_hash("admin123")))
            admin_id = cur.fetchone()["id"]
        ensure_default_accounts(conn, admin_id)
        cur.execute("""
            INSERT INTO cash_account(balance,owner_id)
            VALUES(0,%s)
            ON CONFLICT(owner_id) DO NOTHING
        """, (admin_id,))
    conn.commit()



@app.route("/")
def home():
    if logged_in():
        return redirect("/admin-dashboard" if is_admin() else "/dashboard")
    return render_template_string(AUTH_HTML, css=BASE_CSS)

@app.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if len(username) < 3:
        return jsonify(success=False, message="Username must contain at least 3 characters."), 400
    if len(password) < 4:
        return jsonify(success=False, message="Password must contain at least 4 characters."), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO users(username,password,role) VALUES(%s,%s,'user') RETURNING id", (username, generate_password_hash(password)))
            user_id = cur.fetchone()["id"]
            ensure_default_accounts(conn, user_id)
            cur.execute("INSERT INTO cash_account(balance,owner_id) VALUES(0,%s)", (user_id,))
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        conn.close()
        return jsonify(success=False, message="Username already exists."), 409
    finally:
        if not conn.closed:
            conn.close()
    return jsonify(success=True, message="Account created successfully!")

@app.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,username,password,role,is_active FROM users WHERE username=%s", (username,))
            user = cur.fetchone()
    finally:
        conn.close()
    if not user or not check_password_hash(user["password"], password):
        return jsonify(success=False, message="Invalid username or password."), 401
    if not user["is_active"]:
        return jsonify(success=False, message="Your account has been deactivated by the administrator."), 403
    session.clear()
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET last_seen=CURRENT_TIMESTAMP WHERE id=%s",(user["id"],))
        conn.commit()
    finally:
        conn.close()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    return jsonify(success=True, message="Login successful!", redirect="/admin-dashboard" if user["role"] == "admin" else "/dashboard")

@app.post("/change-password")
@login_required
def change_password():
    data = request.get_json(silent=True) or {}
    current_password = str(data.get("current_password", ""))
    new_password = str(data.get("new_password", ""))
    confirm_password = str(data.get("confirm_password", ""))
    if not current_password or not new_password or not confirm_password:
        return jsonify(success=False, message="All password fields are required."), 400
    if len(new_password) < 4:
        return jsonify(success=False, message="New password must contain at least 4 characters."), 400
    if new_password != confirm_password:
        return jsonify(success=False, message="New passwords do not match."), 400
    if current_password == new_password:
        return jsonify(success=False, message="New password must be different from current password."), 400
    uid = session.get("user_id")
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT password FROM users WHERE id=%s", (uid,))
            user = cur.fetchone()
            if not user or not check_password_hash(user["password"], current_password):
                return jsonify(success=False, message="Current password is incorrect."), 401
            cur.execute("UPDATE users SET password=%s WHERE id=%s", (generate_password_hash(new_password), uid))
        conn.commit()
        return jsonify(success=True, message="Password changed successfully.")
    except Exception as e:
        conn.rollback()
        print("CHANGE PASSWORD ERROR:", e)
        return jsonify(success=False, message="Password change failed. No changes were saved."), 500
    finally:
        conn.close()

@app.get("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.get("/dashboard")
@login_required
def dashboard():
    if is_admin():
        return redirect("/admin-dashboard")
    return render_template_string(DASHBOARD_HTML, css=BASE_CSS, username=current_username())

@app.get("/dashboard-data")
@login_required
def dashboard_data():
    user_id = current_user_id()
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM products WHERE owner_id=%s", (user_id,)); total_products=cur.fetchone()["n"]
            cur.execute("SELECT COALESCE(SUM(quantity),0) AS n FROM products WHERE owner_id=%s", (user_id,)); total_stock=cur.fetchone()["n"]
            cur.execute("SELECT COALESCE(SUM(quantity*purchase_price),0) AS n FROM products WHERE owner_id=%s", (user_id,)); stock_value=cur.fetchone()["n"]
            cur.execute("SELECT COALESCE(SUM(quantity*(selling_price-purchase_price)),0) AS n FROM products WHERE owner_id=%s", (user_id,)); potential=cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM products WHERE owner_id=%s AND quantity<=5", (user_id,)); low=cur.fetchone()["n"]
            cur.execute("SELECT COALESCE(balance,0) AS n FROM cash_account WHERE owner_id=%s", (user_id,)); cash=cur.fetchone()["n"]
            cur.execute("SELECT COALESCE(SUM(amount),0) AS n FROM transactions WHERE owner_id=%s AND transaction_type='STOCK OUT'", (user_id,)); sales=cur.fetchone()["n"]
            cur.execute("SELECT COALESCE(SUM(profit),0) AS n FROM transactions WHERE owner_id=%s AND transaction_type='STOCK OUT'", (user_id,)); profit=cur.fetchone()["n"]
    finally: conn.close()
    return jsonify(success=True,total_products=total_products,total_stock=total_stock,stock_value=float(stock_value),potential_profit=float(potential),low_stock=low,cash_balance=float(cash),total_sales=float(sales),total_profit=float(profit))

@app.get("/invoice")
@login_required
def invoice_page():
    if is_admin():
        return redirect("/admin-dashboard")
    return render_template_string(INVOICE_HTML, css=BASE_CSS)
INVOICE_DETAILS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Invoice Details</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f4f6f8;
            margin: 0;
            padding: 20px;
        }

        .container {
            max-width: 1000px;
            margin: auto;
        }

        .invoice-box {
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        }

        .top {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 20px;
            margin-bottom: 25px;
        }

        h1 {
            margin: 0 0 8px;
        }

        .muted {
            color: #666;
        }

        .customer {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }

        .summary {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
            margin: 20px 0;
        }

        .card {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
        }

        .card strong {
            display: block;
            font-size: 20px;
            margin-top: 5px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }

        th, td {
            padding: 12px;
            border-bottom: 1px solid #ddd;
            text-align: left;
        }

        th {
            background: #f1f3f5;
        }

        .right {
            text-align: right;
        }

        .status {
            display: inline-block;
            padding: 7px 12px;
            border-radius: 20px;
            font-weight: bold;
        }

        .paid {
            background: #d4edda;
            color: #155724;
        }

        .partial {
            background: #fff3cd;
            color: #856404;
        }

        .unpaid {
            background: #f8d7da;
            color: #721c24;
        }

        .actions {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }

        button, a.button {
            border: none;
            padding: 10px 16px;
            border-radius: 7px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
            font-size: 14px;
        }

        .print {
            background: #222;
            color: white;
        }

        .back {
            background: #ddd;
            color: #222;
        }

        .loading {
            text-align: center;
            padding: 40px;
        }

        @media (max-width: 700px) {
            body {
                padding: 10px;
            }

            .invoice-box {
                padding: 15px;
            }

            .top {
                flex-direction: column;
            }

            .summary {
                grid-template-columns: repeat(2, 1fr);
            }

            table {
                font-size: 13px;
            }

            th, td {
                padding: 8px;
            }
        }

        @media print {
            .actions {
                display: none;
            }

            body {
                background: white;
                padding: 0;
            }

            .invoice-box {
                box-shadow: none;
            }
        }
    </style>
</head>

<body>

<div class="container">

    <div class="actions">
        <a class="button back" href="/invoice-history">? Invoice History</a>
        <button class="print" onclick="window.print()">Print Invoice</button>
<button class="download" onclick="downloadInvoicePDF()">Download Invoice PDF</button>
    </div>

    <div id="content" class="invoice-box">
        <div class="loading">Loading invoice...</div>
    </div>

</div>

<script>
const invoiceId = {{ invoice_id }};

function money(value) {
    return Number(value || 0).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function formatDate(value) {
    if (!value) return "";
    return new Date(value).toLocaleString();
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function statusClass(status) {
    if (status === "PAID") return "paid";
    if (status === "PARTIALLY PAID") return "partial";
    return "unpaid";
}

function downloadInvoicePDF() {
    window.location.href = `/api/invoices/${invoiceId}/pdf`;
}

async function loadInvoice() {
    try {
        const response = await fetch("/api/invoices/" + invoiceId);
        const data = await response.json();

        if (!data.success) {
            throw new Error(data.message || "Failed to load invoice.");
        }

        const invoice = data.invoice;

        let itemsHtml = "";

        invoice.items.forEach(item => {
            itemsHtml += `
                <tr>
                    <td>${escapeHtml(item.product_name)}</td>
                    <td>${item.quantity}</td>
                    <td class="right">${money(item.unit_price)}</td>
                    <td class="right">${money(item.line_total)}</td>
                    <td class="right">${money(item.line_profit)}</td>
                </tr>
            `;
        });

        let paymentsHtml = "";

        if (invoice.payments.length === 0) {
            paymentsHtml = `
                <tr>
                    <td colspan="5" class="muted">No payments recorded.</td>
                </tr>
            `;
        } else {
            invoice.payments.forEach(payment => {
                paymentsHtml += `
                    <tr>
                        <td>${formatDate(payment.created_at)}</td>
                        <td>${escapeHtml(payment.payment_method)}</td>
                        <td>${escapeHtml(payment.reference)}</td>
                        <td>${escapeHtml(payment.username)}</td>
                        <td class="right">${money(payment.amount)}</td>
                    </tr>
                `;
            });
        }

        document.getElementById("content").innerHTML = `
            <div class="top">
                <div>
                    <h1>INVOICE</h1>
                    <div class="muted">${escapeHtml(invoice.invoice_number)}</div>
                </div>

                <div style="text-align:right;">
                    <div>${formatDate(invoice.created_at)}</div>
                    <div style="margin-top:8px;">
                        <span class="status ${statusClass(invoice.payment_status)}">
                            ${escapeHtml(invoice.payment_status)}
                        </span>
                    </div>
                </div>
            </div>

            <div class="customer">
                <strong>Customer</strong>
                <div>${escapeHtml(invoice.customer_name)}</div>
                ${invoice.customer_phone
                    ? `<div>${escapeHtml(invoice.customer_phone)}</div>`
                    : ""}
                ${invoice.customer_address
                    ? `<div>${escapeHtml(invoice.customer_address)}</div>`
                    : ""}
                <div style="margin-top:8px;">
                    Cashier: <strong>${escapeHtml(invoice.cashier)}</strong>
                </div>
            </div>

            <h3>Items</h3>

            <table>
                <thead>
                    <tr>
                        <th>Product</th>
                        <th>Qty</th>
                        <th class="right">Unit Price</th>
                        <th class="right">Total</th>
                        <th class="right">Profit</th>
                    </tr>
                </thead>
                <tbody>
                    ${itemsHtml}
                </tbody>
            </table>

            <div class="summary">
                <div class="card">
                    Subtotal
                    <strong>${money(invoice.subtotal)}</strong>
                </div>

                <div class="card">
                    Discount
                    <strong>${money(invoice.discount)}</strong>
                </div>

                <div class="card">
                    Tax
                    <strong>${money(invoice.tax)}</strong>
                </div>

                <div class="card">
                    Total
                    <strong>${money(invoice.total_amount)}</strong>
                </div>
            </div>

            <div class="summary">
                <div class="card">
                    Amount Paid
                    <strong>${money(invoice.amount_paid)}</strong>
                </div>

                <div class="card">
                    Balance
                    <strong>${money(invoice.balance)}</strong>
                </div>
            </div>

            <h3>Payment History</h3>

            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Method</th>
                        <th>Reference</th>
                        <th>User</th>
                        <th class="right">Amount</th>
                    </tr>
                </thead>
                <tbody>
                    ${paymentsHtml}
                </tbody>
            </table>
        `;

    } catch (error) {
        document.getElementById("content").innerHTML = `
            <div style="color:#b00020;">
                Failed to load invoice: ${escapeHtml(error.message)}
            </div>
        `;
    }
}

loadInvoice();
</script>

</body>
</html>
"""
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

@app.get("/api/invoices/<int:invoice_id>/pdf")
@login_required
def download_invoice_pdf(invoice_id):
    uid = current_user_id()
    conn = get_db()

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    invoice_number,
                    created_at,
                    customer_name,
                    customer_phone,
                    customer_address,
                    subtotal,
                    discount,
                    tax,
                    total_amount,
                    amount_paid,
                    balance,
                    payment_status,
                    cashier
                FROM invoices
                WHERE id=%s AND owner_id=%s
            """, (invoice_id, uid))

            invoice = cur.fetchone()

            if not invoice:
                return jsonify(success=False, message="Invoice not found."), 404

            cur.execute("""
                SELECT
                    product_name,
                    quantity,
                    unit_price,
                    line_total,
                    line_profit
                FROM invoice_items
                WHERE invoice_id=%s
                ORDER BY id
            """, (invoice_id,))

            items = cur.fetchall()

        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()

        title_style = styles["Title"]
        right_style = ParagraphStyle(
            "Right",
            parent=styles["Normal"],
            alignment=TA_RIGHT
        )

        story = []

        story.append(Paragraph("INVOICE", title_style))
        story.append(Spacer(1, 10))

        story.append(Paragraph(
            f"<b>Invoice No:</b> {invoice['invoice_number']}",
            styles["Normal"]
        ))

        created = invoice["created_at"].strftime("%Y-%m-%d %H:%M") if invoice["created_at"] else ""

        story.append(Paragraph(
            f"<b>Date:</b> {created}",
            styles["Normal"]
        ))

        story.append(Paragraph(
            f"<b>Status:</b> {invoice['payment_status']}",
            styles["Normal"]
        ))

        story.append(Spacer(1, 12))

        customer_data = [
            ["Customer", invoice["customer_name"] or ""],
            ["Phone", invoice["customer_phone"] or ""],
            ["Address", invoice["customer_address"] or ""],
            ["Cashier", invoice["cashier"] or ""]
        ]

        customer_table = Table(customer_data, colWidths=[100, 390])

        customer_table.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
            ("BACKGROUND", (0,0), (0,-1), colors.lightgrey),
            ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("PADDING", (0,0), (-1,-1), 6)
        ]))

        story.append(customer_table)
        story.append(Spacer(1, 18))

        item_data = [
            ["Product", "Qty", "Unit Price", "Total", "Profit"]
        ]

        for item in items:
            item_data.append([
                str(item["product_name"]),
                str(item["quantity"]),
                f"{float(item['unit_price'] or 0):,.2f}",
                f"{float(item['line_total'] or 0):,.2f}",
                f"{float(item['line_profit'] or 0):,.2f}"
            ])

        item_table = Table(
            item_data,
            colWidths=[190, 45, 90, 90, 90],
            repeatRows=1
        )

        item_table.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("ALIGN", (1,1), (-1,-1), "RIGHT"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("PADDING", (0,0), (-1,-1), 6)
        ]))

        story.append(item_table)
        story.append(Spacer(1, 18))

        summary_data = [
            ["Subtotal", f"{float(invoice['subtotal'] or 0):,.2f} Frw"],
            ["Discount", f"{float(invoice['discount'] or 0):,.2f} Frw"],
            ["Tax", f"{float(invoice['tax'] or 0):,.2f} Frw"],
            ["TOTAL", f"{float(invoice['total_amount'] or 0):,.2f} Frw"],
            ["Amount Paid", f"{float(invoice['amount_paid'] or 0):,.2f} Frw"],
            ["Balance", f"{float(invoice['balance'] or 0):,.2f} Frw"]
        ]

        summary_table = Table(
            summary_data,
            colWidths=[150, 150],
            hAlign="RIGHT"
        )

        summary_table.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
            ("ALIGN", (1,0), (1,-1), "RIGHT"),
            ("FONTNAME", (0,3), (-1,3), "Helvetica-Bold"),
            ("FONTNAME", (0,5), (-1,5), "Helvetica-Bold"),
            ("PADDING", (0,0), (-1,-1), 6)
        ]))

        story.append(summary_table)
        story.append(Spacer(1, 20))

        story.append(Paragraph(
            "Thank you for your business.",
            styles["Normal"]
        ))

        doc.build(story)

        buffer.seek(0)

        from flask import send_file

        filename = f"Invoice_{invoice['invoice_number']}.pdf"

        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype="application/pdf"
        )

    except Exception as e:
        print("INVOICE PDF ERROR:", e)
        return jsonify(
            success=False,
            message="Failed to generate invoice PDF."
        ), 500

    finally:
        conn.close()

@app.get("/invoice/<int:invoice_id>")
@login_required
def invoice_details_page(invoice_id):
    if is_admin():
        return redirect("/admin-dashboard")
    return render_template_string(INVOICE_DETAILS_HTML, css=BASE_CSS, invoice_id=invoice_id)
@app.get("/invoice-history")
@login_required
def invoice_history_page():
    if is_admin():
        return redirect("/admin-dashboard")
    return render_template_string(INVOICE_HISTORY_HTML, css=BASE_CSS)
@app.get("/products")
@login_required
def products_page():
    if is_admin(): return redirect("/admin-dashboard")
    return render_template_string(PRODUCTS_HTML, css=BASE_CSS)

@app.get("/api/products")
@login_required
def get_products():
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,name,quantity,purchase_price,unit_cost,selling_price,created_at FROM products WHERE owner_id=%s ORDER BY id DESC", (current_user_id(),))
            rows=cur.fetchall()
    finally: conn.close()
    return jsonify(success=True, products=[dict(r) for r in rows])

@app.post("/api/products")
@login_required
def add_product():
    data=request.get_json(silent=True) or {}
    name=str(data.get("name","")).strip()
    try: quantity=int(data.get("quantity",0)); purchase=float(data.get("purchase_price",0)); unit_cost=float(data.get("unit_cost",purchase)); selling=float(data.get("selling_price",0))
    except (ValueError,TypeError): return jsonify(success=False,message="Invalid numbers."),400
    if not name: return jsonify(success=False,message="Product name is required."),400
    if quantity<0 or purchase<0 or unit_cost<0 or selling<0: return jsonify(success=False,message="Values cannot be negative."),400
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO products(name,quantity,purchase_price,unit_cost,selling_price,owner_id) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",(name,quantity,purchase,unit_cost,selling,current_user_id()))
            pid=cur.fetchone()["id"]
            if quantity>0:
                cur.execute("""INSERT INTO history(product_id,product_name,action,quantity,previous_quantity,new_quantity,username,owner_id) VALUES(%s,%s,'INITIAL STOCK',%s,0,%s,%s,%s)""",(pid,name,quantity,quantity,current_username(),current_user_id()))
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback(); return jsonify(success=False,message="You already have a product with this name."),409
    except Exception as e:
        conn.rollback(); print("ADD PRODUCT ERROR:",e); return jsonify(success=False,message="Product could not be added."),500
    finally: conn.close()
    return jsonify(success=True,message=f"{name} added successfully!")

@app.put("/api/products/<int:product_id>")
@login_required
def edit_product(product_id):
    data=request.get_json(silent=True) or {}; name=str(data.get("name","")).strip()
    try: purchase=float(data.get("purchase_price")); unit_cost=float(data.get("unit_cost",purchase)); selling=float(data.get("selling_price"))
    except (ValueError,TypeError): return jsonify(success=False,message="Invalid price."),400
    if not name or purchase<0 or unit_cost<0 or selling<0: return jsonify(success=False,message="Enter valid product details."),400
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE products SET name=%s,purchase_price=%s,unit_cost=%s,selling_price=%s WHERE id=%s AND owner_id=%s",(name,purchase,unit_cost,selling,product_id,current_user_id()))
            if cur.rowcount==0: return jsonify(success=False,message="Product not found."),404
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback(); return jsonify(success=False,message="Another product already has that name."),409
    finally: conn.close()
    return jsonify(success=True,message="Product updated successfully!")

@app.put("/api/products/<int:product_id>/stock")
@login_required
def edit_stock(product_id):
    data=request.get_json(silent=True) or {}; reason=str(data.get("reason","Stock correction")).strip()
    try: new_quantity=int(data.get("quantity"))
    except (ValueError,TypeError): return jsonify(success=False,message="Invalid quantity."),400
    if new_quantity<0:return jsonify(success=False,message="Quantity cannot be negative."),400
    uid=current_user_id(); conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM products WHERE id=%s AND owner_id=%s FOR UPDATE",(product_id,uid)); p=cur.fetchone()
            if not p:return jsonify(success=False,message="Product not found."),404
            old=int(p["quantity"]); diff=new_quantity-old
            if diff==0:return jsonify(success=True,message="No stock change was necessary.")
            account=ensure_cash_account(conn,uid); before=float(account["balance"]); value=abs(diff)*float(p["purchase_price"])
            if diff>0:
                if value>before:return jsonify(success=False,message=f"Not enough cash. Cost: {value:,.2f} Frw. Available: {before:,.2f} Frw."),400
                after=before-value; typ="STOCK EDIT IN"; cost=value
            else:
                after=before+value; typ="STOCK EDIT OUT"; cost=-value
            cur.execute("UPDATE products SET quantity=%s WHERE id=%s AND owner_id=%s",(new_quantity,product_id,uid))
            cur.execute("UPDATE cash_account SET balance=%s WHERE owner_id=%s",(after,uid))
            cur.execute("""INSERT INTO transactions(transaction_type,product_id,product_name,quantity,purchase_price,selling_price,amount,cost_amount,profit,cash_before,cash_after,stock_before,stock_after,username,description,owner_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s)""",(typ,product_id,p["name"],abs(diff),p["purchase_price"],p["selling_price"],value,cost,before,after,old,new_quantity,current_username(),reason,uid))
            cur.execute("""INSERT INTO history(product_id,product_name,action,quantity,previous_quantity,new_quantity,username,owner_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",(product_id,p["name"],typ,abs(diff),old,new_quantity,current_username(),uid))
        conn.commit()
    except Exception as e:
        conn.rollback(); print("EDIT STOCK ERROR:",e); return jsonify(success=False,message="Stock correction failed. No changes were saved."),500
    finally: conn.close()
    return jsonify(success=True,message=f"Stock updated. Old: {old}, New: {new_quantity}, Cash: {after:,.2f} Frw")

@app.delete("/api/products/<int:product_id>")
@login_required
def delete_product(product_id):
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT quantity FROM products WHERE id=%s AND owner_id=%s",(product_id,current_user_id())); p=cur.fetchone()
            if not p:return jsonify(success=False,message="Product not found."),404
            if p["quantity"]>0:return jsonify(success=False,message="You cannot delete a product while stock is still available."),400
            cur.execute("DELETE FROM products WHERE id=%s AND owner_id=%s",(product_id,current_user_id()))
        conn.commit()
    finally: conn.close()
    return jsonify(success=True,message="Product deleted successfully!")

@app.get("/stock-in")
@login_required
def stock_in_page():
    if is_admin():return redirect("/admin-dashboard")
    return render_template_string(MOVEMENT_HTML,css=BASE_CSS,title="Stock In",icon="",button="ADD STOCK",color="green",endpoint="/api/stock-in")

@app.post("/api/stock-in")
@login_required
def stock_in():
    data = request.get_json(silent=True) or {}

    try:
        pid = int(data.get("product_id"))
        qty = int(data.get("quantity"))
    except (ValueError, TypeError):
        return jsonify(success=False, message="Invalid product or quantity."), 400

    if qty <= 0:
        return jsonify(success=False, message="Quantity must be greater than zero."), 400

    uid = current_user_id()
    username = current_username()
    conn = get_db()

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM products WHERE id=%s AND owner_id=%s FOR UPDATE",
                (pid, uid)
            )
            p = cur.fetchone()

            if not p:
                return jsonify(success=False, message="Product not found."), 404

            cost = qty * float(p["unit_cost"])

            account = ensure_cash_account(conn, uid)
            before = float(account["balance"])

            if cost > before:
                return jsonify(
                    success=False,
                    message=(
                        f"Not enough cash. Cost: {cost:,.2f} Frw. "
                        f"Available: {before:,.2f} Frw. "
                        f"Use Cash In first."
                    )
                ), 400

            old = int(p["quantity"])
            new = old + qty
            after = before - cost

            # 1. Increase stock
            cur.execute(
                "UPDATE products SET quantity=%s WHERE id=%s AND owner_id=%s",
                (new, pid, uid)
            )

            # 2. Reduce cash
            cur.execute(
                "UPDATE cash_account SET balance=%s WHERE owner_id=%s",
                (after, uid)
            )

            # 3. Existing transaction record
            cur.execute("""
                INSERT INTO transactions(
                    transaction_type,
                    product_id,
                    product_name,
                    quantity,
                    purchase_price,
                    selling_price,
                    amount,
                    cost_amount,
                    profit,
                    cash_before,
                    cash_after,
                    stock_before,
                    stock_after,
                    username,
                    description,
                    owner_id
                )
                VALUES(
                    'STOCK IN',
                    %s,%s,%s,%s,%s,%s,%s,0,
                    %s,%s,%s,%s,%s,%s,%s
                )
            """, (
                pid,
                p["name"],
                qty,
                p["purchase_price"],
                p["selling_price"],
                cost,
                cost,
                before,
                after,
                old,
                new,
                username,
                f"Purchased at {float(p['purchase_price']):,.2f} Frw/unit.",
                uid
            ))

            # 4. Existing history record
            cur.execute("""
                INSERT INTO history(
                    product_id,
                    product_name,
                    action,
                    quantity,
                    previous_quantity,
                    new_quantity,
                    username,
                    owner_id
                )
                VALUES(%s,%s,'STOCK IN',%s,%s,%s,%s,%s)
            """, (
                pid,
                p["name"],
                qty,
                old,
                new,
                username,
                uid
            ))

            # 5. DOUBLE-ENTRY ACCOUNTING
            #
            # Stock purchase:
            # Dr Inventory
            # Cr Cash
            create_journal_entry(
                conn,
                uid,
                "STOCK_IN",
                pid,
                f"Inventory purchase: {qty} x {p['name']}",
                [
                    {
                        "account_code": "1200",
                        "debit": cost,
                        "credit": 0,
                        "description": "Inventory purchased"
                    },
                    {
                        "account_code": "1000",
                        "debit": 0,
                        "credit": cost,
                        "description": "Cash paid for inventory"
                    }
                ],
                username
            )

        conn.commit()

    except Exception as e:
        conn.rollback()
        print("STOCK IN ACCOUNTING ERROR:", e)
        return jsonify(
            success=False,
            message="Stock In failed. No changes were saved."
        ), 500

    finally:
        conn.close()

    return jsonify(
        success=True,
        message=(
            f"STOCK IN SUCCESSFUL! "
            f"Added {qty}. "
            f"Cost {cost:,.2f} Frw. "
            f"New stock {new}. "
            f"Cash {after:,.2f} Frw."
        )
    )

@app.get("/stock-out")
@login_required
def stock_out_page():
    if is_admin():return redirect("/admin-dashboard")
    return render_template_string(MOVEMENT_HTML,css=BASE_CSS,title="Stock Out / Sale",icon="",button="SELL / REMOVE STOCK",color="red",endpoint="/api/stock-out")

@app.post("/api/stock-out")
@login_required
def stock_out():
    data = request.get_json(silent=True) or {}

    try:
        pid = int(data.get("product_id"))
        qty = int(data.get("quantity"))
    except (ValueError, TypeError):
        return jsonify(success=False, message="Invalid product or quantity."), 400

    if qty <= 0:
        return jsonify(success=False, message="Quantity must be greater than zero."), 400

    uid = current_user_id()
    username = current_username()
    conn = get_db()

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM products WHERE id=%s AND owner_id=%s FOR UPDATE",
                (pid, uid)
            )
            p = cur.fetchone()

            if not p:
                return jsonify(success=False, message="Product not found."), 404

            old = int(p["quantity"])

            if qty > old:
                return jsonify(
                    success=False,
                    message=f"Not enough stock. Available: {old}."
                ), 400

            pp = float(p["unit_cost"])
            sp = float(p["selling_price"])

            sales = qty * sp
            cost = qty * pp
            profit = sales - cost
            new = old - qty

            # Cash account
            account = ensure_cash_account(conn, uid)
            before = float(account["balance"])
            after = before + sales

            # 1. Reduce stock
            cur.execute(
                "UPDATE products SET quantity=%s WHERE id=%s AND owner_id=%s",
                (new, pid, uid)
            )

            # 2. Increase cash
            cur.execute(
                "UPDATE cash_account SET balance=%s WHERE owner_id=%s",
                (after, uid)
            )

            # 3. Existing transaction record
            cur.execute("""
                INSERT INTO transactions(
                    transaction_type,
                    product_id,
                    product_name,
                    quantity,
                    purchase_price,
                    selling_price,
                    amount,
                    cost_amount,
                    profit,
                    cash_before,
                    cash_after,
                    stock_before,
                    stock_after,
                    username,
                    description,
                    owner_id
                )
                VALUES(
                    'STOCK OUT',
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
            """, (
                pid,
                p["name"],
                qty,
                pp,
                sp,
                sales,
                cost,
                profit,
                before,
                after,
                old,
                new,
                username,
                f"Sale. Profit: {profit:,.2f} Frw",
                uid
            ))

            # 4. Existing stock history
            cur.execute("""
                INSERT INTO history(
                    product_id,
                    product_name,
                    action,
                    quantity,
                    previous_quantity,
                    new_quantity,
                    username,
                    owner_id
                )
                VALUES(%s,%s,'STOCK OUT',%s,%s,%s,%s,%s)
            """, (
                pid,
                p["name"],
                qty,
                old,
                new,
                username,
                uid
            ))

            # 5. DOUBLE-ENTRY ACCOUNTING
            #
            # Sale:
            # Dr Cash
            # Cr Sales Revenue
            #
            # Cost of stock sold:
            # Dr Cost of Goods Sold
            # Cr Inventory

            create_journal_entry(
                conn,
                uid,
                "STOCK_OUT",
                pid,
                f"Cash sale: {qty} x {p['name']}",
                [
                    {
                        "account_code": "1000",
                        "debit": sales,
                        "credit": 0,
                        "description": "Cash received from sale"
                    },
                    {
                        "account_code": "4000",
                        "debit": 0,
                        "credit": sales,
                        "description": "Sales revenue"
                    }
                ],
                username
            )

            create_journal_entry(
                conn,
                uid,
                "STOCK_OUT_COGS",
                pid,
                f"Cost of goods sold: {qty} x {p['name']}",
                [
                    {
                        "account_code": "5000",
                        "debit": cost,
                        "credit": 0,
                        "description": "Cost of goods sold"
                    },
                    {
                        "account_code": "1200",
                        "debit": 0,
                        "credit": cost,
                        "description": "Inventory reduction"
                    }
                ],
                username
            )

        conn.commit()

    except Exception as e:
        conn.rollback()
        print("STOCK OUT ACCOUNTING ERROR:", e)
        return jsonify(
            success=False,
            message="Sale failed. No changes were saved."
        ), 500

    finally:
        conn.close()

    return jsonify(
        success=True,
        message=(
            f"SALE SUCCESSFUL! "
            f"Sold {qty}. "
            f"Sales {sales:,.2f} Frw. "
            f"Cost {cost:,.2f} Frw. "
            f"Profit {profit:,.2f} Frw. "
            f"Remaining stock {new}. "
            f"Cash {after:,.2f} Frw."
        )
    )

@app.get("/api/invoices")
@login_required
def get_invoices():
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    invoice_number,
                    created_at,
                    customer_name,
                    cashier,
                    total_amount,
                    amount_paid,
                    balance,
                    payment_status
                FROM invoices
                WHERE owner_id=%s
                ORDER BY created_at DESC
            """, (current_user_id(),))
            rows = cur.fetchall()
        conn.close()

        invoices = []
        for row in rows:
            invoices.append({
                "id": row["id"],
                "invoice_number": row["invoice_number"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "customer_name": row["customer_name"],
                "cashier": row["cashier"] or "",
                "total_amount": float(row["total_amount"] or 0),
                "amount_paid": float(row["amount_paid"] or 0),
                "balance": float(row["balance"] or 0),
                "payment_status": row["payment_status"]
            })

        return jsonify(success=True, invoices=invoices)

    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
@app.post("/api/invoices")
@login_required
def create_invoice():
    data = request.get_json(silent=True) or {}
    uid = current_user_id()
    username = current_username()

    customer_name = str(data.get("customer_name", "")).strip()
    customer_phone = str(data.get("customer_phone", "")).strip()
    customer_address = str(data.get("customer_address", "")).strip()

    if not customer_name:
        return jsonify(success=False, message="Customer name is required."), 400

    items = data.get("items", [])
    if not isinstance(items, list) or not items:
        return jsonify(success=False, message="At least one product is required."), 400

    try:
        discount = money(data.get("discount", 0))
        tax = money(data.get("tax", 0))
        amount_paid = money(data.get("amount_paid", 0))
    except ValueError:
        return jsonify(success=False, message="Invalid monetary value."), 400

    if discount < 0 or tax < 0 or amount_paid < 0:
        return jsonify(success=False, message="Amounts cannot be negative."), 400

    payment_method = str(data.get("payment_method", "CASH")).strip().upper()
    if payment_method not in ("CASH", "BANK", "MOBILE MONEY"):
        return jsonify(success=False, message="Invalid payment method."), 400

    conn = get_db()

    try:
        with conn.cursor() as cur:

            # Generate next invoice number for this user
            cur.execute("""
                SELECT invoice_number
                FROM invoices
                WHERE owner_id=%s
                ORDER BY id DESC
                LIMIT 1
                FOR UPDATE
            """, (uid,))

            last_invoice = cur.fetchone()

            if last_invoice:
                try:
                    last_number = int(str(last_invoice["invoice_number"]).replace("INV-", ""))
                except ValueError:
                    last_number = 0
            else:
                last_number = 0

            invoice_number = f"INV-{last_number + 1:04d}"

            # Validate and lock all products first
            prepared_items = []
            subtotal = Decimal("0.00")
            total_cost = Decimal("0.00")

            for item in items:
                try:
                    product_id = int(item.get("product_id"))
                    quantity = int(item.get("quantity"))
                except (ValueError, TypeError):
                    raise ValueError("Invalid product or quantity.")

                if quantity <= 0:
                    raise ValueError("Quantity must be greater than zero.")

                cur.execute("""
                    SELECT id, name, quantity, unit_cost, selling_price
                    FROM products
                    WHERE id=%s AND owner_id=%s
                    FOR UPDATE
                """, (product_id, uid))

                product = cur.fetchone()

                if not product:
                    raise ValueError(f"Product {product_id} was not found.")

                available = int(product["quantity"])

                if quantity > available:
                    raise ValueError(
                        f"Not enough stock for {product['name']}. "
                        f"Available: {available}."
                    )

                unit_price = money(
                    item.get("unit_price", product["selling_price"])
                )
                unit_cost = money(product["unit_cost"])

                if unit_price < 0:
                    raise ValueError("Unit price cannot be negative.")

                line_total = money(unit_price * quantity)
                line_cost = money(unit_cost * quantity)
                line_profit = money(line_total - line_cost)

                subtotal += line_total
                total_cost += line_cost

                prepared_items.append({
                    "product_id": product_id,
                    "name": product["name"],
                    "old_quantity": available,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "unit_cost": unit_cost,
                    "line_total": line_total,
                    "line_cost": line_cost,
                    "line_profit": line_profit
                })

            subtotal = money(subtotal)

            if discount > subtotal:
                raise ValueError("Discount cannot exceed subtotal.")

            total_amount = money(subtotal - discount + tax)

            if amount_paid > total_amount:
                raise ValueError("Payment cannot exceed invoice total.")

            balance = money(total_amount - amount_paid)

            if balance == 0:
                payment_status = "PAID"
            elif amount_paid > 0:
                payment_status = "PARTIALLY PAID"
            else:
                payment_status = "UNPAID"

            # Find customer if supplied
            customer_id = data.get("customer_id")

            if customer_id:
                try:
                    customer_id = int(customer_id)
                except (ValueError, TypeError):
                    raise ValueError("Invalid customer ID.")

                cur.execute("""
                    SELECT id, name, phone, address
                    FROM customers
                    WHERE id=%s AND owner_id=%s
                """, (customer_id, uid))

                customer = cur.fetchone()

                if not customer:
                    raise ValueError("Customer was not found.")

                customer_name = customer["name"]
                customer_phone = customer["phone"] or customer_phone
                customer_address = customer["address"] or customer_address

            # Create invoice
            cur.execute("""
                INSERT INTO invoices(
                    invoice_number,
                    customer_id,
                    customer_name,
                    customer_phone,
                    customer_address,
                    subtotal,
                    discount,
                    tax,
                    total_amount,
                    amount_paid,
                    balance,
                    payment_status,
                    cashier,
                    owner_id
                )
                VALUES(
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                RETURNING id, invoice_number, created_at
            """, (
                invoice_number,
                customer_id,
                customer_name,
                customer_phone,
                customer_address,
                subtotal,
                discount,
                tax,
                total_amount,
                amount_paid,
                balance,
                payment_status,
                username,
                uid
            ))

            invoice = cur.fetchone()
            invoice_id = invoice["id"]

            # Save invoice items and reduce stock
            for item in prepared_items:

                cur.execute("""
                    INSERT INTO invoice_items(
                        invoice_id,
                        product_id,
                        product_name,
                        quantity,
                        unit_price,
                        unit_cost,
                        line_total,
                        line_cost,
                        line_profit
                    )
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    invoice_id,
                    item["product_id"],
                    item["name"],
                    item["quantity"],
                    item["unit_price"],
                    item["unit_cost"],
                    item["line_total"],
                    item["line_cost"],
                    item["line_profit"]
                ))

                new_quantity = item["old_quantity"] - item["quantity"]

                cur.execute("""
                    UPDATE products
                    SET quantity=%s
                    WHERE id=%s AND owner_id=%s
                """, (
                    new_quantity,
                    item["product_id"],
                    uid
                ))

                # Existing transaction table
                cur.execute("""
                    INSERT INTO transactions(
                        transaction_type,
                        product_id,
                        product_name,
                        quantity,
                        purchase_price,
                        selling_price,
                        amount,
                        cost_amount,
                        profit,
                        cash_before,
                        cash_after,
                        stock_before,
                        stock_after,
                        username,
                        description,
                        owner_id
                    )
                    VALUES(
                        'STOCK OUT',
                        %s,%s,%s,%s,%s,%s,%s,%s,
                        0,0,%s,%s,%s,%s,%s
                    )
                """, (
                    item["product_id"],
                    item["name"],
                    item["quantity"],
                    item["unit_cost"],
                    item["unit_price"],
                    item["line_total"],
                    item["line_cost"],
                    item["line_profit"],
                    item["old_quantity"],
                    new_quantity,
                    username,
                    f"Invoice {invoice_number}",
                    uid
                ))

                # Existing history
                cur.execute("""
                    INSERT INTO history(
                        product_id,
                        product_name,
                        action,
                        quantity,
                        previous_quantity,
                        new_quantity,
                        username,
                        owner_id
                    )
                    VALUES(%s,%s,'INVOICE SALE',%s,%s,%s,%s,%s)
                """, (
                    item["product_id"],
                    item["name"],
                    item["quantity"],
                    item["old_quantity"],
                    new_quantity,
                    username,
                    uid
                ))

            # Payment record
            if amount_paid > 0:
                cur.execute("""
                    INSERT INTO payments(
                        invoice_id,
                        amount,
                        payment_method,
                        reference,
                        description,
                        username,
                        owner_id
                    )
                    VALUES(%s,%s,%s,%s,%s,%s,%s)
                """, (
                    invoice_id,
                    amount_paid,
                    payment_method,
                    str(data.get("payment_reference", "")).strip(),
                    f"Initial payment for {invoice_number}",
                    username,
                    uid
                ))

                # CASH affects existing cash balance
                if payment_method == "CASH":
                    cash_account = ensure_cash_account(conn, uid)
                    cash_before = money(cash_account["balance"])
                    cash_after = money(cash_before + amount_paid)

                    cur.execute("""
                        UPDATE cash_account
                        SET balance=%s
                        WHERE owner_id=%s
                    """, (cash_after, uid))
                else:
                    cash_before = money(0)
                    cash_after = money(0)

            # Revenue + receivable/payment accounting
            accounting_lines = []

            if payment_method == "CASH" and amount_paid > 0:
                accounting_lines.append({
                    "account_code": "1000",
                    "debit": amount_paid,
                    "credit": 0,
                    "description": "Cash received from invoice"
                })

            elif payment_method == "BANK" and amount_paid > 0:
                accounting_lines.append({
                    "account_code": "1010",
                    "debit": amount_paid,
                    "credit": 0,
                    "description": "Bank payment received"
                })

            elif payment_method == "MOBILE MONEY" and amount_paid > 0:
                accounting_lines.append({
                    "account_code": "1020",
                    "debit": amount_paid,
                    "credit": 0,
                    "description": "Mobile Money payment received"
                })

            if balance > 0:
                accounting_lines.append({
                    "account_code": "1100",
                    "debit": balance,
                    "credit": 0,
                    "description": "Accounts receivable"
                })

            accounting_lines.append({
                "account_code": "4000",
                "debit": 0,
                "credit": total_amount,
                "description": "Sales revenue"
            })

            create_journal_entry(
                conn,
                uid,
                "INVOICE",
                invoice_id,
                f"Invoice {invoice_number} - Sales",
                accounting_lines,
                username
            )

            # COGS + Inventory
            create_journal_entry(
                conn,
                uid,
                "INVOICE_COGS",
                invoice_id,
                f"Invoice {invoice_number} - Cost of Goods Sold",
                [
                    {
                        "account_code": "5000",
                        "debit": total_cost,
                        "credit": 0,
                        "description": "Cost of goods sold"
                    },
                    {
                        "account_code": "1200",
                        "debit": 0,
                        "credit": total_cost,
                        "description": "Inventory reduction"
                    }
                ],
                username
            )

        conn.commit()

        return jsonify(
            success=True,
            message=f"Invoice {invoice_number} created successfully.",
            invoice={
                "id": invoice_id,
                "invoice_number": invoice_number,
                "customer_name": customer_name,
                "subtotal": float(subtotal),
                "discount": float(discount),
                "tax": float(tax),
                "total_amount": float(total_amount),
                "amount_paid": float(amount_paid),
                "balance": float(balance),
                "payment_status": payment_status,
                "profit": float(money(total_amount - total_cost))
            }
        ), 201

    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400

    except Exception as e:
        conn.rollback()
        print("CREATE INVOICE ERROR:", e)
        return jsonify(
            success=False,
            message="Invoice creation failed. No changes were saved."
        ), 500

    finally:
        conn.close()

@app.get("/api/invoices/<int:invoice_id>")
@login_required
def get_invoice_details(invoice_id):
    uid = current_user_id()
    conn = get_db()

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    invoice_number,
                    created_at,
                    customer_name,
                    customer_phone,
                    customer_address,
                    subtotal,
                    discount,
                    tax,
                    total_amount,
                    amount_paid,
                    balance,
                    payment_status,
                    cashier
                FROM invoices
                WHERE id=%s AND owner_id=%s
            """, (invoice_id, uid))

            invoice = cur.fetchone()

            if not invoice:
                return jsonify(
                    success=False,
                    message="Invoice not found."
                ), 404

            cur.execute("""
                SELECT
                    id,
                    product_id,
                    product_name,
                    quantity,
                    unit_price,
                    unit_cost,
                    line_total,
                    line_cost,
                    line_profit
                FROM invoice_items
                WHERE invoice_id=%s
                ORDER BY id
            """, (invoice_id,))

            items = cur.fetchall()

            cur.execute("""
                SELECT
                    id,
                    amount,
                    payment_method,
                    reference,
                    description,
                    username,
                    created_at
                FROM payments
                WHERE invoice_id=%s
                  AND owner_id=%s
                ORDER BY created_at
            """, (invoice_id, uid))

            payments = cur.fetchall()

        return jsonify(
            success=True,
            invoice={
                "id": invoice["id"],
                "invoice_number": invoice["invoice_number"],
                "created_at": invoice["created_at"].isoformat() if invoice["created_at"] else None,
                "customer_name": invoice["customer_name"],
                "customer_phone": invoice["customer_phone"] or "",
                "customer_address": invoice["customer_address"] or "",
                "subtotal": float(invoice["subtotal"] or 0),
                "discount": float(invoice["discount"] or 0),
                "tax": float(invoice["tax"] or 0),
                "total_amount": float(invoice["total_amount"] or 0),
                "amount_paid": float(invoice["amount_paid"] or 0),
                "balance": float(invoice["balance"] or 0),
                "payment_status": invoice["payment_status"],
                "cashier": invoice["cashier"] or "",
                "items": [
                    {
                        "id": item["id"],
                        "product_id": item["product_id"],
                        "product_name": item["product_name"],
                        "quantity": item["quantity"],
                        "unit_price": float(item["unit_price"] or 0),
                        "unit_cost": float(item["unit_cost"] or 0),
                        "line_total": float(item["line_total"] or 0),
                        "line_cost": float(item["line_cost"] or 0),
                        "line_profit": float(item["line_profit"] or 0)
                    }
                    for item in items
                ],
                "payments": [
                    {
                        "id": payment["id"],
                        "amount": float(payment["amount"] or 0),
                        "payment_method": payment["payment_method"],
                        "reference": payment["reference"] or "",
                        "description": payment["description"] or "",
                        "username": payment["username"] or "",
                        "created_at": payment["created_at"].isoformat() if payment["created_at"] else None
                    }
                    for payment in payments
                ]
            }
        )

    except Exception as e:
        print("GET INVOICE DETAILS ERROR:", e)
        return jsonify(
            success=False,
            message="Failed to load invoice details."
        ), 500

    finally:
        conn.close()
@app.get("/api/customers")
def get_customers():
    uid=current_user_id()
    if not uid:
        return jsonify(success=False,message="Unauthorized"),401
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,name,phone,address,created_at FROM customers WHERE owner_id=%s ORDER BY name",(uid,))
            rows=cur.fetchall()
        return jsonify(success=True,customers=[dict(r) for r in rows])
    finally:
        conn.close()

@app.post("/api/customers")
def create_customer():
    uid=current_user_id()
    if not uid:
        return jsonify(success=False,message="Unauthorized"),401
    data=request.get_json(silent=True) or {}
    name=str(data.get("name","")).strip()
    phone=str(data.get("phone","")).strip()
    address=str(data.get("address","")).strip()
    if not name:
        return jsonify(success=False,message="Customer name is required."),400
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO customers(name,phone,address,owner_id) VALUES(%s,%s,%s,%s) RETURNING id,name,phone,address,created_at",(name,phone,address,uid))
            row=cur.fetchone()
        conn.commit()
        return jsonify(success=True,message="Customer added successfully.",customer=dict(row))
    except Exception as e:
        conn.rollback()
        print("CUSTOMER ERROR:",e)
        return jsonify(success=False,message="Failed to add customer."),500
    finally:
        conn.close()

@app.get("/api/debts")
def get_debts():
    uid=current_user_id()
    if not uid:
        return jsonify(success=False,message="Unauthorized"),401
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT d.id,d.customer_id,c.name AS customer_name,c.phone,
                       d.product_id,d.product_name,d.quantity,d.total_amount,
                       d.amount_paid,d.amount_remaining,d.due_date,d.status,
                       d.description,d.created_at
                FROM debts d
                JOIN customers c ON c.id=d.customer_id
                WHERE d.owner_id=%s
                ORDER BY d.id DESC
            """,(uid,))
            rows=cur.fetchall()
        return jsonify(success=True,debts=[dict(r) for r in rows])
    finally:
        conn.close()

@app.post("/api/debts")
def create_debt():
    uid=current_user_id()
    if not uid:
        return jsonify(success=False,message="Unauthorized"),401
    data=request.get_json(silent=True) or {}
    customer_id=data.get("customer_id")
    product_id=data.get("product_id")
    product_name=str(data.get("product_name","")).strip()
    description=str(data.get("description","")).strip()
    due_date=data.get("due_date") or None
    try:
        quantity=int(data.get("quantity",1))
        total_amount=float(data.get("total_amount",0))
        amount_paid=float(data.get("amount_paid",0))
    except (TypeError,ValueError):
        return jsonify(success=False,message="Enter valid numeric values."),400
    if not customer_id or total_amount<=0 or quantity<=0 or amount_paid<0 or amount_paid>total_amount:
        return jsonify(success=False,message="Invalid debt information."),400
    remaining=total_amount-amount_paid
    status="PAID" if remaining<=0 else ("PARTIAL" if amount_paid>0 else "UNPAID")
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM customers WHERE id=%s AND owner_id=%s",(customer_id,uid))
            if not cur.fetchone():
                return jsonify(success=False,message="Customer not found."),404
            cur.execute("""
                INSERT INTO debts(customer_id,product_id,product_name,quantity,total_amount,amount_paid,amount_remaining,due_date,status,description,owner_id)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """,(customer_id,product_id,product_name,quantity,total_amount,amount_paid,remaining,due_date,status,description,uid))
            debt_id=cur.fetchone()["id"]
            if amount_paid>0:
                cur.execute("""
                    INSERT INTO debt_payments(debt_id,amount,payment_method,description,username,owner_id)
                    VALUES(%s,%s,%s,%s,%s,%s)
                """,(debt_id,amount_paid,"CASH","Initial payment",current_username(),uid))
        conn.commit()
        return jsonify(success=True,message="Debt created successfully.",debt_id=debt_id)
    except Exception as e:
        conn.rollback()
        print("DEBT ERROR:",e)
        return jsonify(success=False,message="Failed to create debt."),500
    finally:
        conn.close()

@app.post("/api/debts/<int:debt_id>/payment")
def pay_debt(debt_id):
    uid=current_user_id()
    if not uid:return jsonify(success=False,message="Unauthorized"),401
    data=request.get_json(silent=True) or {}
    try: amount=float(data.get("amount",0))
    except (TypeError,ValueError): return jsonify(success=False,message="Enter a valid payment amount."),400
    if amount<=0:return jsonify(success=False,message="Payment amount must be greater than zero."),400
    payment_method=str(data.get("payment_method","CASH")).strip().upper(); description=str(data.get("description","Debt payment")).strip(); conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM debts WHERE id=%s AND owner_id=%s FOR UPDATE",(debt_id,uid)); debt=cur.fetchone()
            if not debt:return jsonify(success=False,message="Debt not found."),404
            remaining=float(debt["amount_remaining"] or 0)
            if remaining<=0:return jsonify(success=False,message="This debt is already fully paid."),400
            if amount>remaining:return jsonify(success=False,message=f"Payment cannot exceed remaining debt of {remaining:,.2f} Frw."),400
            new_paid=float(debt["amount_paid"] or 0)+amount; new_remaining=remaining-amount; status="PAID" if new_remaining<=0.001 else "PARTIAL"
            cur.execute("UPDATE debts SET amount_paid=%s,amount_remaining=%s,status=%s WHERE id=%s AND owner_id=%s",(new_paid,new_remaining,status,debt_id,uid))
            cur.execute("INSERT INTO debt_payments(debt_id,amount,payment_method,description,username,owner_id) VALUES(%s,%s,%s,%s,%s,%s)",(debt_id,amount,payment_method,description,current_username(),uid))
        conn.commit(); return jsonify(success=True,message=f"Payment successful. Remaining debt: {new_remaining:,.2f} Frw.",amount_paid=new_paid,amount_remaining=new_remaining,status=status)
    except Exception as e:
        conn.rollback(); print("DEBT PAYMENT ERROR:",e); return jsonify(success=False,message="Debt payment failed."),500
    finally: conn.close()

@app.get("/cash")
@login_required
def cash_page():
    if is_admin():return redirect("/admin-dashboard")
    return render_template_string(CASH_HTML,css=BASE_CSS)

@app.get("/api/cash")
@login_required
def get_cash():
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(balance,0) AS balance FROM cash_account WHERE owner_id=%s",(current_user_id(),));row=cur.fetchone()
    finally:conn.close()
    return jsonify(success=True,balance=float(row["balance"]) if row else 0)

@app.post("/api/cash")
@login_required
def cash_transaction():
    data = request.get_json(silent=True) or {}
    typ = str(data.get("transaction_type", "")).strip().upper()
    desc = str(data.get("description", "Cash transaction")).strip()

    try:
        amount = float(data.get("amount"))
    except (ValueError, TypeError):
        return jsonify(success=False, message="Invalid amount."), 400

    if typ not in ("CASH IN", "CASH OUT") or amount <= 0:
        return jsonify(
            success=False,
            message="Enter a valid cash transaction."
        ), 400

    uid = current_user_id()
    username = current_username()
    conn = get_db()

    try:
        with conn.cursor() as cur:
            account = ensure_cash_account(conn, uid)
            before = float(account["balance"])

            if typ == "CASH OUT" and amount > before:
                return jsonify(
                    success=False,
                    message=f"Not enough cash. Available: {before:,.2f} Frw."
                ), 400

            after = before + amount if typ == "CASH IN" else before - amount

            # 1. Update cash balance
            cur.execute(
                "UPDATE cash_account SET balance=%s WHERE owner_id=%s",
                (after, uid)
            )

            # 2. Existing transaction record
            cur.execute("""
                INSERT INTO transactions(
                    transaction_type,
                    amount,
                    cash_before,
                    cash_after,
                    username,
                    description,
                    owner_id
                )
                VALUES(%s,%s,%s,%s,%s,%s,%s)
            """, (
                typ,
                amount,
                before,
                after,
                username,
                desc,
                uid
            ))

            # 3. DOUBLE-ENTRY ACCOUNTING
            if typ == "CASH IN":
                # Cash received from owner/business capital
                # Dr Cash
                # Cr Owner Capital
                create_journal_entry(
                    conn,
                    uid,
                    "CASH_IN",
                    None,
                    desc or "Cash received",
                    [
                        {
                            "account_code": "1000",
                            "debit": amount,
                            "credit": 0,
                            "description": "Cash received"
                        },
                        {
                            "account_code": "3000",
                            "debit": 0,
                            "credit": amount,
                            "description": "Owner capital"
                        }
                    ],
                    username
                )

            else:
                # Cash used for operating expenses
                # Dr Operating Expenses
                # Cr Cash
                create_journal_entry(
                    conn,
                    uid,
                    "CASH_OUT",
                    None,
                    desc or "Operating expense",
                    [
                        {
                            "account_code": "6000",
                            "debit": amount,
                            "credit": 0,
                            "description": "Operating expense"
                        },
                        {
                            "account_code": "1000",
                            "debit": 0,
                            "credit": amount,
                            "description": "Cash paid"
                        }
                    ],
                    username
                )

        conn.commit()

    except Exception as e:
        conn.rollback()
        print("CASH ACCOUNTING ERROR:", e)
        return jsonify(
            success=False,
            message="Cash transaction failed. No changes were saved."
        ), 500

    finally:
        conn.close()

    return jsonify(
        success=True,
        message=f"{typ} successful. New balance: {after:,.2f} Frw"
    )

@app.get("/history")
@login_required
def history_page():
    if is_admin():return redirect("/admin-dashboard")
    return render_template_string(HISTORY_HTML,css=BASE_CSS)

@app.get("/api/transactions")
@login_required
def get_transactions():
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM transactions WHERE owner_id=%s ORDER BY id DESC",(current_user_id(),));rows=cur.fetchall()
    finally:conn.close()
    return jsonify(success=True,transactions=[dict(r) for r in rows])

@app.get("/api/history")
@login_required
def get_history():
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM history WHERE owner_id=%s ORDER BY id DESC",(current_user_id(),));rows=cur.fetchall()
    finally:conn.close()
    return jsonify(success=True,history=[dict(r) for r in rows])

@app.post("/api/heartbeat")
@login_required
def heartbeat():
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET last_seen=CURRENT_TIMESTAMP WHERE id=%s",(current_user_id(),))
        conn.commit()
    finally:
        conn.close()
    return jsonify(success=True)


@app.get("/admin-dashboard")
@login_required
def admin_dashboard():
    if not is_admin():return redirect("/dashboard")
    return render_template_string(ADMIN_HTML,css=BASE_CSS,username=current_username())

@app.get("/api/admin-dashboard")
@admin_required
def admin_dashboard_data():
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM users WHERE role!='admin'");total_users=cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM products WHERE owner_id IN (SELECT id FROM users WHERE role!='admin')");total_products=cur.fetchone()["n"]
            cur.execute("SELECT COALESCE(SUM(quantity),0) AS n FROM products WHERE owner_id IN (SELECT id FROM users WHERE role!='admin')");total_stock=cur.fetchone()["n"]
            cur.execute("SELECT COALESCE(SUM(balance),0) AS n FROM cash_account WHERE owner_id IN (SELECT id FROM users WHERE role!='admin')");total_cash=cur.fetchone()["n"]
            cur.execute("SELECT COALESCE(SUM(amount),0) AS n FROM transactions WHERE transaction_type='STOCK OUT' AND owner_id IN (SELECT id FROM users WHERE role!='admin')");total_sales=cur.fetchone()["n"]
            cur.execute("SELECT COALESCE(SUM(profit),0) AS n FROM transactions WHERE transaction_type='STOCK OUT' AND owner_id IN (SELECT id FROM users WHERE role!='admin')");total_profit=cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM transactions WHERE transaction_type='STOCK IN' AND owner_id IN (SELECT id FROM users WHERE role!='admin')");stock_in=cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM transactions WHERE transaction_type='STOCK OUT' AND owner_id IN (SELECT id FROM users WHERE role!='admin')");stock_out=cur.fetchone()["n"]
            cur.execute("SELECT id,username,role,is_active,created_at,last_seen,EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP-last_seen)) AS last_seen_seconds FROM users WHERE role!='admin' ORDER BY id DESC");users=cur.fetchall()
            cur.execute("SELECT id,transaction_type,product_name,quantity,amount,profit,username,description,created_at FROM transactions WHERE owner_id IN (SELECT id FROM users WHERE role!='admin') ORDER BY id DESC LIMIT 200");activities=cur.fetchall()
    finally:conn.close()
    return jsonify(success=True,total_users=total_users,total_products=total_products,total_stock=total_stock,total_cash=float(total_cash),total_sales=float(total_sales),total_profit=float(total_profit),stock_in=stock_in,stock_out=stock_out,users=[dict(x) for x in users],activities=[dict(x) for x in activities])

@app.post("/api/admin/users/<int:user_id>/activate")
@admin_required
def activate_user(user_id):
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,username,role FROM users WHERE id=%s",(user_id,))
            user=cur.fetchone()
            if not user:return jsonify(success=False,message="User not found."),404
            if user["role"]=="admin":return jsonify(success=False,message="Admin account cannot be changed here."),403
            cur.execute("UPDATE users SET is_active=TRUE WHERE id=%s",(user_id,))
        conn.commit()
    finally:conn.close()
    return jsonify(success=True,message="Account activated successfully.")

@app.post("/api/admin/users/<int:user_id>/deactivate")
@admin_required
def deactivate_user(user_id):
    conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,username,role FROM users WHERE id=%s",(user_id,))
            user=cur.fetchone()
            if not user:return jsonify(success=False,message="User not found."),404
            if user["role"]=="admin":return jsonify(success=False,message="Admin account cannot be changed here."),403
            cur.execute("UPDATE users SET is_active=FALSE WHERE id=%s",(user_id,))
        conn.commit()
    finally:conn.close()
    return jsonify(success=True,message="Account deactivated successfully.")

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"



DEBT_HTML = '''
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Debts & Customers</title>
<style>{{ css }}</style>
</head>

<body>

<div class="nav">
    <div class="brand">Debts & Customers</div>
    <a class="btn" href="/dashboard">Dashboard</a>
</div>

<div class="container">

<div class="box">

<h2>Add Customer</h2>

<label>Customer Name</label>
<input id="customerName" class="input" placeholder="Customer name">

<label>Phone</label>
<input id="customerPhone" class="input" placeholder="Phone number">

<label>Address</label>
<input id="customerAddress" class="input" placeholder="Address">

<button class="btn green" onclick="addCustomer()">
ADD CUSTOMER
</button>

</div>


<div class="box" style="margin-top:25px">

<h2>Create Debt</h2>

<label>Customer</label>
<select id="customer" class="input"></select>

<label>Product</label>
<select id="product" class="input"></select>

<label>Quantity</label>
<input id="quantity" class="input" type="number" min="1" value="1">

<label>Total Amount</label>
<input id="totalAmount" class="input" type="number" min="0">

<label>Amount Paid</label>
<input id="amountPaid" class="input" type="number" min="0" value="0">

<label>Due Date</label>
<input id="dueDate" class="input" type="date">

<label>Description</label>
<input id="description" class="input">

<button class="btn green" onclick="createDebt()">
CREATE DEBT
</button>

</div>


<div class="section" style="margin-top:25px">

<h2>Customers</h2>

<div class="table-wrap">

<table>

<thead>
<tr>
<th>ID</th>
<th>Name</th>
<th>Phone</th>
<th>Address</th>
<th>Created</th>
</tr>
</thead>

<tbody id="customerRows"></tbody>

</table>

</div>

</div>


<div class="section" style="margin-top:25px">

<h2>Debt Records</h2>

<div class="table-wrap">

<table>

<thead>
<tr>
<th>ID</th>
<th>Customer</th>
<th>Phone</th>
<th>Product</th>
<th>Qty</th>
<th>Total</th>
<th>Paid</th>
<th>Remaining</th>
<th>Due Date</th>
<th>Status</th>
<th>Action</th>
</tr>
</thead>

<tbody id="debtRows"></tbody>

</table>

</div>

</div>

</div>


<script>

let customers = [];
let debts = [];


async function loadCustomers(){

    const r = await fetch('/api/customers');
    const d = await r.json();

    if(!d.success){
        alert(d.message || 'Failed to load customers');
        return;
    }

    customers = d.customers || [];

    const select = document.getElementById('customer');

    select.innerHTML = '<option value="">Select customer</option>';

    customers.forEach(c => {

        select.innerHTML +=
        '<option value="' + c.id + '">' +
        c.name +
        (c.phone ? ' - ' + c.phone : '') +
        '</option>';

    });


    document.getElementById('customerRows').innerHTML =
    customers.map(c =>

        '<tr>' +
        '<td>' + c.id + '</td>' +
        '<td><b>' + c.name + '</b></td>' +
        '<td>' + (c.phone || '-') + '</td>' +
        '<td>' + (c.address || '-') + '</td>' +
        '<td>' + (c.created_at || '-') + '</td>' +
        '</tr>'

    ).join('');

}


async function loadProducts(){

    const r = await fetch('/api/products');
    const d = await r.json();

    if(!d.success){
        console.log(d);
        return;
    }

    const products = d.products || [];

    const select = document.getElementById('product');

    select.innerHTML = '<option value="">Select product</option>';

    products.forEach(p => {

        select.innerHTML +=
        '<option value="' + p.id + '">' +
        (p.name || p.product_name || 'Product') +
        '</option>';

    });

}


async function loadDebts(){

    const r = await fetch('/api/debts');
    const d = await r.json();

    if(!d.success){
        alert(d.message || 'Failed to load debts');
        return;
    }

    debts = d.debts || [];

    const rows = document.getElementById('debtRows');

    if(debts.length === 0){

        rows.innerHTML =
        '<tr>' +
        '<td colspan="11" style="text-align:center;padding:20px">' +
        'No debt records yet.' +
        '</td>' +
        '</tr>';

        return;
    }


    rows.innerHTML = debts.map(d => {

        const remaining = Number(d.amount_remaining || 0);

        let action = '';

        if(remaining > 0){

            action =
            '<button class="btn green" onclick="payDebt(' +
            d.id + ',' + remaining +
            ')">PAY</button>';

        }else{

            action =
            '<b style="color:green">PAID</b>';

        }


        return '<tr>' +

        '<td>' + d.id + '</td>' +

        '<td><b>' + (d.customer_name || '-') + '</b></td>' +

        '<td>' + (d.phone || '-') + '</td>' +

        '<td>' + (d.product_name || '-') + '</td>' +

        '<td>' + (d.quantity || '-') + '</td>' +

        '<td>' +
        Number(d.total_amount || 0).toLocaleString() +
        ' Frw</td>' +

        '<td>' +
        Number(d.amount_paid || 0).toLocaleString() +
        ' Frw</td>' +

        '<td><b>' +
        remaining.toLocaleString() +
        ' Frw</b></td>' +

        '<td>' + (d.due_date || '-') + '</td>' +

        '<td>' + (d.status || '-') + '</td>' +

        '<td>' + action + '</td>' +

        '</tr>';

    }).join('');

}


async function addCustomer(){

    const name =
        document.getElementById('customerName').value.trim();

    const phone =
        document.getElementById('customerPhone').value.trim();

    const address =
        document.getElementById('customerAddress').value.trim();


    if(!name){

        alert('Customer name is required.');

        return;
    }


    const r = await fetch('/api/customers', {

        method:'POST',

        headers:{
            'Content-Type':'application/json'
        },

        body:JSON.stringify({

            name:name,
            phone:phone,
            address:address

        })

    });


    const d = await r.json();

    alert(d.message || 'Request completed.');


    if(d.success){

        document.getElementById('customerName').value = '';
        document.getElementById('customerPhone').value = '';
        document.getElementById('customerAddress').value = '';

        loadCustomers();

    }

}


async function createDebt(){

    const customer_id =
        document.getElementById('customer').value;

    const product_id =
        document.getElementById('product').value;

    const productSelect =
        document.getElementById('product');

    const product_name =
        productSelect.options[
            productSelect.selectedIndex
        ]?.text || '';


    const quantity =
        Number(document.getElementById('quantity').value);

    const total_amount =
        Number(document.getElementById('totalAmount').value);

    const amount_paid =
        Number(document.getElementById('amountPaid').value || 0);

    const due_date =
        document.getElementById('dueDate').value;

    const description =
        document.getElementById('description').value.trim();


    if(!customer_id){

        alert('Select a customer.');

        return;
    }


    if(!product_id){

        alert('Select a product.');

        return;
    }


    if(quantity <= 0){

        alert('Quantity must be greater than zero.');

        return;
    }


    if(total_amount <= 0){

        alert('Total amount must be greater than zero.');

        return;
    }


    if(amount_paid < 0 || amount_paid > total_amount){

        alert('Amount paid cannot exceed total amount.');

        return;
    }


    const r = await fetch('/api/debts', {

        method:'POST',

        headers:{
            'Content-Type':'application/json'
        },

        body:JSON.stringify({

            customer_id:Number(customer_id),
            product_id:Number(product_id),
            product_name:product_name,
            quantity:quantity,
            total_amount:total_amount,
            amount_paid:amount_paid,
            due_date:due_date,
            description:description

        })

    });


    const d = await r.json();

    alert(d.message || 'Request completed.');


    if(d.success){

        document.getElementById('quantity').value = 1;
        document.getElementById('totalAmount').value = '';
        document.getElementById('amountPaid').value = 0;
        document.getElementById('dueDate').value = '';
        document.getElementById('description').value = '';

        loadDebts();

    }

}


async function payDebt(id, remaining){

    const value = prompt(
        'Enter payment amount. Remaining: ' +
        Number(remaining).toLocaleString() +
        ' Frw'
    );


    if(value === null){

        return;
    }


    const amount = Number(value);


    if(amount <= 0){

        alert('Enter a valid amount.');

        return;
    }


    if(amount > remaining){

        alert('Payment cannot exceed remaining debt.');

        return;
    }


    const method =
        prompt('Payment method:', 'CASH') || 'CASH';


    const description =
        prompt('Description:', 'Debt payment') ||
        'Debt payment';


    const r = await fetch(
        '/api/debts/' + id + '/payment',
        {

            method:'POST',

            headers:{
                'Content-Type':'application/json'
            },

            body:JSON.stringify({

                amount:amount,
                payment_method:method,
                description:description

            })

        }
    );


    const d = await r.json();

    alert(d.message || 'Payment completed.');


    if(d.success){

        loadDebts();

    }

}


loadCustomers();
loadProducts();
loadDebts();

setInterval(loadDebts,5000);

</script>

</body>
</html>
'''

@app.get("/debts")
def debts_page():
    if is_admin():
        return redirect("/admin-dashboard")
    return render_template_string(DEBT_HTML, css=BASE_CSS)


if __name__ == "__main__":
    init_database()
    print("==============================================")
    print("       STOCK MANAGEMENT SYSTEM")
    print("==============================================")
    print("Server: http://127.0.0.1:5000")
    print("Admin: admin / admin123")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)








































