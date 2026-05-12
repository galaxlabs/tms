// // Copyright (c) 2025, Galaxy Labs and contributors
// // For license information, please see license.txt

// // frappe.ui.form.on("Trip", {
// // 	refresh(frm) {

// // 	},
// // });
// frappe.ui.form.on('Trip', {
//     refresh(frm) {
//         if (!frm.is_new()) {
//             frm.add_custom_button("Send Trip PDF to Driver", () => {
//                 frappe.call({
//                     method: "tms.utils.print_button.send_trip_pdf_to_driver",
//                     args: { trip_name: frm.doc.name },
//                     callback(r) {
//                         if (r.message) {
//                             frappe.msgprint("✅ Trip PDF sent to driver via WhatsApp.");
//                         }
//                     }
//                 });
//             });
//         }
//     }
// });
// frappe.ui.form.on('Trip', {
//     refresh(frm) {
//         if (!frm.is_new() && !frm.doc.kashf_sent) {
//             frm.add_custom_button("Send Trip PDF to Driver", () => {
//                 frappe.call({
//                     method: "tms.utils.print_button.send_trip_pdf_to_driver",
//                     args: { trip_name: frm.doc.name },
//                     callback(r) {
//                         if (r.message === true) {
//                             frappe.msgprint("✅ Trip PDF sent to driver via WhatsApp.");
//                             frm.reload_doc();  // refresh to disable button
//                         } else if (r.message === "Already sent") {
//                             frappe.msgprint("❗ This Trip PDF was already sent.");
//                         }
//                     }
//                 });
//             });
//         }
//     }
// });
// frappe.ui.form.on('Trip', {
//     refresh(frm) {
//         if (!frm.is_new()) {
//             frm.add_custom_button("Send Trip PDF to Driver", () => {
//                 frappe.call({
//                     method: "tms.utils.whatsapp_utils.send_trip_pdf_via_whatsapp",
//                     args: {
//                         trip_name: frm.doc.name,
//                         phone: frm.doc.driver_phone || "+966572405550" // fallback
//                     },
//                     callback(r) {
//                         if (r.message) {
//                             frappe.msgprint("✅ Trip PDF sent via WhatsApp.");
//                             frm.remove_custom_button("Send Trip PDF to Driver");
//                         }
//                     }
//                 });
//             });
//         }
//     }
// });
// frappe.ui.form.on('Trip', {
//     refresh(frm) {
//         if (!frm.is_new()) {
//             frm.add_custom_button(frm.doc.kashf_sent ? "Resend Trip PDF to Driver" : "Send Trip PDF to Driver", () => {
//                 frappe.call({
//                     method: "tms.utils.whatsapp_utils.send_trip_pdf_via_whatsapp",
//                     args: {
//                         trip_name: frm.doc.name
//                     },
//                     callback(r) {
//                         if (r.message === "sent") {
//                             frappe.msgprint("Trip PDF sent via WhatsApp.");
//                             frm.set_value("kashf_sent", 1);
//                             frm.save();
//                         } else {
//                             frappe.msgprint("Could not send PDF.");
//                         }
//                     }
//                 });
//             });
//         }
//     }
// });

frappe.ui.form.on("Trip", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		if (frm.doc.trip_value) {
			frm.add_custom_button(
				__("Create Trip Invoice"),
				() => {
					frappe.call({
						method:
							"tms.transport_management_system.doctype.trip_invoice.trip_invoice.create_trip_invoice_from_trip",
						args: { trip_name: frm.doc.name, invoice_mode: "Trip" },
						freeze: true,
						freeze_message: __("Creating Trip Invoice..."),
						callback(r) {
							if (!r.message) return;
							frappe.msgprint(__("Trip Invoice created: {0}", [r.message.trip_invoice || r.message.trip_invoices]));
							frm.reload_doc();
						},
					});
				},
				__("Trip Actions")
			);

			frm.add_custom_button(
				__("Create Passenger Trip Invoices"),
				() => {
					frappe.call({
						method:
							"tms.transport_management_system.doctype.trip_invoice.trip_invoice.create_trip_invoice_from_trip",
						args: { trip_name: frm.doc.name, invoice_mode: "Passenger" },
						freeze: true,
						freeze_message: __("Creating Passenger Trip Invoices..."),
						callback(r) {
							if (!r.message) return;
							frappe.msgprint(__("Trip Invoices created: {0}", [(r.message.trip_invoices || []).join(", ")]));
							frm.reload_doc();
						},
					});
				},
				__("Trip Actions")
			);
		}

		if (frm.doc.trip_invoice) {
			frm.add_custom_button(
				__("Open Trip Invoice"),
				() => frappe.set_route("Form", "Trip Invoice", frm.doc.trip_invoice),
				__("Trip Actions")
			);
		}
	},
});
