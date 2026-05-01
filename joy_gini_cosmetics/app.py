from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from config import Config
from models import db, Product, Review, Customer, Order, OrderItem, Employee, Setting, Banner
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import uuid
import json

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    db.create_all()
    # create default admin if not exists
    if not Employee.query.filter_by(email='admin@joygini.com').first():
        admin = Employee(
            employee_id='EMP001',
            name='Admin',
            mobile='0000000000',
            email='admin@joygini.com',
            password_hash=generate_password_hash('admin123'),
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
    # default settings
    if not Setting.query.filter_by(key='gst_rate').first():
        db.session.add_all([
            Setting(key='gst_rate', value='18'),
            Setting(key='store_name', value='Joy Gini Cosmetics'),
            Setting(key='store_address', value='Your Store Address'),
            Setting(key='store_phone', value='+91 9876543210'),
            Setting(key='facebook_url', value=''),
            Setting(key='instagram_url', value=''),
            Setting(key='twitter_url', value=''),
            Setting(key='logo_filename', value='')
        ])
        db.session.commit()

def get_settings():
    return {s.key: s.value for s in Setting.query.all()}

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('admin_login'))
        admin = Employee.query.get(session['admin_id'])
        if not admin or admin.role != 'admin':
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

def employee_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# ------------------ CUSTOMER FRONTEND ------------------
@app.route('/')
def index():
    products = Product.query.all()
    banners = Banner.query.filter_by(is_active=True).order_by(Banner.order_index).all()
    settings = get_settings()
    categories = list(set([p.category for p in products if p.category]))
    
    # Convert products to JSON serializable format
    products_serialized = []
    for p in products:
        products_serialized.append({
            'id': p.id,
            'title': p.title,
            'description': p.description,
            'category': p.category,
            'price': p.price,
            'stock_quantity': p.stock_quantity,
            'image_filename': p.image_filename,
            'barcode_data': p.barcode_data
        })
    
    return render_template('index.html', products=products_serialized, banners=banners, settings=settings, categories=categories)

@app.route('/api/product_rating/<int:id>')
def api_product_rating(id):
    from sqlalchemy import func
    result = db.session.query(func.avg(Review.rating), func.count(Review.id)).filter(Review.product_id == id).first()
    avg = float(result[0]) if result[0] else 0
    count = result[1] if result[1] else 0
    return jsonify({'avg': avg, 'count': count})

@app.route('/product/<int:id>')
def product_detail(id):
    product = Product.query.get_or_404(id)
    reviews = Review.query.filter_by(product_id=id).all()
    settings = get_settings()
    return render_template('product_detail.html', product=product, reviews=reviews, settings=settings)

@app.route('/submit_review', methods=['POST'])
def submit_review():
    product_id = request.form.get('product_id')
    name = request.form.get('name')
    rating = int(request.form.get('rating'))
    comment = request.form.get('comment')
    if product_id and name and rating:
        review = Review(product_id=product_id, customer_name=name, rating=rating, comment=comment)
        db.session.add(review)
        db.session.commit()
        flash('Review submitted!', 'success')
    return redirect(url_for('product_detail', id=product_id))

@app.route('/place_order', methods=['POST'])
def place_order():
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity'))
    customer_name = request.form.get('customer_name')
    customer_mobile = request.form.get('customer_mobile')
    address = request.form.get('address')
    product = Product.query.get_or_404(product_id)
    if product.stock_quantity < quantity:
        flash('Out of stock!', 'danger')
        return redirect(url_for('product_detail', id=product_id))
    total = product.price * quantity
    customer = Customer.query.filter_by(mobile=customer_mobile).first()
    if not customer:
        customer = Customer(name=customer_name, mobile=customer_mobile, address=address)
        db.session.add(customer)
        db.session.commit()
    else:
        customer.name = customer_name
        customer.address = address
        db.session.commit()
    order_id = str(uuid.uuid4().hex[:8].upper())
    new_order = Order(order_id=order_id, customer_id=customer.id, total_amount=total, shipping_address=address, status='Pending')
    db.session.add(new_order)
    db.session.commit()
    order_item = OrderItem(order_id=new_order.id, product_id=product.id, quantity=quantity, price_at_time=product.price)
    db.session.add(order_item)
    product.stock_quantity -= quantity
    db.session.commit()
    return redirect(url_for('order_success', order_id=new_order.id))

@app.route('/order_success/<int:order_id>')
def order_success(order_id):
    order = Order.query.get_or_404(order_id)
    settings = get_settings()
    return render_template('order_success.html', order=order, settings=settings)

# ------------------ ADMIN & EMPLOYEE LOGIN ------------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        emp = Employee.query.filter_by(email=email, is_active=True).first()
        if emp and check_password_hash(emp.password_hash, password):
            session['admin_id'] = emp.id
            session['admin_name'] = emp.name
            session['admin_role'] = emp.role
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('index'))

# ------------------ PASSWORD CHANGE ------------------
@app.route('/admin/change_password', methods=['GET', 'POST'])
@employee_required
def admin_change_password():
    emp = Employee.query.get(session['admin_id'])
    if request.method == 'POST':
        old = request.form.get('old_password')
        new = request.form.get('new_password')
        confirm = request.form.get('confirm_password')
        if not check_password_hash(emp.password_hash, old):
            flash('Current password is incorrect', 'danger')
        elif new != confirm:
            flash('New passwords do not match', 'danger')
        elif len(new) < 4:
            flash('Password must be at least 4 characters', 'danger')
        else:
            emp.password_hash = generate_password_hash(new)
            db.session.commit()
            flash('Password changed successfully! Please login again.', 'success')
            session.clear()
            return redirect(url_for('admin_login'))
    return render_template('admin/change_password.html')

# ------------------ ADMIN DASHBOARD ------------------
@app.route('/admin/dashboard')
@employee_required
def admin_dashboard():
    products_count = Product.query.count()
    orders_count = Order.query.count()
    customers_count = Customer.query.count()
    low_stock = Product.query.filter(Product.stock_quantity < 5).count()
    recent_orders = Order.query.order_by(Order.order_date.desc()).limit(5).all()
    low_stock_items = Product.query.filter(Product.stock_quantity < 5).order_by(Product.stock_quantity.asc()).limit(5).all()
    from sqlalchemy import func
    top_categories = db.session.query(
        Product.category, 
        func.sum(OrderItem.quantity).label('total_sold')
    ).join(OrderItem, Product.id == OrderItem.product_id)\
     .group_by(Product.category)\
     .order_by(func.sum(OrderItem.quantity).desc())\
     .limit(5).all()
    category_labels = [cat[0] if cat[0] else 'Uncategorized' for cat in top_categories]
    category_values = [cat[1] for cat in top_categories]
    return render_template('admin/dashboard.html', 
                           products_count=products_count,
                           orders_count=orders_count,
                           customers_count=customers_count,
                           low_stock=low_stock,
                           recent_orders=recent_orders,
                           low_stock_items=low_stock_items,
                           category_labels=category_labels,
                           category_values=category_values)

# ------------------ PRODUCT MANAGEMENT (3-in-1 AJAX) ------------------
@app.route('/admin/products')
@employee_required
def admin_products():
    products = Product.query.all()
    return render_template('admin/products.html', products=products)

@app.route('/admin/product/data/<int:id>')
@employee_required
def admin_product_data(id):
    product = Product.query.get_or_404(id)
    return jsonify({
        'id': product.id,
        'title': product.title,
        'category': product.category,
        'description': product.description,
        'price': product.price,
        'stock_quantity': product.stock_quantity,
        'barcode_data': product.barcode_data,
        'image_filename': product.image_filename
    })

@app.route('/admin/product/data/by_barcode')
@employee_required
def admin_product_by_barcode():
    barcode = request.args.get('barcode')
    product = Product.query.filter_by(barcode_data=barcode).first()
    if product:
        return jsonify({
            'id': product.id,
            'title': product.title,
            'price': product.price,
            'stock_quantity': product.stock_quantity,
            'barcode_data': product.barcode_data
        })
    return jsonify({'id': None})

@app.route('/admin/product/search')
@employee_required
def admin_product_search():
    q = request.args.get('q', '')
    if len(q) < 2:
        return jsonify([])
    products = Product.query.filter(
        (Product.title.ilike(f'%{q}%')) | (Product.barcode_data.ilike(f'%{q}%'))
    ).limit(10).all()
    return jsonify([{
        'id': p.id,
        'title': p.title,
        'price': p.price,
        'stock': p.stock_quantity,
        'barcode': p.barcode_data
    } for p in products])

@app.route('/admin/product/add', methods=['POST'])
@employee_required
def admin_product_add_ajax():
    title = request.form.get('title')
    description = request.form.get('description')
    category = request.form.get('category')
    price = float(request.form.get('price'))
    stock = int(request.form.get('stock'))
    barcode = request.form.get('barcode') or str(uuid.uuid4().hex[:10])
    image = request.files.get('image')
    filename = ''
    if image and image.filename:
        filename = secure_filename(image.filename)
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'products')
        os.makedirs(upload_path, exist_ok=True)
        image.save(os.path.join(upload_path, filename))
    product = Product(
        title=title,
        description=description,
        category=category,
        price=price,
        stock_quantity=stock,
        barcode_data=barcode,
        image_filename=filename
    )
    db.session.add(product)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/product/edit/<int:id>', methods=['POST'])
@employee_required
def admin_product_edit_ajax(id):
    product = Product.query.get_or_404(id)
    product.title = request.form.get('title')
    product.description = request.form.get('description')
    product.category = request.form.get('category')
    product.price = float(request.form.get('price'))
    product.stock_quantity = int(request.form.get('stock'))
    if request.form.get('barcode'):
        product.barcode_data = request.form.get('barcode')
    if request.files.get('image') and request.files['image'].filename:
        image = request.files['image']
        filename = secure_filename(image.filename)
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'products')
        os.makedirs(upload_path, exist_ok=True)
        image.save(os.path.join(upload_path, filename))
        product.image_filename = filename
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/product/delete/<int:id>', methods=['POST'])
@employee_required
def admin_product_delete_ajax(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    return jsonify({'success': True})

# ------------------ STOCK MANAGEMENT ------------------
@app.route('/admin/stock')
@employee_required
def admin_stock():
    products = Product.query.all()
    total_products = len(products)
    low_stock_count = Product.query.filter(Product.stock_quantity < 5).count()
    total_stock_value = sum(p.price * p.stock_quantity for p in products)
    return render_template('admin/stock.html', 
                           products=products,
                           total_products=total_products,
                           low_stock_count=low_stock_count,
                           total_stock_value=total_stock_value)

@app.route('/admin/stock/update', methods=['POST'])
@employee_required
def admin_stock_update():
    barcode = request.form.get('barcode')
    change = int(request.form.get('change'))
    product = Product.query.filter_by(barcode_data=barcode).first()
    if product:
        product.stock_quantity += change
        if product.stock_quantity < 0:
            product.stock_quantity = 0
        db.session.commit()
        flash(f'Stock updated for {product.title}', 'success')
    else:
        flash('Product not found', 'danger')
    return redirect(url_for('admin_stock'))

@app.route('/admin/stock/update_by_id', methods=['POST'])
@employee_required
def admin_stock_update_by_id():
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        change = int(data.get('change'))
        product = Product.query.get(product_id)
        if not product:
            return jsonify({'success': False, 'message': 'Product not found'}), 404
        new_stock = product.stock_quantity + change
        if new_stock < 0:
            new_stock = 0
        product.stock_quantity = new_stock
        db.session.commit()
        return jsonify({'success': True, 'new_stock': new_stock})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/stock/update_by_barcode', methods=['POST'])
@employee_required
def admin_stock_update_by_barcode():
    try:
        data = request.get_json()
        barcode = data.get('barcode')
        change = int(data.get('change'))
        product = Product.query.filter_by(barcode_data=barcode).first()
        if not product:
            return jsonify({'success': False, 'message': 'Product not found'}), 404
        new_stock = product.stock_quantity + change
        if new_stock < 0:
            new_stock = 0
        product.stock_quantity = new_stock
        db.session.commit()
        return jsonify({'success': True, 'new_stock': new_stock, 'title': product.title})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ------------------ OFFLINE BILLING ------------------
@app.route('/admin/billing', methods=['GET', 'POST'])
@employee_required
def admin_billing():
    if request.method == 'POST':
        is_manual = request.form.get('is_manual') == '1'
        qty = int(request.form.get('quantity'))
        customer_name = request.form.get('customer_name')
        customer_mobile = request.form.get('customer_mobile', '')
        customer_address = request.form.get('customer_address', '')
        discount_type = request.form.get('discount_type')
        discount_value = float(request.form.get('discount_value', 0))
        
        if is_manual:
            # Manual product: create a dummy product or store custom
            product_name = request.form.get('manual_product_name')
            product_price = float(request.form.get('manual_price'))
            # Option 1: Create a temporary product (not recommended)
            # Option 2: Use a special product id = -1 and adjust OrderItem schema
            # For simplicity, we'll treat it as a custom order item without a product record.
            # But OrderItem requires product_id. We can create a dummy product with name "Manual: ..."
            # For now, let's create an ad-hoc product (will be saved in DB)
            dummy = Product(
                title=f"Manual: {product_name}",
                price=product_price,
                stock_quantity=99999,
                barcode_data=f"MANUAL_{uuid.uuid4().hex[:6]}",
                description="Manual entry item"
            )
            db.session.add(dummy)
            db.session.commit()
            product = dummy
        else:
            barcode = request.form.get('barcode')
            product_id = request.form.get('product_id')
            product = None
            if barcode:
                product = Product.query.filter_by(barcode_data=barcode).first()
            if not product and product_id:
                product = Product.query.get(product_id)
            if not product:
                flash('Product not found', 'danger')
                return redirect(url_for('admin_billing'))
            if product.stock_quantity < qty:
                flash(f'Insufficient stock for {product.title}', 'danger')
                return redirect(url_for('admin_billing'))
        
        # Rest of the billing logic ...
        # (subtotal, discount, customer, order, order_item, stock deduction only if not manual)
        # For manual, do not reduce stock.
        
        # Calculate total after discount
        subtotal = product.price * qty
        if discount_type == 'percent':
            discount_amount = subtotal * (discount_value / 100)
        else:
            discount_amount = discount_value
        total = subtotal - discount_amount
        if total < 0:
            total = 0
        
        # Create or update customer
        customer = None
        if customer_mobile:
            customer = Customer.query.filter_by(mobile=customer_mobile).first()
        if not customer:
            customer = Customer(name=customer_name, mobile=customer_mobile or '', address=customer_address)
            db.session.add(customer)
            db.session.commit()
        else:
            customer.name = customer_name
            customer.address = customer_address
            db.session.commit()
        
        # Create order (offline invoice)
        order_id = 'INV-' + datetime.now().strftime('%Y%m%d%H%M%S')
        order = Order(
            order_id=order_id,
            customer_id=customer.id,
            total_amount=total,
            shipping_address=customer_address,
            status='Completed',
            notes=f"Discount: {discount_amount} ({discount_type})" if discount_amount > 0 else ''
        )
        db.session.add(order)
        db.session.commit()
        
        item = OrderItem(order_id=order.id, product_id=product.id, quantity=qty, price_at_time=product.price)
        db.session.add(item)
        product.stock_quantity -= qty
        db.session.commit()
        
        return redirect(url_for('thermal_invoice', order_id=order.id))
    
    products = Product.query.all()
    return render_template('admin/billing.html', products=products)

@app.route('/admin/invoice/<int:order_id>')
@employee_required
def thermal_invoice(order_id):
    order = Order.query.get_or_404(order_id)
    settings = get_settings()
    return render_template('admin/thermal_invoice.html', order=order, settings=settings)

# ------------------ CUSTOMER MANAGEMENT (FIXED DELETE) ------------------
@app.route('/admin/customers')
@employee_required
def admin_customers():
    customers = Customer.query.all()
    return render_template('admin/customers.html', customers=customers)

@app.route('/admin/customer/delete/<int:id>', methods=['POST'])
@employee_required
def admin_customer_delete(id):
    try:
        cust = Customer.query.get_or_404(id)
        
        # First, delete all orders of this customer and restore stock for each order item
        for order in cust.orders:
            for item in order.items:
                product = Product.query.get(item.product_id)
                if product:
                    product.stock_quantity += item.quantity
            db.session.delete(order)
        
        # Now delete the customer
        db.session.delete(cust)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Customer and all orders deleted, stock restored.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/customer/history/<int:id>')
@employee_required
def admin_customer_history(id):
    cust = Customer.query.get_or_404(id)
    orders = cust.orders
    return render_template('admin/customer_history.html', customer=cust, orders=orders)

# ------------------ ONLINE ORDERS MANAGEMENT ------------------
@app.route('/admin/orders')
@employee_required
def admin_orders():
    orders = Order.query.order_by(Order.order_date.desc()).all()
    return render_template('admin/orders.html', orders=orders)

@app.route('/admin/order/update_status/<int:id>', methods=['POST'])
@employee_required
def admin_order_update_status(id):
    order = Order.query.get_or_404(id)
    order.status = request.form.get('status')
    db.session.commit()
    flash('Order status updated', 'success')
    return redirect(url_for('admin_orders'))

@app.route('/admin/order/delete/<int:id>')
@employee_required
def admin_order_delete(id):
    order = Order.query.get_or_404(id)
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product:
            product.stock_quantity += item.quantity
    db.session.delete(order)
    db.session.commit()
    flash('Order deleted and stock restored', 'success')
    return redirect(url_for('admin_orders'))

@app.route('/admin/order/view/<int:id>')
@employee_required
def admin_order_view(id):
    order = Order.query.get_or_404(id)
    settings = get_settings()
    return render_template('admin/order_view.html', order=order, settings=settings)

# ------------------ EMPLOYEE MANAGEMENT ------------------
@app.route('/admin/employees')
@admin_required
def admin_employees():
    employees = Employee.query.all()
    return render_template('admin/employees.html', employees=employees)

@app.route('/admin/employee/add', methods=['GET', 'POST'])
@admin_required
def admin_employee_add():
    if request.method == 'POST':
        name = request.form.get('name')
        mobile = request.form.get('mobile')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        emp_id = 'EMP' + str(uuid.uuid4().hex[:4]).upper()
        emp = Employee(employee_id=emp_id, name=name, mobile=mobile, email=email, password_hash=generate_password_hash(password), role=role)
        db.session.add(emp)
        db.session.commit()
        flash('Employee added', 'success')
        return redirect(url_for('admin_employees'))
    return render_template('admin/employee_form.html', emp=None)

@app.route('/admin/employee/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_employee_edit(id):
    emp = Employee.query.get_or_404(id)
    if request.method == 'POST':
        emp.name = request.form.get('name')
        emp.mobile = request.form.get('mobile')
        emp.email = request.form.get('email')
        if request.form.get('password'):
            emp.password_hash = generate_password_hash(request.form.get('password'))
        emp.role = request.form.get('role')
        emp.is_active = 'is_active' in request.form
        db.session.commit()
        
        # যদি লগইন করা ইউজার নিজের তথ্য পরিবর্তন করে, তাহলে সেশন আপডেট করো
        if session.get('admin_id') == emp.id:
            session['admin_name'] = emp.name
            session['admin_role'] = emp.role
        
        flash('Employee updated', 'success')
        return redirect(url_for('admin_employees'))
    return render_template('admin/employee_form.html', emp=emp)

@app.route('/admin/employee/delete/<int:id>')
@admin_required
def admin_employee_delete(id):
    emp = Employee.query.get_or_404(id)
    db.session.delete(emp)
    db.session.commit()
    flash('Employee deleted', 'success')
    return redirect(url_for('admin_employees'))

# ------------------ SALES REPORT (Excel Download) ------------------
@app.route('/admin/sales_report')
@employee_required
def admin_sales_report():
    return render_template('admin/sales_report.html')

@app.route('/admin/sales_report_data')
@employee_required
def admin_sales_report_data():
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    # Get date range from query parameters
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    period = request.args.get('period', 'custom')
    
    today = datetime.now().date()
    
    # Calculate date range based on period
    if period == 'weekly':
        start_date = today - timedelta(days=7)
        end_date = today
    elif period == 'monthly':
        start_date = today - timedelta(days=30)
        end_date = today
    elif period == '6months':
        start_date = today - timedelta(days=180)
        end_date = today
    elif period == '1year':
        start_date = today - timedelta(days=365)
        end_date = today
    else:  # custom
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else today - timedelta(days=30)
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else today
    
    # Query sales data (only Completed orders)
    sales_data = db.session.query(
        Product.title,
        Product.price,
        func.sum(OrderItem.quantity).label('total_quantity'),
        func.sum(OrderItem.quantity * OrderItem.price_at_time).label('total_amount')
    ).join(OrderItem, Product.id == OrderItem.product_id)\
     .join(Order, Order.id == OrderItem.order_id)\
     .filter(Order.status == 'Completed')\
     .filter(func.date(Order.order_date) >= start_date)\
     .filter(func.date(Order.order_date) <= end_date)\
     .group_by(Product.id)\
     .order_by(func.sum(OrderItem.quantity * OrderItem.price_at_time).desc())\
     .all()
    
    # Calculate grand total
    grand_total = sum(row.total_amount for row in sales_data if row.total_amount)
    
    # Prepare data for JSON response
    data = []
    for row in sales_data:
        data.append({
            'title': row.title,
            'price': float(row.price),
            'total_quantity': int(row.total_quantity),
            'total_amount': float(row.total_amount) if row.total_amount else 0
        })
    
    return jsonify({
        'data': data,
        'grand_total': float(grand_total),
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d')
    })

@app.route('/admin/sales_report_download')
@employee_required
def admin_sales_report_download():
    import csv
    from datetime import datetime, timedelta
    from io import StringIO
    from flask import Response
    
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    period = request.args.get('period', 'custom')
    
    today = datetime.now().date()
    
    if period == 'weekly':
        start_date = today - timedelta(days=7)
        end_date = today
    elif period == 'monthly':
        start_date = today - timedelta(days=30)
        end_date = today
    elif period == '6months':
        start_date = today - timedelta(days=180)
        end_date = today
    elif period == '1year':
        start_date = today - timedelta(days=365)
        end_date = today
    else:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else today - timedelta(days=30)
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else today
    
    sales_data = db.session.query(
        Product.title,
        Product.price,
        func.sum(OrderItem.quantity).label('total_quantity'),
        func.sum(OrderItem.quantity * OrderItem.price_at_time).label('total_amount')
    ).join(OrderItem, Product.id == OrderItem.product_id)\
     .join(Order, Order.id == OrderItem.order_id)\
     .filter(Order.status == 'Completed')\
     .filter(func.date(Order.order_date) >= start_date)\
     .filter(func.date(Order.order_date) <= end_date)\
     .group_by(Product.id)\
     .order_by(Product.title)\
     .all()
    
    grand_total = sum(row.total_amount for row in sales_data if row.total_amount)
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write headers
    writer.writerow(['Sales Report', f'{start_date} to {end_date}'])
    writer.writerow([])
    writer.writerow(['Product Name', 'Unit Price (₹)', 'Quantity Sold', 'Total Amount (₹)'])
    
    # Write data rows
    for row in sales_data:
        writer.writerow([
            row.title,
            f"{float(row.price):.2f}",
            int(row.total_quantity),
            f"{float(row.total_amount):.2f}" if row.total_amount else "0.00"
        ])
    
    writer.writerow([])
    writer.writerow(['GRAND TOTAL', '', '', f"{float(grand_total):.2f}"])
    writer.writerow([])
    writer.writerow(['Generated on:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    
    # Return as CSV file
    output.seek(0)
    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename=sales_report_{start_date}_to_{end_date}.csv'
    
    return response

# ------------------ SETTINGS ------------------
@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    if request.method == 'POST':
        for key in ['gst_rate', 'store_name', 'store_address', 'store_phone', 'facebook_url', 'instagram_url', 'twitter_url']:
            value = request.form.get(key, '')
            setting = Setting.query.filter_by(key=key).first()
            if setting:
                setting.value = value
            else:
                db.session.add(Setting(key=key, value=value))
        logo_file = request.files.get('logo')
        if logo_file and logo_file.filename:
            filename = secure_filename('logo_' + datetime.now().strftime('%Y%m%d%H%M%S') + '.png')
            upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'logo')
            os.makedirs(upload_path, exist_ok=True)
            logo_file.save(os.path.join(upload_path, filename))
            logo_setting = Setting.query.filter_by(key='logo_filename').first()
            if logo_setting:
                logo_setting.value = filename
            else:
                db.session.add(Setting(key='logo_filename', value=filename))
        db.session.commit()
        flash('Settings saved', 'success')
        return redirect(url_for('admin_settings'))
    settings = get_settings()
    banners = Banner.query.all()
    return render_template('admin/settings.html', settings=settings, banners=banners)

@app.route('/admin/banner/add', methods=['POST'])
@admin_required
def admin_banner_add():
    image = request.files.get('banner_image')
    link = request.form.get('link_url')
    if image and image.filename:
        filename = secure_filename('banner_' + datetime.now().strftime('%Y%m%d%H%M%S') + '.jpg')
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'banners')
        os.makedirs(upload_path, exist_ok=True)
        image.save(os.path.join(upload_path, filename))
        banner = Banner(image_filename=filename, link_url=link, order_index=Banner.query.count()+1)
        db.session.add(banner)
        db.session.commit()
        flash('Banner added', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/admin/banner/delete/<int:id>')
@admin_required
def admin_banner_delete(id):
    banner = Banner.query.get_or_404(id)
    db.session.delete(banner)
    db.session.commit()
    flash('Banner deleted', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/admin/banner/edit/<int:id>', methods=['POST'])
@admin_required
def admin_banner_edit(id):
    banner = Banner.query.get_or_404(id)
    banner.link_url = request.form.get('link_url')
    banner.is_active = 'is_active' in request.form
    db.session.commit()
    flash('Banner updated', 'success')
    return redirect(url_for('admin_settings'))

# ------------------ RUN ------------------
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'products'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'banners'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'logo'), exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)