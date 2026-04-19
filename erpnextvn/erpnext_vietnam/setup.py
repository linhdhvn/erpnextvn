"""Vietnam country setup for ERPNext.

This module runs:
1. When the app is installed (via ``after_install`` hook)
2. When a user selects Vietnam in the Setup Wizard (via ``setup_wizard_stages``)

It loads provinces, adds custom fields, installs the Vietnam address
template, and configures company defaults (currency, date format, taxes).
"""

from __future__ import annotations

import json
import os

import frappe
from frappe import _


# ---------------------------------------------------------------------------
# Install / uninstall lifecycle
# ---------------------------------------------------------------------------


def after_install() -> None:
    """Post-install setup: load fixtures, add custom fields, address template."""
    load_provinces()
    add_custom_fields()
    add_address_template()
    frappe.db.commit()
    print("✅ ERPNext Vietnam: Installation complete")


def before_uninstall() -> None:
    """Cleanup before uninstall."""
    delete_custom_fields()
    frappe.db.commit()


# ---------------------------------------------------------------------------
# Setup Wizard
# ---------------------------------------------------------------------------


def get_setup_stages(args=None) -> list[dict]:
    """Return setup wizard stages for Vietnam.

    Called by Frappe's Setup Wizard when user selects Vietnam as country.
    """
    return [
        {
            "status": _("Setting up Vietnam localization"),
            "fail_msg": _("Failed to setup Vietnam localization"),
            "tasks": [
                {
                    "fn": setup_company_vietnam,
                    "args": args,
                    "fail_msg": _("Failed to setup company for Vietnam"),
                }
            ],
        }
    ]


def setup_company_vietnam(args: dict) -> None:
    """Setup a company with Vietnam defaults.

    Called from Setup Wizard when country = Vietnam.

    Args:
        args: Setup wizard arguments containing ``company_name``,
            ``company_abbr``, etc.
    """
    from erpnextvn.accounting.tax_templates import create_tax_templates

    company = args.get("company_name")
    if not company:
        return

    # Set company defaults
    frappe.db.set_value(
        "Company",
        company,
        {
            "country": "Vietnam",
            "default_currency": "VND",
        },
    )

    # Create VAT tax templates (0% / 5% / 8% / 10%)
    try:
        create_tax_templates(company)
    except Exception as exc:
        frappe.log_error(f"create_tax_templates failed for {company}: {exc}")

    # System-wide Vietnam defaults
    frappe.db.set_single_value("System Settings", "date_format", "dd/mm/yyyy")
    frappe.db.set_single_value("System Settings", "time_format", "HH:mm:ss")
    frappe.db.set_single_value("System Settings", "number_format", "#.###")
    frappe.db.set_single_value("System Settings", "currency_precision", "0")
    frappe.db.set_single_value("System Settings", "language", "vi")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def load_provinces() -> None:
    """Load 63 Vietnamese provinces/cities into VN Province DocType."""
    fixture_path = os.path.join(
        os.path.dirname(__file__), "..", "fixtures", "provinces.json"
    )
    if not os.path.exists(fixture_path):
        return

    with open(fixture_path, "r", encoding="utf-8") as f:
        provinces = json.load(f)

    for p in provinces:
        if frappe.db.exists("VN Province", p["province_name"]):
            continue
        frappe.get_doc(
            {
                "doctype": "VN Province",
                "province_name": p["province_name"],
                "province_code": p["province_code"],
                "wage_region": p["wage_region"],
                "tax_authority_code": p.get("tax_authority_code", ""),
            }
        ).insert(ignore_permissions=True)


def add_address_template() -> None:
    """Add Vietnam address template if not already present."""
    if frappe.db.exists("Address Template", "Vietnam"):
        return

    template = (
        "{{ address_line1 }}\n"
        "{% if address_line2 %}{{ address_line2 }}\n{% endif %}"
        "{% if ward %}{{ ward }}, {% endif %}"
        "{% if district %}{{ district }}\n{% endif %}"
        "{{ city }}, Việt Nam\n"
        "{% if phone %}ĐT: {{ phone }}{% endif %}\n"
        "{% if tax_id %}MST: {{ tax_id }}{% endif %}"
    )

    frappe.get_doc(
        {
            "doctype": "Address Template",
            "country": "Vietnam",
            "template": template,
            "is_default": 1,
        }
    ).insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Custom fields
# ---------------------------------------------------------------------------


def _custom_field_definitions() -> dict:
    """Return the custom-field spec keyed by DocType."""
    return {
        "Address": [
            {
                "fieldname": "ward",
                "label": "Phường/Xã",
                "fieldtype": "Data",
                "insert_after": "address_line2",
                "translatable": 0,
                "module": "ERPNext Vietnam",
            },
            {
                "fieldname": "district",
                "label": "Quận/Huyện",
                "fieldtype": "Data",
                "insert_after": "ward",
                "translatable": 0,
                "module": "ERPNext Vietnam",
            },
        ],
        "Company": [
            {
                "fieldname": "vn_chart_of_accounts_type",
                "label": "Hệ thống tài khoản",
                "fieldtype": "Select",
                "options": "\nThông tư 99\nThông tư 200\nThông tư 133",
                "default": "Thông tư 99",
                "insert_after": "default_currency",
                "description": "TT99/2025/TT-BTC có hiệu lực từ 01/01/2026, thay thế TT200. TT133 áp dụng cho DN siêu nhỏ/nhỏ.",
                "module": "ERPNext Vietnam",
            },
        ],
        "Employee": [
            {
                "fieldname": "vn_tax_section",
                "label": "Thông tin thuế Việt Nam",
                "fieldtype": "Section Break",
                "insert_after": "ctc",
                "module": "ERPNext Vietnam",
            },
            {
                "fieldname": "vn_tax_code",
                "label": "Mã số thuế cá nhân",
                "fieldtype": "Data",
                "insert_after": "vn_tax_section",
                "module": "ERPNext Vietnam",
            },
            {
                "fieldname": "vn_number_of_dependents",
                "label": "Số người phụ thuộc",
                "fieldtype": "Int",
                "insert_after": "vn_tax_code",
                "default": "0",
                "module": "ERPNext Vietnam",
            },
            {
                "fieldname": "vn_insurance_salary",
                "label": "Mức lương đóng BH",
                "fieldtype": "Currency",
                "insert_after": "vn_number_of_dependents",
                "description": "Mức lương làm căn cứ đóng BHXH/BHYT/BHTN",
                "module": "ERPNext Vietnam",
            },
            {
                "fieldname": "vn_col_break_tax",
                "fieldtype": "Column Break",
                "insert_after": "vn_insurance_salary",
                "module": "ERPNext Vietnam",
            },
            {
                "fieldname": "vn_contract_type",
                "label": "Loại hợp đồng lao động",
                "fieldtype": "Select",
                "options": (
                    "\nThử việc\nXác định thời hạn\n"
                    "Không xác định thời hạn\nThời vụ"
                ),
                "insert_after": "vn_col_break_tax",
                "module": "ERPNext Vietnam",
            },
            {
                "fieldname": "vn_province",
                "label": "Tỉnh/Thành phố làm việc",
                "fieldtype": "Link",
                "options": "VN Province",
                "insert_after": "vn_contract_type",
                "description": "Dùng để xác định vùng lương tối thiểu",
                "module": "ERPNext Vietnam",
            },
        ],
        "Salary Slip": [
            {
                "fieldname": "vn_insurance_employee",
                "label": "Tổng BH NLĐ đóng",
                "fieldtype": "Currency",
                "insert_after": "total_deduction",
                "read_only": 1,
                "module": "ERPNext Vietnam",
            },
            {
                "fieldname": "vn_pit_amount",
                "label": "Thuế TNCN",
                "fieldtype": "Currency",
                "insert_after": "vn_insurance_employee",
                "read_only": 1,
                "module": "ERPNext Vietnam",
            },
            {
                "fieldname": "vn_taxable_income",
                "label": "Thu nhập tính thuế",
                "fieldtype": "Currency",
                "insert_after": "vn_pit_amount",
                "read_only": 1,
                "module": "ERPNext Vietnam",
            },
        ],
        "Sales Invoice": [
            {
                "fieldname": "vn_einvoice_section",
                "label": "Hóa đơn điện tử",
                "fieldtype": "Section Break",
                "insert_after": "amended_from",
                "collapsible": 1,
                "module": "ERPNext Vietnam",
            },
            {
                "fieldname": "vn_einvoice_status",
                "label": "Trạng thái HĐĐT",
                "fieldtype": "Select",
                "options": (
                    "\nChưa phát hành\nĐã phát hành\nĐã hủy\n"
                    "Đã thay thế\nĐã điều chỉnh"
                ),
                "insert_after": "vn_einvoice_section",
                "read_only": 1,
                "no_copy": 1,
                "module": "ERPNext Vietnam",
            },
            {
                "fieldname": "vn_einvoice_number",
                "label": "Số hóa đơn",
                "fieldtype": "Data",
                "insert_after": "vn_einvoice_status",
                "read_only": 1,
                "no_copy": 1,
                "module": "ERPNext Vietnam",
            },
            {
                "fieldname": "vn_einvoice_col",
                "fieldtype": "Column Break",
                "insert_after": "vn_einvoice_number",
                "module": "ERPNext Vietnam",
            },
            {
                "fieldname": "vn_einvoice_lookup_code",
                "label": "Mã tra cứu",
                "fieldtype": "Data",
                "insert_after": "vn_einvoice_col",
                "read_only": 1,
                "no_copy": 1,
                "module": "ERPNext Vietnam",
            },
            {
                "fieldname": "vn_einvoice_date",
                "label": "Ngày hóa đơn",
                "fieldtype": "Date",
                "insert_after": "vn_einvoice_lookup_code",
                "read_only": 1,
                "no_copy": 1,
                "module": "ERPNext Vietnam",
            },
        ],
    }


def add_custom_fields() -> None:
    """Install Vietnam-specific custom fields on core DocTypes."""
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    # Verify Frappe/ERPNext version compatibility
    import frappe
    try:
        from packaging import version as pkg_version
        frappe_ver = pkg_version.parse(frappe.__version__)
        if frappe_ver < pkg_version.parse("15.0"):
            frappe.log_error(
                title="ERPNext Vietnam Version Incompatibility",
                message="ERPNext Vietnam requires Frappe v15.0 or later. "
                        f"Current version: {frappe.__version__}"
            )
            return
    except Exception:
        # If version check fails, log but continue anyway
        pass

    create_custom_fields(_custom_field_definitions(), update=True)


def delete_custom_fields() -> None:
    """Remove Vietnam custom fields on uninstall."""
    for dt, fields in _custom_field_definitions().items():
        for field_def in fields:
            fieldname = field_def["fieldname"]
            name = frappe.db.get_value(
                "Custom Field", {"dt": dt, "fieldname": fieldname}
            )
            if name:
                frappe.delete_doc("Custom Field", name, ignore_permissions=True)
