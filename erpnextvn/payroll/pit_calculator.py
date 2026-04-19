"""Vietnamese Personal Income Tax (PIT / Thuế TNCN) calculator.

Implements the 7-bracket progressive monthly PIT per the current Vietnamese
tax law, using the "quick deduction" (phương pháp giảm trừ nhanh) method.

Bracket table (monthly taxable income, VND):

=====  ============  ======  ================
Stt    Upper limit   Rate    Quick deduction
=====  ============  ======  ================
1      5,000,000      5%     0
2     10,000,000     10%     250,000
3     18,000,000     15%     750,000
4     32,000,000     20%     1,650,000
5     52,000,000     25%     3,250,000
6     80,000,000     30%     5,850,000
7     > 80,000,000   35%     9,850,000
=====  ============  ======  ================
"""

from __future__ import annotations

from typing import NamedTuple, Optional


class PITResult(NamedTuple):
    """Result of a PIT calculation."""

    taxable_income: float  # Thu nhập tính thuế
    tax_amount: float      # Số thuế TNCN
    effective_rate: float  # Thuế suất thực tế (%)
    bracket: int           # Highest bracket applied (1..7)


#: ``(upper_limit, rate, quick_deduction)`` tuples.
TAX_BRACKETS: list[tuple[float, float, float]] = [
    (5_000_000,   0.05, 0),
    (10_000_000,  0.10, 250_000),
    (18_000_000,  0.15, 750_000),
    (32_000_000,  0.20, 1_650_000),
    (52_000_000,  0.25, 3_250_000),
    (80_000_000,  0.30, 5_850_000),
    (float("inf"), 0.35, 9_850_000),
]


def calculate_pit(
    gross_income: float,
    insurance_deduction: float,
    num_dependents: int = 0,
    personal_deduction: Optional[float] = None,
    dependent_deduction: Optional[float] = None,
    other_deductions: float = 0,
) -> PITResult:
    """Calculate the monthly Personal Income Tax (Thuế TNCN).

    Formula::

        Taxable = Gross
                − Insurance (employee)
                − Personal Deduction
                − (Dependents × Dependent Deduction)
                − Other Deductions

        Tax = Taxable × Rate − Quick Deduction

    Args:
        gross_income: Total gross salary (Tổng thu nhập chịu thuế).
        insurance_deduction: Employee BH contribution (BHXH + BHYT + BHTN).
        num_dependents: Number of registered dependents.
        personal_deduction: Override personal deduction.
            When ``None``, pulls ``VN Payroll Settings.personal_deduction``
            (default 15,500,000 VND per Resolution 110/2025/UBTVQH15,
            effective from tax year 2026).
        dependent_deduction: Override dependent deduction.
            When ``None``, pulls ``VN Payroll Settings.dependent_deduction``
            (default 6,200,000 VND per Resolution 110/2025/UBTVQH15,
            effective from tax year 2026).
        other_deductions: Any additional tax-deductible amounts.

    Returns:
        ``PITResult`` with ``taxable_income``, ``tax_amount``,
        ``effective_rate``, and ``bracket``.
    """
    # Input validation
    if gross_income < 0:
        raise ValueError("gross_income must be non-negative")
    if insurance_deduction < 0:
        raise ValueError("insurance_deduction must be non-negative")
    if num_dependents < 0:
        raise ValueError("num_dependents must be non-negative")
    if other_deductions < 0:
        raise ValueError("other_deductions must be non-negative")
    
    if personal_deduction is None or dependent_deduction is None:
        personal_deduction, dependent_deduction = _resolve_deductions(
            personal_deduction, dependent_deduction
        )

    total_deductions = (
        insurance_deduction
        + personal_deduction
        + (num_dependents * dependent_deduction)
        + other_deductions
    )
    taxable_income = max(0.0, gross_income - total_deductions)

    if taxable_income == 0:
        return PITResult(0.0, 0.0, 0.0, 0)

    tax_amount = 0.0
    bracket = 0
    for i, (upper_limit, rate, quick_deduction) in enumerate(TAX_BRACKETS):
        if taxable_income <= upper_limit:
            tax_amount = taxable_income * rate - quick_deduction
            bracket = i + 1
            break

    tax_amount = max(0.0, round(tax_amount))
    effective_rate = (tax_amount / taxable_income * 100) if taxable_income else 0.0

    return PITResult(
        taxable_income=taxable_income,
        tax_amount=tax_amount,
        effective_rate=round(effective_rate, 2),
        bracket=bracket,
    )


def _resolve_deductions(
    personal: Optional[float], dependent: Optional[float]
) -> tuple[float, float]:
    """Resolve deduction values from ``VN Payroll Settings`` when not given.

    Falls back to the current statutory defaults if the settings doc or
    Frappe itself is unavailable (e.g. when running unit tests outside a
    bench).
    """
    # Statutory defaults per Resolution 110/2025/UBTVQH15 (effective 01/01/2026,
    # applies from tax year 2026).
    default_personal = 15_500_000.0
    default_dependent = 6_200_000.0

    try:
        import frappe

        settings = frappe.get_single("VN Payroll Settings")
        if personal is None:
            personal = settings.personal_deduction or default_personal
        if dependent is None:
            dependent = settings.dependent_deduction or default_dependent
    except Exception:
        if personal is None:
            personal = default_personal
        if dependent is None:
            dependent = default_dependent

    return float(personal), float(dependent)
