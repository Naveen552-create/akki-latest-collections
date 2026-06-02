import time
from flask import Flask, render_template, request, jsonify, redirect, session
import mysql.connector
import os
from werkzeug.utils import secure_filename
from flask import *
from collections import defaultdict
from flask import jsonify
from PIL import Image
from cashfree_pg.api_client import Cashfree
from cashfree_pg.models.create_order_request import CreateOrderRequest
from cashfree_pg.models.customer_details import CustomerDetails
from cashfree_pg.models.order_meta import OrderMeta
import uuid
from flask import flash
import requests


app = Flask(__name__)
app.secret_key = "secret123"   






@app.before_request
def force_https():
    if request.headers.get("X-Forwarded-Proto") == "http":
        return redirect(request.url.replace("http://", "https://", 1), code=301)


# ✅ ALWAYS USE RELATIVE PATH (IMPORTANT)
UPLOAD_FOLDER = os.path.join('static', 'uploads')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024



app.config['CAROUSEL_FOLDER'] = 'static/carousel'




# ================= CASHFREE CONFIG =================
from cashfree_pg.api_client import Cashfree

Cashfree.XClientId = os.environ.get("CASHFREE_CLIENT_ID")

Cashfree.XClientSecret = os.environ.get("CASHFREE_CLIENT_SECRET")

Cashfree.XEnvironment = Cashfree.PRODUCTION


# DB CONNECTION
def get_db_connection():
    return mysql.connector.connect(
        host="srv1408.hstgr.io",
        user="u372412767_akkiuser",
        password="Akki@2026Secure#552",
        database="u372412767_akki",
        autocommit=True,
        connection_timeout=5
    )



API_URL = "https://wasenderapi.com/api/send-message" 
API_KEY = "ead64fbba18e5edaf80f605b0d63a41e5231488d07159726523474275b617340"


def send_whatsapp(number, message, image_url=""):

    phone = str(number).strip()

    if not phone.startswith("91"):
        phone = "91" + phone

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "to": phone,
        "text": message
    }

    if image_url:
        payload["image_url"] = image_url

    response = requests.post(
        API_URL,
        headers=headers,
        json=payload,
        timeout=30
    )

    print("STATUS:", response.status_code)
    print("RESPONSE:", response.text)

    return response  

# ================= HOME =================

from datetime import datetime

def publish_products():
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE products
            SET is_private = 0
            WHERE is_private = 1
            AND publish_at <= NOW()
        """)

        conn.commit()

    except Exception as e:
        print("publish_products error:", e)

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/')
def home():

    conn = None
    cursor = None

    try:
        # Optional: comment this line if not absolutely required
        publish_products()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT *
            FROM carousel
            ORDER BY id DESC
        """)
        carousel_items = cursor.fetchall()

        cursor.execute("""
            SELECT
                p.id,
                p.name,
                p.price,
                p.quantity,
                c.name AS category,
                s.name AS subcategory,
                GROUP_CONCAT(DISTINCT pi.image) AS images
            FROM products p
            LEFT JOIN categories c
                ON p.category_id = c.id
            LEFT JOIN subcategories s
                ON p.subcategory_id = s.id
            LEFT JOIN product_images pi
                ON p.id = pi.product_id
            WHERE p.show_home = 1
            AND p.is_private = 0
            AND (
                p.quantity > 0
                OR EXISTS (
                    SELECT 1
                    FROM product_sizes ps
                    WHERE ps.product_id = p.id
                    AND ps.quantity > 0
                )
            )
            GROUP BY p.id
            ORDER BY p.id DESC
        """)

        products = cursor.fetchall()

        for product in products:
            product['images'] = (
                product['images'].split(',')
                if product['images']
                else []
            )

        cart_count = 0

        if 'user' in session:

            cursor.execute("""
                SELECT COALESCE(SUM(quantity),0) AS total
                FROM cart
                WHERE username=%s
            """, (session['user'],))

            result = cursor.fetchone()

            if result:
                cart_count = result['total']

        return render_template(
            'index.html',
            products=products,
            carousel_items=carousel_items,
            cart_count=cart_count
        )

    except Exception as e:
        print("HOME ERROR:", e)
        return render_template(
            'index.html',
            products=[],
            carousel_items=[],
            cart_count=0
        )

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()

# ================= LOGIN =================
@app.route('/login', methods=['POST'])
def login():

    username = request.form.get('username')
    password = request.form.get('password')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM users
        WHERE username=%s
        AND password=%s
    """, (
        username,
        password
    ))

    user = cursor.fetchone()

    cursor.close()
    conn.close()

    # LOGIN SUCCESS
    if user:

        session['user'] = user['username']

        # CHECK NEXT PAGE
        next_url = session.get('next_url')

        # IF USER CAME FROM CART
        if next_url:

            session.pop('next_url', None)

            return jsonify({
                "status": "success",
                "redirect": next_url
            })

        # DEFAULT HOME PAGE
        return jsonify({
            "status": "success",
            "redirect": "/"
        })

    # LOGIN FAILED
    else:

        return jsonify({
            "status": "fail"
        })


@app.route('/login-page')
def login_page():
    return render_template('login.html')



# REGISTER
@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    password = request.form.get('password')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Check if already exists
    cursor.execute(
        "SELECT * FROM users WHERE username=%s",
        (username,)
    )

    existing = cursor.fetchone()

    if existing:
        cursor.close()
        conn.close()
        return jsonify({"status": "exists"})

    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO users(username,password) VALUES(%s,%s)",
        (username, password)
    )

    conn.commit()

    cursor.close()
    conn.close()

    return jsonify({"status": "success"})


# FORGOT PASSWORD
@app.route('/forgot', methods=['POST'])
def forgot():

    username = request.form.get('username')
    new_password = request.form.get('password')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # CHECK USERNAME EXISTS
    cursor.execute(
        "SELECT * FROM users WHERE username=%s",
        (username,)
    )

    user = cursor.fetchone()

    if not user:
        cursor.close()
        conn.close()
        return jsonify({"status":"notfound"})

    # UPDATE PASSWORD
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE users SET password=%s WHERE username=%s",
        (new_password, username)
    )

    conn.commit()

    cursor.close()
    conn.close()

    return jsonify({"status":"updated"})

# LOGOUT
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')


@app.route('/product/<int:id>')
def product_details(id):

    publish_products()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # PRODUCT
    cursor.execute("""
        SELECT
            p.*,
            c.name AS category,
            s.name AS subcategory
        FROM products p
        LEFT JOIN categories c
            ON p.category_id = c.id
        LEFT JOIN subcategories s
            ON p.subcategory_id = s.id
        WHERE p.id=%s
        AND p.is_private=0
    """, (id,))

    product = cursor.fetchone()

    # PRODUCT NOT FOUND
    if not product:
        cursor.close()
        conn.close()
        return "Product not found"

    # IMAGES
    cursor.execute("""
        SELECT image
        FROM product_images
        WHERE product_id=%s
        ORDER BY id ASC
    """, (id,))

    product['images'] = [
        img['image']
        for img in cursor.fetchall()
    ]

    # SIZES
    cursor.execute("""
        SELECT size,price,quantity
        FROM product_sizes
        WHERE product_id=%s
        ORDER BY id ASC
    """, (id,))

    product['sizes'] = cursor.fetchall()

    # RELATED PRODUCTS
    cursor.execute("""
        SELECT
            p.id,
            p.name,
            p.price,
            GROUP_CONCAT(DISTINCT pi.image) AS images
        FROM products p
        LEFT JOIN product_images pi
            ON p.id = pi.product_id
        WHERE p.category_id=%s
        AND p.id!=%s
        AND p.is_private=0
        AND (
            p.quantity > 0
            OR EXISTS (
                SELECT 1
                FROM product_sizes ps
                WHERE ps.product_id = p.id
                AND ps.quantity > 0
            )
        )
        GROUP BY p.id
        ORDER BY p.id DESC
    """, (product['category_id'], id))

    related_products = cursor.fetchall()

    for item in related_products:

        item['images'] = (
            item['images'].split(',')
            if item['images']
            else []
        )

    cursor.close()
    conn.close()

    return render_template(
        'product_details.html',
        product=product,
        related_products=related_products
    )


@app.route("/search-products")
def search_products():

    keyword = request.args.get("q")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # SAVE SEARCH
    cursor.execute("""
        INSERT INTO search_reports(keyword)
        VALUES(%s)
    """,(keyword,))

    db.commit()

    # SEARCH PRODUCTS
    cursor.execute("""
        SELECT * FROM products
        WHERE category LIKE %s
        OR subcategory LIKE %s
        OR name LIKE %s
    """,(
        f"%{keyword}%",
        f"%{keyword}%",
        f"%{keyword}%"
    ))

    products = cursor.fetchall()

    return jsonify(products)

@app.route('/material/<material_name>')
def material_products(material_name):

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            p.id,
            p.name,
            p.price,
            p.quantity,
            c.name AS category,
            s.name AS subcategory,
            GROUP_CONCAT(DISTINCT pi.image) AS images
        FROM products p

        LEFT JOIN categories c
            ON p.category_id = c.id

        LEFT JOIN subcategories s
            ON p.subcategory_id = s.id

        LEFT JOIN product_images pi
            ON p.id = pi.product_id

        WHERE (
            c.name=%s
            OR s.name=%s
        )

        AND p.is_private=0

        AND (
            p.quantity > 0
            OR EXISTS (
                SELECT 1
                FROM product_sizes ps
                WHERE ps.product_id = p.id
                AND ps.quantity > 0
            )
        )

        GROUP BY p.id
        ORDER BY p.id DESC
    """, (material_name, material_name))

    products = cursor.fetchall()

    for product in products:

        product['images'] = (
            product['images'].split(',')
            if product['images']
            else []
        )

    cursor.close()
    conn.close()

    return render_template(
        'material_products.html',
        products=products,
        material_name=material_name
    )


# ================= CART PAGE =================
@app.route('/cart')
def cart():

    # USER NOT LOGIN
    if 'user' not in session:

        # SAVE RETURN URL
        session['next_url'] = '/cart'

        return redirect('/login-page')

    username = session['user']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            cart.quantity AS cart_qty,
            p.*,
            c.name AS category,
            s.name AS subcategory,
            GROUP_CONCAT(pi.image) AS images

        FROM cart

        JOIN products p
            ON cart.product_id = p.id

        LEFT JOIN categories c
            ON p.category_id = c.id

        LEFT JOIN subcategories s
            ON p.subcategory_id = s.id

        LEFT JOIN product_images pi
            ON p.id = pi.product_id

        WHERE cart.username=%s

        GROUP BY cart.id
    """, (username,))

    products = cursor.fetchall()

    for p in products:

        p['images'] = (
            p['images'].split(',')
            if p['images']
            else []
        )

    cursor.close()
    conn.close()

    return render_template(
        'cart.html',
        products=products
    )


# ================= ADD TO CART =================

@app.route('/add-to-cart/<int:id>/<int:qty>')
def add_to_cart(id, qty):

    # USER NOT LOGIN
    if 'user' not in session:

        # SAVE CURRENT URL
        session['next_url'] = request.url

        return redirect('/login-page')

    username = session['user']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # GET PRODUCT
    cursor.execute("""
        SELECT
            category_id,
            subcategory_id,
            quantity
        FROM products
        WHERE id=%s
    """, (id,))

    product = cursor.fetchone()

    # PRODUCT NOT FOUND
    if not product:

        cursor.close()
        conn.close()

        return redirect('/')

    stock = product['quantity']

    # CHECK EXISTING CART
    cursor.execute("""
        SELECT quantity
        FROM cart
        WHERE username=%s
        AND product_id=%s
    """, (
        username,
        id
    ))

    existing = cursor.fetchone()

    current_cart_qty = (
        existing['quantity']
        if existing
        else 0
    )

    new_qty = current_cart_qty + qty

    # STOCK LIMIT CHECK
    if new_qty > stock:

        cursor.close()
        conn.close()

        flash(
            f"Only {stock} items available in stock",
            "error"
        )

        return redirect('/cart')

    # UPDATE EXISTING
    if existing:

        cursor.execute("""
            UPDATE cart
            SET quantity=%s
            WHERE username=%s
            AND product_id=%s
        """, (
            new_qty,
            username,
            id
        ))

    # INSERT NEW
    else:

        cursor.execute("""
            INSERT INTO cart(
                username,
                product_id,
                category_id,
                subcategory_id,
                quantity
            )
            VALUES(%s,%s,%s,%s,%s)
        """, (
            username,
            id,
            product['category_id'],
            product['subcategory_id'],
            qty
        ))

    conn.commit()

    cursor.close()
    conn.close()

    return redirect('/cart')

  

@app.route('/increase-cart/<int:id>')
def increase_cart(id):

    if 'user' not in session:
        return redirect('/login-page')

    username = session['user']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT quantity
        FROM products
        WHERE id=%s
    """, (id,))
    product = cursor.fetchone()

    cursor.execute("""
        SELECT quantity
        FROM cart
        WHERE username=%s AND product_id=%s
    """, (username, id))

    cart = cursor.fetchone()

    if cart and cart['quantity'] >= product['quantity']:
        conn.close()
        flash(
        f"Only {product['quantity']} items available in stock",
        "error"
        )
        return redirect('/cart')

    cursor.execute("""
        UPDATE cart
        SET quantity = quantity + 1
        WHERE username=%s AND product_id=%s
    """, (username, id))

    conn.commit()
    conn.close()

    return redirect('/cart')



@app.route('/decrease-cart/<int:id>')
def decrease_cart(id):

    conn=get_db_connection()
    cursor=conn.cursor()

    cursor.execute("""
    UPDATE cart
    SET quantity=quantity-1
    WHERE product_id=%s
    AND username=%s
    AND quantity>1
    """,(id,session['user']))

    conn.commit()
    conn.close()

    return redirect('/cart')


@app.route('/delete-cart/<int:id>')
def delete_cart(id):

    conn=get_db_connection()
    cursor=conn.cursor()

    cursor.execute("""
    DELETE FROM cart
    WHERE product_id=%s
    AND username=%s
    """,(id,session['user']))

    conn.commit()
    conn.close()

    return redirect('/cart')


# CHECKOUT PAGE
@app.route('/place-all-order')
def place_all_order():

    if 'user' not in session:
        return redirect('/')

    username=session['user']

    conn=get_db_connection()
    cursor=conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM addresses
        WHERE username=%s
        ORDER BY is_default DESC,id DESC
    """,(username,))

    addresses=cursor.fetchall()

    conn.close()

    return render_template(
        'checkout.html',
        addresses=addresses
    )


# SAVE ADDRESS
@app.route('/save-address',methods=['POST'])
def save_address():

    if 'user' not in session:
        return redirect('/')

    username=session['user']

    address_type=request.form['address_type']
    full_name=request.form['full_name']
    phone=request.form['phone']
    email=request.form['email']
    country=request.form['country']
    state=request.form['state']
    city=request.form['city']
    pincode=request.form['pincode']
    landmark=request.form['landmark']

    conn=get_db_connection()
    cursor=conn.cursor()

    cursor.execute("""
        INSERT INTO addresses(
        username,address_type,full_name,
        phone,email,country,state,
        city,pincode,landmark,is_default
        )
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0)
    """,(
        username,address_type,full_name,
        phone,email,country,state,
        city,pincode,landmark
    ))

    conn.commit()
    conn.close()

    return redirect('/place-all-order')


# SELECT ADDRESS
@app.route('/set-default-address/<int:id>')
def set_default_address(id):

    username=session['user']

    conn=get_db_connection()
    cursor=conn.cursor()

    cursor.execute("""
        UPDATE addresses
        SET is_default=0
        WHERE username=%s
    """,(username,))

    cursor.execute("""
        UPDATE addresses
        SET is_default=1
        WHERE id=%s
    """,(id,))

    conn.commit()
    conn.close()

    return redirect('/place-all-order')



# ================= CREATE CASHFREE ORDER =================
@app.route('/create-cashfree-order', methods=['POST'])
def create_cashfree_order():

    try:

        # ================= LOGIN CHECK =================
        if 'user' not in session:

            return jsonify({
                "error": "Please login first"
            }), 401

        # ================= GET DATA =================
        data = request.get_json()

        amount = float(data['amount'])

        username = session['user']

        # ================= UNIQUE ORDER ID =================
        order_id = "ORDER_" + uuid.uuid4().hex[:12]

        # ================= DB =================
        conn = get_db_connection()

        cursor = conn.cursor(dictionary=True)

        # ================= GET DEFAULT ADDRESS =================
        cursor.execute("""
            SELECT *
            FROM addresses
            WHERE username=%s
            AND is_default=1
        """, (username,))

        address = cursor.fetchone()

        conn.close()

        # ================= ADDRESS NOT SELECTED =================
        if not address:

            return jsonify({
                "error": "Please select address"
            }), 400

        # ================= CUSTOMER DETAILS =================
        customer_phone = str(
            address['phone']
        ).strip()

        customer_email = str(
            address['email']
        ).strip()

        # ================= PHONE VALIDATION =================
        customer_phone = ''.join(
            filter(str.isdigit, customer_phone)
        )

        if len(customer_phone) != 10:

            return jsonify({
                "error": "Invalid phone number"
            }), 400

        # ================= EMAIL VALIDATION =================
        if "@" not in customer_email:

            return jsonify({
                "error": "Invalid email address"
            }), 400

        # ================= CASHFREE CUSTOMER =================
        customer_details = CustomerDetails(

            customer_id=str(username),

            customer_phone=customer_phone,

            customer_email=customer_email
        )

        # ================= RETURN URL =================
        order_meta = OrderMeta(

            return_url=f"https://akkilatestcollections.com/payment-success/Online?order_id={order_id}"
        )

        # ================= CREATE ORDER REQUEST =================
        create_order_request = CreateOrderRequest(

            order_id=order_id,

            order_amount=amount,

            order_currency="INR",

            customer_details=customer_details,

            order_meta=order_meta
        )

        # ================= CASHFREE INSTANCE =================
        cashfree = Cashfree(

            XClientId=Cashfree.XClientId,

            XClientSecret=Cashfree.XClientSecret,

            XEnvironment=Cashfree.XEnvironment
        )

        # ================= CREATE ORDER =================
        response = cashfree.PGCreateOrder(

            x_api_version="2023-08-01",

            create_order_request=create_order_request
        )

        # ================= SUCCESS =================
        return jsonify({

            "payment_session_id":
            response.data.payment_session_id,

            "order_id":
            order_id
        })

    except Exception as e:

        print("CASHFREE ERROR:", e)

        return jsonify({

            "error": str(e)

        }), 500
    


@app.route('/confirm-order')
def confirm_order():

    if 'user' not in session:
        return redirect('/')

    username = session['user']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            cart.*,
            p.name,
            p.price,
            GROUP_CONCAT(pi.image) as images
        FROM cart
        JOIN products p
            ON cart.product_id=p.id
        LEFT JOIN product_images pi
            ON p.id=pi.product_id
        WHERE cart.username=%s
        GROUP BY cart.id
    """, (username,))

    products = cursor.fetchall()

    subtotal = 0

    for p in products:

        p['images'] = (
            p['images'].split(',')
            if p['images'] else []
        )

        subtotal += p['price'] * p['quantity']

    conn.close()

    # ================= SHIPPING =================
    shipping = 50 if subtotal > 0 else 0

    # ================= PLATFORM FEE =================
    platform_fee = 3

    # ================= FINAL TOTAL =================
    total = subtotal + shipping + platform_fee

    return render_template(
        'payment.html',
        products=products,
        subtotal=subtotal,
        shipping=shipping,
        platform_fee=platform_fee,
        total=total
    )



@app.route('/payment-success/<mode>')
def payment_success(mode):

    if 'user' not in session:
        return redirect('/')

    username = session['user']

    # ================= GET ORDER ID =================
    cashfree_order_id = request.args.get("order_id")

    if not cashfree_order_id:
        return redirect('/cart')

    try:

        # ================= VERIFY PAYMENT =================
        cashfree = Cashfree(
            XClientId=Cashfree.XClientId,
            XClientSecret=Cashfree.XClientSecret,
            XEnvironment=Cashfree.XEnvironment
        )

        response = cashfree.PGFetchOrder(
            x_api_version="2023-08-01",
            order_id=cashfree_order_id
        )

        order_status = response.data.order_status

        if order_status != "PAID":
            return redirect('/cart')

        # ================= DB =================
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # ================= ADDRESS =================
        cursor.execute("""
            SELECT *
            FROM addresses
            WHERE username=%s
            AND is_default=1
        """, (username,))

        address = cursor.fetchone()

        if not address:
            return redirect('/place-all-order')

        # ================= CART ITEMS =================
        cursor.execute("""
            SELECT *
            FROM cart
            WHERE username=%s
        """, (username,))

        cart_items = cursor.fetchall()

        # ================= WHATSAPP DATA =================
        order_text = ""
        grand_total = 0
        first_product_image = ""

        for item in cart_items:

            # ================= PRODUCT DETAILS =================
            cursor.execute("""
                SELECT
                    p.*,
                    (
                        SELECT image
                        FROM product_images
                        WHERE product_id = p.id
                        LIMIT 1
                    ) AS image
                FROM products p
                WHERE p.id=%s
            """, (item['product_id'],))

            product = cursor.fetchone()

            if product:

                amount = float(product['price']) * int(item['quantity'])
                grand_total += amount

                size = item.get('size', 'N/A')

                order_text += f"""
🛍 Product: {product['name']}
✨ Design: {product.get('sub_name', '')}
📏 Size: {size}
🔢 Qty: {item['quantity']}
💰 Amount: ₹{amount}

"""

                if not first_product_image and product.get('image'):
                    first_product_image = product['image']

            # ================= INSERT ORDER =================
            cursor.execute("""
                INSERT INTO orders(
                    username,
                    product_id,
                    category_id,
                    subcategory_id,
                    quantity,
                    full_name,
                    phone,
                    email,
                    country,
                    state,
                    city,
                    pincode,
                    landmark,
                    payment_mode,
                    order_status
                )
                VALUES(
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    'Confirmed'
                )
            """, (
                username,
                item['product_id'],
                item['category_id'],
                item['subcategory_id'],
                item['quantity'],
                address['full_name'],
                address['phone'],
                address['email'],
                address['country'],
                address['state'],
                address['city'],
                address['pincode'],
                address['landmark'],
                mode
            ))

            order_id = cursor.lastrowid

            # ================= INSERT ORDER ITEMS =================
            cursor.execute("""
                INSERT INTO order_items(
                    order_id,
                    username,
                    product_id,
                    category_id,
                    subcategory_id,
                    quantity,
                    full_name,
                    phone,
                    email,
                    country,
                    state,
                    city,
                    pincode,
                    landmark,
                    payment_mode
                )
                VALUES(
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
            """, (
                order_id,
                username,
                item['product_id'],
                item['category_id'],
                item['subcategory_id'],
                item['quantity'],
                address['full_name'],
                address['phone'],
                address['email'],
                address['country'],
                address['state'],
                address['city'],
                address['pincode'],
                address['landmark'],
                mode
            ))

            # ================= REDUCE STOCK =================
            cursor.execute("""
                UPDATE products
                SET quantity = quantity - %s
                WHERE id=%s
            """, (
                item['quantity'],
                item['product_id']
            ))

        # ================= WHATSAPP MESSAGE =================

        message = f"""
🌸 Akki Latest Collections 🌸

Dear {address['full_name']},

Thank you for shopping with us.

Your order has been confirmed successfully. ✅

━━━━━━━━━━━━━━━
ORDER DETAILS
━━━━━━━━━━━━━━━

{order_text}

💵 Total Amount: ₹{grand_total}

🚚 Our team is preparing your order and it will be dispatched soon.

Thank you for choosing Akki Latest Collections.

❤️ We look forward to serving you again.

Warm Regards,
Akki Latest Collections
www.akkilatestcollections.com
"""

        try:

            image_url = ""

            if first_product_image:
                image_url = (
                           f"https://akkilatestcollections.com/static/uploads/"
                           f"{first_product_image}"
                        )

            send_whatsapp(
                  address['phone'],
                  message,
                  image_url
            )

        except Exception as whatsapp_error:
            print("WHATSAPP ERROR:", whatsapp_error)

        # ================= CLEAR CART =================
        cursor.execute("""
            DELETE FROM cart
            WHERE username=%s
        """, (username,))

        conn.commit()
        conn.close()

        return """
        <div style='
        text-align:center;
        margin-top:100px;
        font-family:Arial;
        '>

        <h1 style='color:green;'>
        Order Confirmed Successfully
        </h1>

        <br>

        <a href='/'
        style='
        background:#1b8f4b;
        color:white;
        padding:14px 28px;
        text-decoration:none;
        border-radius:10px;
        font-size:16px;
        font-weight:bold;
        display:inline-block;
        '>
        Back To Home
        </a>

        </div>
        """

    except Exception as e:

        print("PAYMENT VERIFY ERROR:", e)

        return redirect('/cart')



# ================= ADMIN LOGIN PAGE =================
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM admins WHERE username=%s AND password=%s",
                       (username, password))
        admin = cursor.fetchone()

        conn.close()

        if admin:
            session['admin'] = admin['username']
            return redirect('/admin/dashboard')
        else:
            return render_template('adminlogin.html', error="Invalid Username or Password")

    return render_template('adminlogin.html')


# ================= ADMIN DASHBOARD =================
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin' not in session:
        return redirect('/admin')

    return render_template('admin_dashboard.html')




@app.route('/add-category', methods=['POST'])
def add_category():
    name = request.form['name'].strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("INSERT INTO categories (name) VALUES (%s)", (name,))
    
    conn.commit()
    conn.close()

    return redirect('/addingproduct')




@app.route('/add-subcategory', methods=['POST'])
def add_subcategory():
    name = request.form['name'].strip()
    category_id = request.form['category_id']

    if not category_id:
        return "Please select a category"

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO subcategories (name, category_id)
        VALUES (%s, %s)
    """, (name, category_id))

    conn.commit()
    conn.close()

    return redirect('/addingproduct')



@app.route('/get-subcategories/<int:category_id>')
def get_subcategories(category_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT id, name FROM subcategories WHERE category_id=%s", (category_id,))
    data = cursor.fetchall()

    conn.close()
    return jsonify(data)



@app.route('/delete-category', methods=['POST'])
def delete_category():
    category_id = request.form['category_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM categories WHERE id=%s", (category_id,))

    conn.commit()
    conn.close()

    return redirect('/addingproduct')



@app.route('/delete-subcategory', methods=['POST'])
def delete_subcategory():
    subcategory_id = request.form['subcategory_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM subcategories WHERE id=%s", (subcategory_id,))

    conn.commit()
    conn.close()

    return redirect('/addingproduct')



@app.route('/addingproduct')
def adding_product_page():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM categories")
    categories = cursor.fetchall()

    cursor.execute("SELECT * FROM subcategories")
    subcategories = cursor.fetchall()

    conn.close()

    return render_template(
        'addingproduct.html',
        categories=categories,
        subcategories=subcategories
    )


@app.errorhandler(413)
def too_large(e):
    return "Upload too large. Please upload smaller images.", 413

# ================= IMAGE OPTIMIZER =================
def save_optimized_image(file, upload_folder):

    img = Image.open(file)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    img.thumbnail((1200, 1200))

    filename = f"{uuid.uuid4().hex}.webp"

    filepath = os.path.join(upload_folder, filename)

    img.save(
        filepath,
        "WEBP",
        quality=70,
        optimize=True
    )

    return f"uploads/{filename}"


@app.route('/add-product', methods=['POST'])
def add_product():

    conn = get_db_connection()
    cursor = conn.cursor()

    name = request.form['name']
    category_id = request.form['category_id']
    subcategory_id = request.form['subcategory_id']
    description = request.form['description']

    show_home = 1 if 'show_home' in request.form else 0
    is_private = 1 if 'is_private' in request.form else 0
    publish_at = request.form.get('publish_at') or None

    price = request.form.get('price') or 0
    quantity = request.form.get('quantity') or 0

    cursor.execute("""
        INSERT INTO products
        (
            name,
            category_id,
            subcategory_id,
            description,
            price,
            quantity,
            show_home,
            is_private,
            publish_at
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """,(
        name,
        category_id,
        subcategory_id,
        description,
        price,
        quantity,
        show_home,
        is_private,
        publish_at
    ))

    product_id = cursor.lastrowid

    # Save Sizes
    sizes = request.form.getlist('sizes[]')

    for size in sizes:

        price_size = request.form.get(f'price_{size}')
        qty_size = request.form.get(f'qty_{size}')

        if price_size and qty_size:

            cursor.execute("""
                INSERT INTO product_sizes
                (
                    product_id,
                    size,
                    price,
                    quantity
                )
                VALUES (%s,%s,%s,%s)
            """,(
                product_id,
                size,
                price_size,
                qty_size
            ))

    # Save Images
    images = request.files.getlist('images')

    for image in images:

        if image.filename:

            filepath = save_optimized_image(
                image,
                app.config['UPLOAD_FOLDER']
            )

            cursor.execute("""
                INSERT INTO product_images
                (
                    product_id,
                    image
                )
                VALUES (%s,%s)
            """,(
                product_id,
                filepath
            ))

    conn.commit()
    conn.close()

    return redirect('/manage-products')


# ================= MANAGE PRODUCTS =================
@app.route('/manage-products')
def manage_products():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            p.*,
            c.name AS category,
            s.name AS subcategory,
            GROUP_CONCAT(
                DISTINCT pi.image
                ORDER BY pi.id ASC
            ) AS images
        FROM products p
        LEFT JOIN categories c
            ON p.category_id = c.id
        LEFT JOIN subcategories s
            ON p.subcategory_id = s.id
        LEFT JOIN product_images pi
            ON p.id = pi.product_id
        GROUP BY p.id
        ORDER BY
            CASE
                WHEN p.quantity = 0 THEN 0
                ELSE 1
            END,
            p.id DESC
    """)

    products = cursor.fetchall()

    for product in products:

        product['images'] = (
            product['images'].split(',')
            if product['images']
            else []
        )

        # fetch sizes
        cursor.execute("""
            SELECT size,price,quantity
            FROM product_sizes
            WHERE product_id=%s
            ORDER BY id ASC
        """,(product['id'],))

        product['sizes']=cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'manage_products.html',
        products=products
    )



# ================= DELETE PRODUCT =================
@app.route('/delete-product/<int:id>')
def delete_product(id):

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # ================= GET PRODUCT IMAGES =================
    cursor.execute("""
        SELECT image
        FROM product_images
        WHERE product_id=%s
    """, (id,))

    images = cursor.fetchall()

    # ================= DELETE IMAGES FROM DISK =================
    for img in images:

        if img['image']:

            file_path = os.path.join(
                app.config['UPLOAD_FOLDER'],
                os.path.basename(img['image'])
            )

            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print("Delete error:", e)

    # ================= DELETE IMAGE PATHS FROM DB =================
    cursor.execute("""
        DELETE FROM product_images
        WHERE product_id=%s
    """, (id,))

    # ================= DELETE PRODUCT =================
    cursor.execute("""
        DELETE FROM products
        WHERE id=%s
    """, (id,))

    conn.commit()

    cursor.close()
    conn.close()

    return redirect('/manage-products')



@app.route('/edit-product/<int:id>', methods=['GET', 'POST'])
def edit_product(id):

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':

        name = request.form['name'].strip()
        category_id = request.form['category_id']
        subcategory_id = request.form['subcategory_id']
        description = request.form['description'].strip()

        show_home = 1 if 'show_home' in request.form else 0

        price = request.form.get('price') or 0
        quantity = request.form.get('quantity') or 0

        cursor.execute("""
            UPDATE products
            SET
                name=%s,
                category_id=%s,
                subcategory_id=%s,
                price=%s,
                quantity=%s,
                description=%s,
                show_home=%s
            WHERE id=%s
        """, (
            name,
            category_id,
            subcategory_id,
            price,
            quantity,
            description,
            show_home,
            id
        ))

        # delete old sizes
        cursor.execute("""
            DELETE FROM product_sizes
            WHERE product_id=%s
        """,(id,))

        # save sizes
        sizes=request.form.getlist('sizes[]')

        for size in sizes:

            price_size=request.form.get(f'price_{size}')
            qty_size=request.form.get(f'qty_{size}')

            if price_size and qty_size:

                cursor.execute("""
                    INSERT INTO product_sizes
                    (product_id,size,price,quantity)
                    VALUES(%s,%s,%s,%s)
                """,(
                    id,size,price_size,qty_size
                ))

        # delete images
        delete_images=request.form.getlist('delete_images')

        for img in delete_images:

            file_path=os.path.join(
                app.config['UPLOAD_FOLDER'],
                os.path.basename(img)
            )

            if os.path.exists(file_path):
                os.remove(file_path)

            cursor.execute("""
                DELETE FROM product_images
                WHERE product_id=%s
                AND image=%s
            """,(id,img))

        # add images
        images=request.files.getlist('images')

        for image in images:

            if image.filename:

                filepath=save_optimized_image(
                    image,
                    app.config['UPLOAD_FOLDER']
                )

                cursor.execute("""
                    INSERT INTO product_images
                    (product_id,image)
                    VALUES(%s,%s)
                """,(id,filepath))

        conn.commit()
        conn.close()

        return redirect('/manage-products')

    # product
    cursor.execute("""
        SELECT *
        FROM products
        WHERE id=%s
    """,(id,))
    product=cursor.fetchone()

    # categories
    cursor.execute("SELECT * FROM categories")
    categories=cursor.fetchall()

    # subcategories
    cursor.execute("""
        SELECT *
        FROM subcategories
        WHERE category_id=%s
    """,(product['category_id'],))
    subcategories=cursor.fetchall()

    # images
    cursor.execute("""
        SELECT image
        FROM product_images
        WHERE product_id=%s
    """,(id,))
    product['images']=cursor.fetchall()

    # sizes
    cursor.execute("""
        SELECT *
        FROM product_sizes
        WHERE product_id=%s
    """,(id,))
    product['sizes']=cursor.fetchall()

    conn.close()

    return render_template(
        'edit_product.html',
        product=product,
        categories=categories,
        subcategories=subcategories
    )


@app.route('/stockentry')
def stock_entry_page():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM categories")
    categories = cursor.fetchall()

    cursor.execute("""
        SELECT se.*, c.name AS category_name, s.name AS subcategory_name
        FROM stock_entries se
        LEFT JOIN categories c ON se.category_id = c.id
        LEFT JOIN subcategories s ON se.subcategory_id = s.id
        ORDER BY se.id DESC
    """)
    stock = cursor.fetchall()

    conn.close()

    return render_template('stockentry.html', categories=categories, stock=stock)


@app.route('/add-stock', methods=['POST'])
def add_stock():

    name = request.form['name']
    category_id = request.form['category_id']
    subcategory_id = request.form['subcategory_id']
    date = request.form['date']
    price = float(request.form['price'])
    quantity = int(request.form['quantity'])
    payment_mode = request.form['payment_mode']

    amount = round(price * quantity, 2)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO stock_entries
        (
            name,
            category_id,
            subcategory_id,
            date,
            price,
            quantity,
            amount,
            payment_mode
        )
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
    """,(
        name,
        category_id,
        subcategory_id,
        date,
        price,
        quantity,
        amount,
        payment_mode
    ))

    conn.commit()
    conn.close()

    return redirect('/stockentry')


@app.route('/delete-stock/<int:id>')
def delete_stock(id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM stock_entries WHERE id=%s", (id,))

    conn.commit()
    conn.close()

    return redirect('/stockentry')



@app.route('/update-stock/<int:id>', methods=['POST'])
def update_stock(id):

    name = request.form['name']
    date = request.form['date']
    price = float(request.form['price'])
    quantity = int(request.form['quantity'])

    amount = price * quantity

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE stock_entries
        SET name=%s, date=%s, price=%s, quantity=%s, amount=%s
        WHERE id=%s
    """, (name, date, price, quantity, amount, id))

    conn.commit()
    conn.close()

    return redirect('/stockentry')



@app.route('/carousel')
def carousel_page():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM carousel ORDER BY id DESC")
    data = cursor.fetchall()

    conn.close()

    return render_template('carousel.html', data=data)


@app.route('/add-carousel', methods=['POST'])
def add_carousel():
    description = request.form['description']
    image = request.files['image']
    filename = ""

    if image and image.filename != "":
        filename = secure_filename(image.filename)

        if not os.path.exists(app.config['CAROUSEL_FOLDER']):
            os.makedirs(app.config['CAROUSEL_FOLDER'])

        image.save(os.path.join(app.config['CAROUSEL_FOLDER'], filename))

        # ✅ SAVE CORRECT PATH
        filename = f"carousel/{filename}"

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO carousel (description, image)
        VALUES (%s, %s)
    """, (description, filename))

    conn.commit()
    conn.close()

    return redirect('/carousel')


@app.route('/delete-carousel/<int:id>')
def delete_carousel(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM carousel WHERE id=%s", (id,))
    conn.commit()
    conn.close()

    return redirect('/carousel')



# BOOKING ORDERS
@app.route('/admin-booking-orders')
def admin_booking_orders():

    if 'admin' not in session:
        return redirect('/admin')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            o.id,
            o.username,
            o.product_id,

            c.name AS category,
            s.name AS subcategory,

            o.quantity,
            o.full_name,
            o.phone,
            o.email,
            o.city,
            o.state,
            o.country,
            o.pincode,
            o.landmark,
            o.payment_mode,
            o.order_status,
            o.created_at,

            GROUP_CONCAT(pi.image) AS images

        FROM orders o

        LEFT JOIN categories c
            ON o.category_id = c.id

        LEFT JOIN subcategories s
            ON o.subcategory_id = s.id

        LEFT JOIN product_images pi
            ON o.product_id = pi.product_id

        WHERE o.order_status='Confirmed'

        GROUP BY o.id
        ORDER BY o.phone, o.id DESC
    """)

    orders = cursor.fetchall()

    for o in orders:
        o['images'] = (
            o['images'].split(',')
            if o['images'] else []
        )

    grouped = defaultdict(list)

    for o in orders:
        grouped[o['phone']].append(o)

    conn.close()

    return render_template(
        'admin_booking_orders.html',
        orders=orders,
        grouped=grouped
    )


@app.route('/parcel-order/<int:id>')
def parcel_order(id):

    if 'admin' not in session:
        return redirect('/admin')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # GET ORDER + PRODUCT DETAILS
    cursor.execute("""
        SELECT
            o.*,
            p.name AS product_name
        FROM orders o
        LEFT JOIN products p
            ON o.product_id = p.id
        WHERE o.id=%s
    """, (id,))

    order = cursor.fetchone()

    if not order:
        conn.close()
        return redirect('/admin-booking-orders')

    # UPDATE STATUS
    cursor.execute("""
        UPDATE orders
        SET order_status='Parcelled'
        WHERE id=%s
    """, (id,))

    conn.commit()

    # SEND WHATSAPP
    try:

        message = f"""
📦 Akki Latest Collections

Dear {order['full_name']},

Good News! 🎉

Your product has been parcelled successfully.

🛍 Product : {order['product_name']}
📦 Quantity : {order['quantity']}

Your parcel is now ready for dispatch and will reach you soon.

Thank you for shopping with Akki Latest Collections ❤️

Regards,
Akki Latest Collections
"""

        send_whatsapp(order['phone'],message)

    except Exception as e:
        print("WHATSAPP ERROR:", e)

    conn.close()

    return redirect('/admin-booking-orders')



# COMPLETE ORDER
@app.route('/complete-order/<int:id>')
def complete_order(id):

    if 'admin' not in session:
        return redirect('/admin')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE orders
        SET order_status='Completed'
        WHERE id=%s
    """,(id,))

    conn.commit()
    conn.close()

    return redirect('/admin-booking-orders')


# COMPLETED ORDERS
@app.route('/admin-completed-orders')
def admin_completed_orders():

    if 'admin' not in session:
        return redirect('/admin')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
    SELECT
        o.id,
        o.username,
        o.product_id,
        c.name AS category,
        s.name AS subcategory,
        o.quantity,
        o.full_name,
        o.phone,
        o.email,
        o.city,
        o.state,
        o.country,
        o.pincode,
        o.landmark,
        o.payment_mode,
        o.order_status,
        o.created_at,
        GROUP_CONCAT(pi.image) AS images
    FROM orders o

    LEFT JOIN categories c
    ON o.category_id = c.id

    LEFT JOIN subcategories s
    ON o.subcategory_id = s.id

    LEFT JOIN product_images pi
    ON o.product_id = pi.product_id

    WHERE o.order_status='Completed'

    GROUP BY o.id
    ORDER BY o.id DESC
""")
    orders = cursor.fetchall()

    for o in orders:
        o['images'] = (
            o['images'].split(',')
            if o['images'] else []
        )

    conn.close()

    return render_template(
        'admin_completed_orders.html',
        orders=orders
    )





@app.route('/admin-whatsapp')
def admin_whatsapp():

    if 'admin' not in session:
        return redirect('/admin')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT COUNT(DISTINCT phone) AS total
        FROM orders
        WHERE phone IS NOT NULL
        AND phone != ''
    """)

    result = cursor.fetchone()

    total_customers = result['total']

    conn.close()

    return render_template(
        'admin_whatsapp.html',
        total_customers=total_customers
    )


@app.route('/send-whatsapp-offer', methods=['POST'])
def send_whatsapp_offer():

    if 'admin' not in session:
        return redirect('/admin')

    user_message = request.form['message']

    message = f"""
🌸 Akki Latest Collections 🌸

{user_message}

━━━━━━━━━━━━━━━━━━

🛍 Shop Now:
https://akkilatestcollections.com

Thank you for choosing Akki Latest Collections ❤️

━━━━━━━━━━━━━━━━━━
"""

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT DISTINCT phone
        FROM orders
        WHERE phone IS NOT NULL
        AND phone != ''
    """)

    customers = cursor.fetchall()

    sent_count = 0
    failed_count = 0

    for customer in customers:

        phone = str(customer['phone']).strip()

        try:

            response = send_whatsapp(
                phone,
                message
            )

            if response and response.status_code == 200:
                sent_count += 1
            else:
                failed_count += 1

            # Wasender protection
            time.sleep(5)

        except Exception as e:

            failed_count += 1

            print(
                f"WhatsApp Error ({phone}):",
                e
            )

    conn.close()

    return f"""
    <html>
    <head>
        <title>WhatsApp Sent</title>

        <style>
            body {{
                font-family: Arial;
                text-align: center;
                padding-top: 100px;
                background: #f5f5f5;
            }}

            .box {{
                background: white;
                width: 500px;
                margin: auto;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 0 10px rgba(0,0,0,.1);
            }}

            .success {{
                color: green;
            }}

            .failed {{
                color: red;
            }}

            a {{
                display:inline-block;
                margin-top:20px;
                background:#25D366;
                color:white;
                padding:10px 20px;
                text-decoration:none;
                border-radius:6px;
            }}
        </style>
    </head>

    <body>

        <div class="box">

            <h2>WhatsApp Broadcast Completed</h2>

            <h3 class="success">
                Successfully Sent : {sent_count}
            </h3>

            <h3 class="failed">
                Failed : {failed_count}
            </h3>

            <a href="/admin-whatsapp">
                Back
            </a>

        </div>

    </body>
    </html>
    """




@app.route('/admin-reports')
def admin_reports():

    if 'admin' not in session:
        return redirect('/admin')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # TODAY SALES
    cursor.execute("""
        SELECT
            COUNT(*) AS orders,
            COALESCE(SUM(p.price * o.quantity),0) AS amount
        FROM orders o
        JOIN products p
            ON o.product_id = p.id
        WHERE DATE(o.created_at)=CURDATE()
    """)
    today = cursor.fetchone()

    # MONTH SALES
    cursor.execute("""
        SELECT
            COUNT(*) AS orders,
            COALESCE(SUM(p.price * o.quantity),0) AS amount
        FROM orders o
        JOIN products p
            ON o.product_id = p.id
        WHERE MONTH(o.created_at)=MONTH(CURDATE())
        AND YEAR(o.created_at)=YEAR(CURDATE())
    """)
    month = cursor.fetchone()

    # TOP PRODUCTS
    cursor.execute("""
        SELECT
            p.name,
            SUM(o.quantity) AS qty
        FROM orders o
        JOIN products p
            ON o.product_id = p.id
        GROUP BY o.product_id
        ORDER BY qty DESC
        LIMIT 10
    """)
    top_products = cursor.fetchall()

    labels = [p['name'] for p in top_products]
    values = [int(p['qty']) for p in top_products]

    conn.close()

    return render_template(
        'admin_reports.html',
        today=today,
        month=month,
        top_products=top_products,
        labels=labels,
        values=values
    )





# ================= LOGOUT =================
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/')


if __name__ == "__main__":
    app.run(debug=True)