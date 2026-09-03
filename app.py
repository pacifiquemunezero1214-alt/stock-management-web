from flask import Flask, request, jsonify, session, redirect, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
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

            # CASH
            cur.execute("""
                            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(14,2) NOT NULL DEFAULT 0")
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

    finally:
        conn.close()


def create_default_admin(conn):

    with conn.cursor() as cur:

        cur.execute(
            "SELECT id FROM users WHERE username=%s",
            ("admin",)
        )

        row = cur.fetchone()

        if row:
            admin_id = row["id"]

            cur.execute(
                "UPDATE users SET role='admin' WHERE id=%s",
                (admin_id,)
            )

        else:

            cur.execute("""
                INSERT INTO users(username, password, role)
                VALUES(%s, %s, 'admin')
                RETURNING id
            """, (
                "admin",
                generate_password_hash("admin123")
            ))

            admin_id = cur.fetchone()["id"]

        cur.execute("""
            INSERT INTO cash_account(balance, owner_id)
            VALUES(0, %s)
            ON CONFLICT(owner_id) DO NOTHING
        """, (admin_id,))

    conn.commit()


def ensure_cash_account(conn, user_id):

    with conn.cursor() as cur:

        cur.execute("""
            INSERT INTO cash_account(balance, owner_id)
            VALUES(0, %s)
            ON CONFLICT(owner_id) DO NOTHING
        """, (user_id,))

        cur.execute("""
            SELECT *
            FROM cash_account
            WHERE owner_id=%s
            FOR UPDATE
        """, (user_id,))

        return cur.fetchone()


# ============================================================
# SESSION
# ============================================================

def logged_in():
    return "user_id" in session


def current_user_id():
    return session.get("user_id")


def current_username():
    return session.get("username")


def is_admin():
    return session.get("role") == "admin"


def login_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if not logged_in():

            if request.path.startswith("/api/") or request.is_json:
                return jsonify(
                    success=False,
                    message="Not logged in."
                ), 401

            return redirect("/")

        return view(*args, **kwargs)

    return wrapped


def admin_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if not logged_in():
            return jsonify(
                success=False,
                message="Not logged in."
            ), 401

        if not is_admin():
            return jsonify(
                success=False,
                message="Admin permission required."
            ), 403

        return view(*args, **kwargs)

    return wrapped


# ============================================================
# CSS
# ============================================================

BASE_CSS = """
*{
    box-sizing:border-box;
}

body{
    font-family:Arial,sans-serif;
    background:#f1f5f9;
    color:#0f172a;
    margin:0;
}

.nav{
    background:#020617;
    color:#fff;
    padding:16px 28px;
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:12px;
}

.brand{
    font-size:21px;
    font-weight:700;
}

.nav a{
    color:#fff;
    text-decoration:none;
}

.container{
    max-width:1500px;
    margin:auto;
    padding:28px 20px;
}

.top{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:15px;
    margin-bottom:24px;
}

.muted{
    color:#64748b;
}

.btn{
    display:inline-block;
    border:0;
    border-radius:8px;
    padding:11px 16px;
    background:#2563eb;
    color:#fff;
    text-decoration:none;
    cursor:pointer;
    font-weight:700;
}

.btn:hover{
    opacity:.88;
}

.green{
    background:#16a34a;
}

.red{
    background:#ef4444;
}

.purple{
    background:#7c3aed;
}

.dark{
    background:#0f172a;
}

.box,
.card,
.section{
    background:#fff;
    padding:22px;
    border-radius:15px;
    box-shadow:0 5px 25px rgba(0,0,0,.06);
}

.box{
    margin-bottom:22px;
}

.cards{
    display:grid;
    grid-template-columns:repeat(4,1fr);
    gap:18px;
}

.card .title{
    color:#64748b;
    font-size:13px;
    font-weight:bold;
}

.num{
    font-size:27px;
    font-weight:700;
    margin-top:10px;
}

.form-grid{
    display:grid;
    grid-template-columns:2fr 1fr 1fr 1fr auto;
    gap:12px;
}

.input,
select{
    width:100%;
    padding:12px;
    border:1px solid #cbd5e1;
    border-radius:8px;
    font-size:15px;
}

label{
    font-weight:700;
    display:block;
    margin:10px 0 7px;
}

table{
    width:100%;
    border-collapse:collapse;
    background:#fff;
}

th,
td{
    padding:12px;
    border-bottom:1px solid #e2e8f0;
    text-align:left;
    white-space:nowrap;
}

th{
    background:#020617;
    color:#fff;
}

.table-wrap{
    overflow-x:auto;
}

.profit{
    color:#16a34a;
    font-weight:700;
}

.loss{
    color:#dc2626;
    font-weight:700;
}

.menu{
    display:grid;
    grid-template-columns:repeat(5,1fr);
    gap:16px;
    margin-top:25px;
}

.menu a{
    background:#fff;
    padding:20px;
    border-radius:14px;
    text-decoration:none;
    color:#0f172a;
    font-weight:700;
    text-align:center;
    box-shadow:0 5px 20px rgba(0,0,0,.06);
}

.menu a:hover{
    background:#2563eb;
    color:#fff;
}

.search{
    margin-bottom:18px;
}

.auth{
    min-height:100vh;
    display:flex;
    align-items:center;
    justify-content:center;
    padding:20px;
    background:linear-gradient(135deg,#020617,#2563eb);
}

.auth-box{
    width:100%;
    max-width:440px;
    background:#fff;
    padding:32px;
    border-radius:18px;
    box-shadow:0 15px 45px rgba(0,0,0,.2);
}

.auth-box h1{
    text-align:center;
}

.auth-box .input{
    margin:8px 0 12px;
}

.auth-box button{
    width:100%;
    margin-top:8px;
}

.message{
    padding:10px;
    border-radius:8px;
    margin:10px 0;
    display:none;
}

.small{
    font-size:13px;
}

.warning{
    background:#fee2e2;
    color:#991b1b;
    padding:16px;
    border-radius:12px;
    margin-bottom:20px;
}

@media(max-width:1100px){

    .cards{
        grid-template-columns:repeat(2,1fr);
    }

    .menu{
        grid-template-columns:repeat(3,1fr);
    }

    .form-grid{
        grid-template-columns:1fr 1fr;
    }
}

@media(max-width:650px){

    .cards,
    .menu,
    .form-grid{
        grid-template-columns:1fr;
    }

    .nav{
        padding:14px;
        flex-wrap:wrap;
    }

    .container{
        padding:18px 12px;
    }
}
"""


# ============================================================
# AUTH PAGE
# ============================================================

AUTH_HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stock Management</title>
<style>{{ css }}</style>
</head>

<body>

<div class="auth">

<div class="auth-box">

<h1> Stock Management</h1>

<p class="muted" style="text-align:center">
Login or create your account
</p>

<div id="msg" class="message"></div>

<input
    id="username"
    class="input"
    placeholder="Username"
    autocomplete="username"
>

<input
    id="password"
    class="input"
    type="password"
    placeholder="Password"
    autocomplete="current-password"
>

<button
    type="button"
    class="btn"
    onclick="loginUser()"
>
LOGIN
</button>

<hr style="margin:25px 0;border:0;border-top:1px solid #e2e8f0">

<h3>Create account</h3>

<input
    id="rusername"
    class="input"
    placeholder="New username"
>

<input
    id="rpassword"
    class="input"
    type="password"
    placeholder="New password"
>

<button
    type="button"
    class="btn green"
    onclick="registerUser()"
>
REGISTER
</button>

<p class="small muted">
Password must contain at least 4 characters.
</p>

</div>
</div>


<script>

function showMessage(text, ok=false){

    const message = document.getElementById("msg");

    message.textContent = text;
    message.style.display = "block";

    if(ok){

        message.style.background = "#dcfce7";
        message.style.color = "#166534";

    }else{

        message.style.background = "#fee2e2";
        message.style.color = "#991b1b";

    }
}


async function loginUser(){

    const username = document
        .getElementById("username")
        .value
        .trim();

    const password = document
        .getElementById("password")
        .value;

    if(!username || !password){

        showMessage("Enter username and password.");
        return;
    }

    try{

        const response = await fetch("/login", {

            method:"POST",

            headers:{
                "Content-Type":"application/json"
            },

            body:JSON.stringify({
                username:username,
                password:password
            })

        });

        const data = await response.json();

        if(data.success){

            window.location.href = data.redirect;

        }else{

            showMessage(data.message);

        }

    }catch(error){

        console.error(error);

        showMessage(
            "Connection error. Please try again."
        );

    }
}


async function registerUser(){

    const username = document
        .getElementById("rusername")
        .value
        .trim();

    const password = document
        .getElementById("rpassword")
        .value;

    if(!username || !password){

        showMessage("Enter username and password.");

        return;
    }

    try{

        const response = await fetch("/register", {

            method:"POST",

            headers:{
                "Content-Type":"application/json"
            },

            body:JSON.stringify({
                username:username,
                password:password
            })

        });

        const data = await response.json();

        showMessage(data.message, data.success);

        if(data.success){

            document.getElementById("username").value = username;

            document.getElementById("password").value = password;

            document.getElementById("rusername").value = "";

            document.getElementById("rpassword").value = "";
        }

    }catch(error){

        console.error(error);

        showMessage(
            "Connection error. Please try again."
        );

    }
}

</script>

</body>
</html>
"""


# ============================================================
# DASHBOARD
# ============================================================

DASHBOARD_HTML = """
<!doctype html>
<html>

<head>

<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">

<title>Dashboard</title>

<style>
{{ css }}
</style>

</head>

<body>

<div class="nav">

<div class="brand">
 Stock Management
</div>

<div>
 {{ username }}

<a class="btn red" href="/logout">
LOGOUT
</a>

</div>

</div>


<div class="container">

<div class="top">

<div>

<h1>
Welcome, {{ username }} 
</h1>

<p class="muted">
Manage stock, cash, sales and profit.
</p>

</div>

</div>


<div class="cards">

<div class="card">
<div class="title">PRODUCTS</div>
<div id="productsCount" class="num">0</div>
</div>

<div class="card">
<div class="title">TOTAL STOCK</div>
<div id="stockCount" class="num">0</div>
</div>

<div class="card">
<div class="title">STOCK VALUE</div>
<div id="stockValue" class="num">0</div>
</div>

<div class="card">
<div class="title">CASH BALANCE</div>
<div id="cashBalance" class="num">0</div>
</div>

<div class="card">
<div class="title">POTENTIAL PROFIT</div>
<div id="potentialProfit" class="num">0</div>
</div>

<div class="card">
<div class="title">TOTAL SALES</div>
<div id="totalSales" class="num">0</div>
</div>

<div class="card">
<div class="title">TOTAL PROFIT</div>
<div id="totalProfit" class="num">0</div>
</div>

<div class="card">
<div class="title">LOW STOCK</div>
<div id="lowStock" class="num">0</div>
</div>

</div>


<div class="menu">

<a href="/products">
 Products
</a>

<a href="/stock-in">
 Stock In
</a>

<a href="/stock-out">
 Stock Out
</a>

<a href="/cash">
 Cash
</a>

<a href="/history">
 History
</a>

</div>

</div>


<script>

function money(value){

    return Number(value || 0).toLocaleString();
}


async function loadDashboard(){

    try{

        const response =
            await fetch("/dashboard-data");

        const data =
            await response.json();

        if(!data.success){

            console.error(data.message);

            return;
        }

        document.getElementById("products")
            .textContent = data.total_products;

        document.getElementById("stock")
            .textContent = data.total_stock;

        document.getElementById("stockValue")
            .textContent = money(data.stock_value);

        document.getElementById("cash")
            .textContent = money(data.cash_balance);

        document.getElementById("potential")
            .textContent = money(data.potential_profit);

        document.getElementById("sales")
            .textContent = money(data.total_sales);

        document.getElementById("profit")
            .textContent = money(data.total_profit);

        document.getElementById("low")
            .textContent = data.low_stock;

        if(data.low_stock > 0){showLowStockNotification(data.low_stock);}

    }catch(error){

        console.error(
            "Dashboard error:",
            error
        );

    }
}


function showLowStockNotification(count){let old=document.getElementById("lowStockNotification");if(old)old.remove();const box=document.createElement("div");box.id="lowStockNotification";box.style.cssText="position:fixed;top:20px;right:20px;background:#dc2626;color:white;padding:16px 20px;border-radius:10px;box-shadow:0 8px 25px rgba(0,0,0,.25);z-index:9999;font-weight:bold;cursor:pointer";box.innerHTML=" LOW STOCK ALERT - "+count+" product(s) have stock of 5 or less.";box.onclick=()=>box.remove();document.body.appendChild(box);setTimeout(()=>box.remove(),8000);};loadDashboard();

setInterval(
    loadDashboard,
    5000
);

</script>

</body>
</html>
"""


# ============================================================
# PRODUCTS PAGE
# ============================================================

PRODUCTS_HTML = """
<!doctype html>
<html>

<head>

<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">

<title>Products</title>

<style>
{{ css }}
</style>

</head>

<body>

<div class="nav">

<div class="brand">
 Products
</div>

<a class="btn" href="/dashboard">
 Dashboard
</a>

</div>


<div class="container">


<div class="box">

<h2>
 Add Product
</h2>

<div class="form-grid">

<input
    id="productName"
    class="input"
    placeholder="Product name"
>

<input
    id="productQuantity"
    class="input"
    type="number"
    min="0"
    placeholder="Initial stock"
>

<input
    id="purchasePrice"
    class="input"
    type="number"
    min="0"
    step="0.01"
    placeholder="Purchase price"
>

<input
    id="unitCost"
    class="input"
    type="number"
    min="0"
    step="0.01"
    placeholder="Unit cost"
>

<input
    id="sellingPrice"
    class="input"
    type="number"
    min="0"
    step="0.01"
    placeholder="Selling price"
>

<button
    type="button"
    class="btn green"
    onclick="addProduct()"
>
ADD
</button>

</div>

<p class="muted">
Initial stock does not change cash.
Use Stock In when purchasing stock.
</p>

</div>


<input
    id="productSearch"
    class="input search"
    placeholder=" Search..."
    oninput="filterProducts()"
>


<div class="table-wrap">

<table>

<thead>

<tr>

<th>ID</th>
<th>Product</th>
<th>Stock</th>
<th>Purchase</th>
<th>Unit Cost</th>
<th>Selling</th>
<th>Profit/Unit</th>
<th>Action</th>

</tr>

</thead>

<tbody id="productRows">

</tbody>

</table>

</div>

</div>


<script>

let productsList = [];


function escapeHTML(value){

    return String(value ?? "")
        .replace(/[&<>"']/g, function(char){

            const map = {

                "&":"&amp;",
                "<":"&lt;",
                ">":"&gt;",
                '"':"&quot;",
                "'":"&#39;"

            };

            return map[char];

        });

}


function money(value){

    return Number(value || 0).toLocaleString();
}


async function loadProducts(){

    try{

        const response =
            await fetch("/api/products");

        const data =
            await response.json();

        if(!data.success){

            alert(data.message);

            return;
        }

        productsList =
            data.products || [];

        renderProducts(productsList);

    }catch(error){

        console.error(error);

        alert(
            "Failed to load products."
        );

    }
}


function renderProducts(list){

    const rows =
        document.getElementById("productRows");

    rows.innerHTML = "";

    if(list.length === 0){

        rows.innerHTML = `
            <tr>
                <td colspan="7"
                    style="text-align:center;padding:30px">
                    No products found.
                </td>
            </tr>
        `;

        return;
    }


    list.forEach(function(product){

        const profit =
            Number(product.selling_price) -
            Number(product.purchase_price);


        const tr =
            document.createElement("tr");


        tr.innerHTML = `

            <td>${product.id}</td>

            <td>
                ${escapeHTML(product.name)}
            </td>

            <td>
                ${product.quantity}
            </td>

            <td>
                ${money(product.purchase_price)}
            </td>

            <td>
                ${money(product.selling_price)}
            </td>

            <td class="${profit >= 0 ? "profit" : "loss"}">
                ${money(profit)}
            </td>

            <td>

                <button
                    type="button"
                    class="btn"
                    onclick="editProduct(${product.id})"
                >
                    EDIT
                </button>

                <button
                    type="button"
                    class="btn purple"
                    onclick="editStock(${product.id}, ${product.quantity})"
                >
                    STOCK
                </button>

                <button
                    type="button"
                    class="btn red"
                    onclick="deleteProduct(${product.id})"
                >
                    DELETE
                </button>

            </td>

        `;

        rows.appendChild(tr);

    });

}


function filterProducts(){

    const query =
        document
        .getElementById("productSearch")
        .value
        .toLowerCase()
        .trim();


    const filtered =
        productsList.filter(function(product){

            return (
                String(product.name)
                .toLowerCase()
                .includes(query)
                ||
                String(product.id)
                .includes(query)
            );

        });


    renderProducts(filtered);
}


async function addProduct(){

    const name =
        document
        .getElementById("productName")
        .value
        .trim();

    const quantity =
        Number(
            document
            .getElementById("productQuantity")
            .value
        );

    const purchase =
        Number(
            document
            .getElementById("purchasePrice")
            .value
        );

    const selling =
        Number(
            document
            .getElementById("sellingPrice")
            .value
        );\n\n    const unitCost =\n        Number(\n            document\n            .getElementById("unitCost")\n            .value\n        );


    if(
        !name ||
        !Number.isInteger(quantity) ||
        quantity < 0 ||
        !Number.isFinite(purchase) ||
        purchase < 0 ||
        !Number.isFinite(selling) ||
        selling < 0,
        !Number.isFinite(unitCost) ||
        unitCost < 0
    ){

        alert(
            "Enter valid product information."
        );

        return;
    }


    try{

        const response =
            await fetch(
                "/api/products",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify({

                        name:name,
                        quantity:quantity,
                        purchase_price:purchase,
                        unit_cost:unitCost,
                        selling_price:selling

                    })
                }
            );


        const data =
            await response.json();


        alert(data.message);


        if(data.success){

            document.getElementById(
                "productName"
            ).value = "";

            document.getElementById(
                "productQuantity"
            ).value = "";

            document.getElementById(
                "purchasePrice"
            ).value = "";

            document.getElementById(
                "sellingPrice"
            ).value = "";

            document.getElementById("unitCost").value = "";

            loadProducts();
        }


    }catch(error){

        console.error(error);

        alert(
            "Could not connect to server."
        );

    }

}


async function editProduct(id){

    const product =
        productsList.find(
            item => Number(item.id) === Number(id)
        );


    if(!product){

        alert("Product not found.");

        return;
    }


    const name =
        prompt(
            "Product name:",
            product.name
        );


    if(name === null){

        return;
    }


    const purchase =
        prompt(
            "Purchase price:",
            product.purchase_price
        );


    if(purchase === null){

        return;
    }


    const selling =
        prompt(
            "Selling price:",
            product.selling_price
        );


    if(selling === null){

        return;
    }


    const purchaseNumber =
        Number(purchase);

    const sellingNumber =
        Number(selling);


    if(
        !name.trim() ||
        !Number.isFinite(purchaseNumber) ||
        purchaseNumber < 0 ||
        !Number.isFinite(sellingNumber) ||
        sellingNumber < 0
    ){

        alert(
            "Enter valid values."
        );

        return;
    }


    try{

        const response =
            await fetch(
                "/api/products/" + id,
                {
                    method:"PUT",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify({

                        name:name.trim(),
                        purchase_price:
                            purchaseNumber,
                        selling_price:
                            sellingNumber

                    })
                }
            );


        const data =
            await response.json();


        alert(data.message);


        if(data.success){

            loadProducts();

        }

    }catch(error){

        console.error(error);

        alert(
            "Could not update product."
        );

    }

}


async function editStock(id, currentQuantity){

    const answer =
        prompt(
            "Current stock: " +
            currentQuantity +
            "\\nEnter correct total stock:",
            currentQuantity
        );


    if(answer === null){

        return;
    }


    const quantity =
        Number(answer);


    if(
        !Number.isInteger(quantity) ||
        quantity < 0
    ){

        alert(
            "Enter a valid whole number."
        );

        return;
    }


    const reason =
        prompt(
            "Reason for correction:",
            "Stock correction"
        );


    if(reason === null){

        return;
    }


    try{

        const response =
            await fetch(
                "/api/products/" +
                id +
                "/stock",
                {
                    method:"PUT",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify({

                        quantity:quantity,
                        reason:reason

                    })
                }
            );


        const data =
            await response.json();


        alert(data.message);


        if(data.success){

            loadProducts();

        }

    }catch(error){

        console.error(error);

        alert(
            "Stock update failed."
        );

    }

}


async function deleteProduct(id){

    if(
        !confirm(
            "Delete this product? Stock must be zero."
        )
    ){

        return;
    }


    try{

        const response =
            await fetch(
                "/api/products/" + id,
                {
                    method:"DELETE"
                }
            );


        const data =
            await response.json();


        alert(data.message);


        if(data.success){

            loadProducts();

        }

    }catch(error){

        console.error(error);

        alert(
            "Could not delete product."
        );

    }

}


loadProducts();

</script>

</body>
</html>
"""


# ============================================================
# STOCK MOVEMENT PAGE
# ============================================================

MOVEMENT_HTML = """
<!doctype html>
<html>

<head>

<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">

<title>{{ title }}</title>

<style>
{{ css }}
</style>

</head>

<body>

<div class="nav">

<div class="brand">
 Stock Management
</div>

<a class="btn" href="/dashboard">
 Dashboard
</a>

</div>


<div class="container">

<div
    class="box"
    style="max-width:700px;margin:auto"
>

<h1>
{{ icon }} {{ title }}
</h1>


<label>
Product
</label>

<select
    id="movementProduct"
    class="input"
>

<option value="">
Select product
</option>

</select>


<label>
Quantity
</label>

<input
    id="movementQuantity"
    class="input"
    type="number"
    min="1"
    placeholder="Enter quantity"
>


<button
    type="button"
    class="btn {{ color }}"
    style="width:100%;margin-top:20px"
    onclick="submitMovement()"
>

{{ button }}

</button>

</div>

</div>


<script>

const movementEndpoint =
    "{{ endpoint }}";


async function loadMovementProducts(){

    try{

        const response =
            await fetch("/api/products");

        const data =
            await response.json();


        if(!data.success){

            alert(data.message);

            return;
        }


        const select =
            document.getElementById(
                "movementProduct"
            );


        select.innerHTML =
            '<option value="">Select product</option>';


        data.products.forEach(function(product){

            const option =
                document.createElement("option");

            option.value =
                product.id;

            option.textContent =
                product.name +
                "  Stock: " +
                product.quantity +
                "  Buy: " +
                Number(
                    product.purchase_price
                ).toLocaleString();

            select.appendChild(option);

        });

    }catch(error){

        console.error(error);

        alert(
            "Could not load products."
        );

    }

}


async function submitMovement(){

    const productId =
        Number(
            document
            .getElementById(
                "movementProduct"
            )
            .value
        );


    const quantity =
        Number(
            document
            .getElementById(
                "movementQuantity"
            )
            .value
        );


    if(
        !productId ||
        !Number.isInteger(quantity) ||
        quantity <= 0
    ){

        alert(
            "Enter valid information."
        );

        return;
    }


    try{

        const response =
            await fetch(
                movementEndpoint,
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify({

                        product_id:productId,
                        quantity:quantity

                    })
                }
            );


        const data =
            await response.json();


        alert(data.message);


        if(data.success){

            document.getElementById(
                "movementQuantity"
            ).value = "";

            await loadMovementProducts();

        }

    }catch(error){

        console.error(error);

        alert(
            "Transaction failed."
        );

    }

}


loadMovementProducts();

</script>

</body>
</html>
"""


# ============================================================
# CASH PAGE
# ============================================================

CASH_HTML = """
<!doctype html>
<html>

<head>

<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">

<title>Cash</title>

<style>
{{ css }}
</style>

</head>

<body>

<div class="nav">

<div class="brand">
 Cash Management
</div>

<a class="btn" href="/dashboard">
 Dashboard
</a>

</div>


<div class="container">


<div class="cards">

<div class="card">

<div class="title">
CURRENT CASH
</div>

<div id="cashBalance" class="num">
0
</div>

</div>

</div>


<div
    class="box"
    style="max-width:700px;margin-top:25px"
>

<h2>
Cash Transaction
</h2>


<select
    id="cashType"
    class="input"
>

<option value="CASH IN">
CASH IN
</option>

<option value="CASH OUT">
CASH OUT
</option>

</select>


<label>
Amount
</label>

<input
    id="cashAmount"
    class="input"
    type="number"
    min="0.01"
    step="0.01"
>


<label>
Description
</label>

<input
    id="cashDescription"
    class="input"
    placeholder="Reason / description"
>


<button
    type="button"
    class="btn green"
    onclick="saveCash()"
>

SAVE TRANSACTION

</button>

</div>

</div>


<script>


function money(value){

    return Number(value || 0).toLocaleString();

}


async function loadCash(){

    try{

        const response =
            await fetch("/api/cash");

        const data =
            await response.json();


        document.getElementById(
            "cashBalance"
        ).textContent =
            money(data.balance);


    }catch(error){

        console.error(error);

    }

}


async function saveCash(){

    const type =
        document.getElementById(
            "cashType"
        ).value;


    const amount =
        Number(
            document.getElementById(
                "cashAmount"
            ).value
        );


    const description =
        document.getElementById(
            "cashDescription"
        ).value
        .trim();


    if(
        !Number.isFinite(amount) ||
        amount <= 0
    ){

        alert(
            "Enter a valid amount."
        );

        return;
    }


    try{

        const response =
            await fetch(
                "/api/cash",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify({

                        transaction_type:type,
                        amount:amount,
                        description:
                            description

                    })
                }
            );


        const data =
            await response.json();


        alert(data.message);


        if(data.success){

            document.getElementById(
                "cashAmount"
            ).value = "";

            document.getElementById(
                "cashDescription"
            ).value = "";

            loadCash();

        }

    }catch(error){

        console.error(error);

        alert(
            "Cash transaction failed."
        );

    }

}


loadCash();

</script>

</body>
</html>
"""


# ============================================================
# HISTORY PAGE
# ============================================================
from flask import Flask, request, jsonify, session, redirect, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
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

            # HISTORY
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

    finally:
        conn.close()


def create_default_admin(conn):

    with conn.cursor() as cur:

        cur.execute(
            "SELECT id FROM users WHERE username=%s",
            ("admin",)
        )

        row = cur.fetchone()

        if row:
            admin_id = row["id"]

            cur.execute(
                "UPDATE users SET role='admin' WHERE id=%s",
                (admin_id,)
            )

        else:

            cur.execute("""
                INSERT INTO users(username, password, role)
                VALUES(%s, %s, 'admin')
                RETURNING id
            """, (
                "admin",
                generate_password_hash("admin123")
            ))

            admin_id = cur.fetchone()["id"]

        cur.execute("""
            INSERT INTO cash_account(balance, owner_id)
            VALUES(0, %s)
            ON CONFLICT(owner_id) DO NOTHING
        """, (admin_id,))

    conn.commit()


def ensure_cash_account(conn, user_id):

    with conn.cursor() as cur:

        cur.execute("""
            INSERT INTO cash_account(balance, owner_id)
            VALUES(0, %s)
            ON CONFLICT(owner_id) DO NOTHING
        """, (user_id,))

        cur.execute("""
            SELECT *
            FROM cash_account
            WHERE owner_id=%s
            FOR UPDATE
        """, (user_id,))

        return cur.fetchone()


# ============================================================
# SESSION
# ============================================================

def logged_in():
    return "user_id" in session


def current_user_id():
    return session.get("user_id")


def current_username():
    return session.get("username")


def is_admin():
    return session.get("role") == "admin"


def login_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if not logged_in():

            if request.path.startswith("/api/") or request.is_json:
                return jsonify(
                    success=False,
                    message="Not logged in."
                ), 401

            return redirect("/")

        return view(*args, **kwargs)

    return wrapped


def admin_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if not logged_in():
            return jsonify(
                success=False,
                message="Not logged in."
            ), 401

        if not is_admin():
            return jsonify(
                success=False,
                message="Admin permission required."
            ), 403

        return view(*args, **kwargs)

    return wrapped


# ============================================================
# CSS
# ============================================================

BASE_CSS = """
*{
    box-sizing:border-box;
}

body{
    font-family:Arial,sans-serif;
    background:#f1f5f9;
    color:#0f172a;
    margin:0;
}

.nav{
    background:#020617;
    color:#fff;
    padding:16px 28px;
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:12px;
}

.brand{
    font-size:21px;
    font-weight:700;
}

.nav a{
    color:#fff;
    text-decoration:none;
}

.container{
    max-width:1500px;
    margin:auto;
    padding:28px 20px;
}

.top{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:15px;
    margin-bottom:24px;
}

.muted{
    color:#64748b;
}

.btn{
    display:inline-block;
    border:0;
    border-radius:8px;
    padding:11px 16px;
    background:#2563eb;
    color:#fff;
    text-decoration:none;
    cursor:pointer;
    font-weight:700;
}

.btn:hover{
    opacity:.88;
}

.green{
    background:#16a34a;
}

.red{
    background:#ef4444;
}

.purple{
    background:#7c3aed;
}

.dark{
    background:#0f172a;
}

.box,
.card,
.section{
    background:#fff;
    padding:22px;
    border-radius:15px;
    box-shadow:0 5px 25px rgba(0,0,0,.06);
}

.box{
    margin-bottom:22px;
}

.cards{
    display:grid;
    grid-template-columns:repeat(4,1fr);
    gap:18px;
}

.card .title{
    color:#64748b;
    font-size:13px;
    font-weight:bold;
}

.num{
    font-size:27px;
    font-weight:700;
    margin-top:10px;
}

.form-grid{
    display:grid;
    grid-template-columns:2fr 1fr 1fr 1fr auto;
    gap:12px;
}

.input,
select{
    width:100%;
    padding:12px;
    border:1px solid #cbd5e1;
    border-radius:8px;
    font-size:15px;
}

label{
    font-weight:700;
    display:block;
    margin:10px 0 7px;
}

table{
    width:100%;
    border-collapse:collapse;
    background:#fff;
}

th,
td{
    padding:12px;
    border-bottom:1px solid #e2e8f0;
    text-align:left;
    white-space:nowrap;
}

th{
    background:#020617;
    color:#fff;
}

.table-wrap{
    overflow-x:auto;
}

.profit{
    color:#16a34a;
    font-weight:700;
}

.loss{
    color:#dc2626;
    font-weight:700;
}

.menu{
    display:grid;
    grid-template-columns:repeat(5,1fr);
    gap:16px;
    margin-top:25px;
}

.menu a{
    background:#fff;
    padding:20px;
    border-radius:14px;
    text-decoration:none;
    color:#0f172a;
    font-weight:700;
    text-align:center;
    box-shadow:0 5px 20px rgba(0,0,0,.06);
}

.menu a:hover{
    background:#2563eb;
    color:#fff;
}

.search{
    margin-bottom:18px;
}

.auth{
    min-height:100vh;
    display:flex;
    align-items:center;
    justify-content:center;
    padding:20px;
    background:linear-gradient(135deg,#020617,#2563eb);
}

.auth-box{
    width:100%;
    max-width:440px;
    background:#fff;
    padding:32px;
    border-radius:18px;
    box-shadow:0 15px 45px rgba(0,0,0,.2);
}

.auth-box h1{
    text-align:center;
}

.auth-box .input{
    margin:8px 0 12px;
}

.auth-box button{
    width:100%;
    margin-top:8px;
}

.message{
    padding:10px;
    border-radius:8px;
    margin:10px 0;
    display:none;
}

.small{
    font-size:13px;
}

.warning{
    background:#fee2e2;
    color:#991b1b;
    padding:16px;
    border-radius:12px;
    margin-bottom:20px;
}

@media(max-width:1100px){

    .cards{
        grid-template-columns:repeat(2,1fr);
    }

    .menu{
        grid-template-columns:repeat(3,1fr);
    }

    .form-grid{
        grid-template-columns:1fr 1fr;
    }
}

@media(max-width:650px){

    .cards,
    .menu,
    .form-grid{
        grid-template-columns:1fr;
    }

    .nav{
        padding:14px;
        flex-wrap:wrap;
    }

    .container{
        padding:18px 12px;
    }
}
"""


# ============================================================
# AUTH PAGE
# ============================================================

AUTH_HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stock Management</title>
<style>{{ css }}</style>
</head>

<body>

<div class="auth">

<div class="auth-box">

<h1> Stock Management</h1>

<p class="muted" style="text-align:center">
Login or create your account
</p>

<div id="msg" class="message"></div>

<input
    id="username"
    class="input"
    placeholder="Username"
    autocomplete="username"
>

<input
    id="password"
    class="input"
    type="password"
    placeholder="Password"
    autocomplete="current-password"
>

<button
    type="button"
    class="btn"
    onclick="loginUser()"
>
LOGIN
</button>

<hr style="margin:25px 0;border:0;border-top:1px solid #e2e8f0">

<h3>Create account</h3>

<input
    id="rusername"
    class="input"
    placeholder="New username"
>

<input
    id="rpassword"
    class="input"
    type="password"
    placeholder="New password"
>

<button
    type="button"
    class="btn green"
    onclick="registerUser()"
>
REGISTER
</button>

<p class="small muted">
Password must contain at least 4 characters.
</p>

</div>
</div>


<script>

function showMessage(text, ok=false){

    const message = document.getElementById("msg");

    message.textContent = text;
    message.style.display = "block";

    if(ok){

        message.style.background = "#dcfce7";
        message.style.color = "#166534";

    }else{

        message.style.background = "#fee2e2";
        message.style.color = "#991b1b";

    }
}


async function loginUser(){

    const username = document
        .getElementById("username")
        .value
        .trim();

    const password = document
        .getElementById("password")
        .value;

    if(!username || !password){

        showMessage("Enter username and password.");
        return;
    }

    try{

        const response = await fetch("/login", {

            method:"POST",

            headers:{
                "Content-Type":"application/json"
            },

            body:JSON.stringify({
                username:username,
                password:password
            })

        });

        const data = await response.json();

        if(data.success){

            window.location.href = data.redirect;

        }else{

            showMessage(data.message);

        }

    }catch(error){

        console.error(error);

        showMessage(
            "Connection error. Please try again."
        );

    }
}


async function registerUser(){

    const username = document
        .getElementById("rusername")
        .value
        .trim();

    const password = document
        .getElementById("rpassword")
        .value;

    if(!username || !password){

        showMessage("Enter username and password.");

        return;
    }

    try{

        const response = await fetch("/register", {

            method:"POST",

            headers:{
                "Content-Type":"application/json"
            },

            body:JSON.stringify({
                username:username,
                password:password
            })

        });

        const data = await response.json();

        showMessage(data.message, data.success);

        if(data.success){

            document.getElementById("username").value = username;

            document.getElementById("password").value = password;

            document.getElementById("rusername").value = "";

            document.getElementById("rpassword").value = "";
        }

    }catch(error){

        console.error(error);

        showMessage(
            "Connection error. Please try again."
        );

    }
}

</script>

</body>
</html>
"""


# ============================================================
# DASHBOARD
# ============================================================

DASHBOARD_HTML = """
<!doctype html>
<html>

<head>

<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">

<title>Dashboard</title>

<style>
{{ css }}
</style>

</head>

<body>

<div class="nav">

<div class="brand">
 Stock Management
</div>

<div>
 {{ username }}

<a class="btn red" href="/logout">
LOGOUT
</a>

</div>

</div>


<div class="container">

<div class="top">

<div>

<h1>
Welcome, {{ username }} 
</h1>

<p class="muted">
Manage stock, cash, sales and profit.
</p>

</div>

</div>


<div class="cards">

<div class="card">
<div class="title">PRODUCTS</div>
<div id="productsCount" class="num">0</div>
</div>

<div class="card">
<div class="title">TOTAL STOCK</div>
<div id="stockCount" class="num">0</div>
</div>

<div class="card">
<div class="title">STOCK VALUE</div>
<div id="stockValue" class="num">0</div>
</div>

<div class="card">
<div class="title">CASH BALANCE</div>
<div id="cashBalance" class="num">0</div>
</div>

<div class="card">
<div class="title">POTENTIAL PROFIT</div>
<div id="potentialProfit" class="num">0</div>
</div>

<div class="card">
<div class="title">TOTAL SALES</div>
<div id="totalSales" class="num">0</div>
</div>

<div class="card">
<div class="title">TOTAL PROFIT</div>
<div id="totalProfit" class="num">0</div>
</div>

<div class="card">
<div class="title">LOW STOCK</div>
<div id="lowStock" class="num">0</div>
</div>

</div>


<div class="menu">

<a href="/products">
 Products
</a>

<a href="/stock-in">
 Stock In
</a>

<a href="/stock-out">
 Stock Out
</a>

<a href="/cash">
 Cash
</a>

<a href="/history">
 History
</a>

</div>

</div>


<script>

function money(value){

    return Number(value || 0).toLocaleString();
}


async function loadDashboard(){

    try{

        const response =
            await fetch("/dashboard-data");

        const data =
            await response.json();

        if(!data.success){

            console.error(data.message);

            return;
        }

        document.getElementById("products")
            .textContent = data.total_products;

        document.getElementById("stock")
            .textContent = data.total_stock;

        document.getElementById("stockValue")
            .textContent = money(data.stock_value);

        document.getElementById("cash")
            .textContent = money(data.cash_balance);

        document.getElementById("potential")
            .textContent = money(data.potential_profit);

        document.getElementById("sales")
            .textContent = money(data.total_sales);

        document.getElementById("profit")
            .textContent = money(data.total_profit);

        document.getElementById("low")
            .textContent = data.low_stock;

    }catch(error){

        console.error(
            "Dashboard error:",
            error
        );

    }
}


loadDashboard();

setInterval(
    loadDashboard,
    5000
);

</script>

</body>
</html>
"""


# ============================================================
# PRODUCTS PAGE
# ============================================================

PRODUCTS_HTML = """
<!doctype html>
<html>

<head>

<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">

<title>Products</title>

<style>
{{ css }}
</style>

</head>

<body>

<div class="nav">

<div class="brand">
 Products
</div>

<a class="btn" href="/dashboard">
 Dashboard
</a>

</div>


<div class="container">


<div class="box">

<h2>
 Add Product
</h2>

<div class="form-grid">

<input
    id="productName"
    class="input"
    placeholder="Product name"
>

<input
    id="productQuantity"
    class="input"
    type="number"
    min="0"
    placeholder="Initial stock"
>

<input
    id="purchasePrice"
    class="input"
    type="number"
    min="0"
    step="0.01"
    placeholder="Purchase price"
>

<input
    id="sellingPrice"
    class="input"
    type="number"
    min="0"
    step="0.01"
    placeholder="Selling price"
>

<button
    type="button"
    class="btn green"
    onclick="addProduct()"
>
ADD
</button>

</div>

<p class="muted">
Initial stock does not change cash.
Use Stock In when purchasing stock.
</p>

</div>


<input
    id="productSearch"
    class="input search"
    placeholder=" Search..."
    oninput="filterProducts()"
>


<div class="table-wrap">

<table>

<thead>

<tr>

<th>ID</th>
<th>Product</th>
<th>Stock</th>
<th>Purchase</th>
<th>Selling</th>
<th>Profit/Unit</th>
<th>Action</th>

</tr>

</thead>

<tbody id="productRows">

</tbody>

</table>

</div>

</div>


<script>

let productsList = [];


function escapeHTML(value){

    return String(value ?? "")
        .replace(/[&<>"']/g, function(char){

            const map = {

                "&":"&amp;",
                "<":"&lt;",
                ">":"&gt;",
                '"':"&quot;",
                "'":"&#39;"

            };

            return map[char];

        });

}


function money(value){

    return Number(value || 0).toLocaleString();
}


async function loadProducts(){

    try{

        const response =
            await fetch("/api/products");

        const data =
            await response.json();

        if(!data.success){

            alert(data.message);

            return;
        }

        productsList =
            data.products || [];

        renderProducts(productsList);

    }catch(error){

        console.error(error);

        alert(
            "Failed to load products."
        );

    }
}


function renderProducts(list){

    const rows =
        document.getElementById("productRows");

    rows.innerHTML = "";

    if(list.length === 0){

        rows.innerHTML = `
            <tr>
                <td colspan="7"
                    style="text-align:center;padding:30px">
                    No products found.
                </td>
            </tr>
        `;

        return;
    }


    list.forEach(function(product){

        const profit =
            Number(product.selling_price) -
            Number(product.purchase_price);


        const tr =
            document.createElement("tr");


        tr.innerHTML = `

            <td>${product.id}</td>

            <td>
                ${escapeHTML(product.name)}
            </td>

            <td>
                ${product.quantity}
            </td>

            <td>
                ${money(product.purchase_price)}
            </td>

            <td>
                ${money(product.selling_price)}
            </td>

            <td class="${profit >= 0 ? "profit" : "loss"}">
                ${money(profit)}
            </td>

            <td>

                <button
                    type="button"
                    class="btn"
                    onclick="editProduct(${product.id})"
                >
                    EDIT
                </button>

                <button
                    type="button"
                    class="btn purple"
                    onclick="editStock(${product.id}, ${product.quantity})"
                >
                    STOCK
                </button>

                <button
                    type="button"
                    class="btn red"
                    onclick="deleteProduct(${product.id})"
                >
                    DELETE
                </button>

            </td>

        `;

        rows.appendChild(tr);

    });

}


function filterProducts(){

    const query =
        document
        .getElementById("productSearch")
        .value
        .toLowerCase()
        .trim();


    const filtered =
        productsList.filter(function(product){

            return (
                String(product.name)
                .toLowerCase()
                .includes(query)
                ||
                String(product.id)
                .includes(query)
            );

        });


    renderProducts(filtered);
}


async function addProduct(){

    const name =
        document
        .getElementById("productName")
        .value
        .trim();

    const quantity =
        Number(
            document
            .getElementById("productQuantity")
            .value
        );

    const purchase =
        Number(
            document
            .getElementById("purchasePrice")
            .value
        );

    const selling =
        Number(
            document
            .getElementById("sellingPrice")
            .value
        );


    if(
        !name ||
        !Number.isInteger(quantity) ||
        quantity < 0 ||
        !Number.isFinite(purchase) ||
        purchase < 0 ||
        !Number.isFinite(selling) ||
        selling < 0
    ){

        alert(
            "Enter valid product information."
        );

        return;
    }


    try{

        const response =
            await fetch(
                "/api/products",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify({

                        name:name,
                        quantity:quantity,
                        purchase_price:purchase,
                        selling_price:selling

                    })
                }
            );


        const data =
            await response.json();


        alert(data.message);


        if(data.success){

            document.getElementById(
                "productName"
            ).value = "";

            document.getElementById(
                "productQuantity"
            ).value = "";

            document.getElementById(
                "purchasePrice"
            ).value = "";

            document.getElementById(
                "sellingPrice"
            ).value = "";

            loadProducts();
        }


    }catch(error){

        console.error(error);

        alert(
            "Could not connect to server."
        );

    }

}


async function editProduct(id){

    const product =
        productsList.find(
            item => Number(item.id) === Number(id)
        );


    if(!product){

        alert("Product not found.");

        return;
    }


    const name =
        prompt(
            "Product name:",
            product.name
        );


    if(name === null){

        return;
    }


    const purchase =
        prompt(
            "Purchase price:",
            product.purchase_price
        );


    if(purchase === null){

        return;
    }


    const selling =
        prompt(
            "Selling price:",
            product.selling_price
        );


    if(selling === null){

        return;
    }


    const purchaseNumber =
        Number(purchase);

    const sellingNumber =
        Number(selling);


    if(
        !name.trim() ||
        !Number.isFinite(purchaseNumber) ||
        purchaseNumber < 0 ||
        !Number.isFinite(sellingNumber) ||
        sellingNumber < 0
    ){

        alert(
            "Enter valid values."
        );

        return;
    }


    try{

        const response =
            await fetch(
                "/api/products/" + id,
                {
                    method:"PUT",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify({

                        name:name.trim(),
                        purchase_price:
                            purchaseNumber,
                        selling_price:
                            sellingNumber

                    })
                }
            );


        const data =
            await response.json();


        alert(data.message);


        if(data.success){

            loadProducts();

        }

    }catch(error){

        console.error(error);

        alert(
            "Could not update product."
        );

    }

}


async function editStock(id, currentQuantity){

    const answer =
        prompt(
            "Current stock: " +
            currentQuantity +
            "\\nEnter correct total stock:",
            currentQuantity
        );


    if(answer === null){

        return;
    }


    const quantity =
        Number(answer);


    if(
        !Number.isInteger(quantity) ||
        quantity < 0
    ){

        alert(
            "Enter a valid whole number."
        );

        return;
    }


    const reason =
        prompt(
            "Reason for correction:",
            "Stock correction"
        );


    if(reason === null){

        return;
    }


    try{

        const response =
            await fetch(
                "/api/products/" +
                id +
                "/stock",
                {
                    method:"PUT",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify({

                        quantity:quantity,
                        reason:reason

                    })
                }
            );


        const data =
            await response.json();


        alert(data.message);


        if(data.success){

            loadProducts();

        }

    }catch(error){

        console.error(error);

        alert(
            "Stock update failed."
        );

    }

}


async function deleteProduct(id){

    if(
        !confirm(
            "Delete this product? Stock must be zero."
        )
    ){

        return;
    }


    try{

        const response =
            await fetch(
                "/api/products/" + id,
                {
                    method:"DELETE"
                }
            );


        const data =
            await response.json();


        alert(data.message);


        if(data.success){

            loadProducts();

        }

    }catch(error){

        console.error(error);

        alert(
            "Could not delete product."
        );

    }

}


loadProducts();

</script>

</body>
</html>
"""


# ============================================================
# STOCK MOVEMENT PAGE
# ============================================================

MOVEMENT_HTML = """
<!doctype html>
<html>

<head>

<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">

<title>{{ title }}</title>

<style>
{{ css }}
</style>

</head>

<body>

<div class="nav">

<div class="brand">
 Stock Management
</div>

<a class="btn" href="/dashboard">
 Dashboard
</a>

</div>


<div class="container">

<div
    class="box"
    style="max-width:700px;margin:auto"
>

<h1>
{{ icon }} {{ title }}
</h1>


<label>
Product
</label>

<select
    id="movementProduct"
    class="input"
>

<option value="">
Select product
</option>

</select>


<label>
Quantity
</label>

<input
    id="movementQuantity"
    class="input"
    type="number"
    min="1"
    placeholder="Enter quantity"
>


<button
    type="button"
    class="btn {{ color }}"
    style="width:100%;margin-top:20px"
    onclick="submitMovement()"
>

{{ button }}

</button>

</div>

</div>


<script>

const movementEndpoint =
    "{{ endpoint }}";


async function loadMovementProducts(){

    try{

        const response =
            await fetch("/api/products");

        const data =
            await response.json();


        if(!data.success){

            alert(data.message);

            return;
        }


        const select =
            document.getElementById(
                "movementProduct"
            );


        select.innerHTML =
            '<option value="">Select product</option>';


        data.products.forEach(function(product){

            const option =
                document.createElement("option");

            option.value =
                product.id;

            option.textContent =
                product.name +
                "  Stock: " +
                product.quantity +
                "  Buy: " +
                Number(
                    product.purchase_price
                ).toLocaleString();

            select.appendChild(option);

        });

    }catch(error){

        console.error(error);

        alert(
            "Could not load products."
        );

    }

}


async function submitMovement(){

    const productId =
        Number(
            document
            .getElementById(
                "movementProduct"
            )
            .value
        );


    const quantity =
        Number(
            document
            .getElementById(
                "movementQuantity"
            )
            .value
        );


    if(
        !productId ||
        !Number.isInteger(quantity) ||
        quantity <= 0
    ){

        alert(
            "Enter valid information."
        );

        return;
    }


    try{

        const response =
            await fetch(
                movementEndpoint,
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify({

                        product_id:productId,
                        quantity:quantity

                    })
                }
            );


        const data =
            await response.json();


        alert(data.message);


        if(data.success){

            document.getElementById(
                "movementQuantity"
            ).value = "";

            await loadMovementProducts();

        }

    }catch(error){

        console.error(error);

        alert(
            "Transaction failed."
        );

    }

}


loadMovementProducts();

</script>

</body>
</html>
"""


# ============================================================
# CASH PAGE
# ============================================================

CASH_HTML = """
<!doctype html>
<html>

<head>

<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">

<title>Cash</title>

<style>
{{ css }}
</style>

</head>

<body>

<div class="nav">

<div class="brand">
 Cash Management
</div>

<a class="btn" href="/dashboard">
 Dashboard
</a>

</div>


<div class="container">


<div class="cards">

<div class="card">

<div class="title">
CURRENT CASH
</div>

<div id="cashBalance" class="num">
0
</div>

</div>

</div>


<div
    class="box"
    style="max-width:700px;margin-top:25px"
>

<h2>
Cash Transaction
</h2>


<select
    id="cashType"
    class="input"
>

<option value="CASH IN">
CASH IN
</option>

<option value="CASH OUT">
CASH OUT
</option>

</select>


<label>
Amount
</label>

<input
    id="cashAmount"
    class="input"
    type="number"
    min="0.01"
    step="0.01"
>


<label>
Description
</label>

<input
    id="cashDescription"
    class="input"
    placeholder="Reason / description"
>


<button
    type="button"
    class="btn green"
    onclick="saveCash()"
>

SAVE TRANSACTION

</button>

</div>

</div>


<script>


function money(value){

    return Number(value || 0).toLocaleString();

}


async function loadCash(){

    try{

        const response =
            await fetch("/api/cash");

        const data =
            await response.json();


        document.getElementById(
            "cashBalance"
        ).textContent =
            money(data.balance);


    }catch(error){

        console.error(error);

    }

}


async function saveCash(){

    const type =
        document.getElementById(
            "cashType"
        ).value;


    const amount =
        Number(
            document.getElementById(
                "cashAmount"
            ).value
        );


    const description =
        document.getElementById(
            "cashDescription"
        ).value
        .trim();


    if(
        !Number.isFinite(amount) ||
        amount <= 0
    ){

        alert(
            "Enter a valid amount."
        );

        return;
    }


    try{

        const response =
            await fetch(
                "/api/cash",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify({

                        transaction_type:type,
                        amount:amount,
                        description:
                            description

                    })
                }
            );


        const data =
            await response.json();


        alert(data.message);


        if(data.success){

            document.getElementById(
                "cashAmount"
            ).value = "";

            document.getElementById(
                "cashDescription"
            ).value = "";

            loadCash();

        }

    }catch(error){

        console.error(error);

        alert(
            "Cash transaction failed."
        );

    }

}


loadCash();

</script>

</body>
</html>
"""


# ============================================================
# HISTORY PAGE
# ============================================================

from flask import Flask, request, jsonify, session, redirect, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "CHANGE-THIS-STOCK-SECRET-KEY")

DATABASE_URL = os.getenv("DATABASE_URL", "")


def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set. Set your PostgreSQL connection string first.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, connect_timeout=30, keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5)


def init_database():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role VARCHAR(20) NOT NULL DEFAULT 'user',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
                    purchase_price NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (purchase_price >= 0),
                    unit_cost NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (unit_cost >= 0),
                    selling_price NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (selling_price >= 0),
                    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(owner_id, name)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cash_account (
                    id SERIAL PRIMARY KEY,
                    balance NUMERIC(16,2) NOT NULL DEFAULT 0,
                    owner_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    transaction_type VARCHAR(50) NOT NULL,
                    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
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
                    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id SERIAL PRIMARY KEY,
                    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
                    product_name VARCHAR(200) NOT NULL,
                    action VARCHAR(50) NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    previous_quantity INTEGER NOT NULL DEFAULT 0,
                    new_quantity INTEGER NOT NULL DEFAULT 0,
                    username VARCHAR(100) NOT NULL,
                    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.commit()
        create_default_admin(conn)
    finally:
        conn.close()


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
        cur.execute("""
            INSERT INTO cash_account(balance,owner_id)
            VALUES(0,%s)
            ON CONFLICT(owner_id) DO NOTHING
        """, (admin_id,))
    conn.commit()


def logged_in():
    return "user_id" in session


def current_user_id():
    return session.get("user_id")


def current_username():
    return session.get("username")


def is_admin():
    return session.get("role") == "admin"


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not logged_in():
            if request.path.startswith("/api/") or request.is_json:
                return jsonify(success=False, message="Not logged in."), 401
            return redirect("/")
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not logged_in():
            return jsonify(success=False, message="Not logged in."), 401
        if not is_admin():
            return jsonify(success=False, message="Admin permission required."), 403
        return view(*args, **kwargs)
    return wrapped


def ensure_cash_account(conn, user_id):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO cash_account(balance,owner_id)
            VALUES(0,%s)
            ON CONFLICT(owner_id) DO NOTHING
        """, (user_id,))
        cur.execute("SELECT * FROM cash_account WHERE owner_id=%s FOR UPDATE", (user_id,))
        return cur.fetchone()

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
<div class="menu"><a href="/products"> Products</a><a href="/stock-in"> Stock In</a><a href="/stock-out"> Stock Out</a><a href="/cash"> Cash</a><a href="/history"> History</a><a href="/debts"> Debts/Credit</a></div></div>
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

CASH_HTML = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cash</title><style>{{ css }}</style></head><body><div class="nav"><div class="brand"> Cash Management</div><a class="btn" href="/dashboard"> Dashboard</a></div><div class="container"><div class="cards"><div class="card"><div class="title">CURRENT CASH</div><div id="balance" class="num">0</div></div></div><div class="box" style="max-width:700px;margin-top:25px"><h2>Cash Transaction</h2><select id="type" class="input"><option value="CASH IN">CASH IN</option><option value="CASH OUT">CASH OUT</option></select><label>Amount</label><input id="amount" class="input" type="number" min="0.01" step="0.01"><label>Description</label><input id="description" class="input" placeholder="Reason / description"><button class="btn green" onclick="save()">SAVE TRANSACTION</button></div></div><script>async function load(){const r=await fetch('/api/cash');const d=await r.json();balance.textContent=Number(d.balance||0).toLocaleString()}async function save(){const r=await fetch('/api/cash',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({transaction_type:type.value,amount:Number(amount.value),description:description.value})});const d=await r.json();alert(d.message);if(d.success){amount.value='';description.value='';load()}}load()</script></body></html>
"""

HISTORY_HTML = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>History</title><style>{{ css }}</style></head><body><div class="nav"><div class="brand"> Transaction History</div><a class="btn" href="/dashboard"> Dashboard</a></div><div class="container"><input id="search" class="input search" placeholder=" Search history..." oninput="filterRows()"><div class="table-wrap"><table><thead><tr><th>ID</th><th>Type</th><th>Product</th><th>Qty</th><th>Amount</th><th>Cost</th><th>Profit</th><th>Stock Before</th><th>Stock After</th><th>Cash Before</th><th>Cash After</th><th>User</th><th>Description</th><th>Date</th></tr></thead><tbody id="rows"></tbody></table></div></div><script>let items=[];async function load(){const r=await fetch('/api/transactions');const d=await r.json();if(!d.success)return alert(d.message);items=d.transactions;render(items)}function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function render(a){rows.innerHTML=a.map(t=>`<tr><td>${t.id}</td><td class="${String(t.transaction_type).includes('IN')?'profit':'loss'}">${esc(t.transaction_type)}</td><td>${esc(t.product_name||'-')}</td><td>${t.quantity??'-'}</td><td>${Number(t.amount||0).toLocaleString()}</td><td>${Number(t.cost_amount||0).toLocaleString()}</td><td class="profit">${Number(t.profit||0).toLocaleString()}</td><td>${t.stock_before??'-'}</td><td>${t.stock_after??'-'}</td><td>${Number(t.cash_before||0).toLocaleString()}</td><td>${Number(t.cash_after||0).toLocaleString()}</td><td>${esc(t.username||'-')}</td><td>${esc(t.description||'-')}</td><td>${t.created_at}</td></tr>`).join('')}function filterRows(){const q=search.value.toLowerCase();render(items.filter(t=>(String(t.transaction_type)+' '+String(t.product_name)+' '+String(t.username)+' '+String(t.description)).toLowerCase().includes(q)))}load()</script></body></html>
"""

ADMIN_HTML = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Admin Dashboard</title><style>{{ css }}</style></head><body><div class="nav"><div class="brand"> Admin Dashboard</div><div>ADMIN ONLY  {{ username }} <a class="btn red" href="/logout">LOGOUT</a></div></div><div class="container"><div class="warning"><b> PRIVATE ADMIN AREA</b><br><br>Only the administrator can access this dashboard. Normal users and their activities are monitored here.</div><div class="cards"><div class="card"><div class="title">USERS</div><div id="usersCount" class="num">0</div></div><div class="card"><div class="title">PRODUCTS</div><div id="productsCount" class="num">0</div></div><div class="card"><div class="title">STOCK</div><div id="stockCount" class="num">0</div></div><div class="card"><div class="title">USERS CASH</div><div id="cash" class="num">0</div></div><div class="card"><div class="title">SALES</div><div id="sales" class="num">0</div></div><div class="card"><div class="title">PROFIT</div><div id="profit" class="num">0</div></div><div class="card"><div class="title">STOCK IN</div><div id="stockIn" class="num">0</div></div><div class="card"><div class="title">STOCK OUT</div><div id="stockOut" class="num">0</div></div></div><div class="section" style="margin-top:25px"><h2> LIVE ACTIVITY <span style="font-size:12px;color:#16a34a"> LIVE</span></h2><div id="liveActivity" style="max-height:420px;overflow-y:auto"></div></div><script>let lastLiveId=0;async function loadLiveActivity(){try{const r=await fetch('/api/admin-dashboard');const d=await r.json();if(!d.success)return;const box=document.getElementById('liveActivity');if(!box)return;const acts=(d.activities||[]).slice(0,30);if(acts.length===0){box.innerHTML='<div style="padding:20px;color:#777">No activity yet.</div>';return;}box.innerHTML=acts.map(a=>{const type=(a.transaction_type||'ACTIVITY').toUpperCase();let icon='';if(type==='STOCK OUT')icon='';else if(type==='STOCK IN')icon='';else if(type.includes('CASH'))icon='';return `<div style="padding:14px;border-bottom:1px solid #eee;display:flex;gap:12px;align-items:flex-start"><div style="font-size:24px">${icon}</div><div style="flex:1"><b>${a.username||'User'}</b> <span style="color:#555">performed</span> <b>${type}</b><br><span style="color:#555">${a.product_name||a.description||'Transaction'}</span>${a.quantity!=null?`  Qty: <b>${a.quantity}</b>`:''}${a.amount?`  Amount: <b>${Number(a.amount).toLocaleString()} Frw</b>`:''}${a.profit?`  Profit: <b>${Number(a.profit).toLocaleString()} Frw</b>`:''}<br><small style="color:#888">${a.created_at||''}</small></div></div>`}).join('');if(acts[0]&&acts[0].id>lastLiveId){lastLiveId=acts[0].id;}}catch(e){console.error('Live activity error:',e);}}loadLiveActivity();setInterval(loadLiveActivity,2000);</script><div class="section" style="margin-top:25px"><h2> Registered Users</h2><div class="table-wrap"><table><thead><tr><th>ID</th><th>Username</th><th>Role</th><th>Created</th><th>Status</th><th>Action</th></tr></thead><tbody id="userRows"></tbody></table></div></div><div class="section" style="margin-top:25px"><h2> User Activity</h2><div class="table-wrap"><table><thead><tr><th>ID</th><th>User</th><th>Action</th><th>Product</th><th>Qty</th><th>Amount</th><th>Profit</th><th>Description</th><th>Date</th></tr></thead><tbody id="activity"></tbody></table></div></div></div><script>async function toggleUser(id,activate){const action=activate?'activate':'deactivate';if(!confirm('Are you sure you want to '+action+' this account?'))return;try{const r=await fetch('/api/admin/users/'+id+'/'+action,{method:'POST'});const d=await r.json();alert(d.message||'Request completed.');if(d.success)load()}catch(e){console.error(e);alert('Request failed: '+e.message)}}async function load(){const r=await fetch('/api/admin-dashboard');const d=await r.json();if(!d.success)return alert(d.message);usersCount.textContent=d.total_users;productsCount.textContent=d.total_products;stockCount.textContent=d.total_stock;cash.textContent=Number(d.total_cash).toLocaleString();sales.textContent=Number(d.total_sales).toLocaleString();profit.textContent=Number(d.total_profit).toLocaleString();stockIn.textContent=d.stock_in;stockOut.textContent=d.stock_out;userRows.innerHTML=d.users.map(u=>{const secs=Number(u.last_seen_seconds);const diff=Number.isFinite(secs)?Math.max(0,secs*1000):999999999;const mins=Math.floor(diff/60000);const online=diff<120000;const status=online?" Online":mins<60?" Last seen "+mins+" minute"+(mins===1?"":"s")+" ago":" Last seen "+Math.floor(mins/60)+" hour"+(Math.floor(mins/60)===1?"":"s")+" ago";const active=Boolean(u.is_active);const action=active?`<button class="btn red" onclick="toggleUser(${u.id},false)">DEACTIVATE</button>`:`<button class="btn green" onclick="toggleUser(${u.id},true)">ACTIVATE</button>`;return `<tr><td>${u.id}</td><td><b>${u.username}</b></td><td>${u.role}</td><td>${u.created_at}</td><td>${status}<br><small>${active?"ACTIVE":"INACTIVE"}</small></td><td>${action}</td></tr>`}).join("");activity.innerHTML=d.activities.map(a=>`<tr><td>${a.id}</td><td><b>${a.username}</b></td><td>${a.transaction_type}</td><td>${a.product_name||'-'}</td><td>${a.quantity??'-'}</td><td>${Number(a.amount||0).toLocaleString()}</td><td>${Number(a.profit||0).toLocaleString()}</td><td>${a.description||'-'}</td><td>${a.created_at}</td></tr>`).join('')}load();setInterval(load,5000);setInterval(()=>fetch("/api/heartbeat",{method:"POST"}),30000);fetch("/api/heartbeat",{method:"POST"})</script></body></html>
"""

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
    data=request.get_json(silent=True) or {}
    try: pid=int(data.get("product_id")); qty=int(data.get("quantity"))
    except (ValueError,TypeError):return jsonify(success=False,message="Invalid product or quantity."),400
    if qty<=0:return jsonify(success=False,message="Quantity must be greater than zero."),400
    uid=current_user_id(); conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM products WHERE id=%s AND owner_id=%s FOR UPDATE",(pid,uid)); p=cur.fetchone()
            if not p:return jsonify(success=False,message="Product not found."),404
            cost=qty*float(p["unit_cost"]); account=ensure_cash_account(conn,uid); before=float(account["balance"])
            if cost>before:return jsonify(success=False,message=f"Not enough cash. Cost: {cost:,.2f} Frw. Available: {before:,.2f} Frw. Use Cash In first."),400
            old=int(p["quantity"]); new=old+qty; after=before-cost
            avg=float(p["unit_cost"])
            cur.execute("UPDATE products SET quantity=%s WHERE id=%s AND owner_id=%s",(new,pid,uid))
            cur.execute("UPDATE cash_account SET balance=%s WHERE owner_id=%s",(after,uid))
            cur.execute("""INSERT INTO transactions(transaction_type,product_id,product_name,quantity,purchase_price,selling_price,amount,cost_amount,profit,cash_before,cash_after,stock_before,stock_after,username,description,owner_id) VALUES('STOCK IN',%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s)""",(pid,p["name"],qty,p["purchase_price"],p["selling_price"],cost,cost,before,after,old,new,current_username(),f"Purchased at {float(p['purchase_price']):,.2f} Frw/unit. ",uid))
            cur.execute("""INSERT INTO history(product_id,product_name,action,quantity,previous_quantity,new_quantity,username,owner_id) VALUES(%s,%s,'STOCK IN',%s,%s,%s,%s,%s)""",(pid,p["name"],qty,old,new,current_username(),uid))
        conn.commit()
    except Exception as e:
        conn.rollback();print("STOCK IN ERROR:",e);return jsonify(success=False,message="Stock In failed. No changes were saved."),500
    finally:conn.close()
    return jsonify(success=True,message=f"STOCK IN SUCCESSFUL! Added {qty}. Cost {cost:,.2f} Frw. New stock {new}. Cash {after:,.2f} Frw.")

@app.get("/stock-out")
@login_required
def stock_out_page():
    if is_admin():return redirect("/admin-dashboard")
    return render_template_string(MOVEMENT_HTML,css=BASE_CSS,title="Stock Out / Sale",icon="",button="SELL / REMOVE STOCK",color="red",endpoint="/api/stock-out")

@app.post("/api/stock-out")
@login_required
def stock_out():
    data=request.get_json(silent=True) or {}
    try:pid=int(data.get("product_id"));qty=int(data.get("quantity"))
    except (ValueError,TypeError):return jsonify(success=False,message="Invalid product or quantity."),400
    if qty<=0:return jsonify(success=False,message="Quantity must be greater than zero."),400
    uid=current_user_id();conn=get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM products WHERE id=%s AND owner_id=%s FOR UPDATE",(pid,uid));p=cur.fetchone()
            if not p:return jsonify(success=False,message="Product not found."),404
            old=int(p["quantity"])
            if qty>old:return jsonify(success=False,message=f"Not enough stock. Available: {old}."),400
            pp=float(p["unit_cost"]);sp=float(p["selling_price"]);sales=qty*sp;cost=qty*pp;profit=sales-cost;new=old-qty
            account=ensure_cash_account(conn,uid);before=float(account["balance"]);after=before+sales
            cur.execute("UPDATE products SET quantity=%s WHERE id=%s AND owner_id=%s",(new,pid,uid));cur.execute("UPDATE cash_account SET balance=%s WHERE owner_id=%s",(after,uid))
            cur.execute("""INSERT INTO transactions(transaction_type,product_id,product_name,quantity,purchase_price,selling_price,amount,cost_amount,profit,cash_before,cash_after,stock_before,stock_after,username,description,owner_id) VALUES('STOCK OUT',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(pid,p["name"],qty,pp,sp,sales,cost,profit,before,after,old,new,current_username(),f"Sale. Profit: {profit:,.2f} Frw",uid))
            cur.execute("""INSERT INTO history(product_id,product_name,action,quantity,previous_quantity,new_quantity,username,owner_id) VALUES(%s,%s,'STOCK OUT',%s,%s,%s,%s,%s)""",(pid,p["name"],qty,old,new,current_username(),uid))
        conn.commit()
    except Exception as e:
        conn.rollback();print("STOCK OUT ERROR:",e);return jsonify(success=False,message="Sale failed. No changes were saved."),500
    finally:conn.close()
    return jsonify(success=True,message=f"SALE SUCCESSFUL! Sold {qty}. Sales {sales:,.2f} Frw. Cost {cost:,.2f} Frw. Profit {profit:,.2f} Frw. Remaining stock {new}. Cash {after:,.2f} Frw.")

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
    data=request.get_json(silent=True) or {};typ=str(data.get("transaction_type","")).strip().upper();desc=str(data.get("description","Cash transaction")).strip()
    try:amount=float(data.get("amount"))
    except (ValueError,TypeError):return jsonify(success=False,message="Invalid amount."),400
    if typ not in ("CASH IN","CASH OUT") or amount<=0:return jsonify(success=False,message="Enter a valid cash transaction."),400
    uid=current_user_id();conn=get_db()
    try:
        with conn.cursor() as cur:
            account=ensure_cash_account(conn,uid);before=float(account["balance"])
            if typ=="CASH OUT" and amount>before:return jsonify(success=False,message=f"Not enough cash. Available: {before:,.2f} Frw."),400
            after=before+amount if typ=="CASH IN" else before-amount
            cur.execute("UPDATE cash_account SET balance=%s WHERE owner_id=%s",(after,uid))
            cur.execute("""INSERT INTO transactions(transaction_type,amount,cash_before,cash_after,username,description,owner_id) VALUES(%s,%s,%s,%s,%s,%s,%s)""",(typ,amount,before,after,current_username(),desc,uid))
        conn.commit()
    except Exception as e:
        conn.rollback();print("CASH ERROR:",e);return jsonify(success=False,message="Cash transaction failed."),500
    finally:conn.close()
    return jsonify(success=True,message=f"{typ} successful. New balance: {after:,.2f} Frw")

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









