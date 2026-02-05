import uuid
from werkzeug.security import generate_password_hash
from sqlalchemy import select
from src import create_app, db
from src.models import Company, Plant, Device

# 1. Initialize the App Context
app = create_app('development')

def register_device():
    with app.app_context():
        print("--- Setting up Factory Environment ---")

        # A. Ensure Company Exists
        company = db.session.execute(select(Company)).scalar_one_or_none()
        if not company:
            company = Company(
                name="African Cocoa Co.",
                gln="1234567000001",
                gcp="1234567"
            )
            db.session.add(company)
            db.session.commit()
            print(f"✔ Created Company: {company.name}")
        else:
            print(f"✔ Found Company: {company.name}")

        # B. Ensure Plant Exists
        plant = db.session.execute(select(Plant)).scalar_one_or_none()
        if not plant:
            plant = Plant(
                company_id=company.id,
                name="Ouagadougou Plant 1",
                gln="1234567000010"  # <--- FIXED (13 digits)
            )
            db.session.add(plant)
            db.session.commit()
            print(f"✔ Created Plant: {plant.name}")
        else:
            print(f"✔ Found Plant: {plant.name}")

        # C. Create the Device
        # Define the RAW key here (or generate random)
        raw_key = "factory-secret-key-123"
        device_role = "line_controller" # Must match what app.py expects

        # Check if exists to avoid duplicates
        existing = db.session.execute(select(Device).where(Device.name == "LineController-01")).scalar_one_or_none()
        
        if existing:
            print("\n⚠ Device 'LineController-01' already exists.")
            print(f"UUID: {existing.id}")
            print(f"KEY:  (Hidden, hopefully you remember '{raw_key}')")
            return

        new_device = Device(
            plant_id=plant.id,
            name="LineController-01",
            device_role=device_role,
            # CRITICAL: We store the HASH, not the key
            api_key_hash=generate_password_hash(raw_key)
        )
        
        db.session.add(new_device)
        db.session.commit()

        print("\n" + "="*40)
        print("SUCCESS! COPY THESE VALUES:")
        print("="*40)
        print(f"export DEVICE_ID=\"{new_device.id}\"")
        print(f"export DEVICE_KEY=\"{raw_key}\"")
        print(f"export PLANT_GLN=\"{plant.gln}\"")
        print("="*40 + "\n")

if __name__ == "__main__":
    register_device()