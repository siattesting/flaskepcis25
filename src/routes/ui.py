# app/routes/ui.py

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash
from sqlalchemy import select, func

from ..models import EPCState, db, User, EPCISEvent, Product, Company

ui_bp = Blueprint('ui', __name__)

@ui_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handles the login form."""
    if current_user.is_authenticated:
        return redirect(url_for('ui.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Look up user
        stmt = select(User).where(User.username == username)
        user = db.session.execute(stmt).scalar_one_or_none()

        if user and check_password_hash(user.password_hash, password):
            # Success: Log them in and create session cookie
            login_user(user)
            flash('Logged in successfully.', 'success')
            
            # Handle "next" redirect if they were forced to login
            next_page = request.args.get('next')
            return redirect(next_page or url_for('ui.dashboard'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')

@ui_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('ui.login'))

@ui_bp.route('/')
@ui_bp.route('/dashboard')
@login_required
def dashboard():
    """Main Analytics View."""
    
    # Example Metrics for the Dashboard
    event_count = db.session.execute(select(func.count(EPCISEvent.id))).scalar()
    product_count = db.session.execute(select(func.count(Product.id))).scalar()
    
    # Fetch 10 most recent events
    recent_events = db.session.execute(
        select(EPCISEvent).order_by(EPCISEvent.event_time.desc()).limit(10)
    ).scalars().all()

    return render_template('dashboard.html', 
                           event_count=event_count, 
                           product_count=product_count,
                           events=recent_events)

# Add to epcis_repo/app/routes/ui.py

@ui_bp.route('/trace', methods=['GET'])
@login_required
def trace_page():
    """Renders the search page."""
    query = request.args.get('q', '').strip()
    tree_data = None
    
    if query:
        # 1. Find the current state of the searched item
        root_state = db.session.get(EPCState, query)
        
        if root_state:
            tree_data = build_hierarchy(root_state)
        else:
            flash(f"EPC {query} not found.", "warning")

    return render_template('trace.html', query=query, tree=tree_data)

def build_hierarchy(state):
    """Recursive helper to build a dictionary tree of items."""
    node = {
        "epc": state.epc,
        "type": "Unit" if "sgtin" in state.epc else "Container",
        "status": state.current_disposition,
        "children": []
    }
    
    # Check if this item is a Parent (has children currently packed inside)
    # This requires a query to find items where parent_epc == state.epc
    children_states = db.session.execute(
        select(EPCState).where(EPCState.parent_epc == state.epc)
    ).scalars().all()
    
    for child in children_states:
        node["children"].append(build_hierarchy(child))
        
    return node



@ui_bp.route('/users', methods=['GET', 'POST'])
@login_required
def manage_users():
    """Admin page to create new Managers/Operators."""
    
    # Security Check: Only Admins can create users
    if current_user.role != 'admin':
        flash("Unauthorized: Only Admins can manage users.", "danger")
        return redirect(url_for('ui.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role') # 'manager' or 'operator'

        # Check if user exists
        existing = db.session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if existing:
            flash(f"User {username} already exists.", "warning")
        else:
            new_user = User(
                username=username,
                password_hash=generate_password_hash(password),
                role=role,
                is_active=True
            )
            db.session.add(new_user)
            db.session.commit()
            flash(f"User {username} created successfully!", "success")

    # List existing users
    users = db.session.execute(select(User)).scalars().all()
    return render_template('users.html', users=users)

@ui_bp.route('/products', methods=['GET', 'POST'])
@login_required
def manage_products():
    """UI for managing Master Data (Products)."""
    
    # Handle Form Submission (Create new product)
    if request.method == 'POST':
        # In a real app, you'd select the company dynamically. 
        # Here we pick the first one found (simulating single-tenant).
        company = db.session.execute(select(Company)).scalars().first()
        if not company:
            flash("Error: No Company defined in DB. Run register_device.py first.", "danger")
        else:
            try:
                new_product = Product(
                    name=request.form.get('name'),
                    gtin=request.form.get('gtin'),
                    sku=request.form.get('sku'),
                    description=request.form.get('description'),
                    company_id=company.id
                )
                db.session.add(new_product)
                db.session.commit()
                flash(f"Product '{new_product.name}' created!", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error creating product: {str(e)}", "danger")

    # Fetch existing products to display in table
    products = db.session.execute(select(Product)).scalars().all()
    
    return render_template('products.html', products=products)