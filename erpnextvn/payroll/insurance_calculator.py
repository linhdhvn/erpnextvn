"""Vietnamese social insurance calculator (BHXH / BHYT / BHTN / KPCĐ).

Default statutory rates (2024+):

Employee share
    BHXH 8%, BHYT 1.5%, BHTN 1%  → total 10.5%

Employer share
    BHXH 17.5%, BHYT 3%, BHTN 1%, KPCĐ 2% → total 23.5%

Ceilings
    BHXH/BHYT ceiling = 20 × base salary (lương cơ sở)
    BHTN ceiling = 20 × regional minimum wage (lương tối thiểu vùng)

The ceilings and rates are read from ``VN Payroll Settings`` when Frappe is
available; otherwise the statutory defaults apply (useful for unit tests).
"""

from __future__ import annotations

from typing import NamedTuple, Optional


class InsuranceResult(NamedTuple):
    """Breakdown of insurance contributions."""

    # Employee-paid
    si_employee: float   # BHXH NLĐ
    hi_employee: float   # BHYT NLĐ
    ui_employee: float   # BHTN NLĐ
    total_employee: float

    # Employer-paid
    si_employer: float   # BHXH DN
    hi_employer: float   # BHYT DN
    ui_employer: float   # BHTN DN
    union_fee: float     # KPCĐ DN
    total_employer: float


_DEFAULTS = {
    "base_salary": 2_340_000.0,
    "si_hi_ceiling_multiplier": 20,
    "ui_ceiling_multiplier": 20,
    "min_wage_region_1": 4_960_000.0,
    "min_wage_region_2": 4_410_000.0,
    "min_wage_region_3": 3_860_000.0,
    "min_wage_region_4": 3_450_000.0,
    "si_employee_rate": 8.0,
    "hi_employee_rate": 1.5,
    "ui_employee_rate": 1.0,
    "si_employer_rate": 17.5,
    "hi_employer_rate": 3.0,
    "ui_employer_rate": 1.0,
    "union_fee_rate": 2.0,
}


def calculate_insurance(
    insurance_salary: float,
    wage_region: str = "I",
    total_payroll: Optional[float] = None,
) -> InsuranceResult:
    """Calculate social insurance contributions for one employee.

    Args:
        insurance_salary: Salary used as the insurance base (Mức lương đóng BH).
        wage_region: One of ``"I"``, ``"II"``, ``"III"``, ``"IV"``.
            Selects the UI (BHTN) ceiling via the regional minimum wage.
        total_payroll: Total company payroll for the period. Used as the
            base for the Trade-Union Fee (KPCĐ). When ``None`` the employee's
            insurance salary is used (approximation).

    Returns:
        ``InsuranceResult`` with rounded-to-integer VND amounts.
    
    Raises:
        ValueError: if insurance_salary or total_payroll is negative.
    """
    # Input validation
    if insurance_salary < 0:
        raise ValueError("insurance_salary must be non-negative")
    if total_payroll is not None and total_payroll < 0:
        raise ValueError("total_payroll must be non-negative")
    
    settings = _load_settings()

    base_salary = settings["base_salary"]
    si_hi_ceiling = settings["si_hi_ceiling_multiplier"] * base_salary

    min_wage_map = {
        "I": settings["min_wage_region_1"],
        "II": settings["min_wage_region_2"],
        "III": settings["min_wage_region_3"],
        "IV": settings["min_wage_region_4"],
    }
    min_wage = min_wage_map.get(wage_region, min_wage_map["I"])
    ui_ceiling = settings["ui_ceiling_multiplier"] * min_wage

    si_hi_base = min(insurance_salary, si_hi_ceiling)
    ui_base = min(insurance_salary, ui_ceiling)

    si_employee = round(si_hi_base * settings["si_employee_rate"] / 100)
    hi_employee = round(si_hi_base * settings["hi_employee_rate"] / 100)
    ui_employee = round(ui_base * settings["ui_employee_rate"] / 100)
    total_employee = si_employee + hi_employee + ui_employee

    si_employer = round(si_hi_base * settings["si_employer_rate"] / 100)
    hi_employer = round(si_hi_base * settings["hi_employer_rate"] / 100)
    ui_employer = round(ui_base * settings["ui_employer_rate"] / 100)

    union_base = total_payroll if total_payroll is not None else insurance_salary
    union_fee = round(union_base * settings["union_fee_rate"] / 100)

    total_employer = si_employer + hi_employer + ui_employer + union_fee

    return InsuranceResult(
        si_employee=si_employee,
        hi_employee=hi_employee,
        ui_employee=ui_employee,
        total_employee=total_employee,
        si_employer=si_employer,
        hi_employer=hi_employer,
        ui_employer=ui_employer,
        union_fee=union_fee,
        total_employer=total_employer,
    )


def _load_settings() -> dict:
    """Read ``VN Payroll Settings`` — fall back to defaults outside Frappe."""
    settings = dict(_DEFAULTS)
    try:
        import frappe

        doc = frappe.get_single("VN Payroll Settings")
        for key in settings.keys():
            value = getattr(doc, key, None)
            if value:
                settings[key] = float(value)
    except Exception:
        pass
    return settings
