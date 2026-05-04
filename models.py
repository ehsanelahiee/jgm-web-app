# =============================================================================
# models.py — Database Table Definitions
# =============================================================================
#
# WHAT IS THIS FILE?
# This file defines the "shape" of our database — what tables exist and what
# columns each table has. We use SQLAlchemy, which lets us write Python classes
# instead of raw SQL. Each class = one database table. Each class attribute
# = one column in that table.
#
# WHY SQLALCHEMY?
# Without it, you'd write raw SQL like:
#   INSERT INTO invoice (num, customer, total) VALUES (?, ?, ?)
# With SQLAlchemy you write Python:
#   inv = Invoice(num="JGM-1001", customer="Al-Madina", total=340.00)
#   db.session.add(inv)
# Much cleaner and less error-prone.
# =============================================================================

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# db is the SQLAlchemy instance. It's created here and then connected
# to the Flask app in app.py. This pattern avoids circular imports.
db = SQLAlchemy()


# =============================================================================
# SETTINGS TABLE
# Stores company details, PIN, invoice prefix, etc.
# Only ever has ONE row — your single company configuration.
# =============================================================================
class Settings(db.Model):
    __tablename__ = 'settings'

    id           = db.Column(db.Integer, primary_key=True)  # always 1
    company      = db.Column(db.String(200), default='JGM Wholesale')
    crn          = db.Column(db.String(50),  default='')    # company reg no.
    vat_no       = db.Column(db.String(50),  default='')
    address      = db.Column(db.String(300), default='')
    postcode     = db.Column(db.String(20),  default='')
    phone        = db.Column(db.String(50),  default='')
    email        = db.Column(db.String(100), default='')
    inv_prefix   = db.Column(db.String(20),  default='JGM-')
    low_stock    = db.Column(db.Integer,     default=10)
    pin          = db.Column(db.String(10),  default='1234')
    next_inv_num = db.Column(db.Integer,     default=1001)  # auto-incrementing invoice number


# =============================================================================
# CUSTOMER TABLE
# One row per customer.
# =============================================================================
class Customer(db.Model):
    __tablename__ = 'customer'

    id           = db.Column(db.Integer, primary_key=True)  # auto-assigned by DB
    name         = db.Column(db.String(200), nullable=False) # business name
    contact_name = db.Column(db.String(200), default='')     # contact person
    contact      = db.Column(db.String(200), default='')     # phone / email
    address      = db.Column(db.String(300), default='')
    postcode     = db.Column(db.String(20),  default='')
    vat_no       = db.Column(db.String(50),  default='')
    crn          = db.Column(db.String(50),  default='')     # customer reg no.
    created_at   = db.Column(db.DateTime,    default=datetime.utcnow)

    # This is a "relationship" — it tells SQLAlchemy that one Customer
    # can have many Invoices. The backref='customer' means you can do
    # invoice.customer to get the Customer object from an Invoice.
    invoices     = db.relationship('Invoice', backref='customer_obj', lazy=True)

    def __repr__(self):
        return f'<Customer {self.name}>'


# =============================================================================
# PRODUCT TABLE
# One row per product in your catalogue.
# =============================================================================
class Product(db.Model):
    __tablename__ = 'product'

    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(300), nullable=False, unique=True)
    sku      = db.Column(db.String(100), default='')   # product code / SKU
    category = db.Column(db.String(100), default='')   # e.g. Drinks, Confectionery
    price    = db.Column(db.Float,   nullable=False, default=0.0)
    vat      = db.Column(db.Integer, nullable=False, default=20)
    stock    = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f'<Product {self.name}>'


# =============================================================================
# INVOICE TABLE
# One row per invoice. The customer name is stored directly (as a string)
# so invoices remain intact even if a customer record is later deleted.
# =============================================================================
class Invoice(db.Model):
    __tablename__ = 'invoice'

    id           = db.Column(db.Integer, primary_key=True)
    num          = db.Column(db.String(50),  nullable=False)  # e.g. JGM-1001
    ref          = db.Column(db.String(100), default='')      # customer's own ref
    date         = db.Column(db.String(20),  nullable=False)  # stored as YYYY-MM-DD string
    due_date     = db.Column(db.String(20),  default='')
    customer     = db.Column(db.String(200), nullable=False)  # business name string
    contact_name = db.Column(db.String(200), default='')
    contact      = db.Column(db.String(200), default='')
    address      = db.Column(db.String(300), default='')
    postcode     = db.Column(db.String(20),  default='')
    cust_vat     = db.Column(db.String(50),  default='')      # customer's VAT no.
    cust_crn     = db.Column(db.String(50),  default='')      # customer's reg no.
    sub          = db.Column(db.Float, default=0.0)           # subtotal (ex-VAT lines)
    vat_amt      = db.Column(db.Float, default=0.0)           # total VAT charged
    total        = db.Column(db.Float, default=0.0)           # grand total
    pay_status   = db.Column(db.String(20),  default='unpaid')  # unpaid/pending/paid
    pay_method   = db.Column(db.String(20),  default='')        # cash/card/bank
    notes        = db.Column(db.Text,        default='')
    created_at   = db.Column(db.DateTime,    default=datetime.utcnow)

    # Relationship: one Invoice has many InvoiceLines
    # cascade="all, delete-orphan" means if you delete an invoice,
    # its lines are automatically deleted too.
    lines        = db.relationship('InvoiceLine', backref='invoice',
                                   cascade='all, delete-orphan', lazy=True)

    # Optional link to customer record (nullable — invoice survives if customer deleted)
    customer_id  = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=True)

    def __repr__(self):
        return f'<Invoice {self.num}>'


# =============================================================================
# INVOICE LINE TABLE
# One row per line item on an invoice.
# This is a separate table because one invoice can have many lines,
# and databases don't support "arrays" inside a single cell.
#
# LESSON — Why a separate table?
# Bad approach (don't do this):
#   invoice.products = "Coca-Cola x10, Pepsi x5"   ← can't query this properly
# Good approach (what we do):
#   Each product on the invoice gets its own row in invoice_line,
#   linked back to the invoice via invoice_id (foreign key).
# =============================================================================
class InvoiceLine(db.Model):
    __tablename__ = 'invoice_line'

    id          = db.Column(db.Integer, primary_key=True)
    invoice_id  = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    product_id  = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)
    product_name= db.Column(db.String(300), default='')  # snapshot of name at time of invoice
    qty         = db.Column(db.Integer, nullable=False, default=1)
    unit_price  = db.Column(db.Float,   nullable=False, default=0.0)
    vat         = db.Column(db.Integer, nullable=False, default=20)   # 0 or 20
    vat_mode    = db.Column(db.String(20), default='standard')        # standard/exempt/inclusive
    line_total  = db.Column(db.Float,   nullable=False, default=0.0)  # final charged amount

    def __repr__(self):
        return f'<InvoiceLine {self.product_name} x{self.qty}>'


# =============================================================================
# CUSTOMER PAYMENT TABLE
# Records partial payments made by a customer against their outstanding balance.
# Each row = one payment event (e.g. "paid £200 on 12/03/2026 by bank transfer").
# The running balance is calculated in Python by summing invoice totals minus payments.
# =============================================================================
class CustomerPayment(db.Model):
    __tablename__ = 'customer_payment'

    id          = db.Column(db.Integer, primary_key=True)
    customer    = db.Column(db.String(200), nullable=False)  # customer name string
    amount      = db.Column(db.Float,   nullable=False, default=0.0)
    method      = db.Column(db.String(50),  default='')   # cash/card/bank
    note        = db.Column(db.String(300), default='')   # optional note
    date        = db.Column(db.String(20),  nullable=False)
    created_at  = db.Column(db.DateTime,    default=datetime.utcnow)

    def __repr__(self):
        return f'<CustomerPayment £{self.amount} from {self.customer}>'
