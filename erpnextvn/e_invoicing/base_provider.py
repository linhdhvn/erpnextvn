"""Abstract base class for Vietnamese e-invoice provider integrations.

All five providers (Viettel, VNPT, MISA, FPT, BKAV) subclass
``BaseEInvoiceProvider`` and implement the common lifecycle:

1. ``authenticate()`` — obtain an access token / session.
2. ``create_draft(invoice_data)`` — create the draft invoice on the
   provider's system.
3. ``sign_and_send(draft_id)`` — sign with digital certificate and
   submit to the tax authority.
4. ``get_status(transaction_id)`` — poll status.
5. ``cancel(invoice_number, reason)`` / ``replace(...)`` — correction flows.
6. ``get_pdf(invoice_number)`` — download the signed PDF.

The base class provides:

- ``map_sales_invoice()`` — provider-neutral mapping from ERPNext Sales
  Invoice to a normalized dict.
- ``create_and_send()`` — template method that orchestrates the full
  flow, writes a ``VN E Invoice Log`` entry, and updates the linked
  Sales Invoice.
"""

from __future__ import annotations

import traceback
from abc import ABC, abstractmethod
from typing import Any

import frappe


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EInvoiceError(Exception):
    """Base exception for e-invoice operations."""


class EInvoiceAuthError(EInvoiceError):
    """Raised when provider authentication fails."""


class EInvoiceSendError(EInvoiceError):
    """Raised when sending an invoice to the provider fails."""


# ---------------------------------------------------------------------------
# Base provider
# ---------------------------------------------------------------------------


class BaseEInvoiceProvider(ABC):
    """Abstract contract implemented by every Vietnamese HĐĐT integration."""

    #: Human-readable provider name (overridden by subclasses).
    provider_name: str = "Base"

    #: Default API base URL (production) — subclasses set this.
    production_url: str = ""

    #: Default API base URL (sandbox) — subclasses set this.
    sandbox_url: str = ""

    def __init__(self) -> None:
        self.settings = frappe.get_doc("VN E Invoice Settings")
        self.sandbox = bool(self.settings.sandbox_mode)
        self.api_url = self.settings.api_url or (
            self.sandbox_url if self.sandbox else self.production_url
        )
        self._token: str | None = None

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def authenticate(self) -> str:
        """Authenticate and return an access token string.

        Raises:
            EInvoiceAuthError: on authentication failure.
        """

    @abstractmethod
    def create_draft(self, invoice_data: dict) -> dict:
        """Create a draft on the provider and return ``{"draft_id", "status"}``."""

    @abstractmethod
    def sign_and_send(self, draft_id: str) -> dict:
        """Sign + publish. Returns ``{invoice_number, lookup_code,
        invoice_date, transaction_id}``."""

    @abstractmethod
    def get_status(self, transaction_id: str) -> dict:
        """Poll status. Returns ``{status: 'accepted'|'rejected'|'pending',
        message}``."""

    @abstractmethod
    def cancel(self, invoice_number: str, reason: str) -> dict:
        """Cancel a published invoice."""

    @abstractmethod
    def replace(self, old_invoice_number: str, new_invoice_data: dict) -> dict:
        """Replace an invoice with a corrected one."""

    @abstractmethod
    def get_pdf(self, invoice_number: str) -> bytes:
        """Download the signed PDF."""

    # ------------------------------------------------------------------
    # Mapping — shared across providers
    # ------------------------------------------------------------------

    def map_sales_invoice(self, sales_invoice_name: str) -> dict:
        """Convert an ERPNext Sales Invoice into a provider-neutral dict.

        Subclasses may override ``_to_provider_payload()`` to adapt this
        structure to their specific schema.
        """
        si = frappe.get_doc("Sales Invoice", sales_invoice_name)
        company = frappe.get_doc("Company", si.company)

        customer_tax_id = si.tax_id or ""
        customer = None
        try:
            customer = frappe.get_doc("Customer", si.customer)
        except frappe.DoesNotExistError:
            # Customer doesn't exist, proceed with None
            pass
        except Exception as e:
            frappe.log_error(f"Unexpected error loading Customer {si.customer}: {e}")
            pass

        items: list[dict] = []
        for item in si.items:
            tax_rate = self._item_tax_rate(si, item)
            items.append(
                {
                    "item_name": item.item_name,
                    "description": item.description or item.item_name,
                    "uom": item.uom,
                    "qty": item.qty,
                    "rate": item.rate,
                    "amount": item.amount,
                    "tax_rate": tax_rate,
                    "tax_amount": round(item.amount * tax_rate / 100),
                }
            )

        return {
            "seller": {
                "name": company.company_name,
                "tax_code": company.tax_id or "",
                "address": self._company_address(si),
                "phone": company.phone_no or "",
                "email": company.email or "",
            },
            "buyer": {
                "name": (customer.customer_name if customer else si.customer_name) or "",
                "tax_code": customer_tax_id,
                "address": si.address_display or "",
                "email": si.contact_email or "",
            },
            "invoice": {
                "date": str(si.posting_date),
                "currency": si.currency,
                "exchange_rate": si.conversion_rate or 1,
                "items": items,
                "total_before_tax": si.net_total,
                "total_tax": si.total_taxes_and_charges or 0,
                "grand_total": si.grand_total,
                "payment_method": si.mode_of_payment or "",
            },
            "erp_reference": {
                "sales_invoice": si.name,
                "posting_date": str(si.posting_date),
            },
        }

    def _item_tax_rate(self, si, item) -> float:
        """Best-effort item VAT rate extraction."""
        for tax in si.taxes or []:
            desc = (tax.description or "").upper()
            if "VAT" in desc or "GTGT" in desc:
                return float(tax.rate or 0)
        return 0.0

    def _company_address(self, si) -> str:
        """Assemble a Vietnamese-style address string for the seller."""
        if not si.company_address:
            return ""
        addr = frappe.get_doc("Address", si.company_address)
        parts = [
            addr.get("address_line1") or "",
            addr.get("address_line2") or "",
            addr.get("ward") or "",
            addr.get("district") or "",
            addr.get("city") or "",
        ]
        return ", ".join(p for p in parts if p)

    # ------------------------------------------------------------------
    # Template method — full workflow
    # ------------------------------------------------------------------

    def create_and_send(self, sales_invoice_name: str) -> dict:
        """End-to-end publishing flow.

        Authenticates, maps, creates draft, signs, sends, logs, and
        updates the Sales Invoice custom fields.
        """
        self.authenticate()
        invoice_data = self.map_sales_invoice(sales_invoice_name)

        try:
            draft = self.create_draft(invoice_data)
            result = self.sign_and_send(draft.get("draft_id", ""))
        except EInvoiceError:
            self._log_failure(sales_invoice_name, "Rejected")
            raise

        self._log_success(sales_invoice_name, result)

        # Update using doc.save() instead of frappe.db.set_value()
        doc = frappe.get_doc("Sales Invoice", sales_invoice_name)
        doc.vn_einvoice_status = "Đã phát hành"
        doc.vn_einvoice_number = result.get("invoice_number", "")
        doc.vn_einvoice_lookup_code = result.get("lookup_code", "")
        doc.vn_einvoice_date = result.get("invoice_date", "")
        doc.save(ignore_permissions=True)
        return result

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _log_success(self, sales_invoice_name: str, result: dict[str, Any]) -> None:
        frappe.get_doc(
            {
                "doctype": "VN E Invoice Log",
                "sales_invoice": sales_invoice_name,
                "provider": self.provider_name,
                "status": "Accepted",
                "invoice_number": result.get("invoice_number", ""),
                "invoice_date": result.get("invoice_date") or None,
                "transaction_id": result.get("transaction_id", ""),
                "lookup_code": result.get("lookup_code", ""),
            }
        ).insert(ignore_permissions=True)

    def _log_failure(self, sales_invoice_name: str, status: str) -> None:
        frappe.get_doc(
            {
                "doctype": "VN E Invoice Log",
                "sales_invoice": sales_invoice_name,
                "provider": self.provider_name,
                "status": status,
                "error_message": traceback.format_exc(),
            }
        ).insert(ignore_permissions=True)
