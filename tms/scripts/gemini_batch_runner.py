import os, json, mimetypes, sys
from google import genai
from google.genai import types

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

SCHEMA = {
  "type": "object",
  "properties": {
    "passengers": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "index": {"type": "integer"},
          "full_name": {"type": "string"},
          "id_no": {"type": "string"},
          "nationality": {"type": "string"},
          "confidence": {"type": "number"},
          "notes": {"type": "string"}
        },
        "required": ["index","full_name","id_no","nationality","confidence","notes"]
      }
    },
    "global_notes": {"type": "string"}
  },
  "required": ["passengers","global_notes"]
}

def _mime(path: str) -> str:
    mt, _ = mimetypes.guess_type(path)
    return mt or "application/octet-stream"

def run(expected_count: int, paths):
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("Missing GEMINI_API_KEY (or GOOGLE_API_KEY)")

    client = genai.Client(api_key=key)

    prompt = f"""
You will receive {len(paths)} passenger ID images, one person per image, in order.
Return ONLY valid JSON matching the schema.

Rules:
- Keep same order: first image=index 1, second=index 2...
- Do NOT merge people.
- If unreadable, return empty strings and low confidence.
- Do NOT guess ID numbers.
- Output must contain exactly {expected_count} passengers.
""".strip()

    contents = [prompt]
    for p in paths:
        with open(p, "rb") as f:
            b = f.read()
        contents.append(types.Part.from_bytes(data=b, mime_type=_mime(p)))

    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=SCHEMA,
        temperature=0.0,
    )

    r = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
    out = r.parsed if getattr(r, "parsed", None) is not None else json.loads(r.text)
    print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    # usage: python gemini_batch_runner.py 3 img1 img2 img3
    expected = int(sys.argv[1])
    run(expected, sys.argv[2:])
