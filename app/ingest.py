import argparse
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from app.config import DATASET
from app.privacy import safe_lines

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
SECTIONS = {"Profile", "Technical Skills", "Experience", "Projects", "Additional Notes"}


def paragraphs(path):
    if path.suffix.lower() != ".docx":
        raise ValueError("Only DOCX resumes are supported.")
    if path.stat().st_size > 2_000_000:
        raise ValueError("Resume exceeds the local demo size limit.")
    with ZipFile(path) as archive:
        if archive.getinfo("word/document.xml").file_size > 2_000_000:
            raise ValueError("Expanded DOCX exceeds the size limit.")
        root = ET.fromstring(archive.read("word/document.xml"))
    return [
        (i, "".join(p.itertext()).strip())
        for i, p in enumerate(root.findall(".//w:body//w:p", NS), 1)
    ]


def resume_chunks(path):
    rows = paragraphs(path)
    match = re.match(r"(CAND-\d{3})_", path.name)
    if not match or not rows or not rows[0][1]:
        raise ValueError("Resume needs a CAND-NNN filename and a name paragraph.")
    candidate_id = match[1]
    name = rows[0][1]
    aliases = {name: candidate_id}
    chunks = []
    section = None
    for paragraph_no, raw in rows[2:]:
        if raw in SECTIONS:
            section = raw
            continue
        if raw == "Education":
            section = None
            continue
        if not section or not raw or raw.startswith("Fictional synthetic profile"):
            continue
        text = safe_lines(raw, aliases)
        if not text:
            continue

        if len(text) > 1800:
            raise ValueError("Paragraph too long: split it before using this demo.")
        chunk_id = f"{candidate_id}:{section.lower().replace(' ', '_')}:{paragraph_no}"
        chunks.append({
            "id": chunk_id, "source_id": candidate_id,
            "candidate_id": candidate_id, "section": section,
            "locator": f"paragraph {paragraph_no}", "text": text,
        })
    if not chunks:
        raise ValueError("Resume has no supported job-relevant content.")
    source = {
        "id": candidate_id, "candidate_id": candidate_id,
        "path": f"resumes/{path.name}", "name": name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    return source, chunks


def load_corpus(dataset=DATASET):
    dataset = Path(dataset)
    jd_path = dataset / "job_description.txt"
    jd = jd_path.read_text(encoding="utf-8-sig")
    criteria = {}
    chunks = []
    for line_no, line in enumerate(jd.splitlines(), 1):
        match = re.match(r"^([RP]\d+)\.\s+(.+)$", line.strip())
        if match:
            key, text = match.groups()
            criteria[key] = text
            chunks.append({
                "id": f"JD:{key}", "source_id": "JD", "candidate_id": None,
                "section": key, "locator": f"line {line_no}", "text": text,
            })
    if set(criteria) != {f"R{i}" for i in range(1, 8)} | {f"P{i}" for i in range(1, 5)}:
        raise ValueError("This demo expects this JD's R1-R7 and P1-P4 criteria.")
    sources = [{
        "id": "JD", "candidate_id": None, "path": "job_description.txt",
        "name": "", "sha256": hashlib.sha256(jd_path.read_bytes()).hexdigest(),
    }]
    files = sorted((dataset / "resumes").glob("*"))
    if not files:
        raise ValueError("No resumes found.")
    for path in files:
        source, rows = resume_chunks(path)
        sources.append(source)
        chunks.extend(rows)
    if len({s["id"] for s in sources}) != len(sources):
        raise ValueError("Duplicate candidate IDs.")
    return sources, chunks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        sources, chunks = load_corpus()
        if not args.dry_run:
            from app.providers import Gateway
            from app.store import Store
            vectors = Gateway().embed([c["text"] for c in chunks])
            Store().replace(sources, chunks, vectors)
        print(json.dumps({"sources": len(sources), "chunks": len(chunks),
                          "dry_run": args.dry_run}))
    except Exception as exc:
        # Avoid printing document content, filenames with names, or provider payloads.
        raise SystemExit(f"Ingestion failed ({type(exc).__name__}). Check files/configuration.")


if __name__ == "__main__":
    main()