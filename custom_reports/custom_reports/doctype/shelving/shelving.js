frappe.ui.form.on("Shelving", {
    setup(frm) {
        frm.set_query("warehouse", () => ({ filters: { use_shelving: 1, is_group: 0 } }));
    },

    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__("Lihat Stok"), () => {
            frappe.set_route("query-report", "Stok per Shelving", { shelving: frm.doc.name });
        });
        frm.add_custom_button(__("Put-away ke Shelving Ini"), () => {
            frappe.new_doc("Shelving Transfer", {
                transfer_type: "Put-away",
                warehouse: frm.doc.warehouse,
                items: [{ to_shelving: frm.doc.name }],
            });
        });
    },
});
