// Shelving di Stock Entry: Ke Shelving wajib bila warehouse tujuan memakai shelving
// (validasi server: shelving/ledger.py)
const shelving_wh_cache = {};

async function uses_shelving(warehouse) {
    if (!warehouse) return false;
    if (!(warehouse in shelving_wh_cache)) {
        const r = await frappe.db.get_value("Warehouse", warehouse, "use_shelving");
        shelving_wh_cache[warehouse] = !!(r.message && r.message.use_shelving);
    }
    return shelving_wh_cache[warehouse];
}

async function mark_required(frm, cdn) {
    const row = locals["Stock Entry Detail"][cdn];
    const grid_row = frm.fields_dict.items.grid.grid_rows_by_docname[cdn];
    if (!row || !grid_row) return;
    grid_row.toggle_reqd("to_shelving", await uses_shelving(row.t_warehouse));
}

frappe.ui.form.on("Stock Entry", {
    setup(frm) {
        const by_row_warehouse = (field) => (doc, cdt, cdn) => {
            const row = locals[cdt][cdn];
            return { filters: { warehouse: row[field] || "", disabled: 0 } };
        };
        frm.set_query("from_shelving", "items", by_row_warehouse("s_warehouse"));
        frm.set_query("to_shelving", "items", by_row_warehouse("t_warehouse"));
    },

    refresh(frm) {
        (frm.doc.items || []).forEach((row) => mark_required(frm, row.name));
    },
});

frappe.ui.form.on("Stock Entry Detail", {
    items_add(frm, cdt, cdn) {
        mark_required(frm, cdn);
    },
    s_warehouse(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, "from_shelving", null);
    },
    t_warehouse(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, "to_shelving", null);
        mark_required(frm, cdn);
    },
});
