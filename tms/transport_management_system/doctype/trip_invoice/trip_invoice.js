frappe.ui.form.on("Trip Invoice", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(
			__("Add Trip Route Line"),
			() => {
				const row = frm.add_child("items", {
					source_type: "Trip Route",
					trip: frm.doc.trip,
					route: frm.doc.trip_route,
					qty: 1,
					rate: frm.doc.trip_value || 0,
					vat_rate: frm.doc.vat_rate || 15,
				});
				row.description = [frm.doc.trip, frm.doc.from_location, frm.doc.to_location]
					.filter(Boolean)
					.join(" | ");
				frm.refresh_field("items");
			},
			__("Invoice Actions")
		);

		frm.add_custom_button(
			__("Add Manual Item"),
			() => {
				frm.add_child("items", {
					source_type: "Manual Item",
					qty: 1,
					vat_rate: frm.doc.vat_rate || 15,
					is_manual: 1,
				});
				frm.refresh_field("items");
			},
			__("Invoice Actions")
		);

		frm.add_custom_button(__("Validate Totals"), () => frm.save(), __("Invoice Actions"));

		if (frm.doc.status === "Draft") {
			frm.add_custom_button(
				__("Mark Ready"),
				() => {
					frappe.call({
						method:
							"tms.transport_management_system.doctype.trip_invoice.trip_invoice.mark_trip_invoice_ready",
						args: { trip_invoice: frm.doc.name },
						freeze: true,
						callback() {
							frm.reload_doc();
						},
					});
				},
				__("Invoice Actions")
			);
		}

		if (frm.doc.kashf_ready) {
			frm.add_custom_button(
				__("Print Kashf"),
				() => frappe.utils.print(frm.doc.doctype, frm.doc.name, "Kashf"),
				__("Invoice Actions")
			);
		}

		if (frm.doc.kashf_ready && !frm.doc.kashf_sent) {
			frm.add_custom_button(
				__("Mark Kashf Sent"),
				() => {
					frappe.call({
						method:
							"tms.transport_management_system.doctype.trip_invoice.trip_invoice.mark_kashf_sent",
						args: { trip_invoice: frm.doc.name },
						freeze: true,
						callback() {
							frm.reload_doc();
						},
					});
				},
				__("Invoice Actions")
			);
		}
	},
});
