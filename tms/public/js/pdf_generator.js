frappe.provide("tms.pdf_generator");

// Add Generate PDF button to relevant doctypes
frappe.ui.form.on("Quotation", {
    refresh: add_pdf_button
});
frappe.ui.form.on("Sales Invoice", {
    refresh: add_pdf_button
});
frappe.ui.form.on("Sales Order", {
    refresh: add_pdf_button
});
frappe.ui.form.on("Delivery Note", {
    refresh: add_pdf_button
});
frappe.ui.form.on("Purchase Invoice", {
    refresh: add_pdf_button
});
frappe.ui.form.on("Purchase Order", {
    refresh: add_pdf_button
});
frappe.ui.form.on("Supplier Quotation", {
    refresh: add_pdf_button
});
frappe.ui.form.on("Payment Entry", {
    refresh: add_pdf_button
});

function add_pdf_button(frm) {
    // Show for all saved docs (draft, submitted, cancelled)
    if (!frm.doc.__islocal) {
        frm.add_custom_button(__("Generate PDF"), function() {
            generate_pdf_dialog(frm);
        }, __("PDF"));
    }
}

function generate_pdf_dialog(frm) {
    // Fetch available print formats for this doctype
    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Print Format",
            filters: {
                doc_type: frm.doctype,
                disabled: 0
            },
            fields: ["name"],
            order_by: "name asc"
        },
        callback: function(r) {
            if (!r.message || r.message.length === 0) {
                frappe.msgprint(__("No print formats found for this document type"));
                return;
            }

            let formats = r.message.map(f => f.name);
            let default_format = frm.meta.default_print_format || formats[0];

            let d = new frappe.ui.Dialog({
                title: __("Generate PDF"),
                fields: [
                    {
                        fieldtype: "Select",
                        fieldname: "print_format",
                        label: __("Print Format"),
                        options: formats,
                        default: default_format,
                        reqd: 1
                    }
                ],
                primary_action_label: __("Generate"),
                primary_action: function() {
                    let pf = d.get_values().print_format;
                    d.hide();
                    frappe.call({
                        method: "tms.api.pdf_generator.generate_pdf",
                        args: {
                            doctype: frm.doctype,
                            docname: frm.docname,
                            print_format: pf
                        },
                        callback: function(res) {
                            if (res.message) {
                                let msg = res.message;
                                frappe.show_alert({
                                    message: __("PDF saved in {0}: {1}", [msg.folder, msg.file_name]),
                                    indicator: "green"
                                }, 8);
                                // Open the file
                                if (msg.file_url) {
                                    window.open(msg.file_url, "_blank");
                                }
                            }
                        },
                        error: function(err) {
                            let msg = "Unknown error";
                            if (err.responseJSON && err.responseJSON.message) {
                                msg = err.responseJSON.message;
                            } else if (err.responseJSON && err.responseJSON.exception) {
                                msg = err.responseJSON.exception;
                            } else if (err.responseText) {
                                msg = err.responseText;
                            }
                            frappe.msgprint(__("PDF generation failed: ") + msg);
                        }
                    });
                }
            });
            d.show();
        }
    });
}
