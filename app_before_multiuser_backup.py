from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
    session,
    redirect,
    render_template_string
)

import sqlite3
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash


# =========================================================
# CONFIGURATION
# =========================================================

app = Flask(__name__)

app.secret_key = "CHANGE-THIS-STOCK-SECRET-KEY"

DATABASE = "stock.db"


# =========================================================
# DATABASE
# =========================================================

def get_db():

    conn = sqlite3.connect(
        DATABASE,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

    return conn


def init_database():

    conn = get_db()

    # USERS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # PRODUCTS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            purchase_price REAL NOT NULL DEFAULT 0,
            selling_price REAL NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # CASH
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cash_account (
            id INTEGER PRIMARY KEY,
            balance REAL NOT NULL DEFAULT 0
        )
    """)

    conn.execute("""
        INSERT OR IGNORE INTO cash_account
        (id, balance)
        VALUES (1, 0)
    """)

    # TRANSACTIONS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            transaction_type TEXT NOT NULL,

            product_id INTEGER,
            product_name TEXT,

            quantity INTEGER DEFAULT 0,

            purchase_price REAL DEFAULT 0,
            selling_price REAL DEFAULT 0,

            amount REAL DEFAULT 0,
            cost_amount REAL DEFAULT 0,
            profit REAL DEFAULT 0,

            cash_before REAL DEFAULT 0,
            cash_after REAL DEFAULT 0,

            stock_before INTEGER DEFAULT 0,
            stock_after INTEGER DEFAULT 0,

            username TEXT,

            description TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # HISTORY
    conn.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            product_id INTEGER,

            product_name TEXT NOT NULL,

            action TEXT NOT NULL,

            quantity INTEGER NOT NULL,

            previous_quantity INTEGER NOT NULL,

            new_quantity INTEGER NOT NULL,

            username TEXT NOT NULL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# LOGIN
# =========================================================

def logged_in():

    return "user_id" in session


def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not logged_in():

            return jsonify(
                success=False,
                message="You are not logged in."
            ), 401

        return function(*args, **kwargs)

    return wrapper


# =========================================================
# HOME FILES
# =========================================================

@app.route("/")
def home():

    return send_from_directory(
        ".",
        "index.html"
    )


@app.route("/style.css")
def style():

    return send_from_directory(
        ".",
        "style.css"
    )


@app.route("/script.js")
def script():

    return send_from_directory(
        ".",
        "script.js"
    )


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["POST"]
)
def register():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify(
            success=False,
            message="Invalid request."
        ), 400

    username = str(
        data.get("username", "")
    ).strip()

    password = str(
        data.get("password", "")
    )

    if len(username) < 3:

        return jsonify(
            success=False,
            message="Username must contain at least 3 characters."
        ), 400

    if len(password) < 4:

        return jsonify(
            success=False,
            message="Password must contain at least 4 characters."
        ), 400

    conn = get_db()

    try:

        conn.execute("""
            INSERT INTO users
            (
                username,
                password
            )
            VALUES (?, ?)
        """, (
            username,
            generate_password_hash(password)
        ))

        conn.commit()

    except sqlite3.IntegrityError:

        conn.close()

        return jsonify(
            success=False,
            message="Username already exists."
        ), 409

    conn.close()

    return jsonify(
        success=True,
        message="Account created successfully."
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["POST"]
)
def login():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify(
            success=False,
            message="Invalid request."
        ), 400

    username = str(
        data.get("username", "")
    ).strip()

    password = str(
        data.get("password", "")
    )

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE username = ?
    """, (
        username,
    )).fetchone()

    conn.close()

    if not user:

        return jsonify(
            success=False,
            message="Invalid username or password."
        ), 401

    try:

        valid = check_password_hash(
            user["password"],
            password
        )

    except Exception:

        valid = (
            user["password"] == password
        )

    if not valid:

        return jsonify(
            success=False,
            message="Invalid username or password."
        ), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]

    return jsonify(
        success=True,
        message="Login successful.",
        username=user["username"]
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# =========================================================
# DASHBOARD
# =========================================================

DASHBOARD_HTML = """
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<title>Stock Management Dashboard</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #f1f5f9;
    color: #0f172a;
}

.navbar {
    background: #0f172a;
    color: white;
    padding: 18px 30px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.brand {
    font-size: 21px;
    font-weight: bold;
}

.logout {
    border: none;
    background: #ef4444;
    color: white;
    padding: 10px 16px;
    border-radius: 8px;
    cursor: pointer;
    font-weight: bold;
}

.container {
    max-width: 1450px;
    margin: auto;
    padding: 30px 20px;
}

.subtitle {
    color: #64748b;
    margin-bottom: 25px;
}

.cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 18px;
}

.card {
    background: white;
    padding: 22px;
    border-radius: 15px;
    box-shadow: 0 4px 20px rgba(0,0,0,.06);
}

.title {
    color: #64748b;
    font-size: 13px;
    font-weight: bold;
    margin-bottom: 12px;
}

.number {
    font-size: 27px;
    font-weight: bold;
}

.cash {
    color: #16a34a;
}

.sales {
    color: #2563eb;
}

.profit {
    color: #7c3aed;
}

.stock {
    color: #ea580c;
}

.low {
    color: #dc2626;
}

.menu {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 15px;
    margin-top: 25px;
}

.menu a {
    text-decoration: none;
    background: white;
    color: #0f172a;
    padding: 20px;
    border-radius: 12px;
    text-align: center;
    font-weight: bold;
    box-shadow: 0 4px 20px rgba(0,0,0,.05);
}

.menu a:hover {
    background: #2563eb;
    color: white;
}

@media(max-width:1000px) {

    .cards {
        grid-template-columns: repeat(2,1fr);
    }

    .menu {
        grid-template-columns: repeat(2,1fr);
    }
}

@media(max-width:600px) {

    .cards {
        grid-template-columns: 1fr;
    }

    .menu {
        grid-template-columns: 1fr;
    }
}

</style>

</head>

<body>

<div class="navbar">

<div class="brand">
📦 Stock Management System
</div>

<div>

👤 {{ username }}

<button
class="logout"
onclick="location.href='/logout'">

LOGOUT

</button>

</div>

</div>

<div class="container">

<h1>
Welcome, {{ username }} 👋
</h1>

<div class="subtitle">
Manage products, stock, cash, sales and profit.
</div>

<div class="cards">

<div class="card">
<div class="title">💰 CASH BALANCE</div>
<div id="cashBalance" class="number cash">0</div>
</div>

<div class="card">
<div class="title">💵 TOTAL SALES</div>
<div id="totalSales" class="number sales">0</div>
</div>

<div class="card">
<div class="title">📈 PROFIT</div>
<div id="profit" class="number profit">0</div>
</div>

<div class="card">
<div class="title">📊 STOCK VALUE</div>
<div id="stockValue" class="number stock">0</div>
</div>

<div class="card">
<div class="title">📦 PRODUCTS</div>
<div id="totalProducts" class="number">0</div>
</div>

<div class="card">
<div class="title">📦 TOTAL STOCK</div>
<div id="totalStock" class="number">0</div>
</div>

<div class="card">
<div class="title">⚠️ LOW STOCK</div>
<div id="lowStock" class="number low">0</div>
</div>

<div class="card">
<div class="title">💸 CASH OUT</div>
<div id="cashOut" class="number low">0</div>
</div>

</div>

<div class="menu">

<a href="/products">
📦 Products
</a>

<a href="/stock-in">
➕ Stock In
</a>

<a href="/stock-out">
🛒 Stock Out
</a>

<a href="/cash">
💰 Cash
</a>

<a href="/history">
🧾 Transactions
</a>

</div>

</div>

<script>

async function loadDashboard() {

    try {

        const response =
            await fetch("/dashboard-data");

        const data =
            await response.json();

        if (!data.success) return;

        document.getElementById(
            "cashBalance"
        ).textContent =
            Number(
                data.cash_balance
            ).toLocaleString();

        document.getElementById(
            "totalSales"
        ).textContent =
            Number(
                data.total_sales
            ).toLocaleString();

        document.getElementById(
            "profit"
        ).textContent =
            Number(
                data.profit
            ).toLocaleString();

        document.getElementById(
            "stockValue"
        ).textContent =
            Number(
                data.stock_value
            ).toLocaleString();

        document.getElementById(
            "totalProducts"
        ).textContent =
            data.total_products;

        document.getElementById(
            "totalStock"
        ).textContent =
            data.total_stock;

        document.getElementById(
            "lowStock"
        ).textContent =
            data.low_stock;

        document.getElementById(
            "cashOut"
        ).textContent =
            Number(
                data.total_cash_out
            ).toLocaleString();

    }

    catch(error) {

        console.log(error);

    }
}

loadDashboard();

setInterval(
    loadDashboard,
    3000
);

</script>

</body>

</html>
"""


@app.route("/dashboard")
def dashboard():

    if not logged_in():

        return redirect("/")

    return render_template_string(
        DASHBOARD_HTML,
        username=session["username"]
    )


# =========================================================
# DASHBOARD DATA
# =========================================================

@app.route("/dashboard-data")
@login_required
def dashboard_data():

    conn = get_db()

    cash = conn.execute("""
        SELECT balance
        FROM cash_account
        WHERE id = 1
    """).fetchone()

    total_products = conn.execute("""
        SELECT COUNT(*)
        FROM products
    """).fetchone()[0]

    total_stock = conn.execute("""
        SELECT COALESCE(
            SUM(quantity), 0
        )
        FROM products
    """).fetchone()[0]

    stock_value = conn.execute("""
        SELECT COALESCE(
            SUM(quantity * purchase_price),
            0
        )
        FROM products
    """).fetchone()[0]

    total_sales = conn.execute("""
        SELECT COALESCE(
            SUM(amount), 0
        )
        FROM transactions
        WHERE transaction_type = 'STOCK OUT'
    """).fetchone()[0]

    profit = conn.execute("""
        SELECT COALESCE(
            SUM(profit), 0
        )
        FROM transactions
        WHERE transaction_type = 'STOCK OUT'
    """).fetchone()[0]

    total_cash_out = conn.execute("""
        SELECT COALESCE(
            SUM(amount), 0
        )
        FROM transactions
        WHERE transaction_type = 'CASH OUT'
    """).fetchone()[0]

    low_stock = conn.execute("""
        SELECT COUNT(*)
        FROM products
        WHERE quantity <= 5
    """).fetchone()[0]

    conn.close()

    return jsonify(
        success=True,
        cash_balance=round(
            float(cash["balance"] if cash else 0), 2
        ),
        total_products=total_products,
        total_stock=total_stock,
        stock_value=round(
            float(stock_value), 2
        ),
        total_sales=round(
            float(total_sales), 2
        ),
        profit=round(
            float(profit), 2
        ),
        total_cash_out=round(
            float(total_cash_out), 2
        ),
        low_stock=low_stock
    )


# =========================================================
# CASH PAGE
# =========================================================

CASH_HTML = """
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<title>Cash Management</title>

<style>

body {
    font-family: Arial;
    background: #f1f5f9;
    padding: 30px;
}

.container {
    max-width: 700px;
    margin: auto;
}

.box {
    background: white;
    padding: 30px;
    border-radius: 15px;
    margin-bottom: 20px;
}

input {
    width: 100%;
    padding: 13px;
    margin: 10px 0;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
}

button {
    width: 100%;
    padding: 14px;
    border: none;
    border-radius: 8px;
    color: white;
    font-weight: bold;
    cursor: pointer;
    margin-top: 10px;
}

.in {
    background: #16a34a;
}

.out {
    background: #ef4444;
}

.balance {
    font-size: 35px;
    font-weight: bold;
    color: #16a34a;
}

</style>

</head>

<body>

<div class="container">

<a href="/dashboard">
← Dashboard
</a>

<h1>
💰 Cash Management
</h1>

<div class="box">

<div>
Current Cash Balance
</div>

<div id="balance"
class="balance">
0
</div>

</div>

<div class="box">

<h2>
➕ Cash In
</h2>

<input
id="cashInAmount"
type="number"
min="0.01"
step="0.01"
placeholder="Amount"
>

<input
id="cashInDescription"
type="text"
placeholder="Description"
>

<button
class="in"
onclick="cashIn()">

ADD CASH

</button>

</div>

<div class="box">

<h2>
➖ Cash Out
</h2>

<input
id="cashOutAmount"
type="number"
min="0.01"
step="0.01"
placeholder="Amount"
>

<input
id="cashOutDescription"
type="text"
placeholder="Description"
>

<button
class="out"
onclick="cashOut()">

REMOVE CASH

</button>

</div>

</div>

<script>

async function loadBalance() {

    const response =
        await fetch("/dashboard-data");

    const data =
        await response.json();

    if(data.success) {

        document.getElementById(
            "balance"
        ).textContent =
            Number(
                data.cash_balance
            ).toLocaleString();

    }
}

async function sendCash(
    type,
    amount,
    description
) {

    const response =
        await fetch(
            "/api/cash",
            {

                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify({
                        type,
                        amount,
                        description
                    })
            }
        );

    const data =
        await response.json();

    alert(data.message);

    if(data.success) {

        loadBalance();

        document.getElementById(
            "cashInAmount"
        ).value = "";

        document.getElementById(
            "cashOutAmount"
        ).value = "";

        document.getElementById(
            "cashInDescription"
        ).value = "";

        document.getElementById(
            "cashOutDescription"
        ).value = "";

    }
}

function cashIn() {

    const amount =
        Number(
            document.getElementById(
                "cashInAmount"
            ).value
        );

    const description =
        document.getElementById(
            "cashInDescription"
        ).value;

    if(amount <= 0) {

        alert(
            "Enter a valid amount."
        );

        return;
    }

    sendCash(
        "CASH IN",
        amount,
        description
    );
}

function cashOut() {

    const amount =
        Number(
            document.getElementById(
                "cashOutAmount"
            ).value
        );

    const description =
        document.getElementById(
            "cashOutDescription"
        ).value;

    if(amount <= 0) {

        alert(
            "Enter a valid amount."
        );

        return;
    }

    sendCash(
        "CASH OUT",
        amount,
        description
    );
}

loadBalance();

</script>

</body>

</html>
"""


@app.route("/cash")
def cash_page():

    if not logged_in():

        return redirect("/")

    return render_template_string(
        CASH_HTML
    )


# =========================================================
# CASH API
# =========================================================

@app.route(
    "/api/cash",
    methods=["POST"]
)
@login_required
def cash_transaction():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify(
            success=False,
            message="Invalid request."
        ), 400

    transaction_type = str(
        data.get("type", "")
    ).upper().strip()

    description = str(
        data.get("description", "")
    ).strip()

    try:

        amount = float(
            data.get("amount")
        )

    except Exception:

        return jsonify(
            success=False,
            message="Invalid amount."
        ), 400

    if amount <= 0:

        return jsonify(
            success=False,
            message="Amount must be greater than zero."
        ), 400

    if transaction_type not in [
        "CASH IN",
        "CASH OUT"
    ]:

        return jsonify(
            success=False,
            message="Invalid cash transaction."
        ), 400

    conn = get_db()

    try:

        row = conn.execute("""
            SELECT balance
            FROM cash_account
            WHERE id = 1
        """).fetchone()

        before = float(row["balance"])

        if (
            transaction_type == "CASH OUT"
            and amount > before
        ):

            conn.close()

            return jsonify(
                success=False,
                message=f"Not enough cash. Available: {before:,.2f} Frw."
            ), 400

        if transaction_type == "CASH IN":

            after = before + amount

        else:

            after = before - amount

        conn.execute("""
            UPDATE cash_account
            SET balance = ?
            WHERE id = 1
        """, (
            after,
        ))

        conn.execute("""
            INSERT INTO transactions
            (
                transaction_type,
                amount,
                cash_before,
                cash_after,
                username,
                description
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            transaction_type,
            amount,
            before,
            after,
            session["username"],
            description
        ))

        conn.commit()

    except Exception as error:

        conn.rollback()
        conn.close()

        print(error)

        return jsonify(
            success=False,
            message="Cash transaction failed."
        ), 500

    conn.close()

    return jsonify(
        success=True,
        message=(
            f"{transaction_type} successful. "
            f"New balance: {after:,.2f} Frw"
        )
    )


# =========================================================
# PRODUCTS PAGE
# =========================================================

PRODUCTS_HTML = """
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<title>Products</title>

<style>

body {
    font-family: Arial;
    background: #f1f5f9;
    padding: 25px;
}

.container {
    max-width: 1400px;
    margin: auto;
}

.box {
    background: white;
    padding: 25px;
    border-radius: 15px;
    margin-bottom: 20px;
}

.grid {
    display: grid;
    grid-template-columns:
        2fr 1fr 1fr 1fr auto;
    gap: 10px;
}

input {
    padding: 12px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
}

button {
    border: none;
    border-radius: 8px;
    padding: 12px 18px;
    cursor: pointer;
    font-weight: bold;
}

.add {
    background: #16a34a;
    color: white;
}

.delete {
    background: #ef4444;
    color: white;
}

.edit {
    background: #2563eb;
    color: white;
    margin: 3px;
}

.stockedit {
    background: #7c3aed;
    color: white;
    margin: 3px;
}

table {
    width: 100%;
    border-collapse: collapse;
    background: white;
}

th,
td {
    padding: 13px;
    border-bottom: 1px solid #ddd;
    text-align: left;
}

th {
    background: #0f172a;
    color: white;
}

@media(max-width:900px) {

    .grid {
        grid-template-columns: 1fr;
    }

    .table-box {
        overflow-x: auto;
    }

}

</style>

</head>

<body>

<div class="container">

<a href="/dashboard">
← Dashboard
</a>

<h1>
📦 Products
</h1>

<div class="box">

<h2>
Add Product
</h2>

<div class="grid">

<input
id="name"
placeholder="Product name"
>

<input
id="quantity"
type="number"
min="0"
placeholder="Initial quantity"
>

<input
id="purchase"
type="number"
min="0"
step="0.01"
placeholder="Purchase price"
>

<input
id="selling"
type="number"
min="0"
step="0.01"
placeholder="Selling price"
>

<button
class="add"
onclick="addProduct()">

ADD PRODUCT

</button>

</div>

<p>
💡 Initial stock is recorded without removing
cash. Use Stock In when buying new stock.
</p>

</div>

<div class="table-box">

<table>

<thead>

<tr>

<th>ID</th>
<th>Product</th>
<th>Stock</th>
<th>Purchase Price</th>
<th>Selling Price</th>
<th>Profit / Unit</th>
<th>Actions</th>

</tr>

</thead>

<tbody id="products">
</tbody>

</table>

</div>

</div>

<script>

async function loadProducts() {

    const response =
        await fetch("/api/products");

    const data =
        await response.json();

    const table =
        document.getElementById(
            "products"
        );

    table.innerHTML = "";

    if(!data.success) {

        alert(data.message);
        return;

    }

    data.products.forEach(
        p => {

            const profit =
                Number(p.selling_price)
                -
                Number(p.purchase_price);

            table.innerHTML += `

            <tr>

            <td>${p.id}</td>

            <td>${p.name}</td>

            <td>${p.quantity}</td>

            <td>
            ${Number(
                p.purchase_price
            ).toLocaleString()}
            </td>

            <td>
            ${Number(
                p.selling_price
            ).toLocaleString()}
            </td>

            <td>
            ${profit.toLocaleString()}
            </td>

            <td>

            <button
            class="edit"
            onclick="editProduct(${p.id})">
            EDIT PRICE
            </button>

            <button
            class="stockedit"
            onclick="editStock(${p.id}, ${p.quantity})">
            EDIT STOCK
            </button>

            <button
            class="delete"
            onclick="deleteProduct(${p.id})">
            DELETE
            </button>

            </td>

            </tr>

            `;

        }
    );

}


async function addProduct() {

    const name =
        document.getElementById(
            "name"
        ).value.trim();

    const quantity =
        Number(
            document.getElementById(
                "quantity"
            ).value
        );

    const purchase =
        Number(
            document.getElementById(
                "purchase"
            ).value
        );

    const selling =
        Number(
            document.getElementById(
                "selling"
            ).value
        );

    if(!name) {

        alert(
            "Product name is required."
        );

        return;
    }

    if(
        quantity < 0 ||
        purchase < 0 ||
        selling < 0
    ) {

        alert(
            "Values cannot be negative."
        );

        return;
    }

    const response =
        await fetch(
            "/api/products",
            {

                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify({

                        name,
                        quantity,
                        purchase_price:
                            purchase,
                        selling_price:
                            selling

                    })
            }
        );

    const data =
        await response.json();

    alert(data.message);

    if(data.success) {

        document.getElementById(
            "name"
        ).value = "";

        document.getElementById(
            "quantity"
        ).value = "";

        document.getElementById(
            "purchase"
        ).value = "";

        document.getElementById(
            "selling"
        ).value = "";

        loadProducts();

    }

}


async function editProduct(id) {

    const name =
        prompt(
            "New product name:"
        );

    if(
        name === null ||
        !name.trim()
    ) return;

    const purchase =
        prompt(
            "New purchase price:"
        );

    if(purchase === null) return;

    const selling =
        prompt(
            "New selling price:"
        );

    if(selling === null) return;

    const response =
        await fetch(
            "/api/products/" + id,
            {

                method: "PUT",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify({

                        name:
                            name.trim(),

                        purchase_price:
                            Number(purchase),

                        selling_price:
                            Number(selling)

                    })
            }
        );

    const data =
        await response.json();

    alert(data.message);

    if(data.success)
        loadProducts();

}


async function editStock(
    id,
    currentQuantity
) {

    const newQuantity =
        prompt(
            `Current stock: ${currentQuantity}

Enter the CORRECT total stock quantity:`
        );

    if(newQuantity === null)
        return;

    const quantity =
        Number(newQuantity);

    if(
        !Number.isInteger(quantity) ||
        quantity < 0
    ) {

        alert(
            "Enter a valid whole number."
        );

        return;
    }

    const reason =
        prompt(
            "Reason for stock correction:"
        );

    if(reason === null)
        return;

    const response =
        await fetch(
            "/api/products/" + id + "/stock",
            {

                method: "PUT",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify({

                        quantity,
                        reason

                    })
            }
        );

    const data =
        await response.json();

    alert(data.message);

    if(data.success)
        loadProducts();

}


async function deleteProduct(id) {

    if(
        !confirm(
            "Delete this product?"
        )
    ) return;

    const response =
        await fetch(
            "/api/products/" + id,
            {
                method: "DELETE"
            }
        );

    const data =
        await response.json();

    alert(data.message);

    if(data.success)
        loadProducts();

}


loadProducts();

</script>

</body>

</html>
"""


@app.route("/products")
def products_page():

    if not logged_in():

        return redirect("/")

    return render_template_string(
        PRODUCTS_HTML
    )


# =========================================================
# GET PRODUCTS
# =========================================================

@app.route("/api/products")
@login_required
def get_products():

    conn = get_db()

    products = conn.execute("""
        SELECT *
        FROM products
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return jsonify(
        success=True,
        products=[
            dict(p)
            for p in products
        ]
    )


# =========================================================
# ADD PRODUCT
# =========================================================

@app.route(
    "/api/products",
    methods=["POST"]
)
@login_required
def add_product():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify(
            success=False,
            message="Invalid request."
        ), 400

    name = str(
        data.get("name", "")
    ).strip()

    try:

        quantity = int(
            data.get("quantity", 0)
        )

        purchase = float(
            data.get(
                "purchase_price",
                0
            )
        )

        selling = float(
            data.get(
                "selling_price",
                0
            )
        )

    except Exception:

        return jsonify(
            success=False,
            message="Invalid numbers."
        ), 400

    if not name:

        return jsonify(
            success=False,
            message="Product name is required."
        ), 400

    if quantity < 0:

        return jsonify(
            success=False,
            message="Quantity cannot be negative."
        ), 400

    if purchase < 0 or selling < 0:

        return jsonify(
            success=False,
            message="Prices cannot be negative."
        ), 400

    conn = get_db()

    try:

        cursor = conn.execute("""
            INSERT INTO products
            (
                name,
                quantity,
                purchase_price,
                selling_price
            )
            VALUES (?, ?, ?, ?)
        """, (
            name,
            quantity,
            purchase,
            selling
        ))

        product_id = cursor.lastrowid

        if quantity > 0:

            conn.execute("""
                INSERT INTO history
                (
                    product_id,
                    product_name,
                    action,
                    quantity,
                    previous_quantity,
                    new_quantity,
                    username
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                product_id,
                name,
                "INITIAL STOCK",
                quantity,
                0,
                quantity,
                session["username"]
            ))

        conn.commit()

    except sqlite3.IntegrityError:

        conn.rollback()
        conn.close()

        return jsonify(
            success=False,
            message="Product already exists."
        ), 409

    conn.close()

    return jsonify(
        success=True,
        message=f"{name} added successfully."
    )


# =========================================================
# EDIT PRODUCT PRICE
# =========================================================

@app.route(
    "/api/products/<int:product_id>",
    methods=["PUT"]
)
@login_required
def edit_product(product_id):

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify(
            success=False,
            message="Invalid request."
        ), 400

    name = str(
        data.get("name", "")
    ).strip()

    try:

        purchase = float(
            data.get("purchase_price")
        )

        selling = float(
            data.get("selling_price")
        )

    except Exception:

        return jsonify(
            success=False,
            message="Invalid price."
        ), 400

    if not name:

        return jsonify(
            success=False,
            message="Product name is required."
        ), 400

    if purchase < 0 or selling < 0:

        return jsonify(
            success=False,
            message="Prices cannot be negative."
        ), 400

    conn = get_db()

    product = conn.execute("""
        SELECT *
        FROM products
        WHERE id = ?
    """, (
        product_id,
    )).fetchone()

    if not product:

        conn.close()

        return jsonify(
            success=False,
            message="Product not found."
        ), 404

    try:

        conn.execute("""
            UPDATE products
            SET
                name = ?,
                purchase_price = ?,
                selling_price = ?
            WHERE id = ?
        """, (
            name,
            purchase,
            selling,
            product_id
        ))

        conn.commit()

    except sqlite3.IntegrityError:

        conn.rollback()
        conn.close()

        return jsonify(
            success=False,
            message="Another product already has that name."
        ), 409

    conn.close()

    return jsonify(
        success=True,
        message="Product updated successfully."
    )


# =========================================================
# ⭐ EDIT STOCK WITH AUTOMATIC CASH CORRECTION
# =========================================================

@app.route(
    "/api/products/<int:product_id>/stock",
    methods=["PUT"]
)
@login_required
def edit_stock(product_id):

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify(
            success=False,
            message="Invalid request."
        ), 400

    try:

        new_quantity = int(
            data.get("quantity")
        )

    except Exception:

        return jsonify(
            success=False,
            message="Invalid quantity."
        ), 400

    reason = str(
        data.get(
            "reason",
            "Stock correction"
        )
    ).strip()

    if new_quantity < 0:

        return jsonify(
            success=False,
            message="Quantity cannot be negative."
        ), 400

    conn = get_db()

    try:

        product = conn.execute("""
            SELECT *
            FROM products
            WHERE id = ?
        """, (
            product_id,
        )).fetchone()

        if not product:

            conn.close()

            return jsonify(
                success=False,
                message="Product not found."
            ), 404

        old_quantity = int(
            product["quantity"]
        )

        purchase_price = float(
            product["purchase_price"]
        )

        difference = (
            new_quantity -
            old_quantity
        )

        # -------------------------------------------------
        # NO CHANGE
        # -------------------------------------------------

        if difference == 0:

            conn.close()

            return jsonify(
                success=True,
                message="No stock change was necessary."
            )

        # -------------------------------------------------
        # GET CASH
        # -------------------------------------------------

        cash_row = conn.execute("""
            SELECT balance
            FROM cash_account
            WHERE id = 1
        """).fetchone()

        cash_before = float(
            cash_row["balance"]
        )

        # -------------------------------------------------
        # INCREASE STOCK
        #
        # Example:
        # old = 2
        # new = 3
        # difference = +1
        #
        # Cash decreases by purchase price.
        # -------------------------------------------------

        if difference > 0:

            correction_cost = (
                difference *
                purchase_price
            )

            if correction_cost > cash_before:

                conn.close()

                return jsonify(
                    success=False,
                    message=(
                        f"Not enough cash for this "
                        f"stock increase.\n\n"
                        f"Additional stock: {difference}\n"
                        f"Cost: {correction_cost:,.2f} Frw\n"
                        f"Available cash: {cash_before:,.2f} Frw"
                    )
                ), 400

            cash_after = (
                cash_before -
                correction_cost
            )

            description = (
                f"Stock correction +{difference}. "
                f"{reason}"
            )

            transaction_type = "STOCK EDIT IN"

            amount = correction_cost

        # -------------------------------------------------
        # DECREASE STOCK
        #
        # Example:
        # old = 3
        # new = 2
        # difference = -1
        #
        # Cash increases because the system reverses
        # the purchase cost of the removed stock.
        # -------------------------------------------------

        else:

            removed_quantity = abs(
                difference
            )

            correction_value = (
                removed_quantity *
                purchase_price
            )

            cash_after = (
                cash_before +
                correction_value
            )

            description = (
                f"Stock correction -{removed_quantity}. "
                f"{reason}"
            )

            transaction_type = "STOCK EDIT OUT"

            amount = correction_value

        # -------------------------------------------------
        # UPDATE STOCK
        # -------------------------------------------------

        conn.execute("""
            UPDATE products
            SET quantity = ?
            WHERE id = ?
        """, (
            new_quantity,
            product_id
        ))

        # -------------------------------------------------
        # UPDATE CASH
        # -------------------------------------------------

        conn.execute("""
            UPDATE cash_account
            SET balance = ?
            WHERE id = 1
        """, (
            cash_after,
        ))

        # -------------------------------------------------
        # TRANSACTION
        # -------------------------------------------------

        conn.execute("""
            INSERT INTO transactions
            (
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
                description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            transaction_type,
            product_id,
            product["name"],
            abs(difference),
            purchase_price,
            product["selling_price"],
            amount,
            amount if difference > 0 else -amount,
            0,
            cash_before,
            cash_after,
            old_quantity,
            new_quantity,
            session["username"],
            description
        ))

        # -------------------------------------------------
        # HISTORY
        # -------------------------------------------------

        conn.execute("""
            INSERT INTO history
            (
                product_id,
                product_name,
                action,
                quantity,
                previous_quantity,
                new_quantity,
                username
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            product_id,
            product["name"],
            transaction_type,
            abs(difference),
            old_quantity,
            new_quantity,
            session["username"]
        ))

        conn.commit()

    except Exception as error:

        conn.rollback()
        conn.close()

        print(error)

        return jsonify(
            success=False,
            message="Stock correction failed. No changes were saved."
        ), 500

    conn.close()

    if difference > 0:

        message = (
            f"STOCK UPDATED!\n\n"
            f"Product: {product['name']}\n"
            f"Old stock: {old_quantity}\n"
            f"New stock: {new_quantity}\n"
            f"Added: {difference}\n"
            f"Cost: {amount:,.2f} Frw\n"
            f"Cash remaining: {cash_after:,.2f} Frw"
        )

    else:

        message = (
            f"STOCK UPDATED!\n\n"
            f"Product: {product['name']}\n"
            f"Old stock: {old_quantity}\n"
            f"New stock: {new_quantity}\n"
            f"Removed: {abs(difference)}\n"
            f"Cash returned: {amount:,.2f} Frw\n"
            f"New cash: {cash_after:,.2f} Frw"
        )

    return jsonify(
        success=True,
        message=message
    )


# =========================================================
# DELETE PRODUCT
# =========================================================

@app.route(
    "/api/products/<int:product_id>",
    methods=["DELETE"]
)
@login_required
def delete_product(product_id):

    conn = get_db()

    product = conn.execute("""
        SELECT *
        FROM products
        WHERE id = ?
    """, (
        product_id,
    )).fetchone()

    if not product:

        conn.close()

        return jsonify(
            success=False,
            message="Product not found."
        ), 404

    if product["quantity"] > 0:

        conn.close()

        return jsonify(
            success=False,
            message=(
                "You cannot delete a product "
                "while stock is still available."
            )
        ), 400

    conn.execute("""
        DELETE FROM products
        WHERE id = ?
    """, (
        product_id,
    ))

    conn.commit()
    conn.close()

    return jsonify(
        success=True,
        message="Product deleted successfully."
    )


# =========================================================
# STOCK IN PAGE
# =========================================================

STOCK_IN_HTML = """
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<title>Stock In</title>

<style>

body {
    font-family: Arial;
    background: #f1f5f9;
    padding: 30px;
}

.container {
    max-width: 650px;
    margin: auto;
}

.box {
    background: white;
    padding: 30px;
    border-radius: 15px;
}

select,
input {
    width: 100%;
    padding: 14px;
    margin: 10px 0 20px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
}

button {
    width: 100%;
    padding: 14px;
    background: #16a34a;
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: bold;
    cursor: pointer;
}

.info {
    background: #eff6ff;
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 20px;
}

</style>

</head>

<body>

<div class="container">

<a href="/dashboard">
← Dashboard
</a>

<h1>
➕ Stock In
</h1>

<div class="box">

<div class="info">

<strong>
Stock In Calculation
</strong>

<br><br>

The system automatically calculates:

<br><br>

Quantity × Purchase Price

<br><br>

The cost is removed from Cash Balance.

</div>

<label>
Product
</label>

<select id="product">

<option value="">
Select product
</option>

</select>

<label>
Quantity
</label>

<input
id="quantity"
type="number"
min="1"
placeholder="Quantity"
>

<button
onclick="stockIn()">

ADD STOCK

</button>

</div>

</div>

<script>

async function loadProducts() {

    const response =
        await fetch("/api/products");

    const data =
        await response.json();

    const select =
        document.getElementById(
            "product"
        );

    select.innerHTML =
        '<option value="">Select product</option>';

    data.products.forEach(
        p => {

            select.innerHTML += `

            <option value="${p.id}">

            ${p.name}
            — Stock: ${p.quantity}
            — Buy:
            ${Number(
                p.purchase_price
            ).toLocaleString()}

            </option>

            `;

        }
    );
}


async function stockIn() {

    const productId =
        document.getElementById(
            "product"
        ).value;

    const quantity =
        Number(
            document.getElementById(
                "quantity"
            ).value
        );

    if(
        !productId ||
        quantity <= 0
    ) {

        alert(
            "Select a product and enter valid quantity."
        );

        return;
    }

    const response =
        await fetch(
            "/api/stock-in",
            {

                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify({

                        product_id:
                            Number(productId),

                        quantity

                    })
            }
        );

    const data =
        await response.json();

    alert(data.message);

    if(data.success) {

        document.getElementById(
            "quantity"
        ).value = "";

        loadProducts();

    }
}


loadProducts();

</script>

</body>

</html>
"""


@app.route("/stock-in")
def stock_in_page():

    if not logged_in():

        return redirect("/")

    return render_template_string(
        STOCK_IN_HTML
    )


# =========================================================
# ⭐ STOCK IN API WITH AVERAGE PURCHASE PRICE
# =========================================================

@app.route(
    "/api/stock-in",
    methods=["POST"]
)
@login_required
def stock_in():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify(
            success=False,
            message="Invalid request."
        ), 400

    try:

        product_id = int(
            data.get("product_id")
        )

        quantity = int(
            data.get("quantity")
        )

    except Exception:

        return jsonify(
            success=False,
            message="Invalid product or quantity."
        ), 400

    if quantity <= 0:

        return jsonify(
            success=False,
            message="Quantity must be greater than zero."
        ), 400

    conn = get_db()

    try:

        product = conn.execute("""
            SELECT *
            FROM products
            WHERE id = ?
        """, (
            product_id,
        )).fetchone()

        if not product:

            conn.close()

            return jsonify(
                success=False,
                message="Product not found."
            ), 404

        old_stock = int(
            product["quantity"]
        )

        old_purchase_price = float(
            product["purchase_price"]
        )

        selling_price = float(
            product["selling_price"]
        )

        # -------------------------------------------------
        # USER CAN ENTER PURCHASE PRICE FOR THIS STOCK IN
        # -------------------------------------------------

        # If frontend did not send it, use current price.
        new_purchase_price = float(
            data.get(
                "purchase_price",
                old_purchase_price
            )
        )

        if new_purchase_price < 0:

            conn.close()

            return jsonify(
                success=False,
                message="Purchase price cannot be negative."
            ), 400

        cost = (
            quantity *
            new_purchase_price
        )

        cash_row = conn.execute("""
            SELECT balance
            FROM cash_account
            WHERE id = 1
        """).fetchone()

        cash_before = float(
            cash_row["balance"]
        )

        if cost > cash_before:

            conn.close()

            return jsonify(
                success=False,
                message=(
                    f"Not enough cash.\n\n"
                    f"Stock cost: {cost:,.2f} Frw\n"
                    f"Available cash: {cash_before:,.2f} Frw\n\n"
                    f"Use Cash In first."
                )
            ), 400

        new_stock = (
            old_stock +
            quantity
        )

        cash_after = (
            cash_before -
            cost
        )

        # -------------------------------------------------
        # AVERAGE PURCHASE PRICE
        # -------------------------------------------------

        if new_stock > 0:

            total_old_value = (
                old_stock *
                old_purchase_price
            )

            total_new_value = (
                quantity *
                new_purchase_price
            )

            average_price = (
                total_old_value +
                total_new_value
            ) / new_stock

        else:

            average_price = new_purchase_price

        # -------------------------------------------------
        # UPDATE PRODUCT
        # -------------------------------------------------

        conn.execute("""
            UPDATE products
            SET
                quantity = ?,
                purchase_price = ?
            WHERE id = ?
        """, (
            new_stock,
            average_price,
            product_id
        ))

        # -------------------------------------------------
        # UPDATE CASH
        # -------------------------------------------------

        conn.execute("""
            UPDATE cash_account
            SET balance = ?
            WHERE id = 1
        """, (
            cash_after,
        ))

        # -------------------------------------------------
        # TRANSACTION
        # -------------------------------------------------

        conn.execute("""
            INSERT INTO transactions
            (
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
                description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "STOCK IN",
            product_id,
            product["name"],
            quantity,
            new_purchase_price,
            selling_price,
            cost,
            cost,
            0,
            cash_before,
            cash_after,
            old_stock,
            new_stock,
            session["username"],
            (
                f"Stock purchased at "
                f"{new_purchase_price:,.2f} Frw/unit. "
                f"Average cost now "
                f"{average_price:,.2f} Frw/unit."
            )
        ))

        # -------------------------------------------------
        # HISTORY
        # -------------------------------------------------

        conn.execute("""
            INSERT INTO history
            (
                product_id,
                product_name,
                action,
                quantity,
                previous_quantity,
                new_quantity,
                username
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            product_id,
            product["name"],
            "STOCK IN",
            quantity,
            old_stock,
            new_stock,
            session["username"]
        ))

        conn.commit()

    except Exception as error:

        conn.rollback()
        conn.close()

        print(error)

        return jsonify(
            success=False,
            message="Stock In failed. No changes were saved."
        ), 500

    conn.close()

    return jsonify(
        success=True,
        message=(
            f"STOCK IN SUCCESSFUL!\n\n"
            f"Product: {product['name']}\n"
            f"Added: {quantity}\n"
            f"Purchase price: {new_purchase_price:,.2f} Frw\n"
            f"Purchase cost: {cost:,.2f} Frw\n"
            f"New stock: {new_stock}\n"
            f"Average purchase price: "
            f"{average_price:,.2f} Frw\n"
            f"Cash remaining: {cash_after:,.2f} Frw"
        )
    )


# =========================================================
# STOCK OUT PAGE
# =========================================================

STOCK_OUT_HTML = """
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<title>Stock Out</title>

<style>

body {
    font-family: Arial;
    background: #f1f5f9;
    padding: 30px;
}

.container {
    max-width: 650px;
    margin: auto;
}

.box {
    background: white;
    padding: 30px;
    border-radius: 15px;
}

select,
input {
    width: 100%;
    padding: 14px;
    margin: 10px 0 20px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
}

button {
    width: 100%;
    padding: 14px;
    background: #ef4444;
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: bold;
    cursor: pointer;
}

.info {
    background: #f0fdf4;
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 20px;
}

</style>

</head>

<body>

<div class="container">

<a href="/dashboard">
← Dashboard
</a>

<h1>
🛒 Stock Out / Sale
</h1>

<div class="box">

<div class="info">

<strong>
Automatic Sale Calculation
</strong>

<br><br>

Sales = Quantity × Selling Price

<br>

Cost = Quantity × Purchase Price

<br>

Profit = Sales − Cost

<br>

Cash increases by Sales.

</div>

<label>
Product
</label>

<select id="product">

<option value="">
Select product
</option>

</select>

<label>
Quantity Sold
</label>

<input
id="quantity"
type="number"
min="1"
placeholder="Quantity sold"
>

<button
onclick="stockOut()">

SELL / REMOVE STOCK

</button>

</div>

</div>

<script>

async function loadProducts() {

    const response =
        await fetch("/api/products");

    const data =
        await response.json();

    const select =
        document.getElementById(
            "product"
        );

    select.innerHTML =
        '<option value="">Select product</option>';

    data.products.forEach(
        p => {

            select.innerHTML += `

            <option value="${p.id}">

            ${p.name}
            — Stock: ${p.quantity}
            — Sell:
            ${Number(
                p.selling_price
            ).toLocaleString()}

            </option>

            `;

        }
    );
}


async function stockOut() {

    const productId =
        document.getElementById(
            "product"
        ).value;

    const quantity =
        Number(
            document.getElementById(
                "quantity"
            ).value
        );

    if(
        !productId ||
        quantity <= 0
    ) {

        alert(
            "Select a product and enter valid quantity."
        );

        return;
    }

    const response =
        await fetch(
            "/api/stock-out",
            {

                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify({

                        product_id:
                            Number(productId),

                        quantity

                    })
            }
        );

    const data =
        await response.json();

    alert(data.message);

    if(data.success) {

        document.getElementById(
            "quantity"
        ).value = "";

        loadProducts();

    }
}


loadProducts();

</script>

</body>

</html>
"""


@app.route("/stock-out")
def stock_out_page():

    if not logged_in():

        return redirect("/")

    return render_template_string(
        STOCK_OUT_HTML
    )


# =========================================================
# STOCK OUT API
# =========================================================

@app.route(
    "/api/stock-out",
    methods=["POST"]
)
@login_required
def stock_out():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify(
            success=False,
            message="Invalid request."
        ), 400

    try:

        product_id = int(
            data.get("product_id")
        )

        quantity = int(
            data.get("quantity")
        )

    except Exception:

        return jsonify(
            success=False,
            message="Invalid product or quantity."
        ), 400

    if quantity <= 0:

        return jsonify(
            success=False,
            message="Quantity must be greater than zero."
        ), 400

    conn = get_db()

    try:

        product = conn.execute("""
            SELECT *
            FROM products
            WHERE id = ?
        """, (
            product_id,
        )).fetchone()

        if not product:

            conn.close()

            return jsonify(
                success=False,
                message="Product not found."
            ), 404

        old_stock = int(
            product["quantity"]
        )

        if quantity > old_stock:

            conn.close()

            return jsonify(
                success=False,
                message=(
                    f"Not enough stock. "
                    f"Available: {old_stock}."
                )
            ), 400

        purchase_price = float(
            product["purchase_price"]
        )

        selling_price = float(
            product["selling_price"]
        )

        sales_amount = (
            quantity *
            selling_price
        )

        cost_amount = (
            quantity *
            purchase_price
        )

        profit = (
            sales_amount -
            cost_amount
        )

        cash_row = conn.execute("""
            SELECT balance
            FROM cash_account
            WHERE id = 1
        """).fetchone()

        cash_before = float(
            cash_row["balance"]
        )

        cash_after = (
            cash_before +
            sales_amount
        )

        new_stock = (
            old_stock -
            quantity
        )

        conn.execute("""
            UPDATE products
            SET quantity = ?
            WHERE id = ?
        """, (
            new_stock,
            product_id
        ))

        conn.execute("""
            UPDATE cash_account
            SET balance = ?
            WHERE id = 1
        """, (
            cash_after,
        ))

        conn.execute("""
            INSERT INTO transactions
            (
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
                description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "STOCK OUT",
            product_id,
            product["name"],
            quantity,
            purchase_price,
            selling_price,
            sales_amount,
            cost_amount,
            profit,
            cash_before,
            cash_after,
            old_stock,
            new_stock,
            session["username"],
            f"Sale. Profit: {profit:,.2f}"
        ))

        conn.execute("""
            INSERT INTO history
            (
                product_id,
                product_name,
                action,
                quantity,
                previous_quantity,
                new_quantity,
                username
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            product_id,
            product["name"],
            "STOCK OUT",
            quantity,
            old_stock,
            new_stock,
            session["username"]
        ))

        conn.commit()

    except Exception as error:

        conn.rollback()
        conn.close()

        print(error)

        return jsonify(
            success=False,
            message="Sale failed. No changes were saved."
        ), 500

    conn.close()

    return jsonify(
        success=True,
        message=(
            f"SALE SUCCESSFUL!\n\n"
            f"Product: {product['name']}\n"
            f"Quantity sold: {quantity}\n"
            f"Sales: {sales_amount:,.2f} Frw\n"
            f"Cost: {cost_amount:,.2f} Frw\n"
            f"PROFIT: {profit:,.2f} Frw\n"
            f"Remaining stock: {new_stock}\n"
            f"New cash: {cash_after:,.2f} Frw"
        )
    )


# =========================================================
# HISTORY PAGE
# =========================================================

HISTORY_HTML = """
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<title>Transaction History</title>

<style>

body {
    font-family: Arial;
    background: #f1f5f9;
    padding: 25px;
}

.container {
    max-width: 1500px;
    margin: auto;
}

.table-box {
    overflow-x: auto;
}

table {
    width: 100%;
    border-collapse: collapse;
    background: white;
}

th,
td {
    padding: 12px;
    border-bottom: 1px solid #ddd;
    text-align: left;
    white-space: nowrap;
}

th {
    background: #0f172a;
    color: white;
}

.in {
    color: #16a34a;
    font-weight: bold;
}

.out {
    color: #dc2626;
    font-weight: bold;
}

.profit {
    color: #7c3aed;
    font-weight: bold;
}

</style>

</head>

<body>

<div class="container">

<a href="/dashboard">
← Dashboard
</a>

<h1>
🧾 Transaction History
</h1>

<div class="table-box">

<table>

<thead>

<tr>

<th>ID</th>
<th>Type</th>
<th>Product</th>
<th>Qty</th>
<th>Purchase</th>
<th>Selling</th>
<th>Amount</th>
<th>Cost</th>
<th>Profit</th>
<th>Stock Before</th>
<th>Stock After</th>
<th>Cash Before</th>
<th>Cash After</th>
<th>User</th>
<th>Description</th>
<th>Date</th>

</tr>

</thead>

<tbody id="history">
</tbody>

</table>

</div>

</div>

<script>

async function loadHistory() {

    const response =
        await fetch(
            "/api/transactions"
        );

    const data =
        await response.json();

    const table =
        document.getElementById(
            "history"
        );

    table.innerHTML = "";

    if(!data.success) {

        alert(data.message);
        return;

    }

    data.transactions.forEach(
        t => {

            const typeClass =
                (
                    t.transaction_type === "STOCK IN"
                    ||
                    t.transaction_type === "STOCK EDIT IN"
                    ||
                    t.transaction_type === "CASH IN"
                )
                ?
                "in"
                :
                "out";

            table.innerHTML += `

            <tr>

            <td>${t.id}</td>

            <td class="${typeClass}">
            ${t.transaction_type}
            </td>

            <td>
            ${t.product_name || "-"}
            </td>

            <td>
            ${t.quantity || "-"}
            </td>

            <td>
            ${Number(
                t.purchase_price || 0
            ).toLocaleString()}
            </td>

            <td>
            ${Number(
                t.selling_price || 0
            ).toLocaleString()}
            </td>

            <td>
            ${Number(
                t.amount || 0
            ).toLocaleString()}
            </td>

            <td>
            ${Number(
                t.cost_amount || 0
            ).toLocaleString()}
            </td>

            <td class="profit">
            ${Number(
                t.profit || 0
            ).toLocaleString()}
            </td>

            <td>
            ${t.stock_before || 0}
            </td>

            <td>
            ${t.stock_after || 0}
            </td>

            <td>
            ${Number(
                t.cash_before || 0
            ).toLocaleString()}
            </td>

            <td>
            ${Number(
                t.cash_after || 0
            ).toLocaleString()}
            </td>

            <td>
            ${t.username || "-"}
            </td>

            <td>
            ${t.description || "-"}
            </td>

            <td>
            ${t.created_at}
            </td>

            </tr>

            `;

        }
    );
}


loadHistory();

</script>

</body>

</html>
"""


@app.route("/history")
def history_page():

    if not logged_in():

        return redirect("/")

    return render_template_string(
        HISTORY_HTML
    )


# =========================================================
# TRANSACTIONS API
# =========================================================

@app.route("/api/transactions")
@login_required
def get_transactions():

    conn = get_db()

    transactions = conn.execute("""
        SELECT *
        FROM transactions
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return jsonify(
        success=True,
        transactions=[
            dict(t)
            for t in transactions
        ]
    )


# =========================================================
# OLD HISTORY API
# =========================================================

@app.route("/api/history")
@login_required
def get_history():

    conn = get_db()

    history = conn.execute("""
        SELECT *
        FROM history
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return jsonify(
        success=True,
        history=[
            dict(h)
            for h in history
        ]
    )


# =========================================================
# DEFAULT ADMIN
# =========================================================

def create_default_admin():

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        LIMIT 1
    """).fetchone()

    if not user:

        conn.execute("""
            INSERT INTO users
            (
                username,
                password,
                role
            )
            VALUES (?, ?, ?)
        """, (
            "admin",
            generate_password_hash(
                "admin123"
            ),
            "admin"
        ))

        conn.commit()

        print(
            "Default account created:"
        )

        print(
            "Username: admin"
        )

        print(
            "Password: admin123"
        )

    conn.close()


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    init_database()

    create_default_admin()

    print()
    print("==============================================")
    print("       STOCK MANAGEMENT SYSTEM")
    print("==============================================")
    print()
    print("Server:")
    print("http://127.0.0.1:5000")
    print()
    print("Dashboard:")
    print("http://127.0.0.1:5000/dashboard")
    print()
    print("Default Admin:")
    print("Username: admin")
    print("Password: admin123")
    print()
    print("==============================================")
    print()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )