from flask import Blueprint, request, jsonify, g
from flask_jwt_extended import jwt_required
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..models import db, Product, Company
from ..middleware.api_key import require_device_key
from ..services.id_gen import IDGenerator

products_bp = Blueprint('products', __name__)

# --- Human/Admin Routes (JWT Protected) ---

@products_bp.route('/', methods=['GET'])
@jwt_required()
def list_products():
    """List all configured products."""
    stmt = select(Product)
    products = db.session.execute(stmt).scalars().all()
    
    return jsonify([{
        "name": p.name,
        "gtin": p.gtin,
        "sku": p.sku,
        "description": p.description
    } for p in products]), 200

@products_bp.route('/', methods=['POST'])
@jwt_required()
def create_product():
    """Create a new product master record."""
    data = request.get_json()
    
    # Basic validation
    required = ['name', 'gtin', 'company_id']
    if not all(k in data for k in required):
        return jsonify({"message": "Missing fields"}), 400

    try:
        new_product = Product(
            name=data['name'],
            gtin=data['gtin'],
            sku=data.get('sku'),
            description=data.get('description'),
            company_id=data['company_id'] 
            # In a real app, you'd validate the user belongs to this company
        )
        db.session.add(new_product)
        db.session.commit()
        return jsonify({"message": "Product created", "gtin": new_product.gtin}), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Product with this GTIN already exists"}), 409


# --- Factory/Device Routes (API Key Protected) ---

@products_bp.route('/<gtin>/request-serials', methods=['POST'])
@require_device_key(required_role='printer') 
# Only 'printer' or 'line_controller' role should generate IDs. 
# Cameras should only read them.
def request_serials(gtin):
    """
    Called by the Line Controller when a print job starts.
    Payload: { "count": 1000 }
    """
    data = request.get_json() or {}
    count = data.get('count', 100) # Default to 100 if not specified
    
    # Cap the request size to prevent timeouts
    if count > 5000:
        return jsonify({"error": "Batch size too large", "max": 5000}), 400

    try:
        # Calls our thread-safe / transaction-safe service
        serial_list = IDGenerator.generate_sgtin_batch(gtin, count)
        
        # Commit the transaction (saving the updated counter)
        db.session.commit()
        
        return jsonify({
            "gtin": gtin,
            "count": len(serial_list),
            "serials": serial_list
        }), 201

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        db.session.rollback()
        # Log this in production!
        return jsonify({"error": "Generation failed", "details": str(e)}), 500