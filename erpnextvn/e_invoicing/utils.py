"""E-Invoice dispatcher utilities.

Provides:

- ``get_provider()`` — factory returning the configured provider instance
- ``on_sales_invoice_submit`` / ``on_sales_invoice_cancel`` — doc hooks
- ``poll_pending_invoices`` — hourly scheduler task
- ``send_einvoice`` / ``cancel_einvoice`` — whitelisted endpoints for the
  Sales Invoice "Phát hành HĐĐT" / "Hủy HĐĐT" buttons
"""

from __future__ import annotations

import importlib

import frappe
from frappe import _

from .base_provider import BaseEInvoiceProvider, EInvoiceError

_PROVIDER_MAP = {
    "Viettel": "erpnextvn.e_invoicing.viettel:ViettelProvider",
    "VNPT": "erpnextvn.e_invoicing.vnpt:VNPTProvider",
    "MISA": "erpnextvn.e_invoicing.misa:MISAProvider",
    "FPT": "erpnextvn.e_invoicing.fpt:FPTProvider",
    "BKAV": "erpnextvn.e_invoicing.bkav:BKAVProvider",
}

_PROVIDER_MAP = {
    "Viettel": "erpnextvn.e_invoicing.viettel:ViettelProvider",
    "VNPT": "erpnextvn.e_invoicing.vnpt:VNPTProvider",
    "MISA": "erpnextvn.e_invoicing.misa:MISAProvider",
    "FPT": "erpnextvn.e_invoicing.fpt:FPTProvider",
    "BKAV": "erpnextvn.e_invoicing.bkav:BKAVProvider",
}


def get_provider() -> BaseEInvoiceProvider:
    """Return the configured provider instance.

    Raises:
        frappe.ValidationError: if no provider is configured.
    """
    settings = frappe.get_doc("VN E Invoice Settings")
    path = _PROVIDER_MAP.get(settings.provider)
    if not path:
        frappe.throw(_("Chưa cấu hình nhà cung cấp hóa đơn điện tử"))

    module_path, class_name = path.split(":")
    module = importlib.import_module(module_path)
    provider_cls = getattr(module, class_name)
    return provider_cls()


# ---------------------------------------------------------------------------
# DocType hooks
# ---------------------------------------------------------------------------


def on_sales_invoice_submit(doc, method=None) -> None:
    """Auto-send e-invoice on Sales Invoice submit when configured."""
    settings = frappe.get_doc("VN E Invoice Settings")
    if not settings.provider or not settings.auto_send_on_submit:
        return

    country = frappe.get_cached_value("Company", doc.company, "country")
    if country != "Vietnam":
        return

    try:
        provider = get_provider()
        provider.create_and_send(doc.name)
        frappe.msgprint(_("Đã phát hành hóa đơn điện tử thành công"), indicator="green")
    except EInvoiceError as exc:
        frappe.log_error(title=f"E-Invoice send error for {doc.name}", message=str(exc))
        frappe.msgprint(
            _("Lỗi phát hành HĐĐT: {0}. Bạn có thể phát hành thủ công sau.").format(str(exc)),
            indicator="orange",
        )


def on_sales_invoice_cancel(doc, method=None) -> None:
    """Warn the user when cancelling a Sales Invoice that has a live HĐĐT."""
    if doc.get("vn_einvoice_status") == "Đã phát hành" and doc.get("vn_einvoice_number"):
        frappe.msgprint(
            _(
                "Lưu ý: Hóa đơn điện tử {0} cần được hủy riêng trên hệ thống HĐĐT."
            ).format(doc.vn_einvoice_number),
            indicator="orange",
        )


def poll_pending_invoices() -> None:
    """Hourly scheduler: refresh status of ``Pending`` e-invoice logs."""
    pending = frappe.get_all(
        "VN E Invoice Log",
        filters={"status": "Pending"},
        fields=["name", "transaction_id", "sales_invoice"],
        limit_page_length=50,
    )
    if not pending:
        return

    try:
        provider = get_provider()
    except Exception as exc:
        frappe.log_error(title="E-Invoice poll: no provider", message=str(exc))
        return

    for log in pending:
        try:
            result = provider.get_status(log.transaction_id)
        except Exception as exc:
            frappe.log_error(
                title=f"E-Invoice poll {log.name}", message=str(exc)
            )
            continue

        if result["status"] == "accepted":
            # Update using doc.save() for better consistency
            log_doc = frappe.get_doc("VN E Invoice Log", log.name)
            log_doc.status = "Accepted"
            log_doc.save(ignore_permissions=True)
            
            # Update the Sales Invoice
            si_doc = frappe.get_doc("Sales Invoice", log.sales_invoice)
            si_doc.vn_einvoice_status = "Đã phát hành"
            si_doc.save(ignore_permissions=True)
        elif result["status"] == "rejected":
            log_doc = frappe.get_doc("VN E Invoice Log", log.name)
            log_doc.status = "Rejected"
            log_doc.save(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Whitelisted endpoints for client-side buttons
# ---------------------------------------------------------------------------


@frappe.whitelist()
def send_einvoice(sales_invoice: str) -> dict:
    """Publish the e-invoice for a given Sales Invoice.

    Called from the "Phát hành HĐĐT" button on the Sales Invoice form.
    """
    # Validate document exists
    if not frappe.db.exists("Sales Invoice", sales_invoice):
        frappe.throw(_("Hóa đơn {0} không tồn tại").format(sales_invoice))
    
    # Check permissions
    if not frappe.has_permission("Sales Invoice", "write", doc=sales_invoice):
        frappe.throw(_("Bạn không có quyền phát hành hóa đơn này"))
    
    # Validate it's submitted
    docstatus = frappe.db.get_value("Sales Invoice", sales_invoice, "docstatus")
    if isinstance(docstatus, tuple):
        docstatus = docstatus[0]
    if docstatus != 1:
        frappe.throw(_("Chỉ có thể phát hành hóa đơn đã được xác nhận"))

    provider = get_provider()
    result = provider.create_and_send(sales_invoice)
    return result


@frappe.whitelist()
def cancel_einvoice(sales_invoice: str, reason: str) -> dict:
    """Cancel the published e-invoice for a Sales Invoice."""
    # Validate document exists
    if not frappe.db.exists("Sales Invoice", sales_invoice):
        frappe.throw(_("Hóa đơn {0} không tồn tại").format(sales_invoice))
    
    # Check permissions
    if not frappe.has_permission("Sales Invoice", "write", doc=sales_invoice):
        frappe.throw(_("Bạn không có quyền hủy hóa đơn này"))

    invoice_number = frappe.db.get_value(
        "Sales Invoice", sales_invoice, "vn_einvoice_number"
    )
    # Handle tuple return from frappe.db.get_value()
    if isinstance(invoice_number, tuple):
        invoice_number = invoice_number[0]
    
    if not invoice_number:
        frappe.throw(_("Hóa đơn chưa có số hóa đơn điện tử"))

    provider = get_provider()
    result = provider.cancel(invoice_number, reason)

    # Update using doc.save() for consistency
    doc = frappe.get_doc("Sales Invoice", sales_invoice)
    doc.vn_einvoice_status = "Đã hủy"
    doc.save(ignore_permissions=True)
    
    frappe.get_doc(
        {
            "doctype": "VN E Invoice Log",
            "sales_invoice": sales_invoice,
            "provider": provider.provider_name,
            "status": "Cancelled",
            "invoice_number": invoice_number,
            "error_message": reason,
        }
    ).insert(ignore_permissions=True)
    return result
