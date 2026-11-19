"""Copy a chosen DOCX without changing its bytes and inspect physical table cells."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

N = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
FILES = {
    "lesson": "公開授課教案格式_空白.docx",
    "observation": "TDO公開授課紀錄表及觀察工具_科技央團_觀課者：XXX_1.docx",
}


def inspect_docx(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        if package.testzip():
            raise ValueError("DOCX package CRC check failed")
        body = ET.fromstring(package.read("word/document.xml")).find("w:body", N)
    if body is None:
        raise ValueError("Missing document body")
    result = {"sha256": hashlib.sha256(data).hexdigest(), "paragraphs": [], "tables": []}
    for block_index, block in enumerate(body):
        if block.tag == "{" + N["w"] + "}p":
            text = "".join(t.text or "" for t in block.findall(".//w:t", N))
            result["paragraphs"].append({"body_index": block_index, "text": text})
        elif block.tag == "{" + N["w"] + "}tbl":
            table = {"table_index": len(result["tables"]), "body_index": block_index, "rows": []}
            for row_index, row in enumerate(block.findall("w:tr", N)):
                cells = []
                for cell_index, cell in enumerate(row.findall("w:tc", N)):
                    props = cell.find("w:tcPr", N)
                    span = props.find("w:gridSpan", N) if props is not None else None
                    merge = props.find("w:vMerge", N) if props is not None else None
                    paragraphs = ["".join(t.text or "" for t in p.findall(".//w:t", N)) for p in cell.findall(".//w:p", N)]
                    cells.append({
                        "physical_cell": cell_index, "text": "\n".join(paragraphs),
                        "grid_span": int(span.get("{" + N["w"] + "}val", "1")) if span is not None else 1,
                        "vertical_merge": None if merge is None else merge.get("{" + N["w"] + "}val", "continue"),
                    })
                table["rows"].append({"row": row_index, "cells": cells})
            result["tables"].append(table)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=FILES, required=True)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--template", type=Path)
    choice.add_argument("--bundle", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inspect-json", type=Path)
    args = parser.parse_args()
    if args.output.suffix.lower() != ".docx":
        parser.error("--output must be a .docx file")
    if args.output.exists():
        parser.error("Output already exists; use a new path")
    filename = FILES[args.kind]
    if args.template:
        data = args.template.read_bytes()
        source = str(args.template.resolve())
    elif args.bundle:
        with zipfile.ZipFile(args.bundle) as bundle:
            candidates = [name for name in bundle.namelist() if name.replace("\\", "/").split("/")[-1] == filename]
            if len(candidates) != 1:
                parser.error("Bundle must contain exactly one matching template")
            data = bundle.read(candidates[0])
            source = str(args.bundle.resolve()) + "!" + candidates[0]
    else:
        template = Path(__file__).resolve().parents[1] / "assets" / "templates" / filename
        data = template.read_bytes()
        source = str(template)
        manifest = json.loads((Path(__file__).resolve().parents[1] / "references" / "template_sources.json").read_text(encoding="utf-8"))
        expected = manifest["templates"][args.kind]["sha256"]
        if hashlib.sha256(data).hexdigest() != expected:
            parser.error("Bundled template changed; inspect and update its manifest before use")
    report = inspect_docx(data)
    report.update({"kind": args.kind, "source": source, "output": str(args.output.resolve())})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(data)
    if args.inspect_json:
        args.inspect_json.parent.mkdir(parents=True, exist_ok=True)
        with args.inspect_json.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"output": report["output"], "sha256": report["sha256"], "tables": len(report["tables"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
