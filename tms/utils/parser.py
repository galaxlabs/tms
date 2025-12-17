# /home/xg/xg-b/apps/tms/tms/utils/parser.py
# tms/utils/parser.py


import re
import unicodedata

AR_COUNTRY_MAP = {
    "مصر": "Egypt",
    "السعودية": "Saudi Arabia",
    "المملكة العربية السعودية": "Saudi Arabia",
    "باكستان": "Pakistan",
    "الهند": "India",
    "اليمن": "Yemen",
    "السودان": "Sudan",
    "سوريا": "Syria",
    "الأردن": "Jordan",
    "فلسطين": "Palestine",
    "بنغلاديش": "Bangladesh",
    "نيبال": "Nepal",
}

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_text(text: str) -> str:
    """Remove direction markers and normalize Arabic digits."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u200e", "").replace("\u200f", "")
    text = text.translate(ARABIC_DIGITS)
    return text

def extract_mrz_name_and_nat(text: str):
    """
    Try to extract (full_name, nationality_code) from MRZ line like:
    P<PAKMAJEED<<NAZIA<<<<<<<<<<<<<<<<<<<<<<<<<<
    Returns (full_name, nat_code) or (None, None)
    """
    if not text:
        return None, None

    # Uppercase and remove spaces for easier matching
    t = normalize_text(text).upper().replace(" ", "")

    # Classic MRZ pattern: P< + 3-letter country + surname + << + given names
    m = re.search(r"P<([A-Z]{3})([A-Z<]+)<<([A-Z<]+)", t)
    if not m:
        return None, None

    nat_code = m.group(1)        # e.g. PAK
    surname_raw = m.group(2)     # MAJEED<<
    given_raw = m.group(3)       # NAZIA<<<<

    surname = surname_raw.replace("<", " ").strip()
    given = given_raw.replace("<", " ").strip()

    # Capitalize properly
    surname = " ".join(w.capitalize() for w in surname.split())
    given = " ".join(w.capitalize() for w in given.split())

    full_name = (given + " " + surname).strip()   # ✅ Given + Surname → Nazia Majeed

    return full_name, nat_code

def try_parse_passport_mrz_like(text: str):
    """
    Handle lines like:
      'Cm05714924 Pak8902188F 28102493110160491492<72'
    which is basically a broken MRZ second line.

    Strategy:
    - Find passport number: 1–2 letters + 7–8 digits + 1 check digit.
      We keep the part without the check digit, e.g. 'CM0571492'.
    - Collect ALL 3-letter codes (PAK, SAU, IND, AND, ...).
      We'll choose the most likely nationality later.
    """
    line = " ".join(l for l in text.splitlines())
    line_up = line.upper()

    doc_no = ""
    nat_codes = []

    # 1) Passport doc_no: 1–2 letters + 7–8 digits + 1 check digit
    m_doc = re.search(r"\b([A-Z]{1,2}[0-9]{7,8})[0-9<]", line_up)
    if m_doc:
        raw_doc = m_doc.group(1)
        # if longer than 9 chars, trim to 9 (common passport length)
        doc_no = raw_doc[:9] if len(raw_doc) > 9 else raw_doc

    # 2) All 3-letter uppercase codes; we will pick the best one
    nat_codes = re.findall(r"\b([A-Z]{3})\b", line_up)

    return {
        "id_no": doc_no,
        "nat_codes": nat_codes,   # e.g. ['AND', 'PAK', ...]
    }

def parse_passenger_details(raw_text: str, fixed_text: str):
    """
    Extract name, ID, and nationality from mixed Arabic/English OCR text.

    - Uses MRZ when available (passports)
    - Has heuristics for Arabic cards (Iqama, etc.)
    """
    text = normalize_text((raw_text or "") + "\n" + (fixed_text or ""))
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    joined = " ".join(lines)

    name = None
    id_no = None
    nationality = None

    # -------------------------
    # ICAO / country code map for MRZ
    # -------------------------
    code_map = {
        "PAK": "Pakistan",
        "SAU": "Saudi Arabia",
        "KSA": "Saudi Arabia",
        "IND": "India",
        "EGY": "Egypt",
        "BGD": "Bangladesh",
        "NPL": "Nepal",
        "YEM": "Yemen",
        "JOR": "Jordan",
        "SYR": "Syria",
    }

    # -------------------------
    # 1) Try MRZ first (passports)
    # -------------------------
    mrz_name, mrz_nat_code = extract_mrz_name_and_nat(text)
    if mrz_name:
        name = mrz_name

    if mrz_nat_code:
        nationality = code_map.get(mrz_nat_code, mrz_nat_code.title())

    # -------------------------
    # 2) Try to detect doc number (passport / ID)
    # -------------------------
    # If CM0571492 or similar exists, prefer that
    m_doc = re.search(r"\b([A-Z]{1,2}[0-9]{6,})\b", joined)
    if m_doc:
        id_no = m_doc.group(1)

    # Fallback numeric ID (Iqama / national ID etc.)
    if not id_no:
        m_id = re.search(r"\b([0-9]{8,13})\b", joined)
        if m_id:
            id_no = m_id.group(1)

    # -------------------------
    # 3) Arabic cards (Iqama) & general name heuristics
    # -------------------------
    # If MRZ already gave us a good name, we still try to improve Iqama cases,
    # but for passports it's usually enough.
    STOP_PHRASES = [
        # English boilerplate
        "to all whom it may concern",
        "request and require",
        "requires and requests",
        "bearer such assistance",
        "afford the bearer",
        "this passport",
        "place of issue",
        "date of issue",
        "valid until",
        "ministry of foreign",
        "ministry of interior",
        "government of pakistan",
        "government of",
        "immigration and passports",
        "islamic republic of pakistan",
        "islamic republic of",
        # Arabic boilerplate (cards, iqama)
        "المملكة العربية السعودية",          # Kingdom of Saudi Arabia
        "وزارة الداخلية",
        "وزارة",
        "الجوازات",
        "هوية مقيم",
        "المديرية العامة للجوازات",
        "صاحب العمل",
        "شركة",
        "الديانة",
        "الإسلام",
        "الجنسية",
    ]

    JOB_KEYWORDS = [
        "عامل",             # worker
        "عامل انشاءات",
        "عامل إنشاءات",
        "سائق",             # driver
        "مهندس",           # engineer
        "طبيب",             # doctor
        "ممرض",             # nurse
        "محاسب",           # accountant
        "موظف",             # employee
    ]

    if not name:
        candidate_name_lines = []
        for l in lines:
            low = l.lower()

            # skip boilerplate
            if any(p in low for p in STOP_PHRASES):
                continue

            # skip job lines
            if any(j in l for j in JOB_KEYWORDS):
                continue

            # skip lines with too many digits
            digit_ratio = len(re.findall(r"[0-9]", l)) / max(len(l), 1)
            if digit_ratio > 0.3:
                continue

            words = l.split()
            if not (1 <= len(words) <= 6):
                continue

            # must have some letters
            if not re.search(r"[A-Za-z\u0600-\u06FF]{3,}", l):
                continue

            # skip big all-caps boilerplate
            if re.fullmatch(r"[A-Z\s,\.]+", l) and len(words) > 3:
                continue

            candidate_name_lines.append(l)

        if candidate_name_lines:
            # Special case: multiple single-word all-caps names (NAZIA / MAJEED)
            one_caps = [
                ln for ln in candidate_name_lines
                if len(ln.split()) == 1 and ln.isupper()
            ]
            if len(one_caps) >= 2:
                given = one_caps[0].title()
                surname = one_caps[1].title()
                name = f"{given} {surname}"
            else:
                # General: pick something that looks like a 2-word name
                def name_score(s: str):
                    w = len(s.split())
                    return (abs(w - 2), len(s))

                best = sorted(candidate_name_lines, key=name_score)[0]
                best = re.sub(r"[^A-Za-z\s\u0600-\u06FF]", " ", best)
                best = re.sub(r"\s+", " ", best).strip()
                name = best

    # -------------------------
    # 4) Nationality cleanup (Arabic blobs → country)
    # -------------------------
    if nationality:
        # If nationality contains a known Arabic country substring, use that mapping
        for ar, en in AR_COUNTRY_MAP.items():
            if ar in nationality:
                nationality = en
                break

    if not nationality:
        # Look for line containing الجنسية: XXX
        m_nat = re.search(r"الجنسية[:\-\s]+([اأإآء-يA-Za-z ]+)", joined)
        if m_nat:
            nat_raw = m_nat.group(1)
            # don't strip all non-letters; keep spaces, then trim by stop words
            nat_clean = nat_raw.strip()

            # cut off at common following labels like الديانة, صاحب العمل, شركة
            for stop in ["الديانة", "صاحب العمل", "صاحبالعمل", "شركة"]:
                idx = nat_clean.find(stop)
                if idx != -1:
                    nat_clean = nat_clean[:idx].strip()
                    break

            # map Arabic country names if possible
            for ar, en in AR_COUNTRY_MAP.items():
                if ar in nat_clean:
                    nationality = en
                    break

            if not nationality:
                nationality = nat_clean.title()

    # -------------------------
    # Final cleanup
    # -------------------------
    name = (name or "").strip()
    id_no = (id_no or "").strip()
    nationality = (nationality or "").strip()

    return {
        "name": name or None,
        "id_no": id_no or None,
        "nationality": nationality or None,
    }

# def parse_passenger_details(raw_text: str, fixed_text: str):
#     """
#     Extract name, ID, and nationality from mixed Arabic/English OCR text.

#     Logic:
#     - Normalize + merge raw & fixed text
#     - Use MRZ-like heuristics for passport ID + nationality code
#     - Use MRZ line (P<...) for full name (Given + Surname)
#     - Heuristics for Arabic cards (Iqama, etc.)
#     """
#     text = normalize_text((raw_text or "") + "\n" + (fixed_text or ""))
#     lines = [l.strip() for l in text.splitlines() if l.strip()]
#     joined = " ".join(lines)

#     name = None
#     id_no = None
#     nationality = None

#     # -------------------------
#     # 0) ICAO / country code map
#     # -------------------------
#     code_map = {
#         "PAK": "Pakistan",
#         "SAU": "Saudi Arabia",
#         "KSA": "Saudi Arabia",
#         "IND": "India",
#         "EGY": "Egypt",
#         "BGD": "Bangladesh",
#         "NPL": "Nepal",
#         "YEM": "Yemen",
#         "JOR": "Jordan",
#         "SYR": "Syria",
#     }

#     # -------------------------
#     # 1) Passport / MRZ-like: ID + nat codes
#     # -------------------------
#     try:
#         mrz_guess = try_parse_passport_mrz_like(joined)
#     except Exception:
#         mrz_guess = {}

#     mrz_doc_no = (mrz_guess.get("id_no") or "").strip()
#     nat_codes = mrz_guess.get("nat_codes") or []

#     if mrz_doc_no:
#         id_no = mrz_doc_no

#     if nat_codes and not nationality:
#         # Prefer known codes
#         for c in nat_codes:
#             if c in code_map:
#                 nationality = code_map[c]
#                 break
#         # Fallback: just use first code as text
#         if not nationality:
#             nationality = nat_codes[0].title()

#     # -------------------------
#     # 2) MRZ line (P<...) → full name = Given + Surname
#     # -------------------------
#     mrz_name = None
#     for l in lines:
#         s = l.strip().upper()
#         if s.startswith("P<"):
#             # Example: P<PAKMAJEED<<NAZIA<<<<<<<<<<<<<<<<<<<<<<<<<<
#             m = re.match(r"^P<([A-Z]{3})([A-Z<]+)<<([A-Z<]+)", s)
#             if m:
#                 issuing_code = m.group(1)
#                 surname_raw = m.group(2)  # MAJEED<<
#                 given_raw = m.group(3)    # NAZIA<<<<

#                 surname = surname_raw.replace("<", " ").strip()
#                 given = given_raw.replace("<", " ").strip()

#                 surname = " ".join(w.capitalize() for w in surname.split())
#                 given = " ".join(w.capitalize() for w in given.split())

#                 # ✅ Ensure order: GivenName Surname → Nazia Majeed
#                 mrz_name = (given + " " + surname).strip()

#                 if not nationality and issuing_code in code_map:
#                     nationality = code_map[issuing_code]
#             break

#     if mrz_name:
#         name = mrz_name

#     # -------------------------
#     # 3) Heuristic Name extraction (only if MRZ didn't give one)
#     # -------------------------
#     if not name:
#         STOP_PHRASES = [
#             # English boilerplate
#             "to all whom it may concern",
#             "request and require",
#             "requires and requests",
#             "bearer such assistance",
#             "afford the bearer",
#             "afford him such",
#             "afford her such",
#             "this passport",
#             "has been issued",
#             "place of issue",
#             "date of issue",
#             "valid until",
#             "minister for foreign",
#             "ministry of foreign",
#             "ministry of interior",
#             "government of pakistan",
#             "government of",
#             "immigration and passports",
#             "islamic republic of pakistan",
#             "islamic republic of",
#             "kingdom of",
#             "republic of",
#             # Arabic boilerplate (Iqama / cards)
#             "الجنسية",
#             "المهنة",
#             "الديانة",
#             "صاحب العمل",
#             "شركة",
#             "وزارة",
#             "الجوازات",
#             "هوية مقيم",
#         ]

#         JOB_KEYWORDS = [
#             "عامل",         # worker
#             "سائق",         # driver
#             "مهندس",       # engineer
#             "طبيب",         # doctor
#             "ممرض",         # nurse
#             "محاسب",       # accountant
#             "موظف",         # employee
#             "عامل انشاءات",
#             "عامل إنشاءات",
#         ]

#         candidate_name_lines = []
#         for l in lines:
#             low = l.lower()

#             # skip known boilerplate
#             if any(p in low for p in STOP_PHRASES):
#                 continue

#             # skip lines that clearly describe job/occupation
#             if any(j in l for j in JOB_KEYWORDS):
#                 continue

#             # Skip lines with too many digits
#             digit_ratio = len(re.findall(r"[0-9]", l)) / max(len(l), 1)
#             if digit_ratio > 0.3:
#                 continue

#             words = l.split()
#             # 1–6 words → good name candidate
#             if not (1 <= len(words) <= 6):
#                 continue

#             # Must contain some letters (Arabic or Latin)
#             if not re.search(r"[A-Za-z\u0600-\u06FF]{3,}", l):
#                 continue

#             # Skip big all-caps Latin boilerplate like "GOVERNMENT OF PAKISTAN"
#             if re.fullmatch(r"[A-Z\s,\.]+", l) and len(words) > 3:
#                 continue

#             candidate_name_lines.append(l)

#         if candidate_name_lines:
#             # Special case: many one-word all-caps lines (NAZIA / MAJEED, etc.)
#             one_word_caps = [
#                 ln for ln in candidate_name_lines
#                 if len(ln.split()) == 1 and ln.isupper()
#             ]
#             if len(one_word_caps) >= 2:
#                 given = one_word_caps[0].title()
#                 surname = one_word_caps[1].title()
#                 name = f"{given} {surname}"
#             else:
#                 # General: choose line that looks most like a 2-word name
#                 def name_score(s: str):
#                     w = len(s.split())
#                     return (abs(w - 2), len(s))  # prefer 2 words, shorter string

#                 best = sorted(candidate_name_lines, key=name_score)[0]
#                 best = re.sub(r"[^A-Za-z\s\u0600-\u06FF]", " ", best)
#                 best = re.sub(r"\s+", " ", best).strip()
#                 name = best

#     # -------------------------
#     # 4) Fallback ID if still empty
#     # -------------------------
#     if not id_no:
#         m_id = re.search(r"\b([0-9]{8,13})\b", joined)
#         if m_id:
#             id_no = m_id.group(1)

#     # -------------------------
#     # 5) Fix nationality blobs (Arabic Iqama etc.)
#     # -------------------------
#     if nationality:
#         # If nationality contains a known Arabic country name, keep only that
#         for ar, en in AR_COUNTRY_MAP.items():
#             if ar in nationality:
#                 nationality = en
#                 break

#     if not nationality:
#         m_nat_ar = re.search(r"الجنسية[:\-\s]+([اأإآء-يA-Za-z ]+)", joined)
#         if m_nat_ar:
#             nat_raw = re.sub(r"[^اأإآء-يA-Za-z]", "", m_nat_ar.group(1)).strip()
#             nationality = AR_COUNTRY_MAP.get(nat_raw, nat_raw.title())

#     # -------------------------
#     # Final cleanup
#     # -------------------------
#     name = (name or "").strip()
#     id_no = (id_no or "").strip()
#     nationality = (nationality or "").strip()

#     return {
#         "name": name or None,
#         "id_no": id_no or None,
#         "nationality": nationality or None,
#     }

# def parse_passenger_details(raw_text: str, fixed_text: str):
#     """
#     Extract name, ID, and nationality from mixed Arabic/English OCR text.

#     Logic:
#     - Normalize + merge raw & fixed text
#     - Use MRZ-like heuristics for passport ID + nationality code
#     - Use MRZ line (P<...) for full name (NAZIA MAJEED)
#     - Fallback heuristics for name / ID / nationality
#     """
#     text = normalize_text((raw_text or "") + "\n" + (fixed_text or ""))
#     lines = [l.strip() for l in text.splitlines() if l.strip()]
#     joined = " ".join(lines)

#     name = None
#     id_no = None
#     nationality = None

#     # -------------------------
#     # 0) Country code map (ICAO-ish)
#     # -------------------------
#     code_map = {
#         "PAK": "Pakistan",
#         "SAU": "Saudi Arabia",
#         "KSA": "Saudi Arabia",
#         "IND": "India",
#         "EGY": "Egypt",
#         "BGD": "Bangladesh",
#         "NPL": "Nepal",
#         "YEM": "Yemen",
#         "JOR": "Jordan",
#         "SYR": "Syria",
#     }

#     # -------------------------
#     # 1) Passport / MRZ-like pass (ID + nat codes)
#     # -------------------------
#     mrz_guess = try_parse_passport_mrz_like(joined)
#     mrz_doc_no = mrz_guess.get("id_no") or ""
#     nat_codes = mrz_guess.get("nat_codes") or []

#     if mrz_doc_no:
#         id_no = mrz_doc_no

#     if nat_codes and not nationality:
#         # 1st priority: codes we know (PAK, SAU, ...)
#         for c in nat_codes:
#             if c in code_map:
#                 nationality = code_map[c]
#                 break

#         # 2nd priority: if nothing matched, at least use the first code as text
#         if not nationality:
#             nationality = nat_codes[0].title()

#     # -------------------------
#     # 2) MRZ line (P<...) → full name (given + surname)
#     # -------------------------
#     mrz_name = None
#     for l in lines:
#         s = l.strip().upper()
#         if s.startswith("P<"):
#             # Example: P<PAKMAJEED<<NAZIA<<<<<<<<<<<<<<<<<<<<<<<<<<
#             m = re.match(r"^P<([A-Z]{3})([A-Z<]+)<<([A-Z<]+)", s)
#             if m:
#                 issuing_code = m.group(1)
#                 surname_raw = m.group(2)  # MAJEED<< or MAJEED<ALI
#                 given_raw = m.group(3)    # NAZIA<<<<

#                 surname = surname_raw.replace("<", " ").strip()
#                 given = given_raw.replace("<", " ").strip()

#                 surname = " ".join(w.capitalize() for w in surname.split())
#                 given = " ".join(w.capitalize() for w in given.split())

#                 # We return: GivenName Surname  → "Nazia Majeed"
#                 mrz_name = (given + " " + surname).strip()

#                 # If nationality still empty, use issuing code
#                 if not nationality and issuing_code in code_map:
#                     nationality = code_map[issuing_code]
#             break

#     if mrz_name:
#         name = mrz_name

#     # -------------------------
#     # 3) Heuristic Name extraction (only if MRZ couldn't give us a name)
#     # -------------------------
#     if not name:
#         STOP_PHRASES = [
#             "to all whom it may concern",
#             "request and require",
#             "requires and requests",
#             "bearer such assistance",
#             "afford the bearer",
#             "afford him such",
#             "afford her such",
#             "this passport",
#             "has been issued",
#             "place of issue",
#             "date of issue",
#             "valid until",
#             "minister for foreign",
#             "ministry of foreign",
#             "ministry of interior",     # 👈 added
#             "government of pakistan",
#             "government of",
#             "immigration and passports",
#             "islamic republic of pakistan",
#             "islamic republic of",
#             "kingdom of",
#             "republic of",
#         ]

#         candidate_name_lines = []
#         for l in lines:
#             low = l.lower()

#             # skip known boilerplate / legal phrases
#             if any(p in low for p in STOP_PHRASES):
#                 continue

#             # Skip lines with too many digits (likely MRZ / numbers)
#             digit_ratio = len(re.findall(r"[0-9]", l)) / max(len(l), 1)
#             if digit_ratio > 0.3:
#                 continue

#             words = l.split()
#             # Relax a bit: 1–6 words (to catch 'NAZIA', 'MAJEED', etc.)
#             if not (1 <= len(words) <= 6):
#                 continue

#             # Must contain some Latin or Arabic letters
#             if not re.search(r"[A-Za-z\u0600-\u06FF]{3,}", l):
#                 continue

#             # Skip all-caps long boilerplate like "GOVERNMENT OF PAKISTAN"
#             if re.fullmatch(r"[A-Z\s,\.]+", l) and len(words) > 3:
#                 continue

#             candidate_name_lines.append(l)

#         if candidate_name_lines:
#             # If we have multiple short one-word lines (NAZIA / MAJEED),
#             # join the best two one-word uppercase lines.
#             one_word_caps = [
#                 ln for ln in candidate_name_lines
#                 if len(ln.split()) == 1 and ln.isupper()
#             ]
#             if len(one_word_caps) >= 2:
#                 # Use first two as Given + Surname
#                 given = one_word_caps[0].title()
#                 surname = one_word_caps[1].title()
#                 name = f"{given} {surname}"
#             else:
#                 # Otherwise: choose the line that "looks" most like a name
#                 def name_score(s: str):
#                     w = len(s.split())
#                     return (abs(w - 2), len(s))  # prefer 2-word, shorter

#                 best = sorted(candidate_name_lines, key=name_score)[0]
#                 best = re.sub(r"[^A-Za-z\s\u0600-\u06FF]", " ", best)
#                 best = re.sub(r"\s+", " ", best).strip()
#                 name = best

#     # -------------------------
#     # 4) Fallback ID if still empty
#     # -------------------------
#     if not id_no:
#         m_id = re.search(r"\b([0-9]{8,13})\b", joined)
#         if m_id:
#             id_no = m_id.group(1)

#     # -------------------------
#     # 5) Fallback Arabic nationality if still empty
#     # -------------------------
#     if not nationality:
#         m_nat_ar = re.search(r"الجنسية[:\-\s]+([اأإآء-يA-Za-z ]+)", joined)
#         if m_nat_ar:
#             nat_raw = re.sub(r"[^اأإآء-يA-Za-z]", "", m_nat_ar.group(1)).strip()
#             nationality = AR_COUNTRY_MAP.get(nat_raw, nat_raw.title())

#     # Final cleanup
#     name = (name or "").strip()
#     id_no = (id_no or "").strip()
#     nationality = (nationality or "").strip()

#     return {
#         "name": name or None,
#         "id_no": id_no or None,
#         "nationality": nationality or None,
#     }

# import re
# import unicodedata

# # Basic Arabic country name → English mapping used as a fallback
# AR_COUNTRY_MAP = {
#     "مصر": "Egypt",
#     "السعودية": "Saudi Arabia",
#     "المملكة العربية السعودية": "Saudi Arabia",
#     "باكستان": "Pakistan",
#     "الهند": "India",
#     "اليمن": "Yemen",
#     "السودان": "Sudan",
#     "سوريا": "Syria",
#     "الأردن": "Jordan",
#     "فلسطين": "Palestine",
#     "بنغلاديش": "Bangladesh",
#     "نيبال": "Nepal",
# }

# # Arabic → Western digits
# ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# # Optional helpers – if not installed, code still works without them
# try:
#     from mrz.base.mrtd import MRZ  # type: ignore
# except Exception:
#     MRZ = None

# try:
#     import pycountry  # type: ignore
# except Exception:
#     pycountry = None


# def normalize_text(text: str) -> str:
#     """Remove direction markers and normalize Arabic digits."""
#     if not text:
#         return ""
#     text = unicodedata.normalize("NFKC", text)
#     text = text.replace("\u200e", "").replace("\u200f", "")
#     text = text.translate(ARABIC_DIGITS)
#     return text


# def _iso3_to_country(code: str):
#     """Map 3-letter ISO code (e.g. PAK) → full country name."""
#     if not code:
#         return None
#     code = code.upper().strip()
#     # Fast path for common codes
#     if code == "PAK":
#         return "Pakistan"
#     if code == "SAU":
#         return "Saudi Arabia"
#     if code == "EGY":
#         return "Egypt"

#     if pycountry:
#         try:
#             c = pycountry.countries.get(alpha_3=code)
#             if c:
#                 return c.name
#         except Exception:
#             pass
#     return None


# def _extract_mrz_block(text: str):
#     """
#     Try to find a MRZ-like block:
#     long run of A–Z / 0–9 / < with no spaces.
#     Works even if Vision OCR merged both MRZ lines.
#     """
#     if not text:
#         return None

#     # Work on upper-case and strip spaces/newlines
#     compact = re.sub(r"\s+", "", text.upper())
#     m = re.search(r"[A-Z0-9<]{25,}", compact)
#     return m.group(0) if m else None


# def _parse_mrz_block(mrz_block: str) -> dict:
#     """
#     Extract id_no and nationality from a MRZ-like string.
#     We don't rely fully on the mrz library because Vision output
#     is often slightly corrupted.
#     """
#     result = {"name": None, "id_no": None, "nationality": None}

#     if not mrz_block:
#         return result

#     # 1) Try official MRZ parser if we somehow have full TD3 (2 lines / 88 chars)
#     if MRZ and len(mrz_block) >= 88:
#         try:
#             mrz = MRZ(mrz_block, check=False)
#             full_name = " ".join([mrz.names or "", mrz.surname or ""]).strip()
#             result["name"] = full_name or None
#             if mrz.number:
#                 result["id_no"] = mrz.number.strip("<")
#             if mrz.nationality:
#                 nat = _iso3_to_country(mrz.nationality)
#                 result["nationality"] = nat or mrz.nationality
#             return result
#         except Exception:
#             # fall through to heuristics
#             pass

#     # 2) Heuristic TD3 line-2 style parsing for passports
#     # Typical (rough): <DOCNO><check><NAT><DOB><check><SEX><EXP>...
#     passport = None
#     # 2 letters + 7–8 digits + optional check digit (rough heuristic)
#     m_doc = re.search(r"[A-Z][A-Z0-9]\d{7,8}", mrz_block)
#     if m_doc:
#         passport = m_doc.group(0)
#         # drop trailing check digit if length 10
#         if len(passport) == 10:
#             passport = passport[:-1]
#     else:
#         # fallback: first long alnum run
#         m_doc = re.search(r"[A-Z0-9]{8,10}", mrz_block)
#         if m_doc:
#             passport = m_doc.group(0)

#     if passport:
#         result["id_no"] = passport

#     # Nationality: look for 3-letter code; prefer ones that map to real countries
#     for match in re.finditer(r"[A-Z]{3}", mrz_block):
#         code = match.group(0)
#         nat_name = _iso3_to_country(code)
#         if nat_name:
#             result["nationality"] = nat_name
#             break

#     return result


# def _parse_generic_block(text: str) -> dict:
#     """
#     Generic parser: look through all text for name / id / nationality
#     without using MRZ structure. This is used as a fallback or to
#     enrich data (e.g. better human-readable name) when MRZ gives only
#     machine form.
#     """
#     text = normalize_text(text or "")
#     if not text.strip():
#         return {"name": None, "id_no": None, "nationality": None}

#     lines = [l.strip() for l in text.splitlines() if l.strip()]
#     joined = " ".join(lines)

#     # --- Nationality ---
#     nationality = None

#     # Arabic "الجنسية: ..."
#     m_nat = re.search(r"الجنسية[:\-\s]+([اأإآء-يA-Za-z ]+)", joined)
#     if m_nat:
#         nat_raw = re.sub(r"[^اأإآء-يA-Za-z ]", "", m_nat.group(1)).strip()
#         if nat_raw in AR_COUNTRY_MAP:
#             nationality = AR_COUNTRY_MAP[nat_raw]
#         else:
#             nationality = nat_raw.title()

#     # Direct Arabic country words
#     if not nationality:
#         for ar, en in AR_COUNTRY_MAP.items():
#             if ar in joined:
#                 nationality = en
#                 break

#     # Simple English nationality
#     if not nationality:
#         m_nat_en = re.search(
#             r"\b(Pakistan|India|Bangladesh|Nepal|Yemen|Egypt|Sudan|Syria|Jordan)\b",
#             joined,
#             re.I,
#         )
#         if m_nat_en:
#             nationality = m_nat_en.group(1).title()

#     # --- ID ---
#     id_no = None
#     # Prefer long numeric blocks, 9–12 digits (Iqama style)
#     m_id = re.search(r"\b\d{9,12}\b", joined)
#     if m_id:
#         id_no = m_id.group(0)

#     # --- Name ---
#     # Choose the "most name-like" line: contains letters, at least 2 words, not labels
#     name_candidates = []
#     for l in lines:
#         if not re.search(r"[A-Za-z]", l):
#             continue
#         # Skip lines that look like headers
#         if re.search(r"PASSPORT|KINGDOM|REPUBLIC|ISLAMIC|MINISTRY", l, re.I):
#             continue
#         words = l.split()
#         if len(words) < 2:
#             continue
#         name_candidates.append(l)

#     full_name = None
#     if name_candidates:
#         cand = max(name_candidates, key=len)
#         # Remove obvious labels / nationality words
#         cand = re.sub(r"(?i)\b(name|full name|الاسم)\b[:\-\s]*", "", cand)
#         cand = re.sub(
#             r"(?i)\b(Pakistan|India|Bangladesh|Nepal|Yemen|Saudi|Arabia)\b", "", cand
#         )
#         cand = re.sub(r"\s+", " ", cand).strip()
#         if cand:
#             full_name = cand.title()

#     return {
#         "name": full_name,
#         "id_no": id_no,
#         "nationality": nationality,
#     }


# def parse_passenger_details(raw_text: str, fixed_text: str):
#     """
#     High-level parser used by OCR manager.

#     1) Normalize & combine raw/fixed text.
#     2) Try to detect a MRZ block and decode id/nationality from it.
#     3) Use generic heuristics to get a human-friendly name and fill any
#        fields MRZ did not provide.
#     4) Compute a simple confidence score.
#     """
#     raw_text = raw_text or ""
#     fixed_text = fixed_text or ""
#     combined = normalize_text(raw_text + "\n" + fixed_text)

#     if not combined.strip():
#         return {"name": None, "id_no": None, "nationality": None, "confidence": 0}

#     # 1) MRZ path (for passports / Iqama with MRZ-like zone)
#     mrz_block = _extract_mrz_block(combined)
#     mrz_data = (
#         _parse_mrz_block(mrz_block)
#         if mrz_block
#         else {"name": None, "id_no": None, "nationality": None}
#     )

#     # 2) Generic text parsing (excluding MRZ block if we found one)
#     generic_text = combined.replace(mrz_block, " ") if mrz_block else combined
#     generic_data = _parse_generic_block(generic_text)

#     # 3) Merge
#     name = mrz_data.get("name") or generic_data.get("name")
#     id_no = mrz_data.get("id_no") or generic_data.get("id_no")
#     nationality = mrz_data.get("nationality") or generic_data.get("nationality")

#     # 4) Confidence
#     confidence = 0
#     if name:
#         confidence += 40
#     if id_no:
#         confidence += 40
#     if nationality:
#         confidence += 20

#     return {
#         "name": name,
#         "id_no": id_no,
#         "nationality": nationality,
#         "confidence": min(confidence, 100),
#     }













# def parse_passenger_details(raw_text: str, fixed_text: str):
#     """
#     Extract name, ID, nationality from mixed Arabic/English OCR text.

#     This version:
#       - normalizes text
#       - prefers passport-like IDs (e.g. CM0571492)
#       - falls back to long numeric IDs
#       - tries to find nationality via keywords or 3-letter country codes
#       - heuristically extracts a person name line
#     """
#     text = normalize_text((raw_text or "") + "\n" + (fixed_text or ""))
#     lines = [l.strip() for l in text.splitlines() if l.strip()]
#     joined = " ".join(lines)

#     # ===== ID =====
#     id_no = _extract_id(joined)

#     # ===== Nationality =====
#     nationality = _extract_nationality(joined)

#     # ===== Name =====
#     name = _extract_name(lines)

#     return {
#         "name": name,
#         "id_no": id_no,
#         "nationality": nationality,
#     }

# import re
# import unicodedata

# AR_COUNTRY_MAP = {
#     "مصر": "Egypt",
#     "السعودية": "Saudi Arabia",
#     "المملكة العربية السعودية": "Saudi Arabia",
#     "باكستان": "Pakistan",
#     "الهند": "India",
#     "اليمن": "Yemen",
#     "السودان": "Sudan",
#     "سوريا": "Syria",
#     "الأردن": "Jordan",
#     "فلسطين": "Palestine",
#     "بنغلاديش": "Bangladesh",
#     "نيبال": "Nepal"
# }

# ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# def normalize_text(text: str) -> str:
#     """Remove direction markers and normalize Arabic digits."""
#     text = unicodedata.normalize("NFKC", text)
#     text = text.replace("\u200e", "").replace("\u200f", "")
#     text = text.translate(ARABIC_DIGITS)
#     return text

# def parse_passenger_details(raw_text: str, fixed_text: str):
#     """Extract name, ID, and nationality from mixed Arabic/English OCR text."""
#     text = normalize_text(raw_text + "\n" + fixed_text)
#     lines = [l.strip() for l in text.splitlines() if l.strip()]
#     joined = " ".join(lines)

#     name = id_no = nationality = None

#     # --- Name ---
#     candidates = [l for l in lines if re.search(r"[A-Z]{3,}", l)]
#     if candidates:
#         name = max(candidates, key=len).strip().title()

#     # --- ID (Arabic or English digits) ---
#     match_id = re.search(r"\b([0-9٠-٩]{9,12})\b", joined)
#     if match_id:
#         id_no = match_id.group(1).translate(ARABIC_DIGITS)

#     # --- Nationality ---
#     match_nat = re.search(r"الجنسية[:\-\s]+([اأإآء-يA-Za-z ]+)", joined)
#     if match_nat:
#         nat = re.sub(r"[^اأإآء-يA-Za-z]", "", match_nat.group(1)).strip()
#         nationality = AR_COUNTRY_MAP.get(nat, nat.title())

#     return {"name": name, "id_no": id_no, "nationality": nationality}

# import re
# from unidecode import unidecode

# AR_COUNTRY_MAP = {
#     "مصر": "Egypt", "السعودية": "Saudi Arabia", "باكستان": "Pakistan",
#     "الهند": "India", "اليمن": "Yemen", "السودان": "Sudan",
#     "سوريا": "Syria", "الأردن": "Jordan", "فلسطين": "Palestine",
#     "بنغلاديش": "Bangladesh", "نيبال": "Nepal"
# }

# def parse_passenger_details(raw_text, fixed_text):
#     """
#     Robust bilingual parser: works with Arabic + English OCR text.
#     Tries three passes → fixed Arabic → raw → ASCII translit.
#     """

#     variants = [
#         "\n".join(l.strip() for l in fixed_text.splitlines() if l.strip()),
#         "\n".join(l.strip() for l in raw_text.splitlines() if l.strip()),
#     ]
#     translit = unidecode(variants[0] or variants[1])
#     variants.append(translit)

#     name = id_no = nationality = None

#     # Ignore obvious headers
#     BAD_WORDS = ("KINGDOM", "MINISTRY", "INTERIOR", "IDENTITY")

#     def likely_name(line):
#         s = line.strip()
#         if len(s) < 10 or any(w in s for w in BAD_WORDS):
#             return False
#         upper = sum(c.isupper() for c in s)
#         return upper >= 5 and upper / max(1, len(s.replace(" ", ""))) > 0.5

#     for txt in variants:
#         # --- Name ---
#         if not name:
#             # labeled name
#             m = re.search(r"(?:Name|Full Name|Passenger)\s*[:\-]\s*([A-Za-z ]{5,})", txt, re.I)
#             if m:
#                 name = m.group(1).strip()
#         if not name:
#             # longest uppercase line
#             lines = [l for l in txt.splitlines() if likely_name(l)]
#             if lines:
#                 name = max(lines, key=len).strip()

#         # --- ID ---
#         if not id_no:
#             m = re.search(r"\b(\d{10,12})\b", txt)
#             if m:
#                 id_no = m.group(1)

#         # --- Nationality ---
#         if not nationality:
#             m = re.search(r"(?:Nationality|Country)\s*[:\-]\s*([A-Za-z ]+)", txt, re.I)
#             if m:
#                 nationality = m.group(1).strip()
#         if not nationality:
#             m = re.search(r"الجنسية[:\-\s]+([اأإآء-يA-Za-z ]+)", txt)
#             if m:
#                 nat_ar = m.group(1).strip()
#                 nationality = AR_COUNTRY_MAP.get(nat_ar, nat_ar)

#     if name:
#         name = re.sub(r"\s{2,}", " ", name).title()
#     if nationality:
#         nationality = nationality.title()

#     return {"name": name, "id_no": id_no, "nationality": nationality}

# # tms/utils/parser.py
# import re
# from unidecode import unidecode

# AR_COUNTRY_MAP = {
#     "مصر": "Egypt", "السعودية": "Saudi Arabia", "المملكة العربية السعودية": "Saudi Arabia",
#     "باكستان": "Pakistan", "الهند": "India", "اليمن": "Yemen", "السودان": "Sudan",
#     "سوريا": "Syria", "الأردن": "Jordan", "فلسطين": "Palestine", "بنغلاديش": "Bangladesh",
#     "نيبال": "Nepal"
# }

# EXCLUDE_UPPER_LINES = (
#     "KINGDOM OF SAUDI ARABIA", "MINISTRY OF INTERIOR", "RESIDENT IDENTITY",
#     "KINGDOM", "MINISTRY", "RESIDENT"
# )

# def _longest_upper_name(lines):
#     cand = ""
#     for ln in lines:
#         s = ln.strip()
#         if len(s) < 8: 
#             continue
#         # mostly uppercase & spaces
#         if sum(c.isupper() for c in s) >= max(4, int(0.6*len(s.replace(' ','')))):
#             if not any(h in s for h in EXCLUDE_UPPER_LINES):
#                 if len(s) > len(cand):
#                     cand = s
#     return cand or None

# def _arabic_after(label, text):
#     # find word right after Arabic label like "الجنسية"
#     m = re.search(label + r"\s*[:\-]?\s*([^\n\r]+)", text)
#     if m:
#         # take first token-ish
#         return re.split(r"[^\w\u0600-\u06FF]+", m.group(1).strip())[0]
#     return None

# def parse_passenger_details(raw_text: str, fixed_text: str):
#     """
#     Parse on multiple variants:
#       1) fixed_text (Arabic shaped & RTL-correct)
#       2) raw_text (original)
#       3) transliterated (ASCII) for greedy Latin matches
#     """
#     variants = []
#     for t in (fixed_text, raw_text):
#         t = t or ""
#         t = "\n".join(x.strip() for x in t.splitlines() if x.strip())
#         variants.append(t)
#     translit = unidecode(variants[0] or variants[1])
#     variants.append(translit)

#     name = id_no = nationality = None

#     # 1) Direct label patterns (both languages)
#     for txt in variants:
#         if not name:
#             m = re.search(r"(?:Name|Full Name|Passenger Name|Traveler Name)\s*[:\-]\s*([A-Za-z ]{3,})", txt, re.I)
#             if m: name = m.group(1).strip()

#         if not id_no:
#             # iqama/passport or any 10–12 consecutive digits (Saudi iqama is 10)
#             m = re.search(r"(?:ID|Iqama|Passport|Resident|Identity)\s*(?:No|#)?\s*[:#\-]?\s*([0-9]{10,12})", txt, re.I)
#             if not m:
#                 m = re.search(r"\b(\d{10,12})\b", txt)  # fallback
#             if m: id_no = m.group(1)

#         if not nationality:
#             m = re.search(r"(?:Nationality|Country|Citizenship)\s*[:\-]\s*([A-Za-z ]+)", txt, re.I)
#             if m: nationality = m.group(1).strip()

#     # 2) Arabic label fallbacks
#     if not nationality:
#         nat_ar = _arabic_after("الجنسية", variants[0])
#         if nat_ar:
#             nationality = AR_COUNTRY_MAP.get(nat_ar, nat_ar)

#     # 3) Heuristic name: longest uppercase line (skip headers)
#     if not name:
#         lines = (variants[2] or "").splitlines()  # use translit for this
#         name = _longest_upper_name(lines)

#     # Cleanups
#     if name:
#         name = re.sub(r"\s{2,}", " ", name).strip()
#     if nationality:
#         nationality = nationality.title()

#     return {"name": name, "id_no": id_no, "nationality": nationality}

# import re
# import arabic_reshaper
# from bidi.algorithm import get_display
# from unidecode import unidecode


# def parse_passenger_details(text):
#     """
#     Extracts passenger details from bilingual (Arabic + English) Saudi or GCC ID cards.
#     Handles right-to-left Arabic text reshaping and normalization.
#     """

#     # Step 1️⃣: Normalize text
#     # Clean spacing and unify formatting
#     clean = " ".join(text.split())
    
#     # Step 2️⃣: Fix Arabic text direction
#     try:
#         reshaped = arabic_reshaper.reshape(clean)
#         fixed_text = get_display(reshaped)
#     except Exception:
#         fixed_text = clean  # fallback if reshaping fails

#     # Step 3️⃣: Transliterate to ASCII for regex matching on English/Latin text
#     translit = unidecode(fixed_text)

#     # Step 4️⃣: Define regex patterns (Arabic + English)
#     patterns = {
#         "name": [
#             r"(?:Name|Full Name|Passenger Name|Traveler Name)[:\-\s]+([A-Za-z ]+)",
#             r"([A-Z]{3,}(?: [A-Z]{2,}){1,3})",  # fallback for long uppercase English name
#             r"الاسم[:\-\s]+([اأإآء-ي ]+)"        # Arabic "الاسم"
#         ],
#         "id_no": [
#             r"(?:ID|Iqama|Passport|Passport No|ID No|Resident|Residency|Identity)[:#\-\s]*([0-9]{6,15})",
#             r"الرقم[:\-\s]*([0-9]{6,15})"
#         ],
#         "nationality": [
#             r"(?:Nationality|Country|Citizenship)[:\-\s]+([A-Za-z ]+)",
#             r"الجنسية[:\-\s]+([اأإآء-يA-Za-z ]+)"
#         ]
#     }

#     # Step 5️⃣: Helper to test multiple patterns safely
#     def find_match(pattern_list, text):
#         for p in pattern_list:
#             match = re.search(p, text, re.I)
#             if match:
#                 return match.group(1).strip()
#         return None

#     # Step 6️⃣: Extract each field from both Arabic and transliterated text
#     name = find_match(patterns["name"], fixed_text) or find_match(patterns["name"], translit)
#     id_no = find_match(patterns["id_no"], fixed_text)
#     nationality = find_match(patterns["nationality"], fixed_text)

#     # Step 7️⃣: Optional: Auto-translate common Arabic nationalities
#     arabic_to_english = {
#         "مصر": "Egypt",
#         "باكستان": "Pakistan",
#         "الهند": "India",
#         "السودان": "Sudan",
#         "بنغلاديش": "Bangladesh",
#         "اليمن": "Yemen",
#         "سوريا": "Syria",
#         "الأردن": "Jordan",
#         "فلسطين": "Palestine",
#         "نيبال": "Nepal"
#     }

#     if nationality in arabic_to_english:
#         nationality = arabic_to_english[nationality]

#     return {
#         "name": name,
#         "id_no": id_no,
#         "nationality": nationality
#     }
