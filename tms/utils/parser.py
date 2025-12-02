# /home/xg/xg-b/apps/tms/tms/utils/parser.py
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
    "نيبال": "Nepal"
}

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def normalize_text(text: str) -> str:
    """Remove direction markers and normalize Arabic digits."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u200e", "").replace("\u200f", "")
    text = text.translate(ARABIC_DIGITS)
    return text

def parse_passenger_details(raw_text: str, fixed_text: str):
    """Extract name, ID, and nationality from mixed Arabic/English OCR text."""
    text = normalize_text(raw_text + "\n" + fixed_text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    joined = " ".join(lines)

    name = id_no = nationality = None

    # --- Name ---
    candidates = [l for l in lines if re.search(r"[A-Z]{3,}", l)]
    if candidates:
        name = max(candidates, key=len).strip().title()

    # --- ID (Arabic or English digits) ---
    match_id = re.search(r"\b([0-9٠-٩]{9,12})\b", joined)
    if match_id:
        id_no = match_id.group(1).translate(ARABIC_DIGITS)

    # --- Nationality ---
    match_nat = re.search(r"الجنسية[:\-\s]+([اأإآء-يA-Za-z ]+)", joined)
    if match_nat:
        nat = re.sub(r"[^اأإآء-يA-Za-z]", "", match_nat.group(1)).strip()
        nationality = AR_COUNTRY_MAP.get(nat, nat.title())

    return {"name": name, "id_no": id_no, "nationality": nationality}

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
