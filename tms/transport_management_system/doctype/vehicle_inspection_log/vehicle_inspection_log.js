// Copyright (c) 2026, Galaxy Labs and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Vehicle Inspection Log", {
// 	refresh(frm) {

// 	},
// });
// PROOF this file is loaded:
console.log("[VIL] JS LOADED");

function has_real_rows(frm) {
  const rows = frm.doc.items || [];
  return rows.some((r) => (r.item_en || "").trim()); // only count rows that have item_en
}

frappe.ui.form.on("Vehicle Inspection Log", {
  onload(frm) {
    console.log("[VIL] onload fired", frm.is_new());
    setTimeout(() => frm.trigger("prefill_checklist"), 300);
  },

  refresh(frm) {
    console.log("[VIL] refresh fired", frm.is_new(), (frm.doc.items || []).length);

    // if new and not really filled, try again
    if (frm.is_new() && !has_real_rows(frm)) {
      setTimeout(() => frm.trigger("prefill_checklist"), 300);
    } else {
      frm.trigger("lock_grid");
    }
  },

  prefill_checklist(frm) {
    if (!frm.is_new()) return;

    // ✅ skip ONLY if there are real filled rows
    if (has_real_rows(frm)) {
      frm.trigger("lock_grid");
      return;
    }

    console.log("[VIL] prefill starting...");

    frappe
      .call({
        method:
          "tms.transport_management_system.doctype.vehicle_inspection_log.vehicle_inspection_log.get_checklist_rows",
      })
      .then((r) => {
        const rows = r.message || [];
        console.log("[VIL] rows fetched:", rows.length);
        if (!rows.length) return;

        // clear whatever blank row exists
        frm.clear_table("items");

        rows.forEach((d) => {
          const row = frm.add_child("items");
          row.section = d.section || "";
          row.item_en = d.item_en;
          row.category = d.category || "";
          row.item = d.item || "";
          row.sort_order = d.sort_order || 0;
          row.status = d.status || "Sound | سليم";
        });

        frm.refresh_field("items");
        console.log("[VIL] rows rendered:", (frm.doc.items || []).length);

        frm.trigger("lock_grid");
      })
      .catch((e) => console.error("[VIL] prefill error:", e));
  },

  lock_grid(frm) {
    const grid = frm.fields_dict.items?.grid;
    if (!grid) return;

    grid.cannot_add_rows = true;
    grid.cannot_delete_rows = true;

    grid.toggle_enable("status", true);
    ["section", "item_en", "category", "item", "notes", "sort_order"].forEach((f) => {
      grid.toggle_enable(f, false);
    });

    frm.refresh_field("items");
  },
});