const PUTAWAY = "Put-away";
const MOVE = "Pindah Shelving";
const REMOVE = "Keluarkan dari Shelving";

frappe.ui.form.on("Shelving Transfer", {
    setup(frm) {
        const by_warehouse = () => ({ filters: { warehouse: frm.doc.warehouse, disabled: 0 } });
        frm.set_query("from_shelving", "items", by_warehouse);
        frm.set_query("to_shelving", "items", by_warehouse);
    },

    refresh(frm) {
        frm.trigger("toggle_columns");
    },

    transfer_type(frm) {
        frm.trigger("toggle_columns");
    },

    warehouse(frm) {
        // shelving milik warehouse lama tidak valid lagi
        (frm.doc.items || []).forEach((row) => {
            row.from_shelving = null;
            row.to_shelving = null;
        });
        frm.refresh_field("items");
    },

    toggle_columns(frm) {
        const grid = frm.fields_dict.items.grid;
        const type = frm.doc.transfer_type;
        const show_from = type === MOVE || type === REMOVE;
        const show_to = type === PUTAWAY || type === MOVE;
        grid.update_docfield_property("from_shelving", "hidden", show_from ? 0 : 1);
        grid.update_docfield_property("from_shelving", "reqd", show_from ? 1 : 0);
        grid.update_docfield_property("to_shelving", "hidden", show_to ? 0 : 1);
        grid.update_docfield_property("to_shelving", "reqd", show_to ? 1 : 0);
        grid.reset_grid();
    },
});
