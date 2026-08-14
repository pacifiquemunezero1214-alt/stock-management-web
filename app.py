from flask import Flask, request, jsonify, send_from_directory, session, redirect, render_template_string
import sqlite3

app = Flask(__name__)
app.secret_key = "stock-management-secret-key"
DATABASE = "stock.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            price REAL NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

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


def logged_in():
    return "user_id" in session


# =========================================================
# HOME / STATIC FILES
# =========================================================

@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/style.css")
def css():
    return send_from_directory(".", "style.css")


@app.route("/script.js")
def javascript():
    return send_from_directory(".", "script.js")


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)

    if not data:
        return jsonify(
            success=False,
            message="Invalid request."
        ), 400

    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    if not username or not password:
        return jsonify(
            success=False,
            message="Username and password are required."
        ), 400

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
        conn.execute(
            """
            INSERT INTO users (username, password)
            VALUES (?, ?)
            """,
            (username, password)
        )

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
        message="Account created successfully!"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)

    if not data:
        return jsonify(
            success=False,
            message="Invalid request."
        ), 400

    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    conn = get_db()

    user = conn.execute(
        """
        SELECT id, username
        FROM users
        WHERE username = ?
        AND password = ?
        """,
        (username, password)
    ).fetchone()

    conn.close()

    if not user:
        return jsonify(
            success=False,
            message="Invalid username or password."
        ), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]

    return jsonify(
        success=True,
        message="Login successful!"
    )


# =========================================================
# DASHBOARD
# =========================================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>Dashboard - Stock Management</title>

    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: Arial, sans-serif;
            background: #f8fafc;
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

        .user-area {
            display: flex;
            align-items: center;
            gap: 15px;
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
            max-width: 1250px;
            margin: auto;
            padding: 35px 25px;
        }

        .header {
            margin-bottom: 30px;
        }

        .header h1 {
            font-size: 30px;
            margin-bottom: 8px;
        }

        .header p {
            color: #64748b;
        }

        .cards {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
        }

        .card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 25px rgba(0,0,0,0.06);
        }

        .card-title {
            color: #64748b;
            font-size: 14px;
            font-weight: bold;
            margin-bottom: 15px;
        }

        .card-number {
            font-size: 32px;
            font-weight: bold;
        }

        .blue {
            color: #2563eb;
        }

        .green {
            color: #16a34a;
        }

        .orange {
            color: #ea580c;
        }

        .red {
            color: #dc2626;
        }

        .menu {
            margin-top: 30px;
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 18px;
        }

        .menu button {
            border: none;
            background: white;
            padding: 22px;
            border-radius: 14px;
            cursor: pointer;
            font-size: 16px;
            font-weight: bold;
            box-shadow: 0 5px 20px rgba(0,0,0,0.06);
            transition: 0.2s;
        }

        .menu button:hover {
            transform: translateY(-2px);
            background: #2563eb;
            color: white;
        }

        @media (max-width: 900px) {
            .cards {
                grid-template-columns: repeat(2, 1fr);
            }

            .menu {
                grid-template-columns: repeat(2, 1fr);
            }
        }

        @media (max-width: 600px) {
            .user-area span {
                display: none;
            }

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
        📦 Stock Management
    </div>

    <div class="user-area">

        <span>
            👤 {{ username }}
        </span>

        <button
            class="logout"
            onclick="location.href='/logout'"
        >
            LOGOUT
        </button>

    </div>

</div>


<div class="container">

    <div class="header">

        <h1>
            Welcome, {{ username }} 👋
        </h1>

        <p>
            Manage your inventory from one place.
        </p>

    </div>


    <div class="cards">

        <div class="card">

            <div class="card-title">
                TOTAL PRODUCTS
            </div>

            <div
                id="totalProducts"
                class="card-number blue"
            >
                0
            </div>

        </div>


        <div class="card">

            <div class="card-title">
                TOTAL STOCK
            </div>

            <div
                id="totalStock"
                class="card-number green"
            >
                0
            </div>

        </div>


        <div class="card">

            <div class="card-title">
                STOCK VALUE
            </div>

            <div
                id="stockValue"
                class="card-number orange"
            >
                0
            </div>

        </div>


        <div class="card">

            <div class="card-title">
                LOW STOCK
            </div>

            <div
                id="lowStock"
                class="card-number red"
            >
                0
            </div>

        </div>

    </div>


    <div class="menu">

        <button onclick="location.href='/products'">
            📦 Products
        </button>

        <button onclick="location.href='/stock-in'">
            ➕ Stock In
        </button>

        <button onclick="location.href='/stock-out'">
            ➖ Stock Out
        </button>

        <button onclick="location.href='/history'">
            📜 History
        </button>

    </div>

</div>


<script>
async function loadDashboard() {

    try {

        const response =
            await fetch("/dashboard-data");

        const data =
            await response.json();

        if (data.success) {

            document.getElementById(
                "totalProducts"
            ).textContent =
                data.total_products;

            document.getElementById(
                "totalStock"
            ).textContent =
                data.total_stock;

            document.getElementById(
                "stockValue"
            ).textContent =
                Number(
                    data.stock_value
                ).toLocaleString();

            document.getElementById(
                "lowStock"
            ).textContent =
                data.low_stock;
        }

    } catch (error) {

        console.error(error);

    }
}

loadDashboard();
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
def dashboard_data():

    if not logged_in():
        return jsonify(
            success=False,
            message="Not logged in."
        ), 401

    conn = get_db()

    total_products = conn.execute(
        "SELECT COUNT(*) FROM products"
    ).fetchone()[0]

    total_stock = conn.execute(
        """
        SELECT COALESCE(SUM(quantity), 0)
        FROM products
        """
    ).fetchone()[0]

    stock_value = conn.execute(
        """
        SELECT COALESCE(
            SUM(quantity * price),
            0
        )
        FROM products
        """
    ).fetchone()[0]

    low_stock = conn.execute(
        """
        SELECT COUNT(*)
        FROM products
        WHERE quantity <= 5
        """
    ).fetchone()[0]

    conn.close()

    return jsonify(
        success=True,
        total_products=total_products,
        total_stock=total_stock,
        stock_value=round(float(stock_value), 2),
        low_stock=low_stock
    )


# =========================================================
# PRODUCTS PAGE
# =========================================================

PRODUCTS_HTML = """
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>Products - Stock Management</title>

<style>

* {
    box-sizing: border-box;
}

body {
    font-family: Arial, sans-serif;
    background: #f8fafc;
    margin: 0;
    padding: 30px;
}

.container {
    max-width: 1200px;
    margin: auto;
}

.top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 25px;
}

h1 {
    color: #0f172a;
}

.back {
    background: #2563eb;
    color: white;
    text-decoration: none;
    padding: 11px 18px;
    border-radius: 8px;
}

.form-box {
    background: white;
    padding: 25px;
    border-radius: 15px;
    margin-bottom: 25px;
    box-shadow: 0 5px 25px rgba(0,0,0,0.06);
}

.form-box h2 {
    margin-bottom: 20px;
}

.form-grid {
    display: grid;
    grid-template-columns: 2fr 1fr 1fr auto;
    gap: 12px;
}

input {
    padding: 13px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    font-size: 15px;
}

.add {
    background: #16a34a;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 13px 20px;
    cursor: pointer;
    font-weight: bold;
}

.add:hover {
    background: #15803d;
}

.search {
    width: 100%;
    padding: 13px;
    margin-bottom: 20px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
}

.table-box {
    overflow-x: auto;
}

table {
    width: 100%;
    border-collapse: collapse;
    background: white;
    box-shadow: 0 5px 25px rgba(0,0,0,0.06);
}

th,
td {
    padding: 15px;
    border-bottom: 1px solid #e2e8f0;
    text-align: left;
}

th {
    background: #0f172a;
    color: white;
}

.delete {
    background: #ef4444;
    color: white;
    border: none;
    padding: 8px 12px;
    border-radius: 6px;
    cursor: pointer;
}

@media (max-width: 800px) {

    .form-grid {
        grid-template-columns: 1fr;
    }

    body {
        padding: 15px;
    }

}

</style>

</head>

<body>

<div class="container">

<div class="top">

<h1>
    📦 Products
</h1>

<a
    href="/dashboard"
    class="back"
>
    ← Dashboard
</a>

</div>


<div class="form-box">

<h2>
    ➕ Add New Product
</h2>

<div class="form-grid">

<input
    id="productName"
    type="text"
    placeholder="Product name"
>

<input
    id="productQuantity"
    type="number"
    min="0"
    placeholder="Initial quantity"
>

<input
    id="productPrice"
    type="number"
    min="0"
    step="0.01"
    placeholder="Price"
>

<button
    class="add"
    onclick="addProduct()"
>
    ADD PRODUCT
</button>

</div>

</div>


<input
    id="search"
    class="search"
    type="text"
    placeholder="🔎 Search product..."
    onkeyup="searchProducts()"
>


<div class="table-box">

<table>

<thead>

<tr>
<th>ID</th>
<th>Product</th>
<th>Quantity</th>
<th>Price</th>
<th>Date</th>
<th>Action</th>
</tr>

</thead>

<tbody id="productTable"></tbody>

</table>

</div>

</div>


<script>

async function loadProducts() {

    try {

        const response =
            await fetch("/api/products");

        const data =
            await response.json();

        const table =
            document.getElementById(
                "productTable"
            );

        table.innerHTML = "";

        if (!data.success) {

            alert(data.message);
            return;

        }

        data.products.forEach(product => {

            const row =
                document.createElement("tr");

            row.innerHTML = `

                <td>${product.id}</td>

                <td>${product.name}</td>

                <td>${product.quantity}</td>

                <td>
                    ${Number(
                        product.price
                    ).toLocaleString()}
                </td>

                <td>
                    ${product.created_at}
                </td>

                <td>

                    <button
                        class="delete"
                        onclick="deleteProduct(
                            ${product.id}
                        )"
                    >
                        DELETE
                    </button>

                </td>

            `;

            table.appendChild(row);

        });

    } catch (error) {

        console.error(error);

        alert(
            "Could not load products."
        );

    }

}


async function addProduct() {

    const name =
        document
        .getElementById(
            "productName"
        )
        .value
        .trim();

    const quantityText =
        document
        .getElementById(
            "productQuantity"
        )
        .value;

    const priceText =
        document
        .getElementById(
            "productPrice"
        )
        .value;


    if (!name) {

        alert(
            "Please enter product name."
        );

        return;

    }


    if (quantityText === "") {

        alert(
            "Please enter quantity."
        );

        return;

    }


    if (priceText === "") {

        alert(
            "Please enter price."
        );

        return;

    }


    const quantity =
        Number(quantityText);

    const price =
        Number(priceText);


    if (
        !Number.isInteger(quantity) ||
        quantity < 0
    ) {

        alert(
            "Quantity must be a valid whole number."
        );

        return;

    }


    if (
        !Number.isFinite(price) ||
        price < 0
    ) {

        alert(
            "Price must be a valid number."
        );

        return;

    }


    try {

        const response =
            await fetch(
                "/api/products",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        name: name,
                        quantity: quantity,
                        price: price
                    })
                }
            );


        const data =
            await response.json();


        alert(data.message);


        if (data.success) {

            document.getElementById(
                "productName"
            ).value = "";

            document.getElementById(
                "productQuantity"
            ).value = "";

            document.getElementById(
                "productPrice"
            ).value = "";

            await loadProducts();

        }

    } catch (error) {

        console.error(error);

        alert(
            "Cannot connect to Flask server."
        );

    }

}


async function deleteProduct(id) {

    if (
        !confirm(
            "Are you sure you want to delete this product?"
        )
    ) {
        return;
    }


    try {

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


        if (data.success) {

            await loadProducts();

        }

    } catch (error) {

        console.error(error);

        alert(
            "Could not delete product."
        );

    }

}


function searchProducts() {

    const value =
        document
        .getElementById(
            "search"
        )
        .value
        .toLowerCase();


    document
        .querySelectorAll(
            "#productTable tr"
        )
        .forEach(row => {

            row.style.display =
                row
                .textContent
                .toLowerCase()
                .includes(value)
                ? ""
                : "none";

        });

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
# PRODUCTS API - GET
# =========================================================

@app.route("/api/products", methods=["GET"])
def get_products():

    if not logged_in():
        return jsonify(
            success=False,
            message="Not logged in."
        ), 401

    conn = get_db()

    products = conn.execute(
        """
        SELECT *
        FROM products
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return jsonify(
        success=True,
        products=[
            dict(product)
            for product in products
        ]
    )


# =========================================================
# PRODUCTS API - ADD
# =========================================================

@app.route("/api/products", methods=["POST"])
def add_product():

    if not logged_in():
        return jsonify(
            success=False,
            message="Not logged in."
        ), 401

    data = request.get_json(silent=True)

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

        price = float(
            data.get("price", 0)
        )

    except (ValueError, TypeError):

        return jsonify(
            success=False,
            message="Quantity and price must be numbers."
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

    if price < 0:
        return jsonify(
            success=False,
            message="Price cannot be negative."
        ), 400

    conn = get_db()

    try:

        cursor = conn.execute(
            """
            INSERT INTO products
            (name, quantity, price)
            VALUES (?, ?, ?)
            """,
            (
                name,
                quantity,
                price
            )
        )

        product_id = cursor.lastrowid


        if quantity > 0:

            conn.execute(
                """
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
                """,
                (
                    product_id,
                    name,
                    "INITIAL STOCK",
                    quantity,
                    0,
                    quantity,
                    session["username"]
                )
            )


        conn.commit()

    except sqlite3.IntegrityError:

        conn.rollback()
        conn.close()

        return jsonify(
            success=False,
            message="This product already exists."
        ), 409

    except Exception as error:

        conn.rollback()
        conn.close()

        print(
            "ADD PRODUCT ERROR:",
            error
        )

        return jsonify(
            success=False,
            message="An error occurred while adding the product."
        ), 500

    conn.close()

    return jsonify(
        success=True,
        message=f"{name} added successfully!"
    )


# =========================================================
# DELETE PRODUCT
# =========================================================

@app.route(
    "/api/products/<int:product_id>",
    methods=["DELETE"]
)
def delete_product(product_id):

    if not logged_in():

        return jsonify(
            success=False,
            message="Not logged in."
        ), 401

    conn = get_db()

    product = conn.execute(
        """
        SELECT *
        FROM products
        WHERE id = ?
        """,
        (product_id,)
    ).fetchone()

    if not product:

        conn.close()

        return jsonify(
            success=False,
            message="Product not found."
        ), 404

    conn.execute(
        """
        DELETE FROM products
        WHERE id = ?
        """,
        (product_id,)
    )

    conn.commit()
    conn.close()

    return jsonify(
        success=True,
        message="Product deleted successfully!"
    )


# =========================================================
# STOCK IN PAGE
# =========================================================

STOCK_IN_HTML = """
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>Stock In</title>

<style>

body {
    font-family: Arial, sans-serif;
    background: #f8fafc;
    margin: 0;
    padding: 30px;
}

.container {
    max-width: 700px;
    margin: auto;
}

.top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 25px;
}

.back {
    background: #2563eb;
    color: white;
    text-decoration: none;
    padding: 10px 16px;
    border-radius: 8px;
}

.box {
    background: white;
    padding: 30px;
    border-radius: 15px;
    box-shadow: 0 5px 25px rgba(0,0,0,0.07);
}

label {
    display: block;
    margin: 18px 0 7px;
    font-weight: bold;
}

select,
input {
    width: 100%;
    padding: 13px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    font-size: 15px;
}

.submit {
    width: 100%;
    margin-top: 25px;
    padding: 14px;
    border: none;
    border-radius: 8px;
    background: #16a34a;
    color: white;
    font-weight: bold;
    cursor: pointer;
    font-size: 16px;
}

</style>

</head>

<body>

<div class="container">

<div class="top">

<h1>➕ Stock In</h1>

<a
    href="/dashboard"
    class="back"
>
    ← Dashboard
</a>

</div>


<div class="box">

<label>
    Select Product
</label>

<select id="product">

<option value="">
    Select product
</option>

</select>


<label>
    Quantity to Add
</label>

<input
    id="quantity"
    type="number"
    min="1"
    placeholder="Enter quantity"
>


<button
    class="submit"
    onclick="stockIn()"
>
    ADD STOCK
</button>

</div>

</div>


<script>

async function loadProducts() {

    try {

        const response =
            await fetch(
                "/api/products"
            );

        const data =
            await response.json();

        const select =
            document.getElementById(
                "product"
            );

        select.innerHTML =
            '<option value="">Select product</option>';


        if (!data.success) {

            alert(data.message);
            return;

        }


        data.products.forEach(
            product => {

                const option =
                    document.createElement(
                        "option"
                    );

                option.value =
                    product.id;

                option.textContent =
                    product.name +
                    " (Current: " +
                    product.quantity +
                    ")";

                select.appendChild(
                    option
                );

            }
        );

    } catch (error) {

        console.error(error);

        alert(
            "Could not load products."
        );

    }

}


async function stockIn() {

    const productId =
        document
        .getElementById("product")
        .value;

    const quantityText =
        document
        .getElementById("quantity")
        .value;


    if (
        !productId ||
        !quantityText
    ) {

        alert(
            "Please select a product and enter quantity."
        );

        return;

    }


    const quantity =
        Number(quantityText);


    if (
        !Number.isInteger(quantity) ||
        quantity <= 0
    ) {

        alert(
            "Quantity must be greater than 0."
        );

        return;

    }


    try {

        const response =
            await fetch(
                "/api/stock-in",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify(
                        {
                            product_id:
                                Number(productId),

                            quantity:
                                quantity
                        }
                    )
                }
            );


        const data =
            await response.json();


        alert(data.message);


        if (data.success) {

            document.getElementById(
                "quantity"
            ).value = "";

            await loadProducts();

        }

    } catch (error) {

        console.error(error);

        alert(
            "Cannot connect to server."
        );

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
# STOCK IN API
# =========================================================

@app.route(
    "/api/stock-in",
    methods=["POST"]
)
def stock_in():

    if not logged_in():

        return jsonify(
            success=False,
            message="Not logged in."
        ), 401

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

    except (ValueError, TypeError):

        return jsonify(
            success=False,
            message="Invalid product or quantity."
        ), 400

    if quantity <= 0:

        return jsonify(
            success=False,
            message="Quantity must be greater than 0."
        ), 400

    conn = get_db()

    product = conn.execute(
        """
        SELECT *
        FROM products
        WHERE id = ?
        """,
        (product_id,)
    ).fetchone()

    if not product:

        conn.close()

        return jsonify(
            success=False,
            message="Product not found."
        ), 404

    old_quantity = product["quantity"]

    new_quantity = old_quantity + quantity

    conn.execute(
        """
        UPDATE products
        SET quantity = ?
        WHERE id = ?
        """,
        (
            new_quantity,
            product_id
        )
    )

    conn.execute(
        """
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
        """,
        (
            product_id,
            product["name"],
            "STOCK IN",
            quantity,
            old_quantity,
            new_quantity,
            session["username"]
        )
    )

    conn.commit()
    conn.close()

    return jsonify(
        success=True,
        message=(
            f"Stock In successful! "
            f"{quantity} units added to "
            f"{product['name']}."
        )
    )


# =========================================================
# STOCK OUT PAGE
# =========================================================

STOCK_OUT_HTML = """
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>Stock Out</title>

<style>

body {
    font-family: Arial, sans-serif;
    background: #f8fafc;
    margin: 0;
    padding: 30px;
}

.container {
    max-width: 700px;
    margin: auto;
}

.top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 25px;
}

.back {
    background: #2563eb;
    color: white;
    text-decoration: none;
    padding: 10px 16px;
    border-radius: 8px;
}

.box {
    background: white;
    padding: 30px;
    border-radius: 15px;
    box-shadow: 0 5px 25px rgba(0,0,0,0.07);
}

label {
    display: block;
    margin: 18px 0 7px;
    font-weight: bold;
}

select,
input {
    width: 100%;
    padding: 13px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    font-size: 15px;
}

.submit {
    width: 100%;
    margin-top: 25px;
    padding: 14px;
    border: none;
    border-radius: 8px;
    background: #ef4444;
    color: white;
    font-weight: bold;
    cursor: pointer;
    font-size: 16px;
}

</style>

</head>

<body>

<div class="container">

<div class="top">

<h1>➖ Stock Out</h1>

<a
    href="/dashboard"
    class="back"
>
    ← Dashboard
</a>

</div>


<div class="box">

<label>
    Select Product
</label>

<select id="product">

<option value="">
    Select product
</option>

</select>


<label>
    Quantity to Remove
</label>

<input
    id="quantity"
    type="number"
    min="1"
    placeholder="Enter quantity"
>


<button
    class="submit"
    onclick="stockOut()"
>
    REMOVE STOCK
</button>

</div>

</div>


<script>

async function loadProducts() {

    try {

        const response =
            await fetch(
                "/api/products"
            );

        const data =
            await response.json();

        const select =
            document.getElementById(
                "product"
            );

        select.innerHTML =
            '<option value="">Select product</option>';


        if (!data.success) {

            alert(data.message);
            return;

        }


        data.products.forEach(
            product => {

                const option =
                    document.createElement(
                        "option"
                    );

                option.value =
                    product.id;

                option.textContent =
                    product.name +
                    " (Available: " +
                    product.quantity +
                    ")";

                select.appendChild(
                    option
                );

            }
        );

    } catch (error) {

        console.error(error);

        alert(
            "Could not load products."
        );

    }

}


async function stockOut() {

    const productId =
        document
        .getElementById("product")
        .value;

    const quantityText =
        document
        .getElementById("quantity")
        .value;


    if (
        !productId ||
        !quantityText
    ) {

        alert(
            "Please select a product and enter quantity."
        );

        return;

    }


    const quantity =
        Number(quantityText);


    if (
        !Number.isInteger(quantity) ||
        quantity <= 0
    ) {

        alert(
            "Quantity must be greater than 0."
        );

        return;

    }


    if (
        !confirm(
            "Are you sure you want to remove this stock?"
        )
    ) {

        return;

    }


    try {

        const response =
            await fetch(
                "/api/stock-out",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify(
                        {
                            product_id:
                                Number(productId),

                            quantity:
                                quantity
                        }
                    )
                }
            );


        const data =
            await response.json();


        alert(data.message);


        if (data.success) {

            document.getElementById(
                "quantity"
            ).value = "";

            await loadProducts();

        }

    } catch (error) {

        console.error(error);

        alert(
            "Cannot connect to server."
        );

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
def stock_out():

    if not logged_in():

        return jsonify(
            success=False,
            message="Not logged in."
        ), 401

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

    except (ValueError, TypeError):

        return jsonify(
            success=False,
            message="Invalid product or quantity."
        ), 400

    if quantity <= 0:

        return jsonify(
            success=False,
            message="Quantity must be greater than 0."
        ), 400

    conn = get_db()

    product = conn.execute(
        """
        SELECT *
        FROM products
        WHERE id = ?
        """,
        (product_id,)
    ).fetchone()

    if not product:

        conn.close()

        return jsonify(
            success=False,
            message="Product not found."
        ), 404

    old_quantity = product["quantity"]

    if quantity > old_quantity:

        conn.close()

        return jsonify(
            success=False,
            message=(
                f"Not enough stock. "
                f"Available: {old_quantity}."
            )
        ), 400

    new_quantity = old_quantity - quantity

    conn.execute(
        """
        UPDATE products
        SET quantity = ?
        WHERE id = ?
        """,
        (
            new_quantity,
            product_id
        )
    )

    conn.execute(
        """
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
        """,
        (
            product_id,
            product["name"],
            "STOCK OUT",
            quantity,
            old_quantity,
            new_quantity,
            session["username"]
        )
    )

    conn.commit()
    conn.close()

    return jsonify(
        success=True,
        message=(
            f"Stock Out successful! "
            f"{quantity} units removed from "
            f"{product['name']}."
        )
    )


# =========================================================
# HISTORY PAGE
# =========================================================

HISTORY_HTML = """
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>Stock History</title>

<style>

* {
    box-sizing: border-box;
}

body {
    font-family: Arial, sans-serif;
    background: #f8fafc;
    margin: 0;
    padding: 30px;
}

.container {
    max-width: 1250px;
    margin: auto;
}

.top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 25px;
}

.back {
    background: #2563eb;
    color: white;
    text-decoration: none;
    padding: 10px 16px;
    border-radius: 8px;
}

.search {
    width: 100%;
    padding: 13px;
    margin-bottom: 20px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
}

.table-box {
    overflow-x: auto;
}

table {
    width: 100%;
    background: white;
    border-collapse: collapse;
    box-shadow: 0 5px 25px rgba(0,0,0,0.06);
}

th,
td {
    padding: 14px;
    border-bottom: 1px solid #e2e8f0;
    text-align: left;
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

</style>

</head>

<body>

<div class="container">

<div class="top">

<h1>
    📜 Stock History
</h1>

<a
    href="/dashboard"
    class="back"
>
    ← Dashboard
</a>

</div>


<input
    id="search"
    class="search"
    placeholder="🔎 Search history..."
    onkeyup="filterHistory()"
>


<div class="table-box">

<table>

<thead>

<tr>
<th>ID</th>
<th>Product</th>
<th>Action</th>
<th>Quantity</th>
<th>Previous</th>
<th>New Stock</th>
<th>User</th>
<th>Date & Time</th>
</tr>

</thead>

<tbody id="historyTable"></tbody>

</table>

</div>

</div>


<script>

async function loadHistory() {

    try {

        const response =
            await fetch(
                "/api/history"
            );

        const data =
            await response.json();

        const table =
            document.getElementById(
                "historyTable"
            );

        table.innerHTML = "";


        if (!data.success) {

            alert(data.message);
            return;

        }


        data.history.forEach(
            item => {

                const row =
                    document.createElement(
                        "tr"
                    );

                const actionClass =
                    item.action === "STOCK OUT"
                    ? "out"
                    : "in";


                row.innerHTML = `

                    <td>${item.id}</td>

                    <td>
                        ${item.product_name}
                    </td>

                    <td class="${actionClass}">
                        ${item.action}
                    </td>

                    <td>
                        ${item.quantity}
                    </td>

                    <td>
                        ${item.previous_quantity}
                    </td>

                    <td>
                        ${item.new_quantity}
                    </td>

                    <td>
                        ${item.username}
                    </td>

                    <td>
                        ${item.created_at}
                    </td>

                `;

                table.appendChild(row);

            }
        );

    } catch (error) {

        console.error(error);

        alert(
            "Could not load history."
        );

    }

}


function filterHistory() {

    const value =
        document
        .getElementById(
            "search"
        )
        .value
        .toLowerCase();


    document
        .querySelectorAll(
            "#historyTable tr"
        )
        .forEach(
            row => {

                row.style.display =
                    row
                    .textContent
                    .toLowerCase()
                    .includes(value)
                    ? ""
                    : "none";

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
# HISTORY API
# =========================================================

@app.route("/api/history")
def get_history():

    if not logged_in():

        return jsonify(
            success=False,
            message="Not logged in."
        ), 401

    conn = get_db()

    history = conn.execute(
        """
        SELECT *
        FROM history
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return jsonify(
        success=True,
        history=[
            dict(item)
            for item in history
        ]
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    init_database()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )