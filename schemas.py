"""Pydantic models for Level 1 output and the history tables used by Level 2."""
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator

ChargeType = Literal["energy", "fixed", "fpa", "quarterly_adjustment", "surcharge",
                     "meter_rent", "subsidy", "other"]
TaxType = Literal["gst", "electricity_duty", "income_tax", "municipal_tax", "other_tax"]

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH = re.compile(r"^\d{4}-\d{2}$")


class Line(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    amount: float


class Charge(Line):
    type: ChargeType


class Tax(Line):
    type: TaxType


class Bill(BaseModel):
    """Level 1 schema (guide section 5.1). Field order = JSON key order."""
    model_config = ConfigDict(extra="ignore")

    provider: Optional[Literal["KE", "LESCO", "IESCO"]] = None
    tariff: Optional[str] = None
    sanctioned_load_kw: Optional[float] = None
    bill_month: Optional[str] = None
    reading_date: Optional[str] = None
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    previous_reading: Optional[float] = None
    current_reading: Optional[float] = None
    units_consumed: Optional[float] = None
    charges: list[Charge] = []
    total_charges: Optional[float] = None
    taxes: list[Tax] = []
    total_taxes: Optional[float] = None
    current_bill: Optional[float] = None
    arrears: Optional[float] = None
    payable_within_due_date: Optional[float] = None
    payable_after_due_date: Optional[float] = None

    @field_validator("bill_month")
    @classmethod
    def _month(cls, v):
        if v is not None and not _MONTH.match(v):
            raise ValueError("bill_month must be YYYY-MM")
        return v

    @field_validator("reading_date", "issue_date", "due_date")
    @classmethod
    def _date(cls, v):
        if v is not None and not _DATE.match(v):
            raise ValueError("dates must be YYYY-MM-DD")
        return v

    @field_validator("charges", "taxes", mode="before")
    @classmethod
    def _none_list(cls, v):
        return [] if v is None else v

    def to_json_dict(self) -> dict:
        d = self.model_dump()
        # Whole numbers print as 3 rather than 3.0, matching the guide's example.
        def clean(x):
            if isinstance(x, float) and x.is_integer():
                return int(x)
            if isinstance(x, dict):
                return {k: clean(v) for k, v in x.items()}
            if isinstance(x, list):
                return [clean(i) for i in x]
            return x
        return clean(d)


def null_bill(provider: Optional[str] = None) -> dict:
    """Full schema with null values (fallback when extraction fails)."""
    return Bill(provider=provider).to_json_dict()


# ---- history tables (Level 2 helper step) ----
class UsageRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    month: Optional[str] = None          # YYYY-MM
    units: Optional[float] = None


class BillingRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    month: Optional[str] = None          # YYYY-MM
    billed_amount: Optional[float] = None
    pay_date: Optional[str] = None
    payment: Optional[float] = None


class History(BaseModel):
    model_config = ConfigDict(extra="ignore")
    usage_history: list[UsageRow] = []
    billing_history: list[BillingRow] = []

    @field_validator("usage_history", "billing_history", mode="before")
    @classmethod
    def _none_list(cls, v):
        return [] if v is None else v
