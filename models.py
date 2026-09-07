from sqlalchemy import Column, Integer, String, Date, Numeric
from database import Base

class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True)
    asset_code = Column(String(50), unique=True, nullable=False)
    description = Column(String(255), nullable=False)
    asset_classification = Column(String(100), nullable=False)
    purchase_date = Column(Date, nullable=False)
    depreciation_method = Column(String(10), default="SL")
    status = Column(String(20), default="ACTIVE")
        # Tax depreciation details
    tax_original_cost = Column(Numeric(12, 2), nullable=False)
    opening_tax_wdv = Column(Numeric(12, 2), nullable=False)
    tax_depreciation_type = Column(String(30), nullable=False)
    tax_depreciation_rate = Column(Numeric(5, 2), nullable=False)
    tax_depreciation_date = Column(Date, nullable=False)

    # Book depreciation details
    book_original_cost = Column(Numeric(12, 2), nullable=False)
    opening_book_wdv = Column(Numeric(12, 2), nullable=False)
    book_depreciation_type = Column(String(30), nullable=False)
    book_depreciation_rate = Column(Numeric(5, 2), nullable=False)
    book_depreciation_date = Column(Date, nullable=False)