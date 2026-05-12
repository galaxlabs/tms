const SALES_TYPES = ["Sales Quotation", "Sales Order", "Proforma Invoice", "Sales Invoice"];
const PURCHASE_TYPES = ["Purchase Order", "Purchase Invoice"];
const SUPPORTED_CREATE_TYPES = [...SALES_TYPES, ...PURCHASE_TYPES];

frappe.ui.form.on("VAT Process", {
	refresh(frm) {
		set_company_user_query(frm);
		toggle_form_fields(frm);
		hide_internal_fields(frm);
		renderUploadPanel(frm);
		add_grouped_buttons(frm);
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
		toggle_form_fields(frm);
		renderUploadPanel(frm);
	},

	vat_rate(frm) {
		(frm.doc.items || []).forEach((row) => {
			if (row.vat_rate === undefined || row.vat_rate === null || row.vat_rate === "") {
				frappe.model.set_value(row.doctype, row.name, "vat_rate", frm.doc.vat_rate || 15);
			}
			recalculate_row(row, frm.doc.vat_rate || 15);
		});
		refresh_parent_totals(frm);
	},

	discount_amount(frm) {
		refresh_parent_totals(frm);
	},

	airfreight_charges(frm) {
		refresh_parent_totals(frm);
	},

	rounding_adjustment(frm) {
		refresh_parent_totals(frm);
	},

	tc_name(frm) {
		if (!frm.doc.tc_name) {
			return;
		}

		frappe.db.get_value("Terms and Conditions", frm.doc.tc_name, "terms").then((r) => {
			if (r.message?.terms && !frm.doc.terms) {
				frm.set_value("terms", r.message.terms);
			}
		});
	},

	company_user(frm) {
		const selected = (frm._company_users || []).find((user) => user.name === frm.doc.company_user);
		if (selected) {
			frm.set_value("company_user_full_name", selected.full_name || selected.name);
			return;
		}
		if (!frm.doc.company_user) {
			frm.set_value("company_user_full_name", "");
			return;
		}
		frappe.db.get_value("User", frm.doc.company_user, "full_name").then((r) => {
			frm.set_value("company_user_full_name", r.message?.full_name || "");
		});
	},
});

frappe.ui.form.on("VAT Process Item", {
	item_text(frm, cdt, cdn) {
		enforce_service_defaults(cdt, cdn);
	},

	item_code(frm, cdt, cdn) {
		enforce_service_defaults(cdt, cdn);
	},

	calculation_type(frm, cdt, cdn) {
		recalculate_and_refresh(frm, cdt, cdn);
	},

	lump_sum_amount(frm, cdt, cdn) {
		recalculate_and_refresh(frm, cdt, cdn);
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

function add_grouped_buttons(frm) {
	if (frm.is_new()) {
		return;
	}

	const targetDoctype = getTargetDoctype(frm.doc.process_type);
	const reviewStatus = frm.doc.review_status || frm.doc.status;
	const canCreate = SUPPORTED_CREATE_TYPES.includes(frm.doc.process_type) && !has_created_document(frm.doc);

	if (frm.doc.process_type === "Purchase Invoice") {
		frm.add_custom_button(__("Upload Source Document"), () => openVatProcessUploader(frm), __("Actions"));
	}

	if (frm.doc.source_document && targetDoctype === "Purchase Invoice") {
		frm.add_custom_button(__("Extract from Source Document"), () => {
			callVatProcessMethod(frm, "extract_from_source_document", __("Source document extracted"));
		}, __("Actions"));
	}

	if (!has_created_document(frm.doc)) {
		frm.add_custom_button(__("Validate Totals"), () => {
			callVatProcessMethod(frm, "validate_totals", __("Totals validated"), ({ message }) => {
				if (message) {
					frm.set_value("net_total", message.net_total);
					frm.set_value("vat_amount", message.vat_amount);
					frm.set_value("grand_total", message.grand_total);
					frm.set_value("totals_validated", 1);
				}
			});
		}, __("Actions"));
	}

	if (frappe.user.has_role("VAT Manager") || frappe.user.has_role("System Manager")) {
		frm.add_custom_button(__("Setup VAT Accounts & Templates"), () => {
			callVatProcessMethod(frm, "setup_vat_accounts_and_templates", __("VAT setup completed"));
		}, __("Setup"));
	}

	if (canCreate) {
		frm.add_custom_button(__("Create / Match Party"), () => {
			callVatProcessMethod(frm, "create_or_match_party", __("Party checked"));
		}, __("Setup"));

		frm.add_custom_button(__("Create / Match Items"), () => {
			callVatProcessMethod(frm, "create_or_match_items", __("Items checked"));
		}, __("Setup"));
	}

	if (canCreate && ["Ready", "Reviewed"].includes(reviewStatus)) {
		frm.add_custom_button(__("Create ERPNext Document"), () => {
			const preflightMessage = getCreatePreflightMessage(frm.doc);
			if (preflightMessage) {
				frappe.msgprint(preflightMessage);
				return;
			}
			callVatProcessMethod(frm, "create_erpnext_document", __("ERPNext document created"), ({ message }) => {
				if (message?.doctype && message?.name) {
					frappe.show_alert({
						message: __("Created {0} {1}", [message.doctype, message.name]),
						indicator: "green",
					});
				}
			});
		}, __("Create"));
	}

	if (frm.doc.created_document_type && frm.doc.created_document) {
		frm.add_custom_button(__("Open Created Document"), () => {
			frappe.set_route("Form", frm.doc.created_document_type, frm.doc.created_document);
		}, __("Create"));
	}

	if (frm.doc.process_type === "Proforma Invoice" && frm.doc.created_document_type === "Sales Order" && frm.doc.created_document) {
		frm.add_custom_button(__("Print Proforma"), () => {
			const printUrl = frappe.urllib.get_full_url(
				`/printview?doctype=${encodeURIComponent("Sales Order")}&name=${encodeURIComponent(frm.doc.created_document)}&format=${encodeURIComponent("Profarma Invoice")}&no_letterhead=0`
			);
			window.open(printUrl, "_blank");
		}, __("Print"));
	}
}

function callVatProcessMethod(frm, method, successMessage, onSuccess) {
	frm.call(method).then((r) => {
		if (onSuccess) {
			onSuccess(r);
		}
		if (successMessage) {
			frappe.show_alert({ message: successMessage, indicator: "green" });
		}
		frm.reload_doc();
	});
}

function has_created_document(doc) {
	return Boolean(
		doc.created_document ||
		doc.created_sales_invoice ||
		doc.created_purchase_invoice ||
		doc.created_purchase_order ||
		doc.created_quotation
	);
}

function getTargetDoctype(processType) {
	const mapping = {
		"Sales Quotation": "Quotation",
		"Sales Order": "Sales Order",
		"Proforma Invoice": "Sales Order",
		"Sales Invoice": "Sales Invoice",
		"Purchase Order": "Purchase Order",
		"Purchase Invoice": "Purchase Invoice",
	};
	return mapping[(processType || "").trim()] || "";
}

function getCreatePreflightMessage(doc) {
	const targetDoctype = getTargetDoctype(doc.process_type);
	if (!doc.process_type || !targetDoctype) {
		return __("Please select a supported Process Type first.");
	}
	if (["Quotation", "Sales Order", "Sales Invoice"].includes(targetDoctype) && !doc.customer && !doc.party_name_text) {
		return __("Please set a Customer or party details before creating this document.");
	}
	if (["Purchase Order", "Purchase Invoice"].includes(targetDoctype) && !doc.supplier && !doc.party_name_text) {
		return __("Please set a Supplier or party details before creating this document.");
	}
	if (targetDoctype === "Purchase Invoice" && !doc.external_invoice_no) {
		return __("Please set External Invoice No before creating a Purchase Invoice.");
	}
	return "";
}

function set_company_user_query(frm) {
	frm.set_query("company_user", () => {
		const users = frm._company_user_ids || [];
		if (frm.doc.company && !users.length) {
			return { filters: [["User", "name", "=", "__no_company_users__"]] };
		}
		if (users.length) {
			return { filters: [["User", "name", "in", users], ["User", "enabled", "=", 1]] };
		}
		return { filters: [["User", "enabled", "=", 1]] };
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
		},
	});
}

function hide_internal_fields(frm) {
	[
		"status",
		"source_type",
		"ocr_reference",
		"extracted_text",
		"extraction_confidence",
		"requires_review",
		"issuer_name_text",
		"issuer_name_arabic",
		"issuer_vat_no",
		"issuer_cr_no",
		"issuer_address_text",
		"document_customer_name_text",
		"document_customer_name_arabic",
		"document_customer_vat_no",
		"document_customer_cr_no",
		"document_customer_address_text",
		"company_name_arabic",
		"party_name_arabic",
		"company_user",
		"company_user_full_name",
		"difference_amount",
		"invoice_created_on",
		"invoice_created_by",
		"created_invoice_type",
		"created_doctype",
		"created_sales_invoice",
		"created_purchase_invoice",
		"created_purchase_order",
		"created_quotation",
		"rejection_reason",
	].forEach((fieldname) => {
		if (frm.fields_dict[fieldname]) {
			frm.toggle_display(fieldname, false);
		}
	});
}

function toggle_form_fields(frm) {
	const type = (frm.doc.process_type || "").trim();
	const targetDoctype = getTargetDoctype(type);
	const isPurchaseInvoice = type === "Purchase Invoice";
	const isPurchaseOrder = type === "Purchase Order";
	const isSalesQuotation = type === "Sales Quotation";
	const isSalesOrder = type === "Sales Order";
	const isProforma = type === "Proforma Invoice";
	const isSalesInvoice = type === "Sales Invoice";
	const isBillingType = ["Project Billing", "Service Billing"].includes(type);
	const needsCustomer = SALES_TYPES.includes(type);
	const needsSupplier = PURCHASE_TYPES.includes(type);
	const showTerms = ["Quotation", "Sales Order", "Sales Invoice", "Purchase Order"].includes(targetDoctype);

	frm.toggle_display("customer", needsCustomer);
	frm.toggle_display("supplier", needsSupplier);
	frm.toggle_display("source_document", isPurchaseInvoice);
	frm.toggle_display("upload_actions_html", isPurchaseInvoice);
	frm.toggle_display("invoice_date", isSalesInvoice || isPurchaseInvoice);
	frm.toggle_display("external_invoice_no", isSalesInvoice || isPurchaseInvoice);
	frm.toggle_reqd("external_invoice_no", isPurchaseInvoice);
	frm.toggle_display("required_by_date", isPurchaseOrder || isSalesOrder || isProforma);
	frm.toggle_display("valid_till", isSalesQuotation);
	frm.toggle_display("tc_name", showTerms);
	frm.toggle_display("terms", showTerms);
	frm.toggle_display("print_notes", showTerms);
	[
		"business_vertical",
		"project",
		"cost_center",
		"site_location",
		"contract_no",
		"work_period_from",
		"work_period_to",
		"billing_basis",
		"linked_sales_order",
		"linked_purchase_order",
	].forEach((fieldname) => {
		if (frm.fields_dict[fieldname]) {
			frm.toggle_display(fieldname, isBillingType);
		}
	});
}

function enforce_service_defaults(cdt, cdn) {
	frappe.model.set_value(cdt, cdn, "is_service_item", 1);
	const row = locals[cdt][cdn];
	if (!row.item_group) {
		frappe.model.set_value(cdt, cdn, "item_group", "Services");
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
	const calculationType = row.calculation_type || "Qty x Rate";
	const qty = flt(row.qty || 0) > 0 ? flt(row.qty || 0) : 1;
	const rate = flt(row.rate || 0);
	const lumpSumAmount = flt(row.lump_sum_amount || 0);
	const vatRate = row.vat_rate === undefined || row.vat_rate === null || row.vat_rate === "" ? flt(defaultVatRate || 0) : flt(row.vat_rate || 0);

	row.calculation_type = calculationType;
	row.qty = qty;
	row.vat_rate = vatRate;

	if (calculationType === "Lump Sum Amount") {
		row.amount = lumpSumAmount;
		row.rate = qty > 0 ? lumpSumAmount / qty : lumpSumAmount;
	} else {
		row.amount = qty * rate;
	}

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
	frm.set_value("grand_total", netTotal + vatAmount + flt(frm.doc.airfreight_charges || 0) - flt(frm.doc.discount_amount || 0) + flt(frm.doc.rounding_adjustment || 0));
}

function openVatProcessUploader(frm) {
	if (!frm.doc.name) {
		frm.save().then(() => openVatProcessUploader(frm)).catch(() => {
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
					frm.reload_doc();
				},
			});
		},
	});
}

function renderUploadPanel(frm) {
	if (!frm.fields_dict.upload_actions_html) {
		return;
	}

	if (frm.doc.process_type !== "Purchase Invoice") {
		frm.fields_dict.upload_actions_html.$wrapper.empty();
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
					<div class="text-muted small">${__("Upload one source file and reuse it for extraction without creating duplicate attachments.")}</div>
				</div>
				<div style="display:flex; gap:8px; flex-wrap:wrap;">
					<button class="btn btn-primary btn-sm" data-action="upload-vat-docs">${__("Upload Documents")}</button>
					<button class="btn btn-default btn-sm" data-action="refresh-vat-docs">${__("Refresh Files")}</button>
				</div>
			</div>
			<div data-vat-attachment-list style="margin-top: 12px;"></div>
			${sourceDocument}
		</div>
	`);

	wrapper.find('[data-action="upload-vat-docs"]').on("click", () => openVatProcessUploader(frm));
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
			const attachments = r.message?.attachments || [];
			if (!attachments.length) {
				listWrapper.html(`<div class="text-muted small">${__("No attachments yet.")}</div>`);
				return;
			}
			const items = attachments
				.map((file) => `<div class="small" style="margin-bottom:6px;"><a href="${file.file_url}" target="_blank">${frappe.utils.escape_html(file.file_name || file.file_url)}</a></div>`)
				.join("");
			listWrapper.html(`<div class="small" style="margin-bottom:8px; font-weight:600;">${__("Attached Files")}: ${attachments.length}</div>${items}`);
		},
	});
}
