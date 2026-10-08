// Shelving di Stock Entry: Ke Shelving wajib bila warehouse tujuan memakai shelving
// (validasi server: shelving/ledger.py)
frappe.ui.form.on("Stock Entry", {
    setup(frm) {
        const by_row_warehouse = (field) => (doc, cdt, cdn) => {
            const row = locals[cdt][cdn];
            return { filters: { warehouse: row[field] || "", disabled: 0 } };
        };
        frm.set_query("from_shelving", "items", by_row_warehouse("s_warehouse"));
        frm.set_query("to_shelving", "items", by_row_warehouse("t_warehouse"));
    },
});

frappe.ui.form.on("Stock Entry Detail", {
    s_warehouse(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, "from_shelving", null);
    },
    t_warehouse(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, "to_shelving", null);
    },
});
