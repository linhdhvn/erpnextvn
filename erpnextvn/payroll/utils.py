"""Vietnamese payroll and formatting utilities.

Exposed via Jinja to all print formats:

- ``so_tien_bang_chu`` — convert a number to Vietnamese words
- ``format_vnd`` — format a number as Vietnamese Dong (``1.234.567 ₫``)

Also provides ``validate_salary_slip`` — a ``doc_events`` hook that auto-fills
BHXH/BHYT/BHTN and Personal Income Tax on every Salary Slip validate.
"""

from __future__ import annotations

from typing import Union

import frappe

from erpnextvn.payroll.insurance_calculator import calculate_insurance
from erpnextvn.payroll.pit_calculator import calculate_pit

Number = Union[int, float]


# Vietnamese number words
_ONES = ["", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
_POSITIONS = ["", "nghìn", "triệu", "tỷ"]


def _read_three_digits(n: int, show_zero_hundred: bool = False) -> str:
    """Convert a 3-digit number (0–999) to Vietnamese words.

    Args:
        n: Integer in range [0, 999].
        show_zero_hundred: When True, prefix "không trăm" for numbers
            under 100 (used for non-leading groups).

    Returns:
        Vietnamese text representation. Empty string for ``n == 0``.
    """
    if n == 0:
        return ""

    hundred = n // 100
    ten = (n % 100) // 10
    one = n % 10

    parts: list[str] = []

    if hundred > 0:
        parts.append(f"{_ONES[hundred]} trăm")
    elif show_zero_hundred:
        parts.append("không trăm")

    if ten > 1:
        parts.append(f"{_ONES[ten]} mươi")
        if one == 1:
            parts.append("mốt")
        elif one == 4:
            parts.append("tư")
        elif one == 5:
            parts.append("lăm")
        elif one > 0:
            parts.append(_ONES[one])
    elif ten == 1:
        parts.append("mười")
        if one == 5:
            parts.append("lăm")
        elif one > 0:
            parts.append(_ONES[one])
    elif ten == 0 and one > 0:
        if hundred > 0 or show_zero_hundred:
            parts.append("lẻ")
        parts.append(_ONES[one])

    return " ".join(parts)


def so_tien_bang_chu(amount: Number, currency: str = "đồng") -> str:
    """Convert a monetary amount to Vietnamese words.

    Usage inside a Jinja Print Format::

        {{ so_tien_bang_chu(doc.grand_total) }}

    Args:
        amount: The monetary amount. Rounded to integer before conversion.
            Negative values are rendered as the absolute value.
        currency: Suffix (default ``"đồng"``).

    Returns:
        Capitalized Vietnamese text.
        Example: ``so_tien_bang_chu(1234567)`` →
        ``"Một triệu hai trăm ba mươi bốn nghìn năm trăm sáu mươi bảy đồng"``.
    """
    amount = int(round(abs(amount)))

    if amount == 0:
        return f"Không {currency}".strip()

    # Split into groups of 3 digits (right-to-left).
    groups: list[int] = []
    while amount > 0:
        groups.append(amount % 1000)
        amount //= 1000

    parts: list[str] = []
    for i in range(len(groups) - 1, -1, -1):
        if groups[i] == 0:
            continue
        # For non-leading groups, show "không trăm" to preserve digit positions.
        show_zero = i < len(groups) - 1
        text = _read_three_digits(groups[i], show_zero)
        if text:
            position = _POSITIONS[i] if i < len(_POSITIONS) else ""
            parts.append(f"{text} {position}".strip())

    result = " ".join(parts)
    result = result[0].upper() + result[1:]
    return f"{result} {currency}".strip()


def format_vnd(amount: Number) -> str:
    """Format a number as Vietnamese Dong.

    Uses ``.`` as thousands separator (Vietnamese convention).

    Args:
        amount: The monetary amount (rounded to integer).

    Returns:
        Formatted string like ``"1.234.567 ₫"``.
    """
    amount = int(round(amount))
    formatted = f"{amount:,.0f}".replace(",", ".")
    return f"{formatted} ₫"


# ---------------------------------------------------------------------------
# Salary Slip hook
# ---------------------------------------------------------------------------


def validate_salary_slip(doc, method=None) -> None:
    """Salary Slip ``validate`` hook — compute VN insurance + PIT.

    Wired via ``doc_events`` in ``hooks.py``. Only runs when the company's
    country is Vietnam. Populates the custom fields:

    - ``vn_insurance_employee`` (total employee BHXH + BHYT + BHTN)
    - ``vn_pit_amount`` (Thuế TNCN)
    - ``vn_taxable_income`` (Thu nhập tính thuế)
    """
    if not getattr(doc, "employee", None):
        return

    company_country = frappe.get_cached_value("Company", doc.company, "country")
    if company_country != "Vietnam":
        return

    employee = frappe.get_doc("Employee", doc.employee)
    insurance_salary = (
        getattr(employee, "vn_insurance_salary", None)
        or getattr(doc, "base_gross_pay", None)
        or getattr(doc, "gross_pay", 0)
    )
    num_dependents = getattr(employee, "vn_number_of_dependents", 0) or 0

    # Resolve wage region from employee province.
    wage_region = "I"
    province = getattr(employee, "vn_province", None)
    if province:
        region = frappe.db.get_value("VN Province", province, "wage_region")
        if region:
            # Handle tuple return from frappe.db.get_value()
            if isinstance(region, tuple):
                region = region[0]
            wage_region = region

    insurance = calculate_insurance(insurance_salary, wage_region)
    pit = calculate_pit(
        gross_income=doc.gross_pay or 0,
        insurance_deduction=insurance.total_employee,
        num_dependents=num_dependents,
    )

    doc.vn_insurance_employee = insurance.total_employee
    doc.vn_pit_amount = pit.tax_amount
    doc.vn_taxable_income = pit.taxable_income
