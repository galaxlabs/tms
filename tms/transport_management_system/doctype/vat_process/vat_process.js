frappe.ui.form.on("VAT Process", {
	refresh(frm) {
		set_company_user_query(frm);
		toggle_party_fields(frm);
		renderUploadPanel(frm);

		if (!has_created_invoice(frm.doc)) {
			frm.add_custom_button(__("Upload Documents"), () => {
				openVatProcessUploader(frm);
			});
		}

		if (!frm.is_new() && frm.doc.source_document && !has_created_invoice(frm.doc)) {
			frm.add_custom_button(__("Analyze with Gemini"), () => {
				analyzeVatDocument(frm);
			});
		}

		if (!frm.is_new() && !has_created_invoice(frm.doc) && frm.doc.process_type) {
			frm.add_custom_button(getInvoiceButtonLabel(frm.doc.process_type), () => {
				const preflightMessage = getInvoicePreflightMessage(frm.doc);
				if (preflightMessage) {
					frappe.msgprint(preflightMessage);
					return;
				}

				if (frm.doc.status !== "Reviewed") {
					frappe.msgprint(__("Please change the VAT Process status to Reviewed before creating the ERPNext invoice."));
					return;
				}

				frappe.call({
					method: "tms.transport_management_system.doctype.vat_process.vat_process.create_invoice_from_vat_process",
					args: { name: frm.doc.name },
					callback(r) {
						if (r.message) {
							frappe.show_alert({
								message: __("Created {0} {1}", [r.message.doctype, r.message.name]),
								indicator: "green",
							});
							frm.reload_doc();
						}
					},
				});
			});
		}

		if (!frm.is_new() && has_created_invoice(frm.doc)) {
			frm.add_custom_button(getOpenInvoiceLabel(frm.doc), () => {
				const doctype = frm.doc.created_sales_invoice ? "Sales Invoice" : "Purchase Invoice";
				const name = frm.doc.created_sales_invoice || frm.doc.created_purchase_invoice;
				if (doctype && name) {
					frappe.set_route("Form", doctype, name);
				}
			});
		}

		if (!frm.is_new() && frm.doc.status !== "Invoice Created") {
			frm.add_custom_button(__("Validate Totals"), () => {
				frappe.call({
					method: "tms.transport_management_system.doctype.vat_process.vat_process.validate_totals_for_vat_process",
					args: { name: frm.doc.name },
					callback(r) {
						if (r.message) {
							frm.set_value("net_total", r.message.net_total);
							frm.set_value("vat_amount", r.message.vat_amount);
							frm.set_value("grand_total", r.message.grand_total);
							frm.set_value("totals_validated", 1);
							frappe.show_alert({ message: __("Totals validated"), indicator: "green" });
						}
					},
				});
			});
		}

		if (!frm.is_new() && frm.doc.status !== "Invoice Created") {
			frm.add_custom_button(__("Create Missing Items"), () => {
				frappe.call({
					method: "tms.transport_management_system.doctype.vat_process.vat_process.create_missing_items_for_vat_process",
					args: { name: frm.doc.name },
					callback() {
						frappe.show_alert({ message: __("Missing items created"), indicator: "green" });
						frm.reload_doc();
					},
				});
			});
		}
	},

	onload(frm) {
		set_company_user_query(frm);
	},

	onload_post_render(frm) {
		renderUploadPanel(frm);
	},

	company(frm) {
		frm.set_value("company_user", "");
		frm.set_value("company_user_full_name", "");
		load_company_users(frm);
	},

	process_type(frm) {
		toggle_party_fields(frm);
	},

	vat_rate(frm) {
		(frm.doc.items || []).forEach((row) => {
			if (!row.vat_rate && row.vat_rate !== 0) {
				frappe.model.set_value(row.doctype, row.name, "vat_rate", frm.doc.vat_rate || 15);
			}
			recalculate_row(row, frm.doc.vat_rate || 15);
		});
		refresh_parent_totals(frm);
	},

	company_user(frm) {
		const selected = (frm._company_users || []).find((user) => user.name === frm.doc.company_user);
		if (selected) {
			frm.set_value("company_user_full_name", selected.full_name || selected.name);
			return;
		}
		if (frm.doc.company_user) {
			frappe.db.get_value("User", frm.doc.company_user, "full_name").then((r) => {
				frm.set_value("company_user_full_name", r.message?.full_name || "");
			});
		} else {
			frm.set_value("company_user_full_name", "");
		}
	},
});

frappe.ui.form.on("VAT Process Item", {
	item_text(frm, cdt, cdn) {
		enforce_service_defaults(cdt, cdn);
	},

	item_code(frm, cdt, cdn) {
		enforce_service_defaults(cdt, cdn);
	},

	qty(frm, cdt, cdn) {
		recalculate_and_refresh(frm, cdt, cdn);
	},

	rate(frm, cdt, cdn) {
		recalculate_and_refresh(frm, cdt, cdn);
	},

	vat_rate(frm, cdt, cdn) {
		recalculate_and_refresh(frm, cdt, cdn);
	},
});

function has_created_invoice(doc) {
	return Boolean(doc.created_sales_invoice || doc.created_purchase_invoice);
}

function getInvoiceButtonLabel(processType) {
	return processType === "Purchase" ? __("Create Draft Purchase Invoice") : __("Create Draft Sales Invoice");
}

function getOpenInvoiceLabel(doc) {
	return doc.created_sales_invoice ? __("Open Sales Invoice") : __("Open Purchase Invoice");
}

function getInvoicePreflightMessage(doc) {
	if (!doc.process_type) {
		return __("Please select the VAT Process type first.");
	}

	if (doc.process_type === "Sales" && !doc.customer) {
		return __("This is a Sales VAT Process. Please set a Customer before creating the draft Sales Invoice.");
	}

	if (doc.process_type === "Purchase" && !doc.supplier) {
		return __("This is a Purchase VAT Process. Please set a Supplier before creating the draft Purchase Invoice.");
	}

	return "";
}

function set_company_user_query(frm) {
	frm.set_query("company_user", () => {
		const users = frm._company_user_ids || [];
		if (frm.doc.company && !users.length) {
			return {
				filters: [["User", "name", "=", "__no_company_users__"]],
			};
		}
		if (users.length) {
			return {
				filters: [["User", "name", "in", users], ["User", "enabled", "=", 1]],
			};
		}
		return {
			filters: [["User", "enabled", "=", 1]],
		};
	});
}

function load_company_users(frm) {
	frm._company_users = [];
	frm._company_user_ids = [];
	set_company_user_query(frm);

	if (!frm.doc.company) {
		return;
	}

	frappe.call({
		method: "tms.transport_management_system.doctype.vat_process.vat_process.get_company_users",
		args: { company: frm.doc.company },
		callback(r) {
			const users = r.message || [];
			frm._company_users = users;
			frm._company_user_ids = users.map((user) => user.name);
			set_company_user_query(frm);

			if (!frm.doc.company_user && users.length === 1) {
				frm.set_value("company_user", users[0].name);
				frm.set_value("company_user_full_name", users[0].full_name || users[0].name);
			}
		},
	});
}

function toggle_party_fields(frm) {
	const isSales = frm.doc.process_type === "Sales";
	const isPurchase = frm.doc.process_type === "Purchase";

	frm.toggle_display("customer", isSales);
	frm.toggle_display("supplier", isPurchase);
}

function enforce_service_defaults(cdt, cdn) {
	frappe.model.set_value(cdt, cdn, "is_service_item", 1);
	const row = locals[cdt][cdn];
	if (!row.item_group) {
		frappe.model.set_value(cdt, cdn, "item_group", "Services");
	}
	if (!row.uom) {
		frappe.model.set_value(cdt, cdn, "uom", "Nos");
	}
}

function recalculate_and_refresh(frm, cdt, cdn) {
	enforce_service_defaults(cdt, cdn);
	const row = locals[cdt][cdn];
	recalculate_row(row, frm.doc.vat_rate || 15);
	refresh_parent_totals(frm);
	frm.refresh_field("items");
}

function recalculate_row(row, defaultVatRate) {
	const qty = flt(row.qty || 0);
	const rate = flt(row.rate || 0);
	const vatRate = row.vat_rate === undefined || row.vat_rate === null || row.vat_rate === ""
		? flt(defaultVatRate || 0)
		: flt(row.vat_rate || 0);

	row.vat_rate = vatRate;
	row.amount = qty * rate;
	row.vat_amount = row.amount * vatRate / 100;
	row.total_amount = row.amount + row.vat_amount;
	row.is_service_item = 1;
}

function refresh_parent_totals(frm) {
	let netTotal = 0;
	let vatAmount = 0;

	(frm.doc.items || []).forEach((row) => {
		netTotal += flt(row.amount || 0);
		vatAmount += flt(row.vat_amount || 0);
	});

	frm.set_value("net_total", netTotal);
	frm.set_value("vat_amount", vatAmount);
	frm.set_value("grand_total", netTotal + vatAmount + flt(frm.doc.rounding_adjustment || 0));
}

function openVatProcessUploader(frm) {
	if (!frm.doc.name) {
		frm.save()
			.then(() => {
				openVatProcessUploader(frm);
			})
			.catch(() => {
				frappe.msgprint(__("Please fill the required fields and save before uploading documents."));
			});
		return;
	}

	new frappe.ui.FileUploader({
		doctype: frm.doctype,
		docname: frm.doc.name,
		allow_multiple: true,
		restrictions: {
			allowed_file_types: [".pdf", ".png", ".jpg", ".jpeg", ".webp"],
		},
		on_success(file) {
			frappe.call({
				method: "tms.transport_management_system.doctype.vat_process.vat_process.attach_existing_file_to_vat_process",
				args: {
					name: frm.doc.name,
					file_url: file.file_url,
					file_name: file.name || file.file_name,
				},
				callback() {
					analyzeVatDocument(frm, { silent: true });
				},
			});
		},
	});
}

function analyzeVatDocument(frm, { silent = false } = {}) {
	if (!frm.doc.name) {
		frappe.msgprint(__("Please save the VAT Process before analyzing the document."));
		return;
	}

	frappe.call({
		method: "tms.transport_management_system.doctype.vat_process.vat_process.analyze_vat_process_with_gemini",
		args: { name: frm.doc.name },
		callback(r) {
			if (r.message && !silent) {
				const processType = r.message.process_type || __("Unknown");
				frappe.show_alert({
					message: __("Gemini analyzed this document as {0}", [processType]),
					indicator: "green",
				});
			}
			frm.reload_doc();
		},
		error() {
			if (!silent) {
				frappe.msgprint(__("Gemini analysis could not complete for this document."));
			}
		},
	});
}

function renderUploadPanel(frm) {
	if (!frm.fields_dict.upload_actions_html) {
		return;
	}

	const wrapper = frm.fields_dict.upload_actions_html.$wrapper;
	const sourceDocument = frm.doc.source_document
		? `<div class="text-muted small" style="margin-top: 8px;">${__("Primary document")}: <a href="${frm.doc.source_document}" target="_blank">${frm.doc.source_document}</a></div>`
		: `<div class="text-muted small" style="margin-top: 8px;">${__("No document uploaded yet.")}</div>`;

	wrapper.html(`
		<div style="border: 1px solid var(--border-color); border-radius: 12px; padding: 16px; background: var(--subtle-fg);">
			<div style="display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap;">
				<div>
					<div style="font-weight:600; margin-bottom:4px;">${__("VAT Document Upload")}</div>
					<div class="text-muted small">${__("Upload invoice, bill, or scanned PDF/image files here just like the trip scanner flow.")}</div>
				</div>
				${has_created_invoice(frm.doc) ? "" : `
				<div style="display:flex; gap:8px; flex-wrap:wrap;">
					<button class="btn btn-primary btn-sm" data-action="upload-vat-docs">${__("Upload Documents")}</button>
					${frm.doc.source_document ? `<button class="btn btn-default btn-sm" data-action="analyze-vat-docs">${__("Analyze with Gemini")}</button>` : ""}
					<button class="btn btn-default btn-sm" data-action="refresh-vat-docs">${__("Refresh Files")}</button>
				</div>
				`}
			</div>
			<div data-vat-attachment-list style="margin-top: 12px;"></div>
			${sourceDocument}
		</div>
	`);

	wrapper.find('[data-action="upload-vat-docs"]').on("click", () => openVatProcessUploader(frm));
	wrapper.find('[data-action="analyze-vat-docs"]').on("click", () => analyzeVatDocument(frm));
	wrapper.find('[data-action="refresh-vat-docs"]').on("click", () => loadAttachmentSummary(frm));
	loadAttachmentSummary(frm);
}

function loadAttachmentSummary(frm) {
	const wrapper = frm.fields_dict.upload_actions_html?.$wrapper;
	const listWrapper = wrapper?.find("[data-vat-attachment-list]");
	if (!listWrapper?.length) {
		return;
	}

	if (!frm.doc.name) {
		listWrapper.html(`<div class="text-muted small">${__("Save the VAT Process once, then upload documents.")}</div>`);
		return;
	}

	listWrapper.html(`<div class="text-muted small">${__("Loading attachments...")}</div>`);

	frappe.call({
		method: "tms.transport_management_system.doctype.vat_process.vat_process.get_vat_process_attachments",
		args: { name: frm.doc.name },
		callback(r) {
			const result = r.message || {};
			const attachments = result.attachments || [];
			if (!attachments.length) {
				listWrapper.html(`<div class="text-muted small">${__("No attachments yet.")}</div>`);
				return;
			}

			const items = attachments
				.map((file) => `<div class="small" style="margin-bottom:6px;"><a href="${file.file_url}" target="_blank">${frappe.utils.escape_html(file.file_name || file.file_url)}</a></div>`)
				.join("");

			listWrapper.html(`
				<div class="small" style="margin-bottom:8px; font-weight:600;">${__("Attached Files")}: ${attachments.length}</div>
				${items}
			`);
		},
	});
}
