// Copyright (c) 2026, Galaxy Labs and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Employment Application", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on("Employment Application", {
  refresh(frm) {
    if (!frm.is_new() && !frm.doc.employee) {
      frm.add_custom_button("Create Employee", () => {
        frappe.call({
          method: "tms.transport_management_system.doctype.employment_application.employment_application.create_employee_from_application",
          args: { application_name: frm.doc.name },
          freeze: true,
          callback(r) {
            if (r.message) {
              frm.set_value("employee", r.message);
              frm.save().then(() => {
                frappe.msgprint("Employee created: " + r.message);
                frappe.set_route("Form", "Employee", r.message);
              });
            }
          }
        });
      });
    }

    if (frm.doc.employee) {
      frm.add_custom_button("Open Employee", () => {
        frappe.set_route("Form", "Employee", frm.doc.employee);
      });
    }
  }
});
