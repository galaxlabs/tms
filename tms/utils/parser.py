import re
from unidecode import unidecode

def parse_passenger_details(text):
    clean = " ".join(text.split())
    name = re.search(r"(Name|Full Name)[:\- ]+([A-Z][A-Za-z ]+)", clean, re.I)
    id_no = re.search(r"(ID|Iqama|Passport)[#:\- ]+([A-Z]?\d{6,12})", clean, re.I)
    nationality = re.search(r"(Nationality)[:\- ]+([A-Za-z ]+)", clean, re.I)

    return {
        "name": name.group(2).strip() if name else None,
        "id_no": id_no.group(2).strip() if id_no else None,
        "nationality": nationality.group(2).strip() if nationality else None
    }
