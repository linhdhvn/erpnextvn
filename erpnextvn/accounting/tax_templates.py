"""Vietnam VAT tax template setup.

Creates Sales/Purchase tax templates for the standard Vietnamese VAT rates:
0% (export), 5% (essentials), 8% (reduced per NQ), 10% (standard).

Also provides the ``get_round_off_accounts`` regional override which maps
to account 6428 (Other miscellaneous expenses). The account numbers
``33311``, ``1331``, and ``6428`` are shared by TT200 and TT99/2025, so
this module works for both chart-of-accounts variants.
"""

from __future__ import annotations

import frappe


VAT_RATES = [
    {
        "title": "VAT 0% - Xuất khẩu",
        "rate": 0,
        "description": "Thuế suất 0% cho hàng xuất khẩu",
    },
    {
        "title": "VAT 5% - Thiết yếu",
        "rate": 5,
        "description": "Thuế suất 5% cho hàng thiết yếu",
    },
    {
        "title": "VAT 8% - Giảm thuế",
        "rate": 8,
        "description": "Thuế suất 8% theo Nghị quyết giảm thuế",
    },
    {
        "title": "VAT 10% - Phổ thông",
        "rate": 10,
        "description": "Thuế suất phổ thông 10%",
    },
]


def create_tax_templates(company: str) -> None:
    """Create Vietnam VAT tax templates for a company.

    Args:
        company: Company name (Frappe primary key).
    """
    abbr = frappe.get_cached_value("Company", company, "abbr")

    # Default account heads (assumes TT200 CoA is already loaded).
    sales_tax_account = f"33311 - Thuế GTGT đầu ra - {abbr}"
    purchase_tax_account = f"1331 - Thuế GTGT được khấu trừ của hàng hóa, dịch vụ - {abbr}"

    # Fall back to any VAT-looking account if the exact name is missing.
    if not frappe.db.exists("Account", sales_tax_account):
        sales_tax_account = _find_account(company, ["3331", "33311"])
    if not frappe.db.exists("Account", purchase_tax_account):
        purchase_tax_account = _find_account(company, ["1331", "133"])

    for vat in VAT_RATES:
        sales_name = f"{vat['title']} - {abbr}"
        if not frappe.db.exists("Sales Taxes and Charges Template", sales_name):
            frappe.get_doc(
                {
                    "doctype": "Sales Taxes and Charges Template",
                    "title": vat["title"],
                    "company": company,
                    "taxes": [
                        {
                            "charge_type": "On Net Total",
                            "account_head": sales_tax_account,
                            "description": vat["description"],
                            "rate": vat["rate"],
                        }
                    ],
                }
            ).insert(ignore_permissions=True)

        purchase_name = f"{vat['title']} - {abbr}"
        if not frappe.db.exists("Purchase Taxes and Charges Template", purchase_name):
            frappe.get_doc(
                {
                    "doctype": "Purchase Taxes and Charges Template",
                    "title": vat["title"],
                    "company": company,
                    "taxes": [
                        {
                            "charge_type": "On Net Total",
                            "account_head": purchase_tax_account,
                            "description": vat["description"],
                            "rate": vat["rate"],
                        }
                    ],
                }
            ).insert(ignore_permissions=True)


def _find_account(company: str, account_number_prefixes: list[str]) -> str | None:
    """Best-effort lookup of an account by number prefix."""
    for prefix in account_number_prefixes:
        result = frappe.db.get_value(
            "Account",
            {"company": company, "account_number": prefix, "is_group": 0},
            "name",
        )
        # Handle tuple return from frappe.db.get_value()
        if result:
            if isinstance(result, tuple):
                return result[0]
            return result
    return None


def get_round_off_accounts(company: str) -> dict:
    """Return the round-off account for Vietnam.

    Regional override for
    ``erpnext.controllers.taxes_and_totals.get_regional_round_off_accounts``.
    """
    abbr = frappe.get_cached_value("Company", company, "abbr")
    cost_center = frappe.get_cached_value("Company", company, "cost_center")
    return {
        "round_off_account": f"6428 - Chi phí bằng tiền khác - {abbr}",
        "round_off_cost_center": cost_center,
    }
