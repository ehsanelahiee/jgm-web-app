# JGM Wholesale — Flask Invoicing App

## How to run this app (step by step)

### Step 1 — Make sure Python is installed
Open a terminal (Command Prompt on Windows, Terminal on Mac/Linux) and type:
```
python --version
```
You should see Python 3.8 or higher. If not, download it from python.org.

---

### Step 2 — Navigate to the project folder
```
cd jgm-flask
```

---

### Step 3 — Create a virtual environment
A virtual environment is an isolated Python environment just for this project.
It means the packages you install here won't interfere with anything else on your computer.
```
python -m venv venv
```

Activate it:
- **Windows:**  `venv\Scripts\activate`
- **Mac/Linux:** `source venv/bin/activate`

You'll see `(venv)` appear in your terminal — that means it's active.

---

### Step 4 — Install the required packages
```
pip install -r requirements.txt
```
This installs Flask, SQLAlchemy, and Flask-Migrate — the three packages listed in requirements.txt.

---

### Step 5 — Run the app
```
python app.py
```
You'll see output like:
```
 * Running on http://127.0.0.1:5000
 * Debug mode: on
```

Open your browser and go to: **http://127.0.0.1:5000**

The database (jgm.db) is created automatically on first run.
Default PIN: **1234**

---

## Project structure explained

```
jgm-flask/
├── app.py          ← All routes (URL handlers). This is where requests are processed.
├── models.py       ← Database table definitions (Settings, Customer, Product, Invoice, InvoiceLine)
├── templates/      ← HTML files Flask renders. Use {{ }} for variables, {% %} for logic.
│   ├── base.html       Shared layout (nav, flash messages) — all pages inherit from this
│   ├── pin.html        Login screen
│   ├── home.html       Dashboard
│   ├── invoice.html    New invoice form (most complex — has JavaScript for live calculations)
│   ├── records.html    Sales history
│   ├── print_invoice.html  Printable invoice (no nav)
│   ├── customers.html
│   ├── products.html
│   ├── inventory.html
│   ├── ledger.html
│   ├── ledger_detail.html
│   └── settings.html
├── static/
│   └── style.css   ← Stylesheet (same design as the single-file HTML app)
├── requirements.txt  ← pip install -r requirements.txt
└── jgm.db          ← SQLite database file (auto-created, do not delete)
```

---

## Key concepts to understand

### Routes
Every page is a Python function decorated with @app.route().
```python
@app.route('/customers')
def customers():
    all_customers = Customer.query.all()
    return render_template('customers.html', customers=all_customers)
```
- `/customers` is the URL
- `customers()` is the function that runs when that URL is visited
- `Customer.query.all()` fetches all rows from the customer table
- `render_template()` sends the HTML page back to the browser

### GET vs POST
- GET = user is viewing a page (no data being sent)
- POST = user submitted a form (data is being saved)

### Templates (Jinja2)
- `{{ variable }}` — outputs a value
- `{% if condition %}...{% endif %}` — conditional
- `{% for item in list %}...{% endfor %}` — loop
- `{% extends "base.html" %}` — inherit the shared layout
- `{% block content %}...{% endblock %}` — fill in the content area

### Database (SQLAlchemy)
- `Product.query.all()` — get all products
- `Product.query.get(id)` — get one product by ID
- `Product.query.filter_by(name='Coca-Cola').first()` — find by field
- `db.session.add(obj)` — stage a new record
- `db.session.commit()` — save everything to the database

---

## Deploying to a live server (Railway — free tier)

1. Create a free account at railway.app
2. Install Railway CLI: `npm install -g @railway/cli`
3. In the project folder: `railway login` then `railway init`
4. Add a `Procfile` file containing: `web: python app.py`
5. Change `app.run(debug=True)` to `app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))`
6. Deploy: `railway up`

Your app will be live at a public URL — accessible from any device, any browser.

---

## Adding new features without losing data

When you add a new column to a model, use Flask-Migrate:
```
flask db migrate -m "add delivery_notes to invoice"
flask db upgrade
```
This updates the database structure safely. Existing data is untouched.
