"""Frappe app hooks for erpnextvn (ERPNext Vietnam Localization).

This module registers all integration points with Frappe/ERPNext:
- Lifecycle hooks (after_install, before_uninstall)
- DocType event subscriptions (Sales Invoice, Salary Slip)
- Setup Wizard stages for Vietnam country
- Fixtures, Jinja helpers, regional overrides
- Scheduler tasks, client scripts
"""

app_name = "erpnextvn"
app_title = "ERPNext Vietnam"
app_publisher = "1nguoi.com"
app_description = (
    "Vietnamese Localization for ERPNext v16 — "
    "Accounting, Tax, E-Invoicing, Payroll, Translation"
)
app_email = "hello@1nguoi.com"
app_license = "GPL-3.0"
app_icon = "octicon octicon-globe"
app_color = "#DA251D"  # Vietnamese flag red

required_apps = ["frappe", "erpnext", "hrms"]

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

after_install = "erpnextvn.erpnext_vietnam.setup.after_install"
before_uninstall = "erpnextvn.erpnext_vietnam.setup.before_uninstall"

# ---------------------------------------------------------------------------
# Setup Wizard
# ---------------------------------------------------------------------------

setup_wizard_requires = "assets/erpnextvn/js/setup_wizard.js"
setup_wizard_stages = "erpnextvn.erpnext_vietnam.setup.get_setup_stages"

# ---------------------------------------------------------------------------
# DocType Events
# ---------------------------------------------------------------------------

doc_events = {
    "Sales Invoice": {
        "on_submit": "erpnextvn.e_invoicing.utils.on_sales_invoice_submit",
        "on_cancel": "erpnextvn.e_invoicing.utils.on_sales_invoice_cancel",
    },
    "Salary Slip": {
        "validate": "erpnextvn.payroll.utils.validate_salary_slip",
    },
}

# ---------------------------------------------------------------------------
# Fixtures — exported via `bench export-fixtures` for this module
# ---------------------------------------------------------------------------

fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["module", "=", "ERPNext Vietnam"]],
    },
    {
        "dt": "Property Setter",
        "filters": [["module", "=", "ERPNext Vietnam"]],
    },
]

# ---------------------------------------------------------------------------
# Jinja template helpers (available in Print Formats)
# ---------------------------------------------------------------------------

jinja = {
    "methods": [
        "erpnextvn.payroll.utils.so_tien_bang_chu",
        "erpnextvn.payroll.utils.format_vnd",
    ],
}

# ---------------------------------------------------------------------------
# Regional overrides — replace ERPNext defaults when country == "Vietnam"
# ---------------------------------------------------------------------------

regional_overrides = {
    "Vietnam": {
        "erpnext.controllers.taxes_and_totals.get_regional_round_off_accounts": (
            "erpnextvn.accounting.tax_templates.get_round_off_accounts"
        ),
    },
}

# ---------------------------------------------------------------------------
# Override ERPNext's CoA discovery to include TT99/TT200/TT133
# ---------------------------------------------------------------------------

override_whitelisted_methods = {
    "erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts.get_charts_for_country": (
        "erpnextvn.accounting.chart_of_accounts.get_charts_for_country"
    ),
}

# Apply CoA monkey-patch on every request and every session boot.
# `before_request` runs in every worker process before the request handler,
# guaranteeing the patch is applied before Company.on_update fires.
before_request = ["erpnextvn.accounting.chart_of_accounts.ensure_patched"]
boot_session = "erpnextvn.accounting.chart_of_accounts.ensure_patched"

# ---------------------------------------------------------------------------
# Website / URL rules
# ---------------------------------------------------------------------------

website_route_rules = []

# ---------------------------------------------------------------------------
# Scheduler — polls pending e-invoices hourly
# ---------------------------------------------------------------------------

scheduler_events = {
    "hourly": [
        "erpnextvn.e_invoicing.utils.poll_pending_invoices",
    ],
}

# ---------------------------------------------------------------------------
# Client scripts
# ---------------------------------------------------------------------------

doctype_js = {
    "Sales Invoice": "public/js/vn_einvoice.js",
}

# ---------------------------------------------------------------------------
# Global assets
# ---------------------------------------------------------------------------

app_include_css = ["/assets/erpnextvn/css/vn_print.css"]
app_include_js = []

# Optional overrides
override_doctype_class = {}
