import frappe
from frappe import _
from frappe.utils import flt
from erpnext.accounts.report.financial_statements import (
    get_period_list,
    get_data,
    get_columns,
)


def execute(filters=None):
    if not filters:
        filters = {}

    # ===== Setup periode =====
    period_list = get_period_list(
        filters.get("from_fiscal_year"),
        filters.get("to_fiscal_year"),
        filters.get("period_start_date"),
        filters.get("period_end_date"),
        filters.get("filter_based_on"),
        filters.get("periodicity", "Yearly"),
        company=filters.get("company"),
    )

    currency = filters.get("presentation_currency") or frappe.get_cached_value(
        "Company", filters.get("company"), "default_currency"
    )

    # ===== 1. Tarik data Income & Expense =====
    income = get_data(
        filters.get("company"),
        "Income",
        "Credit",
        period_list,
        filters=filters,
        accumulated_values=filters.get("accumulated_values"),
        ignore_closing_entries=True,
        ignore_accumulated_values_for_fy=True,
    )

    expense = get_data(
        filters.get("company"),
        "Expense",
        "Debit",
        period_list,
        filters=filters,
        accumulated_values=filters.get("accumulated_values"),
        ignore_closing_entries=True,
        ignore_accumulated_values_for_fy=True,
    )

    # ===== 2. Helper: cek valid data row (skip Total Row & separator) =====
    def is_valid_row(row):
        """Skip baris yang bukan account asli (Total Row, separator, empty)"""
        if not row:
            return False
        # Total Row dari get_data: is_group=None, indent=None
        if row.get("is_group") is None:
            return False
        if row.get("indent") is None:
            return False
        return True

    # ===== 3. Pisahkan akun berdasarkan kode akun =====
    operating_income = []
    other_income = []
    cogs = []
    operating_expense = []

    for row in income:
        if not is_valid_row(row):
            continue
        acc = (row.get("account") or "")
        acc_name = (row.get("account_name") or "").upper()
        if "7-" in acc or "LAIN" in acc_name or "OTHER" in acc_name:
            other_income.append(row)
        else:
            operating_income.append(row)

    for row in expense:
        if not is_valid_row(row):
            continue
        acc = (row.get("account") or "")
        acc_name = (row.get("account_name") or "").upper()
        acc_type = (row.get("account_type") or "")
        if "5-" in acc or "HPP" in acc_name or acc_type == "Cost of Goods Sold":
            cogs.append(row)
        else:
            operating_expense.append(row)

    # ===== 4. Hitung total: ambil dari ROOT GROUP (indent=0) =====
    # Karena ERPNext sudah accumulate values ke parent (group account),
    # nilai di indent=0 sudah merupakan total semua child-nya.
    def total_from_roots(rows, period_list):
        totals = {}
        for p in period_list:
            totals[p.key] = 0.0
        totals["total"] = 0.0
        for row in rows:
            # Hanya ambil baris dengan indent=0 (root group accounts)
            if flt(row.get("indent")) != 0:
                continue
            for p in period_list:
                current = totals.get(p.key, 0)
                totals[p.key] = current + flt(row.get(p.key, 0))
            current_total = totals.get("total", 0)
            totals["total"] = current_total + flt(row.get("total", 0))
        return totals

    op_income_total = total_from_roots(operating_income, period_list)
    cogs_total = total_from_roots(cogs, period_list)
    op_expense_total = total_from_roots(operating_expense, period_list)
    other_income_total = total_from_roots(other_income, period_list)

    # ===== Helper functions =====
    def section_header(label, period_list):
        row = {
            "account": label,
            "account_name": label,
            "currency": currency,
            "indent": 0,
            "has_value": False,
        }
        for p in period_list:
            row[p.key] = None
        row["total"] = None
        return row

    def subtotal_row(label, totals, period_list):
        row = {
            "account": label,
            "account_name": label,
            "currency": currency,
            "indent": 0.5,
            "has_value": True,
        }
        for p in period_list:
            row[p.key] = totals.get(p.key, 0)
        row["total"] = totals.get("total", 0)
        return row

    def total_row(label, totals, period_list):
        row = {
            "account": label,
            "account_name": label,
            "currency": currency,
            "indent": 0,
            "has_value": True,
        }
        for p in period_list:
            row[p.key] = totals.get(p.key, 0)
        row["total"] = totals.get("total", 0)
        return row

    def blank_row(period_list):
        row = {
            "account": "",
            "account_name": "",
            "currency": currency,
            "indent": 0,
            "has_value": False,
        }
        for p in period_list:
            row[p.key] = None
        row["total"] = None
        return row

    def calc_diff(a, b, period_list):
        result = {}
        for p in period_list:
            result[p.key] = flt(a.get(p.key, 0)) - flt(b.get(p.key, 0))
        result["total"] = flt(a.get("total", 0)) - flt(b.get("total", 0))
        return result

    def calc_sum(a, b, period_list):
        result = {}
        for p in period_list:
            result[p.key] = flt(a.get(p.key, 0)) + flt(b.get(p.key, 0))
        result["total"] = flt(a.get("total", 0)) + flt(b.get("total", 0))
        return result

    # ===== 5. Susun output rows =====
    data = []

    data.append(section_header("PENDAPATAN USAHA", period_list))
    for r in operating_income:
        data.append(r)
    data.append(subtotal_row("Total Pendapatan Usaha", op_income_total, period_list))
    data.append(blank_row(period_list))

    data.append(section_header("HARGA POKOK PENJUALAN", period_list))
    for r in cogs:
        data.append(r)
    data.append(subtotal_row("Total HPP", cogs_total, period_list))
    data.append(blank_row(period_list))

    gross_profit = calc_diff(op_income_total, cogs_total, period_list)
    data.append(total_row("GROSS PROFIT (LABA KOTOR)", gross_profit, period_list))
    data.append(blank_row(period_list))

    data.append(section_header("BEBAN OPERASIONAL", period_list))
    for r in operating_expense:
        data.append(r)
    data.append(subtotal_row("Total Beban Operasional", op_expense_total, period_list))
    data.append(blank_row(period_list))

    op_profit = calc_diff(gross_profit, op_expense_total, period_list)
    data.append(total_row("OPERATING PROFIT (LABA USAHA)", op_profit, period_list))
    data.append(blank_row(period_list))

    if other_income:
        data.append(section_header("PENDAPATAN LAIN-LAIN", period_list))
        for r in other_income:
            data.append(r)
        data.append(subtotal_row("Total Pendapatan Lain-Lain", other_income_total, period_list))
        data.append(blank_row(period_list))

    net_profit = calc_sum(op_profit, other_income_total, period_list)
    data.append(total_row("NET PROFIT (LABA BERSIH)", net_profit, period_list))

    # ===== 6. Columns =====
    columns = get_columns("Profit and Loss", period_list, company=filters.get("company"))

    # ===== 7. Chart =====
    labels = []
    for p in period_list:
        labels.append(p.label)

    op_income_values = []
    gross_profit_values = []
    op_profit_values = []
    net_profit_values = []
    for p in period_list:
        op_income_values.append(op_income_total.get(p.key, 0))
        gross_profit_values.append(gross_profit.get(p.key, 0))
        op_profit_values.append(op_profit.get(p.key, 0))
        net_profit_values.append(net_profit.get(p.key, 0))

    chart = {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Pendapatan Usaha", "values": op_income_values},
                {"name": "Gross Profit", "values": gross_profit_values},
                {"name": "Operating Profit", "values": op_profit_values},
                {"name": "Net Profit", "values": net_profit_values},
            ],
        },
        "type": "bar",
        "fieldtype": "Currency",
        "options": {"currency": currency},
    }

    # ===== 8. Summary cards =====
    op_income_val = op_income_total.get("total", 0)
    gp_val = gross_profit.get("total", 0)
    op_val = op_profit.get("total", 0)
    net_val = net_profit.get("total", 0)

    if op_income_val:
        gp_margin = gp_val / op_income_val * 100
        op_margin = op_val / op_income_val * 100
        net_margin = net_val / op_income_val * 100
    else:
        gp_margin = 0
        op_margin = 0
        net_margin = 0

    report_summary = [
        {
            "value": op_income_val,
            "label": "Pendapatan Usaha",
            "datatype": "Currency",
            "currency": currency,
        },
        {
            "value": gp_val,
            "label": "Gross Profit ({0:.1f}%)".format(gp_margin),
            "indicator": "Green" if gp_val >= 0 else "Red",
            "datatype": "Currency",
            "currency": currency,
        },
        {
            "value": op_val,
            "label": "Operating Profit ({0:.1f}%)".format(op_margin),
            "indicator": "Green" if op_val >= 0 else "Red",
            "datatype": "Currency",
            "currency": currency,
        },
        {
            "value": net_val,
            "label": "Net Profit ({0:.1f}%)".format(net_margin),
            "indicator": "Green" if net_val >= 0 else "Red",
            "datatype": "Currency",
            "currency": currency,
        },
    ]

    return columns, data, None, chart, report_summary
