import base64
import io
import os
import secrets
from datetime import datetime, timezone
from urllib.parse import quote

import frappe
from frappe.utils import cint, get_url
from frappe.utils.file_manager import save_file

from tms.utils.chrome_pdf import get_pdf as chrome_get_pdf

DEFAULT_SALES_INVOICE_PRINT_FORMAT = "KSA TMS Sales Invoice"
DEFAULT_ZATCA_PDFA_PRINT_FORMAT = "ZATCA PDF-A 3B Dynamic"
COMPANY_PRINT_FORMAT_FIELD = "custom_sales_invoice_print_format"
SALES_INVOICE_XML_FIELD = "custom_invoice_xml"


def _doctype_field_is_queryable(doctype: str, fieldname: str) -> bool:
    try:
        meta = frappe.get_meta(doctype)
        if not meta or not meta.has_field(fieldname):
            return False
    except Exception:
        return False

    try:
        return bool(frappe.db.has_column(doctype, fieldname))
    except Exception:
        return False


def get_company_invoice_print_format(
    company: str | None, fallback: str = DEFAULT_SALES_INVOICE_PRINT_FORMAT
) -> str:
    if not company:
        return fallback

    if not _doctype_field_is_queryable("Company", COMPANY_PRINT_FORMAT_FIELD):
        return fallback

    return (
        frappe.db.get_value("Company", company, COMPANY_PRINT_FORMAT_FIELD)
        or fallback
    )


def resolve_sales_invoice_print_format(
    doc=None,
    requested_format: str | None = None,
    fallback: str = DEFAULT_SALES_INVOICE_PRINT_FORMAT,
) -> str:
    if requested_format:
        return requested_format

    return get_company_invoice_print_format(getattr(doc, "company", None), fallback=fallback)


def build_public_invoice_url(name: str, token: str, print_format: str, endpoint: str) -> str:
    base_url = get_url().rstrip("/")
    return (
        f"{base_url}/api/method/{endpoint}"
        f"?name={quote(name)}&token={quote(token)}&format={quote(print_format)}"
    )


def _build_tlv_value(tag: int, value: str) -> bytes:
    encoded = (value or "").encode("utf-8")
    return bytes([tag]) + bytes([len(encoded)]) + encoded


def build_zatca_qr_payload(doc) -> str:
    company = frappe.get_doc("Company", doc.company)
    seller_name = (
        getattr(company, "company_name_arabic", None)
        or getattr(company, "company_name", None)
        or getattr(doc, "company", "")
    )
    vat_number = getattr(doc, "company_tax_id", None) or getattr(company, "tax_id", None) or ""
    posting_timestamp = frappe.utils.get_datetime(
        f"{getattr(doc, 'posting_date', '')} {getattr(doc, 'posting_time', '')}"
    ).isoformat()
    total_amount = f"{float(getattr(doc, 'grand_total', 0) or 0):.2f}"
    vat_amount = f"{float(getattr(doc, 'total_taxes_and_charges', 0) or 0):.2f}"

    payload = b"".join(
        [
            _build_tlv_value(1, seller_name),
            _build_tlv_value(2, vat_number),
            _build_tlv_value(3, posting_timestamp),
            _build_tlv_value(4, total_amount),
            _build_tlv_value(5, vat_amount),
        ]
    )
    return base64.b64encode(payload).decode("utf-8")


def sync_sales_invoice_qr_payload(doc) -> str | None:
    if not getattr(doc, "name", None) or str(doc.name).startswith("new-sales-invoice"):
        return None

    payload = build_zatca_qr_payload(doc)
    current_payload = getattr(doc, "zatca_qr_payload", None)
    if current_payload != payload:
        doc.zatca_qr_payload = payload
        if hasattr(doc, "db_set"):
            doc.db_set("zatca_qr_payload", payload, update_modified=False)

    return payload


def ensure_public_invoice_qr(
    doc,
    method=None,
    print_format: str | None = None,
    endpoint: str = "tms.api.invoice_public.print_invoice",
):
    if not getattr(doc, "name", None) or doc.name.startswith("new-sales-invoice"):
        return

    return sync_sales_invoice_qr_payload(doc)


def validate_public_invoice_access(doc, token: str | None = None) -> None:
    if frappe.session.user == "Guest" or not doc.has_permission("read"):
        frappe.throw("Not permitted", frappe.PermissionError)

    if token:
        if not getattr(doc, "zatca_qr_png", None) or doc.zatca_qr_png != token:
            frappe.throw("Invalid or expired link", frappe.PermissionError)


def render_sales_invoice_html(name: str, token: str | None = None, print_format: str | None = None) -> str:
    doc = frappe.get_doc("Sales Invoice", name)
    sync_sales_invoice_qr_payload(doc)
    validate_public_invoice_access(doc, token)

    resolved_format = resolve_sales_invoice_print_format(doc, requested_format=print_format)
    return frappe.get_print(
        doctype="Sales Invoice",
        name=name,
        print_format=resolved_format,
        no_letterhead=0,
    )


def render_sales_invoice_pdf(name: str, token: str | None = None, print_format: str | None = None) -> bytes:
    html = render_sales_invoice_html(name, token, print_format=print_format)
    return chrome_get_pdf(html, options={"page-size": "A4"})


def get_sales_invoice_pdf_bytes(doc, print_format: str | None = None) -> bytes:
    sync_sales_invoice_qr_payload(doc)
    resolved_format = resolve_sales_invoice_print_format(doc, requested_format=print_format)
    html = frappe.get_print(
        "Sales Invoice",
        doc.name,
        print_format=resolved_format,
        no_letterhead=0,
    )
    return chrome_get_pdf(html, options={"page-size": "A4"})


def locate_sales_invoice_xml(doc) -> str | None:
    xml_reference = getattr(doc, SALES_INVOICE_XML_FIELD, None)
    if not xml_reference:
        return None

    if os.path.isfile(xml_reference):
        return xml_reference

    site_path = frappe.local.site_path
    if xml_reference.startswith("/private/files/"):
        candidate = os.path.join(site_path, xml_reference.lstrip("/"))
        if os.path.isfile(candidate):
            return candidate
    if xml_reference.startswith("/files/"):
        candidate = os.path.join(site_path, "public", xml_reference.lstrip("/"))
        if os.path.isfile(candidate):
            return candidate

    file_name = os.path.basename(xml_reference)
    attachment = frappe.db.get_value(
        "File",
        {
            "attached_to_doctype": "Sales Invoice",
            "attached_to_name": doc.name,
            "file_name": file_name,
        },
        ["file_url", "is_private"],
        as_dict=True,
    )
    if not attachment or not attachment.file_url:
        return None

    base_folder = "private" if cint(attachment.is_private) else "public"
    candidate = os.path.join(site_path, base_folder, attachment.file_url.lstrip("/"))
    return candidate if os.path.isfile(candidate) else None


def locate_icc_profile() -> str | None:
    candidates = [
        frappe.get_app_path("tms", "public", "sRGB2014.icc"),
        "/usr/share/color/icc/ghostscript/srgb.icc",
        "/usr/share/color/icc/colord/sRGB.icc",
        "/usr/share/color/icc/sRGB.icc",
    ]

    try:
        candidates.insert(1, frappe.get_app_path("zatca_integration", "public", "sRGB2014.icc"))
    except Exception:
        pass

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate

    return None


def build_pdfa_xmp(invoice_name: str) -> bytes:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    xmp = f"""<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:format>application/pdf</dc:format>
      <dc:title>
        <rdf:Alt>
          <rdf:li xml:lang="x-default">Sales Invoice {invoice_name}</rdf:li>
        </rdf:Alt>
      </dc:title>
    </rdf:Description>
    <rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/">
      <xmp:CreateDate>{now}</xmp:CreateDate>
      <xmp:ModifyDate>{now}</xmp:ModifyDate>
      <xmp:MetadataDate>{now}</xmp:MetadataDate>
      <xmp:CreatorTool>TMS ZATCA PDF/A-3B</xmp:CreatorTool>
    </rdf:Description>
    <rdf:Description xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
      <pdfaid:part>3</pdfaid:part>
      <pdfaid:conformance>B</pdfaid:conformance>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
    return xmp.encode("utf-8")


def finalize_pdfa_3b(pdf_bytes: bytes, invoice_name: str, xml_path: str | None = None) -> bytes:
    import pikepdf
    from pikepdf import Array, Dictionary, Name, String

    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        metadata_stream = pdf.make_stream(build_pdfa_xmp(invoice_name))
        metadata_stream["/Subtype"] = Name("/XML")
        metadata_stream["/Type"] = Name("/Metadata")
        pdf.Root["/Metadata"] = metadata_stream
        pdf.Root["/Lang"] = String("en-US")
        pdf.Root["/MarkInfo"] = Dictionary({"/Marked": False})
        pdf.Root["/Trapped"] = Name("/False")

        icc_path = locate_icc_profile()
        if icc_path:
            with open(icc_path, "rb") as icc_file:
                icc_stream = pdf.make_stream(icc_file.read())
            icc_stream["/N"] = 3
            pdf.Root["/OutputIntents"] = Array(
                [
                    Dictionary(
                        {
                            "/Type": Name("/OutputIntent"),
                            "/S": Name("/GTS_PDFA1"),
                            "/OutputConditionIdentifier": "sRGB",
                            "/OutputCondition": "sRGB IEC61966-2.1",
                            "/Info": "sRGB IEC61966-2.1",
                            "/DestOutputProfile": icc_stream,
                        }
                    )
                ]
            )

        if xml_path and os.path.isfile(xml_path):
            with open(xml_path, "rb") as xml_file:
                xml_bytes = xml_file.read()
            embedded_stream = pdf.make_stream(xml_bytes)
            embedded_stream["/Type"] = Name("/EmbeddedFile")
            embedded_stream["/Subtype"] = Name("/application/xml")
            embedded_stream["/Params"] = Dictionary(
                {
                    "/Size": len(xml_bytes),
                    "/ModDate": String(datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%SZ")),
                }
            )
            embedded_ref = pdf.make_indirect(embedded_stream)
            xml_name = f"{invoice_name}_zatca.xml"
            filespec = pdf.make_indirect(
                Dictionary(
                    {
                        "/Type": Name("/Filespec"),
                        "/F": String(xml_name),
                        "/UF": String(xml_name),
                        "/EF": Dictionary({"/F": embedded_ref, "/UF": embedded_ref}),
                        "/Desc": String("ZATCA invoice XML"),
                        "/AFRelationship": Name("/Data"),
                    }
                )
            )
            names = pdf.Root.get("/Names", Dictionary())
            names["/EmbeddedFiles"] = Dictionary({"/Names": Array([String(xml_name), filespec])})
            pdf.Root["/Names"] = names
            pdf.Root["/AF"] = Array([filespec])

        output = io.BytesIO()
        pdf.save(output, linearize=False)
        return output.getvalue()


def generate_sales_invoice_pdfa_3b_bytes(doc, print_format: str | None = None) -> tuple[bytes, str, bool]:
    resolved_format = resolve_sales_invoice_print_format(
        doc,
        requested_format=print_format,
        fallback=DEFAULT_ZATCA_PDFA_PRINT_FORMAT,
    )
    pdf_bytes = get_sales_invoice_pdf_bytes(doc, print_format=resolved_format)
    xml_path = locate_sales_invoice_xml(doc)
    final_bytes = finalize_pdfa_3b(pdf_bytes, doc.name, xml_path=xml_path)
    return final_bytes, resolved_format, bool(xml_path)


@frappe.whitelist()
def generate_sales_invoice_pdfa_3b(invoice_name: str, print_format: str | None = None, attach: int = 1):
    if not frappe.db.exists("Sales Invoice", invoice_name):
        frappe.throw(f"Sales Invoice {invoice_name} does not exist")

    doc = frappe.get_doc("Sales Invoice", invoice_name)
    pdf_bytes, resolved_format, xml_embedded = generate_sales_invoice_pdfa_3b_bytes(
        doc,
        print_format=print_format,
    )

    response = {
        "invoice": invoice_name,
        "print_format": resolved_format,
        "xml_embedded": xml_embedded,
    }

    if cint(attach):
        file_doc = save_file(
            fname=f"Sales-Invoice-{invoice_name}-PDF-A3B.pdf".replace("/", "-"),
            content=pdf_bytes,
            dt="Sales Invoice",
            dn=invoice_name,
            is_private=1,
        )
        response["file_name"] = file_doc.file_name
        response["file_url"] = file_doc.file_url
        response["file_id"] = file_doc.name

    frappe.local.response.filename = f"{invoice_name}-PDF-A3B.pdf".replace("/", "-")
    frappe.local.response.filecontent = pdf_bytes
    frappe.local.response.type = "download"
    frappe.local.response.display_content_as = "inline"
    frappe.local.response.content_type = "application/pdf"

    return response
