# Isi Sales YTD History dari angka file "SALES X-SHA GROUP_YTD_ 2026" (2019 s/d
# Sept 2026), lihat custom_reports/sales_ytd.py. Idempoten (baris yg sudah ada dilewati).
from custom_reports.sales_ytd import import_history


def execute():
    import_history()
