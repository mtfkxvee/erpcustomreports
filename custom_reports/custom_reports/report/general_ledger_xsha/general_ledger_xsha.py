import copy
import frappe
from frappe import _, _dict
from frappe.utils import getdate
from erpnext.accounts.report.general_ledger.general_ledger import (
    execute as original_execute,
    get_gl_entries,
    get_columns,
    validate_filters,
    validate_party,
    set_account_currency,
    get_data_with_opening_closing,
    get_totals_dict,
    initialize_gle_map,
    group_by_field,
    get_account_type_map,
    get_accountwise_gle,
    set_bill_no,
)
from collections import OrderedDict
from frappe.utils import cstr


# Account types yang dianggap P&L (tidak punya opening balance)
PNL_ACCOUNT_TYPES = {
    "Income Account",
    "Expense Account",
    "Cost of Goods Sold",
    "Tax",
    "Chargeable",
    "Stock Adjustment",
    "Direct Expense",
    "Indirect Expense",
    "Direct Income",
    "Indirect Income",
}


def execute(filters=None):
    if not filters:
        return [], []

    account_details = {}
    for acc in frappe.db.sql("SELECT name, is_group, account_type, root_type FROM tabAccount", as_dict=1):
        account_details.setdefault(acc.name, acc)

    if filters.get("party"):
        filters.party = frappe.parse_json(filters.get("party"))

    validate_filters(filters, account_details)
    validate_party(filters)
    filters = set_account_currency(filters)

    columns = get_columns(filters)

    # Ambil accounting dimensions
    from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions
    accounting_dimensions = get_accounting_dimensions()

    gl_entries = get_gl_entries(filters, accounting_dimensions)

    # Identifikasi akun P&L
    pnl_accounts = set()
    for acc_name, acc in account_details.items():
        if acc.get("root_type") in ("Income", "Expense") or acc.get("account_type") in PNL_ACCOUNT_TYPES:
            pnl_accounts.add(acc_name)

    # Build data dengan custom opening logic
    res = get_data_with_opening_closing_xsha(filters, account_details, accounting_dimensions, gl_entries, pnl_accounts)

    return columns, res


def get_data_with_opening_closing_xsha(filters, account_details, accounting_dimensions, gl_entries, pnl_accounts):
    data = []
    totals_dict = get_totals_dict()
    set_bill_no(gl_entries)
    gle_map = initialize_gle_map(gl_entries, filters, totals_dict)

    totals, entries = get_accountwise_gle_xsha(filters, accounting_dimensions, gl_entries, gle_map, totals_dict, pnl_accounts)

    data.append(totals.opening)

    if filters.get("categorize_by") != "Categorize by Voucher (Consolidated)":
        for _acc, acc_dict in gle_map.items():
            if acc_dict.entries:
                data.append({"debit_in_transaction_currency": None, "credit_in_transaction_currency": None})
                if (not filters.get("categorize_by") and not filters.get("voucher_no")) or (
                    filters.get("categorize_by") and filters.get("categorize_by") != "Categorize by Voucher"
                ):
                    data.append(acc_dict.totals.opening)
                data += acc_dict.entries
                if filters.get("categorize_by") or not filters.voucher_no:
                    data.append(acc_dict.totals.total)
                if (not filters.get("categorize_by") and not filters.get("voucher_no")) or (
                    filters.get("categorize_by") and filters.get("categorize_by") != "Categorize by Voucher"
                ):
                    data.append(acc_dict.totals.closing)
        data.append({"debit_in_transaction_currency": None, "credit_in_transaction_currency": None})
    else:
        data += entries

    data.append(totals.total)
    data.append(totals.closing)
    return data


def get_accountwise_gle_xsha(filters, accounting_dimensions, gl_entries, gle_map, totals, pnl_accounts):
    entries = []
    consolidated_gle = OrderedDict()
    group_by = group_by_field(filters.get("categorize_by"))
    group_by_voucher_consolidated = filters.get("categorize_by") == "Categorize by Voucher (Consolidated)"

    immutable_ledger = frappe.db.get_single_value("Accounts Settings", "enable_immutable_ledger")

    def update_value_in_dict(data, key, gle, show_net_values=False):
        data[key].debit  += gle.debit
        data[key].credit += gle.credit
        data[key].debit_in_account_currency  += gle.debit_in_account_currency
        data[key].credit_in_account_currency += gle.credit_in_account_currency
        if filters.get("add_values_in_transaction_currency") and key not in ["opening", "closing", "total"]:
            data[key].debit_in_transaction_currency  += gle.debit_in_transaction_currency
            data[key].credit_in_transaction_currency += gle.credit_in_transaction_currency
        if data[key].against_voucher and gle.against_voucher:
            data[key].against_voucher += ", " + gle.against_voucher

    from_date = getdate(filters.from_date)
    to_date   = getdate(filters.to_date)
    show_opening_entries = filters.get("show_opening_entries")

    for gle in gl_entries:
        group_by_value = gle.get(group_by)
        gle.voucher_type = gle.voucher_type

        is_pnl = gle.get("account") in pnl_accounts

        if gle.posting_date < from_date or (cstr(gle.is_opening) == "Yes" and not show_opening_entries):
            # P&L accounts: skip opening balance (set 0)
            if is_pnl:
                continue

            if not group_by_voucher_consolidated:
                update_value_in_dict(gle_map[group_by_value].totals, "opening", gle, True)
                update_value_in_dict(gle_map[group_by_value].totals, "closing", gle, True)

            update_value_in_dict(totals, "opening", gle, True)
            update_value_in_dict(totals, "closing", gle, True)

        elif gle.posting_date <= to_date or (cstr(gle.is_opening) == "Yes" and show_opening_entries):
            if not group_by_voucher_consolidated:
                update_value_in_dict(gle_map[group_by_value].totals, "total", gle)
                update_value_in_dict(gle_map[group_by_value].totals, "closing", gle)
                update_value_in_dict(totals, "total", gle)
                update_value_in_dict(totals, "closing", gle)
                gle_map[group_by_value].entries.append(gle)

            elif group_by_voucher_consolidated:
                keylist = [
                    gle.get("posting_date"), gle.get("voucher_type"), gle.get("voucher_no"),
                    gle.get("account"), gle.get("party_type"), gle.get("party"),
                ]
                if immutable_ledger:
                    keylist.append(gle.get("creation"))
                if filters.get("include_dimensions"):
                    for dim in accounting_dimensions:
                        keylist.append(gle.get(dim))
                    keylist.append(gle.get("cost_center"))
                    keylist.append(gle.get("project"))
                key = tuple(keylist)
                if key not in consolidated_gle:
                    consolidated_gle.setdefault(key, gle)
                else:
                    update_value_in_dict(consolidated_gle, key, gle)

    for value in consolidated_gle.values():
        update_value_in_dict(totals, "total", value)
        update_value_in_dict(totals, "closing", value)
        entries.append(value)

    return totals, entries
