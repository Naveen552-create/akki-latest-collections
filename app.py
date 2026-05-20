import time
from flask import Flask, render_template, request, jsonify, redirect, session
import mysql.connector
import os
from werkzeug.utils import secure_filename
from flask import *
from collections import defaultdict
from flask import jsonify
from cashfree_pg.api_client import Cashfree
from cashfree_pg.models.create_order_request import CreateOrderRequest
from cashfree_pg.models.customer_details import CustomerDetails
from cashfree_pg.models.order_meta import OrderMeta
import uuid


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
        database="u372412767_akki"
    )

# ================= HOME =================



@app.route('/')
def home():

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
            GROUP_CONCAT(pi.image) AS images
        FROM products p
        LEFT JOIN categories c
            ON p.category_id=c.id
        LEFT JOIN subcategories s
            ON p.subcategory_id=s.id
        LEFT JOIN product_images pi
            ON p.id=pi.product_id
        WHERE p.show_home=1
        AND p.quantity>0
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
            SELECT SUM(quantity) AS total
            FROM cart
            WHERE username=%s
        """, (session['user'],))

        result = cursor.fetchone()

        if result and result['total']:
            cart_count = result['total']

    cursor.close()
    conn.close()

    return render_template(
        'index.html',
        products=products,
        carousel_items=carousel_items,
        cart_count=cart_count
    )


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
        WHERE username=%s AND password=%s
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

        # RETURN TO PREVIOUS PAGE
        next_url = session.pop('next_url', None)

        return jsonify({
            "status": "success",
            "redirect": next_url if next_url else "/"
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

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

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
    """, (id,))

    product = cursor.fetchone()

    if not product:
        cursor.close()
        conn.close()
        return "Product not found"

    cursor.execute("""
        SELECT image
        FROM product_images
        WHERE product_id=%s
        ORDER BY id ASC
    """, (id,))

    product['images'] = [
        img['image']
        for img in cursor.fetchall()
        if img['image']
    ]

    cursor.execute("""
        SELECT
            p.id,
            p.name,
            p.price,
            GROUP_CONCAT(pi.image) AS images
        FROM products p
        LEFT JOIN product_images pi
            ON p.id = pi.product_id
        WHERE p.category_id=%s
        AND p.id!=%s
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





@app.route('/cart')
def cart():

    if 'user' not in session:
        return redirect('/')

    username=session['user']

    conn=get_db_connection()
    cursor=conn.cursor(dictionary=True)

    cursor.execute("""
SELECT
    cart.quantity as cart_qty,
    p.*,
    c.name as category,
    s.name as subcategory,
    GROUP_CONCAT(pi.image) as images
FROM cart
JOIN products p
    ON cart.product_id=p.id
LEFT JOIN categories c
    ON p.category_id=c.id
LEFT JOIN subcategories s
    ON p.subcategory_id=s.id
LEFT JOIN product_images pi
    ON p.id=pi.product_id
WHERE cart.username=%s
GROUP BY cart.id
""",(username,))


    products=cursor.fetchall()

    for p in products:
        p['images']=(
            p['images'].split(',')
            if p['images'] else []
        )

    conn.close()

    return render_template(
        'cart.html',
        products=products
    )

# ================= ADD TO CART =================
@app.route('/add-to-cart/<int:id>/<int:qty>')
def add_to_cart(id, qty):

    # LOGIN CHECK
    if 'user' not in session:

        # SAVE CURRENT URL
        session['next_url'] = request.url

        return redirect('/login-page')

    username = session['user']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # GET PRODUCT
    cursor.execute("""
        SELECT category_id, subcategory_id
        FROM products
        WHERE id=%s
    """, (id,))

    product = cursor.fetchone()

    # PRODUCT NOT FOUND
    if not product:

        conn.close()

        return redirect('/')

    # CHECK PRODUCT ALREADY IN CART
    cursor.execute("""
        SELECT * FROM cart
        WHERE username=%s AND product_id=%s
    """, (
        username,
        id
    ))

    existing = cursor.fetchone()

    # UPDATE QUANTITY
    if existing:

        cursor.execute("""
            UPDATE cart
            SET quantity = quantity + %s
            WHERE username=%s AND product_id=%s
        """, (
            qty,
            username,
            id
        ))

    # INSERT NEW PRODUCT
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
    conn.close()

    return redirect('/cart')


  


@app.route('/increase-cart/<int:id>')
def increase_cart(id):

    conn=get_db_connection()
    cursor=conn.cursor()

    cursor.execute("""
    UPDATE cart
    SET quantity=quantity+1
    WHERE product_id=%s
    AND username=%s
    """,(id,session['user']))

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

        # ================= PAYMENT FAILED/CANCELLED =================
        if order_status != "PAID":

            return redirect('/cart')

        # ================= PAYMENT SUCCESS =================
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # DEFAULT ADDRESS
        cursor.execute("""
            SELECT * FROM addresses
            WHERE username=%s AND is_default=1
        """, (username,))

        address = cursor.fetchone()

        if not address:
            return redirect('/place-all-order')

        # CART ITEMS
        cursor.execute("""
            SELECT * FROM cart
            WHERE username=%s
        """, (username,))

        cart_items = cursor.fetchall()

        for item in cart_items:

            # INSERT ORDER
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
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Confirmed')
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

            # INSERT ORDER ITEMS
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
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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

            # REDUCE STOCK
            cursor.execute("""
                UPDATE products
                SET quantity = quantity - %s
                WHERE id=%s
            """, (
                item['quantity'],
                item['product_id']
            ))

        # CLEAR CART
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




@app.route('/add-product', methods=['POST'])
def add_product():
    name = request.form['name'].strip()
    category_id = request.form['category_id']
    subcategory_id = request.form['subcategory_id']
    quantity = request.form['quantity']
    price = request.form['price']
    description = request.form['description']

    show_home = 1 if 'show_home' in request.form else 0

    if not category_id or not subcategory_id:
        return "Please select category and subcategory"

    conn = get_db_connection()
    cursor = conn.cursor()

    # Insert product
    cursor.execute("""
        INSERT INTO products
        (name, category_id, subcategory_id, quantity, price, description, show_home)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, (
        name,
        category_id,
        subcategory_id,
        quantity,
        price,
        description,
        show_home
    ))

    product_id = cursor.lastrowid

    images = request.files.getlist('images')

    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    for image in images:
        if image and image.filename != '':
            filename = secure_filename(image.filename)

            image.save(
                os.path.join(
                    app.config['UPLOAD_FOLDER'],
                    filename
                )
            )

            filepath = f"uploads/{filename}"

            cursor.execute("""
                INSERT INTO product_images
                (product_id, image)
                VALUES (%s,%s)
            """, (product_id, filepath))

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
            GROUP_CONCAT(pi.image) AS images
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

    # 1. Get all images of product
    cursor.execute("""
        SELECT image
        FROM product_images
        WHERE product_id=%s
    """, (id,))

    images = cursor.fetchall()

    # 2. Delete images from disk safely
    for img in images:
        if img['image']:
            file_path = os.path.join(
                app.config['UPLOAD_FOLDER'],
                os.path.basename(img['image'])  # only filename
            )

            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print("File delete error:", file_path, e)

    # 3. Delete from product_images table
    cursor.execute("""
        DELETE FROM product_images
        WHERE product_id=%s
    """, (id,))

    # 4. Delete from products table
    cursor.execute("""
        DELETE FROM products
        WHERE id=%s
    """, (id,))

    conn.commit()

    cursor.close()
    conn.close()

    return redirect('/admin/products')
# ================= EDIT PRODUCT =================
@app.route('/edit-product/<int:id>', methods=['GET', 'POST'])
def edit_product(id):

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':

        name = request.form['name'].strip()
        price = float(request.form['price'])
        quantity = int(request.form['quantity'])
        description = request.form['description'].strip()

        show_home = 1 if 'show_home' in request.form else 0

        # Update product
        cursor.execute("""
            UPDATE products
            SET
                name=%s,
                price=%s,
                quantity=%s,
                description=%s,
                show_home=%s
            WHERE id=%s
        """,(
            name,
            price,
            quantity,
            description,
            show_home,
            id
        ))


        # Delete selected images
        delete_images = request.form.getlist('delete_images')

        for img in delete_images:

            img_path = os.path.join('static', img)

            if os.path.exists(img_path):
                os.remove(img_path)

            cursor.execute("""
                DELETE FROM product_images
                WHERE product_id=%s
                AND image=%s
            """,(id,img))


        # Add new images
        images = request.files.getlist('images')

        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])

        for image in images:

            if image and image.filename != '':

                filename = secure_filename(image.filename)

                save_path = os.path.join(
                    app.config['UPLOAD_FOLDER'],
                    filename
                )

                image.save(save_path)

                filepath = f"uploads/{filename}"

                cursor.execute("""
                    INSERT INTO product_images
                    (product_id,image)
                    VALUES(%s,%s)
                """,(id,filepath))


        conn.commit()
        conn.close()

        return redirect('/manage-products')


    # GET PRODUCT
    cursor.execute("""
        SELECT *
        FROM products
        WHERE id=%s
    """,(id,))

    product = cursor.fetchone()


    # GET PRODUCT IMAGES
    cursor.execute("""
        SELECT image
        FROM product_images
        WHERE product_id=%s
    """,(id,))

    product['images'] = cursor.fetchall()

    conn.close()

    return render_template(
        'edit_product.html',
        product=product
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



















# ================= LOGOUT =================
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/')


if __name__ == "__main__":
    app.run(debug=True)