"""Recover source from the context PDF, even if attachments were stripped.
Usage: python tools/recover_pdf.py Raven-Muse-Control_Claude_Context.pdf clean-folder
Requires: pip install pypdf
"""
import base64
import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path
from pypdf import PdfReader

reader = PdfReader(sys.argv[1])
name = "Raven-Muse-Control_Source.zip"
raw = reader.attachments[name][0] if name in reader.attachments else None
if raw is None:
    chunks = []
    for page in reader.pages:
        chunks.extend(re.findall(r"(?m)^RMC64:([A-Za-z0-9+/=]+)\s*$", page.extract_text() or ""))
    if not chunks:
        raise SystemExit("No archive attachment or text payload found")
    raw = base64.b64decode("".join(chunks), validate=True)
expected = (reader.metadata or {}).get("/MuseArchiveSHA256")
actual = hashlib.sha256(raw).hexdigest()
if expected and actual != expected:
    raise SystemExit("Source archive checksum mismatch")
root = Path(sys.argv[2]).resolve()
root.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for item in z.infolist():
        dest = (root / item.filename).resolve()
        if root not in dest.parents:
            raise SystemExit("Unsafe archive path")
        if item.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        data = z.read(item)
        if dest.exists() and dest.read_bytes() != data:
            raise SystemExit("Refusing to overwrite different file: " + str(dest))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
print("Recovered Raven-Muse-Control. Archive SHA-256:", actual)
print("Read CLAUDE.md, README.md and TEST_RESULTS.md in", root)
