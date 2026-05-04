# =============================================================================
# app.py — The Flask Application
# =============================================================================
#
# WHAT IS THIS FILE?
# This is the brain of the app. Every URL the browser visits maps to a
# Python function here (called a "route" or "view"). The function does some
# work — reads from the database, processes data, etc. — then returns an
# HTML page for the browser to display.
#
# HOW A ROUTE WORKS:
#
#   @app.route('/customers')       ← "When the browser visits /customers..."
#   def customers():               ← "...run this function"
#       all_customers = Customer.query.all()   ← get data from DB
#       return render_template('customers.html', customers=all_customers)
#                                  ← send HTML page back to browser
#
# The data you pass into render_template() becomes available as variables
# inside the HTML template. So {{ customers }} in the HTML will show the list.
#
# HTTP METHODS — GET vs POST:
#   GET  = browser is *fetching* a page (just viewing it)
#   POST = browser is *sending* data (submitting a form, saving something)
#
#   @app.route('/customers', methods=['GET', 'POST'])
#   means this route handles both viewing the page AND saving new customers.
# =============================================================================

import os
import json
from datetime import datetime
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify)
from flask_migrate import Migrate

from models import db, Settings, Customer, Product, Invoice, InvoiceLine, CustomerPayment

# =============================================================================
# APP CONFIGURATION
# =============================================================================

app = Flask(__name__)

# SECRET_KEY is used to encrypt the session cookie (the thing that remembers
# you're logged in between page visits). In production you'd use a long random
# string. os.environ.get() checks for an environment variable first —
# this is how you'd set it on a live server without hardcoding it.
app.secret_key = os.environ.get('SECRET_KEY', 'jgm-dev-secret-change-in-production')

# Tell SQLAlchemy where the database file is.
# /// means "relative path from this file". So jgm.db will be created
# in the same folder as app.py.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///jgm.db'

# Disable a feature we don't need (saves memory)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Connect the db object (from models.py) to this Flask app
db.init_app(app)

# Flask-Migrate manages database structure changes (adding columns, etc.)
# without losing your data. Think of it as version control for your database.
migrate = Migrate(app, db)


# =============================================================================
# DATABASE INITIALISATION
# =============================================================================
# This runs once when the app starts. It creates the database file and all
# tables if they don't exist yet. If they already exist, it does nothing —
# so your data is safe.

def init_db():
    with app.app_context():
        db.create_all()
        # Create the default settings row if it doesn't exist yet
        if not Settings.query.first():
            db.session.add(Settings())
            db.session.commit()
        # Seed default products if the products table is empty
        if not Product.query.first():
            defaults = [
                Product(name='Coca-Cola 500ml x24',       sku='CC-500-24', category='Drinks',        price=12.50, vat=20, stock=50),
                Product(name='Pepsi 500ml x24',            sku='PP-500-24', category='Drinks',        price=11.99, vat=20, stock=40),
                Product(name='Red Bull 250ml x24',         sku='RB-250-24', category='Drinks',        price=22.00, vat=20, stock=30),
                Product(name='Walkers Crisps Variety x32', sku='WK-VAR-32', category='Snacks',        price=9.50,  vat=20, stock=25),
                Product(name='Basmati Rice 5kg',           sku='BR-5KG',    category='Grocery',       price=8.99,  vat=0,  stock=60),
                Product(name='Plain Flour 1.5kg',          sku='PF-15KG',   category='Grocery',       price=1.49,  vat=0,  stock=80),
                Product(name='Digestive Biscuits x24',     sku='DB-24',     category='Confectionery', price=14.40, vat=0,  stock=20),
                Product(name='Fairy Liquid 900ml x6',      sku='FL-900-6',  category='Household',     price=13.20, vat=20, stock=35),
                Product(name='Nescafe Gold 200g',          sku='NE-200G',   category='Hot Drinks',    price=6.50,  vat=20, stock=45),
                Product(name='Tetley Tea Bags 240',        sku='TT-240',    category='Hot Drinks',    price=5.99,  vat=0,  stock=55),
            ]
            db.session.add_all(defaults)
            db.session.commit()

# This ensures init_db() runs whether the app is started via
# "python app.py" (local) OR via gunicorn (Railway production).
with app.app_context():
    init_db()


# =============================================================================
# HELPER: LOGIN REQUIRED
# =============================================================================
# This is a decorator factory. Any route decorated with @login_required
# will redirect to the PIN screen if the user isn't logged in.
#
# session is a Flask object that stores data for the current user between
# requests (it's stored in a cookie in their browser).

from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('pin'))
        return f(*args, **kwargs)
    return decorated


# =============================================================================
# HELPER: VAT CALCULATION
# =============================================================================
def calc_line_total(unit_price, qty, vat_rate, vat_mode):
    """
    Calculate the final charged total for a line item.
    - standard:  price is ex-VAT, VAT added on top
    - exempt:    price charged as-is, no VAT
    - inclusive: price already contains VAT, charged as-is
    """
    net = unit_price * qty
    if vat_mode == 'standard':
        return round(net + net * (vat_rate / 100), 2)
    return round(net, 2)  # exempt and inclusive: straight total


def calc_invoice_totals(lines_data):
    """
    Given a list of line dicts, return (sub, vat_amt, total).
    sub     = net amount of standard-rated lines (ex-VAT)
    vat_amt = total VAT charged (from standard lines only)
    total   = everything added together
    """
    std_net = 0.0
    std_vat = 0.0
    exempt_net = 0.0
    incl_total = 0.0

    for ln in lines_data:
        net = ln['unit_price'] * ln['qty']
        vm  = ln.get('vat_mode', 'standard')
        if vm == 'standard':
            v = net * (ln.get('vat', 20) / 100)
            std_net += net
            std_vat += v
        elif vm == 'exempt':
            exempt_net += net
        elif vm == 'inclusive':
            incl_total += net

    sub   = std_net + exempt_net + incl_total
    total = std_net + std_vat + exempt_net + incl_total
    return round(sub, 2), round(std_vat, 2), round(total, 2)


# =============================================================================
# ── AUTHENTICATION ROUTES ─────────────────────────────────────────────────────
# =============================================================================

@app.route('/', methods=['GET', 'POST'])
def pin():
    """
    The PIN login screen.
    GET  → show the PIN page
    POST → check the submitted PIN against the database
    """
    if session.get('logged_in'):
        return redirect(url_for('home'))

    if request.method == 'POST':
        entered = request.form.get('pin', '')
        settings = Settings.query.first()
        if entered == settings.pin:
            session['logged_in'] = True      # store login state in session
            return redirect(url_for('home'))
        else:
            flash('Incorrect PIN. Please try again.', 'error')

    return render_template('pin.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('pin'))


# =============================================================================
# ── HOME ──────────────────────────────────────────────────────────────────────
# =============================================================================

@app.route('/home')
@login_required
def home():
    settings  = Settings.query.first()
    products  = Product.query.all()
    invoices  = Invoice.query.all()
    customers = Customer.query.all()

    # ── Summary stats ──────────────────────────────────────────────────────
    total_rev  = sum(i.total for i in invoices)
    total_vat  = sum(i.vat_amt for i in invoices)
    unpaid_cnt = sum(1 for i in invoices if i.pay_status == 'unpaid')
    low_stock  = [p for p in products if p.stock <= settings.low_stock]

    hour = datetime.now().hour
    if hour < 12:   greeting = 'Good morning'
    elif hour < 17: greeting = 'Good afternoon'
    else:           greeting = 'Good evening'

    # ── CHART 1: Monthly revenue (last 6 months) ───────────────────────────
    # We group invoices by YYYY-MM and sum their totals.
    # The result is passed to the template as two parallel lists:
    # chart_months = ['2025-10', '2025-11', ...] (labels for X axis)
    # chart_revenue = [1240.0, 980.5, ...]        (values for Y axis)
    from collections import defaultdict
    monthly = defaultdict(float)
    for inv in invoices:
        # inv.date is stored as 'YYYY-MM-DD' string — take first 7 chars for 'YYYY-MM'
        if inv.date and len(inv.date) >= 7:
            month_key = inv.date[:7]
            monthly[month_key] += inv.total

    # Sort by date and take last 6 months
    sorted_months = sorted(monthly.keys())[-6:]
    chart_months  = sorted_months
    chart_revenue = [round(monthly[m], 2) for m in sorted_months]

    # Make month labels more readable: '2025-10' → 'Oct 25'
    import calendar
    def fmt_month(ym):
        try:
            y, m = ym.split('-')
            return calendar.month_abbr[int(m)] + ' ' + y[2:]
        except:
            return ym
    chart_month_labels = [fmt_month(m) for m in chart_months]

    # ── CHART 2: Payment status breakdown (doughnut) ───────────────────────
    paid_cnt    = sum(1 for i in invoices if i.pay_status == 'paid')
    pending_cnt = sum(1 for i in invoices if i.pay_status == 'pending')
    # unpaid_cnt already calculated above

    # ── CHART 3: Top 5 customers by revenue (horizontal bar) ──────────────
    cust_totals = defaultdict(float)
    for inv in invoices:
        cust_totals[inv.customer] += inv.total
    top_customers = sorted(cust_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    top_cust_labels = [c[0] for c in top_customers]
    top_cust_values = [round(c[1], 2) for c in top_customers]

    return render_template('home.html',
        settings=settings,
        greeting=greeting,
        total_invoices=len(invoices),
        total_revenue=total_rev,
        total_customers=len(customers),
        unpaid_count=unpaid_cnt,
        low_stock_products=low_stock,
        # Chart data — passed as JSON-safe Python lists
        chart_month_labels=chart_month_labels,
        chart_revenue=chart_revenue,
        paid_count=paid_cnt,
        pending_count=pending_cnt,
        unpaid_chart=unpaid_cnt,
        top_cust_labels=top_cust_labels,
        top_cust_values=top_cust_values,
    )


# =============================================================================
# ── INVOICE ───────────────────────────────────────────────────────────────────
# =============================================================================

@app.route('/invoice', methods=['GET', 'POST'])
@login_required
def invoice():
    settings  = Settings.query.first()
    products  = Product.query.all()
    customers = Customer.query.all()

    if request.method == 'POST':
        # ── Collect form data ──────────────────────────────────────────────
        num      = request.form.get('inv_num', '').strip()
        ref      = request.form.get('inv_ref', '').strip()
        date     = request.form.get('inv_date', '')
        due      = request.form.get('inv_due', '')
        cust_name= request.form.get('cust_name', '').strip()

        if not num or not date or not cust_name:
            flash('Invoice number, date, and customer name are required.', 'error')
            return redirect(url_for('invoice'))

        # ── Collect line items from form ───────────────────────────────────
        # The form sends arrays: product_id[], qty[], unit_price[], vat_mode[]
        # We zip them together to get one dict per line.
        product_ids = request.form.getlist('product_id[]')
        qtys        = request.form.getlist('qty[]')
        unit_prices = request.form.getlist('unit_price[]')
        vat_modes   = request.form.getlist('vat_mode[]')

        lines_data = []
        for pid, qty, price, vmode in zip(product_ids, qtys, unit_prices, vat_modes):
            if not pid:
                continue  # skip empty lines
            prod = Product.query.get(int(pid))
            if not prod:
                continue
            lines_data.append({
                'product_id': int(pid),
                'product_name': prod.name,
                'qty': max(1, int(qty or 1)),
                'unit_price': float(price or 0),
                'vat': prod.vat,
                'vat_mode': vmode or 'standard',
            })

        if not lines_data:
            flash('Please add at least one product.', 'error')
            return redirect(url_for('invoice'))

        # ── Deduct stock ───────────────────────────────────────────────────
        for ln in lines_data:
            prod = Product.query.get(ln['product_id'])
            if prod:
                prod.stock = max(0, prod.stock - ln['qty'])

        # ── Save/update customer if checkbox ticked ────────────────────────
        save_cust = request.form.get('save_cust') == 'on'
        cust_id   = None
        if save_cust and cust_name:
            existing = Customer.query.filter(
                db.func.lower(Customer.name) == cust_name.lower()
            ).first()
            cust_data = dict(
                name=cust_name,
                contact_name=request.form.get('cust_contact_name', ''),
                contact=request.form.get('cust_contact', ''),
                address=request.form.get('cust_addr', ''),
                postcode=request.form.get('cust_postcode', ''),
                vat_no=request.form.get('cust_vat', ''),
                crn=request.form.get('cust_crn', ''),
            )
            if existing:
                for k, v in cust_data.items():
                    setattr(existing, k, v)
                cust_id = existing.id
            else:
                new_cust = Customer(**cust_data)
                db.session.add(new_cust)
                db.session.flush()   # flush to get the new id before commit
                cust_id = new_cust.id

        # ── Calculate totals ───────────────────────────────────────────────
        sub, vat_amt, total = calc_invoice_totals(lines_data)

        # ── Build and save the Invoice object ──────────────────────────────
        inv = Invoice(
            num=num, ref=ref, date=date, due_date=due,
            customer=cust_name,
            contact_name=request.form.get('cust_contact_name', ''),
            contact=request.form.get('cust_contact', ''),
            address=request.form.get('cust_addr', ''),
            postcode=request.form.get('cust_postcode', ''),
            cust_vat=request.form.get('cust_vat', ''),
            cust_crn=request.form.get('cust_crn', ''),
            sub=sub, vat_amt=vat_amt, total=total,
            pay_status=request.form.get('pay_status', 'unpaid'),
            pay_method=request.form.get('pay_method', ''),
            notes=request.form.get('notes', ''),
            customer_id=cust_id,
        )
        db.session.add(inv)
        db.session.flush()  # get inv.id before adding lines

        # ── Save each line ─────────────────────────────────────────────────
        for ln in lines_data:
            lt = calc_line_total(ln['unit_price'], ln['qty'], ln['vat'], ln['vat_mode'])
            db.session.add(InvoiceLine(
                invoice_id=inv.id,
                product_id=ln['product_id'],
                product_name=ln['product_name'],
                qty=ln['qty'],
                unit_price=ln['unit_price'],
                vat=ln['vat'],
                vat_mode=ln['vat_mode'],
                line_total=lt,
            ))

        # ── Increment invoice number in settings ───────────────────────────
        settings.next_inv_num += 1

        # ── Commit everything to database in one go ────────────────────────
        # If anything above failed, nothing gets saved (atomicity).
        db.session.commit()
        flash(f'Invoice {num} saved successfully.', 'success')
        return redirect(url_for('records'))

    # GET request — just show the blank form
    next_num = settings.inv_prefix + str(settings.next_inv_num)
    today    = datetime.today().strftime('%Y-%m-%d')
    return render_template('invoice.html',
        settings=settings,
        products=products,
        customers=customers,
        next_num=next_num,
        today=today,
    )


# =============================================================================
# ── PRINT INVOICE ─────────────────────────────────────────────────────────────
# =============================================================================

@app.route('/invoice/<int:inv_id>/print')
@login_required
def print_invoice(inv_id):
    inv      = Invoice.query.get_or_404(inv_id)
    settings = Settings.query.first()
    return render_template('print_invoice.html', inv=inv, settings=settings)


# =============================================================================
# ── SALES HISTORY / RECORDS ───────────────────────────────────────────────────
# =============================================================================

@app.route('/records')
@login_required
def records():
    search    = request.args.get('q', '').strip()
    status_f  = request.args.get('status', '')
    settings  = Settings.query.first()

    query = Invoice.query
    if search:
        query = query.filter(
            db.or_(
                Invoice.customer.ilike(f'%{search}%'),
                Invoice.num.ilike(f'%{search}%'),
            )
        )
    if status_f:
        query = query.filter(Invoice.pay_status == status_f)

    invoices = query.order_by(Invoice.created_at.desc()).all()

    total_rev  = sum(i.total   for i in Invoice.query.all())
    total_vat  = sum(i.vat_amt for i in Invoice.query.all())
    unpaid_cnt = Invoice.query.filter_by(pay_status='unpaid').count()

    return render_template('records.html',
        invoices=invoices,
        search=search, status_f=status_f,
        total_rev=total_rev, total_vat=total_vat,
        unpaid_count=unpaid_cnt,
        settings=settings,
    )


@app.route('/invoice/<int:inv_id>/status', methods=['POST'])
@login_required
def update_status(inv_id):
    inv = Invoice.query.get_or_404(inv_id)
    inv.pay_status = request.form.get('pay_status', inv.pay_status)
    if inv.pay_status != 'paid':
        inv.pay_method = ''
    db.session.commit()
    flash('Payment status updated.', 'success')
    return redirect(url_for('records'))


@app.route('/invoice/<int:inv_id>/delete', methods=['POST'])
@login_required
def delete_invoice(inv_id):
    inv = Invoice.query.get_or_404(inv_id)
    db.session.delete(inv)
    db.session.commit()
    flash('Invoice deleted.', 'success')
    return redirect(url_for('records'))


# =============================================================================
# ── CUSTOMERS ─────────────────────────────────────────────────────────────────
# =============================================================================

@app.route('/customers', methods=['GET', 'POST'])
@login_required
def customers():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Business name is required.', 'error')
            return redirect(url_for('customers'))
        if Customer.query.filter(db.func.lower(Customer.name) == name.lower()).first():
            flash('A customer with that name already exists.', 'error')
            return redirect(url_for('customers'))

        db.session.add(Customer(
            name=name,
            contact_name=request.form.get('contact_name', ''),
            contact=request.form.get('contact', ''),
            address=request.form.get('address', ''),
            postcode=request.form.get('postcode', ''),
            vat_no=request.form.get('vat_no', ''),
            crn=request.form.get('crn', ''),
        ))
        db.session.commit()
        flash(f'Customer "{name}" added.', 'success')
        return redirect(url_for('customers'))

    search = request.args.get('q', '')
    query  = Customer.query
    if search:
        query = query.filter(
            db.or_(
                Customer.name.ilike(f'%{search}%'),
                Customer.contact.ilike(f'%{search}%'),
            )
        )
    all_customers = query.order_by(Customer.name).all()

    # Invoice count per customer (for the table)
    inv_counts = {
        c.id: Invoice.query.filter_by(customer_id=c.id).count()
        for c in all_customers
    }
    return render_template('customers.html',
        customers=all_customers,
        inv_counts=inv_counts,
        search=search,
    )


@app.route('/customers/<int:cid>/delete', methods=['POST'])
@login_required
def delete_customer(cid):
    c = Customer.query.get_or_404(cid)
    db.session.delete(c)
    db.session.commit()
    flash('Customer removed.', 'success')
    return redirect(url_for('customers'))


# API endpoint — returns customer data as JSON so the invoice form
# can auto-fill fields when an existing customer is selected.
@app.route('/api/customer/<int:cid>')
@login_required
def api_customer(cid):
    c = Customer.query.get_or_404(cid)
    return jsonify({
        'name': c.name, 'contact_name': c.contact_name,
        'contact': c.contact, 'address': c.address,
        'postcode': c.postcode, 'vat_no': c.vat_no, 'crn': c.crn,
    })


# =============================================================================
# ── LEDGER ────────────────────────────────────────────────────────────────────
# =============================================================================

@app.route('/ledger')
@login_required
def ledger():
    search = request.args.get('q', '').strip()
    # Group invoices by customer name using Python (not SQL) for simplicity
    all_invoices = Invoice.query.order_by(Invoice.customer).all()
    ledger_map   = {}
    for inv in all_invoices:
        k = inv.customer
        if k not in ledger_map:
            ledger_map[k] = {'name': k, 'invoices': [], 'total': 0,
                             'vat': 0, 'unpaid': 0}
        ledger_map[k]['invoices'].append(inv)
        ledger_map[k]['total']  += inv.total
        ledger_map[k]['vat']    += inv.vat_amt
        ledger_map[k]['unpaid'] += 1 if inv.pay_status == 'unpaid' else 0

    rows = sorted(ledger_map.values(), key=lambda x: x['total'], reverse=True)
    if search:
        rows = [r for r in rows if search.lower() in r['name'].lower()]

    return render_template('ledger.html', rows=rows, search=search)


@app.route('/ledger/<path:cust_name>')
@login_required
def ledger_detail(cust_name):
    invoices = Invoice.query.filter_by(customer=cust_name)\
                            .order_by(Invoice.date.desc()).all()
    if not invoices:
        flash('No invoices found for this customer.', 'error')
        return redirect(url_for('ledger'))

    total_spend = sum(i.total   for i in invoices)
    total_vat   = sum(i.vat_amt for i in invoices)
    avg_invoice = total_spend / len(invoices) if invoices else 0

    # Partial payments
    payments      = CustomerPayment.query.filter_by(customer=cust_name)\
                                         .order_by(CustomerPayment.date.desc()).all()
    total_paid    = sum(p.amount for p in payments)
    balance_due   = round(total_spend - total_paid, 2)

    # Top 5 products by spend for this customer
    prod_map = {}
    for inv in invoices:
        for ln in inv.lines:
            nm = ln.product_name
            if nm not in prod_map:
                prod_map[nm] = {'qty': 0, 'spend': 0}
            prod_map[nm]['qty']   += ln.qty
            prod_map[nm]['spend'] += ln.line_total
    top_products = sorted(prod_map.items(), key=lambda x: x[1]['spend'], reverse=True)[:5]

    return render_template('ledger_detail.html',
        cust_name=cust_name, invoices=invoices,
        total_spend=total_spend, total_vat=total_vat,
        avg_invoice=avg_invoice, top_products=top_products,
        payments=payments, total_paid=total_paid, balance_due=balance_due,
        today=datetime.today().strftime('%Y-%m-%d'),
    )


# =============================================================================
# ── INVENTORY ─────────────────────────────────────────────────────────────────
# =============================================================================

@app.route('/ledger/<path:cust_name>/add-payment', methods=['POST'])
@login_required
def add_customer_payment(cust_name):
    amount = request.form.get('amount', '0')
    try:   amount = round(float(amount), 2)
    except: amount = 0.0
    if amount <= 0:
        flash('Please enter a valid payment amount.', 'error')
        return redirect(url_for('ledger_detail', cust_name=cust_name))
    db.session.add(CustomerPayment(
        customer=cust_name,
        amount=amount,
        method=request.form.get('method', ''),
        note=request.form.get('note', ''),
        date=request.form.get('date', datetime.today().strftime('%Y-%m-%d')),
    ))
    db.session.commit()
    flash(f'Payment of £{amount:.2f} recorded.', 'success')
    return redirect(url_for('ledger_detail', cust_name=cust_name))


@app.route('/ledger/<path:cust_name>/delete-payment/<int:pid>', methods=['POST'])
@login_required
def delete_customer_payment(cust_name, pid):
    p = CustomerPayment.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    flash('Payment record deleted.', 'success')
    return redirect(url_for('ledger_detail', cust_name=cust_name))


# =============================================================================
# ── INVENTORY ─────────────────────────────────────────────────────────────────
# =============================================================================

@app.route('/inventory')
@login_required
def inventory():
    settings = Settings.query.first()
    search   = request.args.get('q', '')
    query    = Product.query
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    products = query.order_by(Product.name).all()
    return render_template('inventory.html',
        products=products, settings=settings, search=search)


@app.route('/inventory/<int:pid>/update', methods=['POST'])
@login_required
def update_stock(pid):
    prod = Product.query.get_or_404(pid)
    action = request.form.get('action')
    if action == 'set':
        val = request.form.get('stock_val', '')
        if val.isdigit():
            prod.stock = int(val)
    elif action == 'add10':
        prod.stock += 10
    db.session.commit()
    flash(f'Stock updated for {prod.name}.', 'success')
    return redirect(url_for('inventory'))


# =============================================================================
# ── PRODUCTS ──────────────────────────────────────────────────────────────────
# =============================================================================

@app.route('/products', methods=['GET', 'POST'])
@login_required
def products():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Product name is required.', 'error')
            return redirect(url_for('products'))
        if Product.query.filter(db.func.lower(Product.name) == name.lower()).first():
            flash('Product already exists.', 'error')
            return redirect(url_for('products'))

        db.session.add(Product(
            name=name,
            sku=request.form.get('sku', '').strip(),
            category=request.form.get('category', '').strip(),
            price=float(request.form.get('price', 0) or 0),
            vat=int(request.form.get('vat', 20) or 20),
            stock=int(request.form.get('stock', 0) or 0),
        ))
        db.session.commit()
        flash(f'Product "{name}" added.', 'success')
        return redirect(url_for('products'))

    search   = request.args.get('q', '')
    cat      = request.args.get('cat', '')
    query    = Product.query
    if search:
        query = query.filter(
            db.or_(Product.name.ilike(f'%{search}%'), Product.sku.ilike(f'%{search}%'))
        )
    if cat:
        query = query.filter(Product.category == cat)
    all_products = query.order_by(Product.name).all()
    categories   = [r[0] for r in db.session.query(Product.category).distinct() if r[0]]
    return render_template('products.html', products=all_products,
                           search=search, cat=cat, categories=categories)


@app.route('/products/<int:pid>/delete', methods=['POST'])
@login_required
def delete_product(pid):
    prod = Product.query.get_or_404(pid)
    db.session.delete(prod)
    db.session.commit()
    flash(f'Product "{prod.name}" removed.', 'success')
    return redirect(url_for('products'))


@app.route('/products/<int:pid>/update', methods=['POST'])
@login_required
def update_product(pid):
    prod = Product.query.get_or_404(pid)
    name = request.form.get('name', '').strip()
    if not name:
        flash('Product name is required.', 'error')
        return redirect(url_for('product_detail', pid=pid))
    # Check for duplicate name (excluding this product)
    existing = Product.query.filter(
        db.func.lower(Product.name) == name.lower(),
        Product.id != pid
    ).first()
    if existing:
        flash('Another product with that name already exists.', 'error')
        return redirect(url_for('product_detail', pid=pid))
    prod.name     = name
    prod.sku      = request.form.get('sku', '').strip()
    prod.category = request.form.get('category', '').strip()
    prod.price    = float(request.form.get('price', prod.price) or prod.price)
    prod.vat      = int(request.form.get('vat', prod.vat) or prod.vat)
    prod.stock    = int(request.form.get('stock', prod.stock) or prod.stock)
    db.session.commit()
    flash(f'Product "{prod.name}" updated.', 'success')
    return redirect(url_for('product_detail', pid=pid))


@app.route('/products/<int:pid>')
@login_required
def product_detail(pid):
    prod = Product.query.get_or_404(pid)
    # All invoice lines for this product
    lines = InvoiceLine.query.filter_by(product_id=pid).all()
    total_units = sum(l.qty for l in lines)
    total_revenue = sum(l.line_total for l in lines)
    # Monthly sales (last 6 months)
    from collections import defaultdict
    monthly = defaultdict(lambda: {'qty': 0, 'revenue': 0.0})
    for l in lines:
        inv = Invoice.query.get(l.invoice_id)
        if inv and inv.date and len(inv.date) >= 7:
            key = inv.date[:7]
            monthly[key]['qty'] += l.qty
            monthly[key]['revenue'] += l.line_total
    sorted_months = sorted(monthly.keys())[-6:]
    import calendar
    def fmt_month(ym):
        try:
            y, m = ym.split('-')
            return calendar.month_abbr[int(m)] + ' ' + y[2:]
        except: return ym
    chart_labels   = [fmt_month(m) for m in sorted_months]
    chart_qty      = [monthly[m]['qty'] for m in sorted_months]
    chart_revenue  = [round(monthly[m]['revenue'], 2) for m in sorted_months]
    # Top customers
    cust_map = defaultdict(lambda: {'qty': 0, 'spend': 0.0})
    for l in lines:
        inv = Invoice.query.get(l.invoice_id)
        if inv:
            cust_map[inv.customer]['qty'] += l.qty
            cust_map[inv.customer]['spend'] += l.line_total
    top_customers = sorted(cust_map.items(), key=lambda x: x[1]['spend'], reverse=True)[:5]
    return render_template('product_detail.html',
        prod=prod, total_units=total_units, total_revenue=total_revenue,
        invoice_count=len(set(l.invoice_id for l in lines)),
        chart_labels=chart_labels, chart_qty=chart_qty, chart_revenue=chart_revenue,
        top_customers=top_customers,
    )


# API — returns all products as JSON for the invoice form's live search
@app.route('/api/products')
@login_required
def api_products():
    q        = request.args.get('q', '').lower()
    products = Product.query.filter(Product.name.ilike(f'%{q}%')).all()
    return jsonify([{
        'id': p.id, 'name': p.name,
        'price': p.price, 'vat': p.vat, 'stock': p.stock,
    } for p in products])


# =============================================================================
# ── CSV EXPORTS & IMPORTS ─────────────────────────────────────────────────────
# =============================================================================
import csv
import io
from flask import Response, send_file
import tempfile

def make_csv_response(rows, filename):
    """Helper: build a CSV download response from a list of rows."""
    output = io.StringIO()
    writer = csv.writer(output)
    for row in rows:
        writer.writerow(row)
    response = Response(
        '\ufeff' + output.getvalue(),   # BOM for Excel compatibility
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )
    return response

@app.route('/export/invoices.csv')
@login_required
def export_invoices_csv():
    rows = [['Invoice No', 'Customer Ref', 'Date', 'Due Date', 'Customer',
             'Total', 'VAT', 'Pay Status', 'Pay Method']]
    for i in Invoice.query.order_by(Invoice.created_at.desc()).all():
        rows.append([i.num, i.ref, i.date, i.due_date, i.customer,
                     f'{i.total:.2f}', f'{i.vat_amt:.2f}',
                     i.pay_status, i.pay_method])
    return make_csv_response(rows, 'JGM_Sales_History.csv')

@app.route('/export/customers.csv')
@login_required
def export_customers_csv():
    rows = [['Business Name', 'Contact Person', 'Phone/Email',
             'Address', 'Postcode', 'VAT No', 'Reg No']]
    for c in Customer.query.order_by(Customer.name).all():
        rows.append([c.name, c.contact_name, c.contact,
                     c.address, c.postcode, c.vat_no, c.crn])
    return make_csv_response(rows, 'JGM_Customers.csv')

@app.route('/export/inventory.csv')
@login_required
def export_inventory_csv():
    rows = [['Product', 'VAT %', 'Unit Price (£)', 'Stock']]
    for p in Product.query.order_by(Product.name).all():
        rows.append([p.name, p.vat, f'{p.price:.2f}', p.stock])
    return make_csv_response(rows, 'JGM_Inventory.csv')

@app.route('/export/products.csv')
@login_required
def export_products_csv():
    rows = [['Name', 'Price', 'VAT', 'Stock', 'SKU', 'Category']]
    for p in Product.query.order_by(Product.name).all():
        rows.append([p.name, f'{p.price:.2f}', p.vat, p.stock, p.sku or '', p.category or ''])
    return make_csv_response(rows, 'JGM_Products.csv')

@app.route('/export/ledger.csv')
@login_required
def export_ledger_csv():
    rows = [['Customer', 'Invoice No', 'Ref', 'Date', 'Total', 'VAT', 'Pay Status']]
    for i in Invoice.query.order_by(Invoice.customer, Invoice.date).all():
        rows.append([i.customer, i.num, i.ref, i.date,
                     f'{i.total:.2f}', f'{i.vat_amt:.2f}', i.pay_status])
    return make_csv_response(rows, 'JGM_Customer_Ledger.csv')

@app.route('/products/import-csv', methods=['POST'])
@login_required
def import_products_csv():
    file = request.files.get('csv_file')
    if not file or not file.filename.endswith('.csv'):
        flash('Please upload a valid .csv file.', 'error')
        return redirect(url_for('products'))
    content = file.read().decode('utf-8-sig').splitlines()
    reader  = csv.reader(content)
    added = skipped = errors = 0
    for idx, row in enumerate(reader):
        if idx == 0:
            try: float(row[1]);
            except (IndexError, ValueError): continue
        if len(row) < 2:
            errors += 1; continue
        name     = row[0].strip()
        try:     price = float(row[1].strip())
        except:  errors += 1; continue
        vat      = int(row[2].strip()) if len(row) > 2 and row[2].strip().isdigit() else 20
        stock    = int(row[3].strip()) if len(row) > 3 and row[3].strip().isdigit() else 0
        sku      = row[4].strip() if len(row) > 4 else ''
        category = row[5].strip() if len(row) > 5 else ''
        if not name: errors += 1; continue
        if Product.query.filter(db.func.lower(Product.name)==name.lower()).first():
            skipped += 1; continue
        db.session.add(Product(name=name, price=price, vat=0 if vat==0 else 20,
                               stock=stock, sku=sku, category=category))
        added += 1
    db.session.commit()
    flash(f'Import complete: {added} added, {skipped} skipped (duplicates), {errors} errors.', 'success')
    return redirect(url_for('products'))

@app.route('/products/template.csv')
@login_required
def download_product_template():
    rows = [['Name', 'Price', 'VAT', 'Stock', 'SKU', 'Category'],
            ['Coca-Cola 500ml x24', '12.50', '20', '50', 'CC-500-24', 'Drinks'],
            ['Basmati Rice 5kg', '8.99', '0', '60', 'BR-5KG', 'Grocery']]
    return make_csv_response(rows, 'JGM_Products_Template.csv')


# =============================================================================
# ── SETTINGS ──────────────────────────────────────────────────────────────────
# =============================================================================

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    s = Settings.query.first()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'save_settings':
            s.company    = request.form.get('company', '').strip()
            s.crn        = request.form.get('crn', '').strip()
            s.vat_no     = request.form.get('vat_no', '').strip()
            s.address    = request.form.get('address', '').strip()
            s.postcode   = request.form.get('postcode', '').strip()
            s.phone      = request.form.get('phone', '').strip()
            s.email      = request.form.get('email', '').strip()
            s.inv_prefix = request.form.get('inv_prefix', 'JGM-').strip()
            s.low_stock  = int(request.form.get('low_stock', 10) or 10)
            db.session.commit()
            flash('Settings saved.', 'success')

        elif action == 'change_pin':
            cur  = request.form.get('pin_cur', '')
            new  = request.form.get('pin_new', '')
            conf = request.form.get('pin_conf', '')
            if cur != s.pin:
                flash('Current PIN is incorrect.', 'error')
            elif not new.isdigit() or len(new) != 4:
                flash('New PIN must be exactly 4 digits.', 'error')
            elif new != conf:
                flash('New PINs do not match.', 'error')
            else:
                s.pin = new
                db.session.commit()
                flash('PIN updated successfully.', 'success')

        return redirect(url_for('settings'))

    return render_template('settings.html', settings=s)


# =============================================================================
# ── RUN THE APP ───────────────────────────────────────────────────────────────
# =============================================================================
# When running LOCALLY:  python app.py  → debug mode on, port 5000
# When running on Railway: gunicorn starts the app instead (see Procfile),
#   so this block is never executed there. But we still read PORT from the
#   environment variable Railway sets automatically.

if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    app.run(host='0.0.0.0', port=port, debug=debug)
