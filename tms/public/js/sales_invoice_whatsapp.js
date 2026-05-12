frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("Send Invoice PDF"), () => {
			open_sales_invoice_whatsapp(frm, "tms.utils.whatsapp_document.prepare_sales_invoice_pdf_whatsapp_link");
		}, __("WhatsApp"));

		frm.add_custom_button(__("Send Proforma PDF"), () => {
			open_sales_invoice_whatsapp(frm, "tms.utils.whatsapp_document.prepare_proforma_invoice_whatsapp_link");
		}, __("WhatsApp"));

		frm.add_custom_button(__("Send ZATCA PDF/A"), () => {
			open_sales_invoice_whatsapp(
				frm,
				"tms.utils.whatsapp_document.prepare_sales_invoice_pdf_whatsapp_link",
				"ZATCA PDF-A 3B Dynamic"
			);
		}, __("WhatsApp"));
	},
});

function open_sales_invoice_whatsapp(frm, method, print_format) {
	const guessed_number = guess_sales_invoice_whatsapp_number(frm);

	frappe.prompt(
		[
			{
				fieldname: "to",
				fieldtype: "Data",
				label: __("WhatsApp Number"),
				reqd: 1,
				default: guessed_number,
				description: __("Enter country code with the number, for example 9665XXXXXXXX."),
			},
		],
		(values) => {
			const args = {
				invoice_name: frm.doc.name,
				to: values.to,
			};

			if (print_format) {
				args.print_format = print_format;
			}

			frappe.call({
				method,
				args,
				freeze: true,
				freeze_message: __("Preparing WhatsApp PDF link"),
				callback(r) {
					if (!r.exc && r.message) {
						window.open(r.message.whatsapp_url, "_blank");
						frappe.show_alert({
							message: __("WhatsApp opened for {0}", [r.message.to]),
							indicator: "green",
						});
					}
				},
			});
		},
		__("Send PDF on WhatsApp"),
		__("Open WhatsApp")
	);
}

function guess_sales_invoice_whatsapp_number(frm) {
	const fields = [
		"contact_mobile",
		"contact_phone",
		"mobile_no",
		"customer_mobile",
		"customer_phone",
	];

	for (const fieldname of fields) {
		if (frm.doc[fieldname]) {
			return frm.doc[fieldname];
		}
	}

	return "";
}
