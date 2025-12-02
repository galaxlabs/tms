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
//                             frappe.msgprint("✅ Trip PDF sent via WhatsApp.");
//                             frm.set_value("kashf_sent", 1);
//                             frm.save();
//                         } else {
//                             frappe.msgprint("⚠️ Could not send PDF.");
//                         }
//                     }
//                 });
//             });
//         }
//     }
// });
