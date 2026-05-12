frappe.ui.form.on("Trip", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(
			__("Open WhatsApp PDF"),
			() => {
				frappe.call({
					method: "tms.utils.whatsapp_document.prepare_trip_pdf_whatsapp_link",
					args: {
						trip_name: frm.doc.name,
					},
					freeze: true,
					freeze_message: __("Preparing WhatsApp PDF link"),
					callback(r) {
						if (!r.exc && r.message) {
							window.open(r.message.whatsapp_url, "_blank");
							frappe.show_alert({
								message: __("WhatsApp opened for {0}", [r.message.to]),
								indicator: "green",
							});
							frm.reload_doc();
						}
					},
				});
			},
			__("WhatsApp")
		);
	},
});
