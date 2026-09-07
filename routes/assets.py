from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from database import SessionLocal
from models import Asset
from datetime import datetime

assets_bp = Blueprint("assets", __name__)
assets_bp.secret_key = 'analyst_portfolio_secret_key_here'

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _validate_asset_form(form):
    errors = []
    values = {}

    date_fields = [
        "purchase_date",
        "tax_depreciation_date",
        "book_depreciation_date",
    ]
    for field in date_fields:
        value = form.get(field, "").strip()
        if not value:
            errors.append(f"{field.replace('_', ' ').title()} is required.")
            continue
        try:
            values[field] = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            errors.append(f"{field.replace('_', ' ').title()} must be a valid date.")

    numeric_fields = [
        "tax_original_cost",
        "opening_tax_wdv",
        "book_original_cost",
        "opening_book_wdv",
    ]
    for field in numeric_fields:
        value = form.get(field, "").strip()
        try:
            number = float(value)
            if number < 0:
                errors.append(f"{field.replace('_', ' ').title()} cannot be negative.")
            else:
                values[field] = number
        except (TypeError, ValueError):
            errors.append(f"{field.replace('_', ' ').title()} is required and must be a number.")

    rate_fields = ["tax_depreciation_rate", "book_depreciation_rate"]
    for field in rate_fields:
        value = form.get(field, "").strip()
        try:
            rate = float(value)
            if not 0 <= rate <= 100:
                errors.append(f"{field.replace('_', ' ').title()} must be between 0 and 100.")
            else:
                values[field] = rate
        except (TypeError, ValueError):
            errors.append(f"{field.replace('_', ' ').title()} is required and must be a number.")

    return values, errors

# --- 1. WEB UI ROUTE: Dashboard (Read) & Form Submission (Create) ---
@assets_bp.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    # Open a database session manually for the route logic
    db = SessionLocal()
    
    try:
        if request.method == 'POST':
            values, errors = _validate_asset_form(request.form)
            if errors:
                for error in errors:
                    flash(error, "danger")
                all_assets = db.query(Asset).order_by(Asset.purchase_date.desc()).all()
                return render_template('dashboard.html', assets=all_assets)

            # Instantiate a new Asset ORM model instance mapping directly to SQL Server
            new_asset = Asset(
                asset_code=request.form.get('asset_code'),
                description=request.form.get('description'),
                asset_classification=request.form.get('asset_classification'),
                purchase_date=values['purchase_date'],
                tax_original_cost=values['tax_original_cost'],
                opening_tax_wdv=values['opening_tax_wdv'],
                tax_depreciation_type=request.form.get(
                    'tax_depreciation_type'
                ),
                tax_depreciation_rate=values['tax_depreciation_rate'],
                tax_depreciation_date=values['tax_depreciation_date'],
                book_original_cost=values['book_original_cost'],
                opening_book_wdv=values['opening_book_wdv'],
                book_depreciation_type=request.form.get(
                    'book_depreciation_type'
                ),
                book_depreciation_rate=values['book_depreciation_rate'],
                book_depreciation_date=values['book_depreciation_date'],
                # Note: Check if your 'Asset' model has these calculated fields, 
                # otherwise you can leave them out or add them to your models.py
                status='ACTIVE' 
            )
            
            # Save to SQL Server via ORM Session
            db.add(new_asset)
            db.commit()
            flash('Asset successfully catalogued via Web Interface!', 'success')
            return redirect(url_for('assets.dashboard'))

        # GET Request: Retrieve all assets from SQL Server via ORM query
        all_assets = db.query(Asset).order_by(Asset.purchase_date.desc()).all()
        return render_template('dashboard.html', assets=all_assets)
        
    except Exception as e:
        db.rollback()
        flash(f'Database Operation Error: {str(e)}', 'danger')
        return render_template('dashboard.html', assets=[])
    finally:
        db.close()

# --- VIEW ROUTE: Displays an asset without editing it ---
@assets_bp.route("/assets/view/<int:asset_id>")
def view_asset(asset_id):
    db = SessionLocal()
    try:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            flash("Asset not found.", "danger")
            return redirect(url_for("assets.dashboard"))

        return render_template("view_asset.html", asset=asset)
    finally:
        db.close()

# --- 3. DELETE ROUTE: Removes an asset from SQL Server ---
@assets_bp.route('/assets/delete/<int:asset_id>', methods=['POST'])
def delete_asset(asset_id):
    db = SessionLocal()
    try:
        # Find the asset in the database using its primary key ID
        asset_to_delete = db.query(Asset).get(asset_id)
        
        if asset_to_delete:
            db.delete(asset_to_delete)
            db.commit()
            flash(f"Asset '{asset_to_delete.asset_code}' was successfully deleted.", "success")
        else:
            flash("Asset not found.", "danger")
            
    except Exception as e:
        db.rollback()
        flash(f"Error deleting asset: {str(e)}", "danger")
    finally:
        db.close()
        
    return redirect(url_for('assets.dashboard'))

# --- 4. TOGGLE STATUS ROUTE: Switches between ACTIVE and DISPOSED ---
@assets_bp.route('/assets/toggle-status/<int:asset_id>', methods=['POST'])
def toggle_asset_status(asset_id):
    db = SessionLocal()
    try:
        asset_to_update = db.query(Asset).get(asset_id)

        if asset_to_update:
            asset_to_update.status = (
                'DISPOSED'
                if asset_to_update.status == 'ACTIVE'
                else 'ACTIVE'
            )
            db.commit()
            flash(
                f"Status for '{asset_to_update.asset_code}' updated to "
                f"{asset_to_update.status}.",
                'success'
            )
        else:
            flash('Asset not found.', 'danger')

    except Exception as e:
        db.rollback()
        flash(f'Error updating asset status: {str(e)}', 'danger')
    finally:
        db.close()

    return redirect(url_for('assets.dashboard'))

# --- 5. EDIT ROUTE: Allows modification of an existing asset ---
@assets_bp.route("/assets/edit/<int:asset_id>", methods=["GET", "POST"])
def edit_asset(asset_id):
    db = SessionLocal()

    try:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()

        if not asset:
            flash("Asset not found.", "danger")
            return redirect(url_for("assets.dashboard"))

        if request.method == "POST":
            values, errors = _validate_asset_form(request.form)
            if errors:
                for error in errors:
                    flash(error, "danger")
                return render_template("edit_asset.html", asset=asset)

            asset.asset_code = request.form.get("asset_code")
            asset.description = request.form.get("description")
            asset.asset_classification = request.form.get("asset_classification")
            asset.tax_original_cost = values["tax_original_cost"]
            asset.opening_tax_wdv = values["opening_tax_wdv"]
            asset.tax_depreciation_type = request.form.get(
                "tax_depreciation_type"
            )
            asset.tax_depreciation_rate = values["tax_depreciation_rate"]
            asset.tax_depreciation_date = values["tax_depreciation_date"]
            asset.book_original_cost = values["book_original_cost"]
            asset.opening_book_wdv = values["opening_book_wdv"]
            asset.book_depreciation_type = request.form.get(
                "book_depreciation_type"
            )
            asset.book_depreciation_rate = values["book_depreciation_rate"]
            asset.book_depreciation_date = values["book_depreciation_date"]
            asset.purchase_date = values["purchase_date"]

            db.commit()
            flash("Asset updated successfully.", "success")
            return redirect(url_for("assets.dashboard"))

        return render_template("edit_asset.html", asset=asset)

    except Exception as e:
        db.rollback()
        flash(f"Error updating asset: {str(e)}", "danger")
        return redirect(url_for("assets.dashboard"))

    finally:
        db.close()
        

        
    return redirect(url_for('assets.dashboard'))

# @assets_bp.route('/depreciation.py', methods=['POST'])
# # --- 2. API ROUTE: Handles your PowerShell JSON Payload ---
# @assets_bp.route('/assets', methods=['POST'])
# def api_add_asset():
#     data = request.get_json()
#     if not data:
#         return jsonify({"error": "Invalid payload format"}), 400
    
#     db = SessionLocal()
#     try:
#         # Parse the JSON string date into a Python object
#         p_date = datetime.strptime(data.get('purchase_date'), '%Y-%m-%d') if data.get('purchase_date') else datetime.now()
        
#         # Build the model matching your PowerShell payload data structure
#         api_asset = Asset(
#             asset_code=data.get('asset_code'),
#             description=data.get('description'),
#             purchase_date=p_date,
#             status=data.get('status', 'ACTIVE')
#         )
        
#         db.add(api_asset)
#         db.commit()
#         return jsonify({"message": "Asset created successfully via PowerShell API", "code": api_asset.asset_code}), 201
        
#     except Exception as e:
#         db.rollback()
#         return jsonify({"error": str(e)}), 500
#     finally:
#         db.close()
        
# #create an asset

# # @assets_bp.route("/assets", methods=["POST"])
# # def create_asset():
# #     db = next(get_db())
# #     data = request.json
# #     asset = Asset(
# #         asset_code=data["asset_code"],
# #         description=data.get("description", ""),
# #         purchase_date=datetime.strptime(data["purchase_date"], "%Y-%m-%d"),
# #         depreciation_method=data.get("depreciation_method", "SL"),
# #         status="ACTIVE"
# #     )
# #     db.add(asset)
# #     db.commit()
# #     db.refresh(asset)
# #     return jsonify({"message": "Asset created", "id": asset.id})

# #read assets

# @assets_bp.route("/assets", methods=["GET"])

# def list_assets():
#     db = next(get_db())
#     assets = db.query(Asset).all()

#     result = []
#     for a in assets:
#         result.append({
#             "id": a.id,
#             "asset_code": a.asset_code,
#             "description": a.description,
#             "asset_classification": a.asset_classification,
#             "purchase_date": a.purchase_date.isoformat(),
#             "depreciation_method": a.depreciation_method,
#             "status": a.status
#         })

#     return jsonify(result)

# # edit an asset

# @assets_bp.route("/assets/<int:asset_id>", methods=["PUT"])

# def update_asset(asset_id):
#     db = next(get_db())
#     data = request.json

#     asset = db.query(Asset).filter(Asset.id == asset_id).first()
#     if not asset:
#         return jsonify({"error": "Asset not found"}), 404

#     for field in ["asset_code", "description", "asset_classification",
#                   "depreciation_method", "status"]:
#         if field in data:
#             setattr(asset, field, data[field])

#     if "purchase_date" in data:
#         asset.purchase_date = datetime.strptime(data["purchase_date"], "%Y-%m-%d")

#     db.commit()
#     return jsonify({"message": "Asset updated"})

# delete an asset

# @assets_bp.route("/assets/<int:asset_id>", methods=["DELETE"])

# def api_delete_asset(asset_id):
#     db = next(get_db())
#     asset = db.query(Asset).filter(Asset.id == asset_id).first()

#     if not asset:
#         return jsonify({"error": "Asset not found"}), 404

#     db.delete(asset)
#     db.commit()

#     return jsonify({"message": "Asset deleted"})
