import frappe, base64

def run():
    doc = frappe.get_doc("Sales Invoice", "ACC-SINV-2026-00014")
    
    ret = {
        "apply_retention": doc.get("apply_retention"),
        "retention_percentage": doc.get("retention_percentage"),
        "retention_amount": doc.get("retention_amount"),
        "grand_total": doc.grand_total,
        "rounded_total": doc.rounded_total,
        "net_payable_after_retention": doc.get("net_payable_after_retention"),
        "outstanding_amount": doc.outstanding_amount,
        "total": doc.total,
        "total_taxes_and_charges": doc.total_taxes_and_charges,
    }
    
    print("=== Invoice Data ===")
    for k, v in ret.items():
        print(f"  {k}: {v}")
    
    payload = doc.get("zatca_qr_payload") or ""
    print(f"\n=== QR Payload ===")
    print(f"  length: {len(payload)}")
    print(f"  raw (first 80): {repr(payload[:80])}")
    
    try:
        decoded = base64.b64decode(payload).decode("utf-8", errors="replace")
        print(f"  decoded: {repr(decoded)}")
    except:
        print(f"  could not base64 decode")
        try:
            decoded = base64.b64decode(payload + "==").decode("utf-8", errors="replace")
            print(f"  decoded (padded): {repr(decoded)}")
        except:
            print(f"  not base64 payload")
