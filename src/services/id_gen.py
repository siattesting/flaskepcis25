from sqlalchemy import select
from ..models import db, Product, SerialCounter
from ..config import Config

class IDGenerator:
    """
    Service to safely generate unique serial numbers and SGTINs.
    Uses database row locking to prevent race conditions in high-speed factories.
    """

    @staticmethod
    def generate_sgtin_batch(gtin: str, count: int):
        """
        Generates a batch of SGTINs for a specific GTIN.
        Returns a list of URN strings.
        """
        # Start a transaction
        try:
            # 1. Fetch Product
            product = db.session.execute(
                select(Product).where(Product.gtin == gtin)
            ).scalar_one_or_none()

            if not product:
                raise ValueError(f"Product with GTIN {gtin} not found")

            # 2. Fetch or Create Counter with ROW LOCK
            # 'with_for_update()' tells Postgres: "Lock this row until I commit"
            # This forces other printers to wait their turn.
            stmt = select(SerialCounter).where(
                SerialCounter.product_id == product.id
            ).with_for_update()
            
            counter = db.session.execute(stmt).scalar_one_or_none()

            if not counter:
                counter = SerialCounter(product_id=product.id, last_serial=0)
                db.session.add(counter)

            # 3. Calculate Range
            start_serial = counter.last_serial + 1
            end_serial = counter.last_serial + count

            # 4. Update Counter
            counter.last_serial = end_serial
            
            # 5. Commit logic happens at the end of the route, 
            # but we can flush here to ensure IDs are reserved.
            db.session.flush()

            # 6. Format SGTINs (URN Format)
            # Format: urn:epc:id:sgtin:CompanyPrefix.ItemRef.Serial
            # Note: We need to split GTIN into CompanyPrefix and ItemRef.
            # For simplicity in this phase, we assume the config holds the prefix 
            # and we derive the Item Reference from the GTIN (removing check digit).
            
            # Helper to parse GTIN-14 to EPC format
            company_prefix = Config.COMPANY_PREFIX
            # Typical logic: ItemRef is digits after prefix, excluding last check digit.
            # This is a simplified implementation. Real world requires specific mask logic.
            item_ref = gtin[len(company_prefix)+1:-1] 
            
            urn_prefix = f"urn:epc:id:sgtin:{company_prefix}.{item_ref}"
            
            generated_ids = []
            for i in range(start_serial, end_serial + 1):
                generated_ids.append(f"{urn_prefix}.{i}")

            return generated_ids

        except Exception as e:
            # Let the route handle the rollback
            raise e