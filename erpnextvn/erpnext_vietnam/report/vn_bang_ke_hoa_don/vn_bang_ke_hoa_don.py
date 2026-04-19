"""VN Bảng Kê Hóa Đơn — Invoice Register.

Lists Sales Invoices (or Purchase Invoices) for a period with VAT
breakdown. Supports the ``invoice_type`` filter to switch between
Sales ("Bán ra") and Purchase ("Mua vào").
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _


def execute(filters: dict | None = None) -> tuple[list[dict], list[dict]]:
    filters = filters or {}
    columns = [
        {"label": _("STT"), "fieldname": "idx", "fieldtype": "Int", "width": 60},
        {"label": _("Ngày HĐ"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("Số HĐ"), "fieldname": "invoice_no", "fieldtype": "Data", "width": 160},
        {"label": _("Ký hiệu"), "fieldname": "series_symbol", "fieldtype": "Data", "width": 100},
        {"label": _("Khách hàng / NCC"), "fieldname": "party", "fieldtype": "Data", "width": 220},
        {"label": _("MST"), "fieldname": "tax_id", "fieldtype": "Data", "width": 120},
        {"label": _("Giá trị trước thuế"), "fieldname": "net_total", "fieldtype": "Currency", "width": 140},
        {"label": _("Thuế suất"), "fieldname": "tax_rate", "fieldtype": "Percent", "width": 90},
        {"label": _("Tiền thuế"), "fieldname": "tax_amount", "fieldtype": "Currency", "width": 120},
        {"label": _("Tổng tiền"), "fieldname": "grand_total", "fieldtype": "Currency", "width": 140},
    ]

    invoice_type = filters.get("invoice_type", "Sales")
    doctype = "Sales Invoice" if invoice_type == "Sales" else "Purchase Invoice"
    party_field = "customer_name" if invoice_type == "Sales" else "supplier_name"

    # Build filter conditions using frappe.get_all safe method
    filter_conditions = [["docstatus", "=", 1]]
    if filters.get("company"):
        filter_conditions.append([doctype, "company", "=", filters["company"]])
    if filters.get("from_date"):
        filter_conditions.append([doctype, "posting_date", ">=", filters["from_date"]])
    if filters.get("to_date"):
        filter_conditions.append([doctype, "posting_date", "<=", filters["to_date"]])

    # Use frappe.get_all for safer, more maintainable queries
    field_list = ["name", "posting_date", party_field, "tax_id", "net_total", "grand_total", "total_taxes_and_charges"]
    if invoice_type == "Sales":
        field_list.append("vn_einvoice_number")
    
    rows = frappe.get_all(
        doctype,
        filters=filter_conditions,
        fields=field_list,
        order_by="posting_date, name"
    )

    data: list[dict] = []
    for i, r in enumerate(rows, start=1):
        tax_rate = 0
        if r.get("net_total"):
            tax_rate = round((r.get("total_taxes_and_charges") or 0) / r.net_total * 100, 2)
        data.append({
            "idx": i,
            "posting_date": r.posting_date,
            "invoice_no": r.get("vn_einvoice_number") or r.name,
            "series_symbol": "",
            "party": r.get(party_field) or "",
            "tax_id": r.tax_id or "",
            "net_total": r.net_total or 0,
            "tax_rate": tax_rate,
            "tax_amount": r.get("total_taxes_and_charges") or 0,
            "grand_total": r.grand_total or 0,
        })
    return columns, data
