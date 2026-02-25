// Copyright (c) 2026, Galaxy Labs and contributors
// For license information, please see license.txt

// frappe.ui.form.on("TMS Settings", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on("TMS Settings", {
  refresh(frm) {
    // Add button in toolbar
    frm.add_custom_button(__("Export Fixtures"), async () => {
      // confirm
      const ok = await frappe.confirm(
        __("This will export fixtures using your hooks.py filters. Continue?"),
      );
      if (!ok) return;

      frm.disable_save();
      frappe.dom.freeze(__("Exporting fixtures..."));

      try {
        const r = await frappe.call({
          method: "tms.utils.fixtures_export.run",
          args: {},
          freeze: false,
        });

        frappe.msgprint({
          title: __("Done"),
          message: __(r.message || "OK: fixtures exported"),
          indicator: "green",
        });
      } catch (e) {
        frappe.msgprint({
          title: __("Export failed"),
          message: __(e.message || e),
          indicator: "red",
        });
      } finally {
        frappe.dom.unfreeze();
        frm.enable_save();
      }
    });
  },
});