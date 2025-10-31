#!/usr/bin/env python3
"""Invoice processing tool for PDF files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover - handled gracefully at runtime
    raise SystemExit(
        "pypdf is required to run this script. Install it via 'pip install pypdf'."
    ) from exc


@dataclass
class InvoiceRecord:
    """Represents an extracted invoice."""

    code: str
    number: str
    issue_date: Optional[str]
    sha256: str
    source_path: Path
    dest_path: Optional[Path] = None

    def as_dict(self) -> Dict[str, Optional[str]]:
        data = asdict(self)
        data["source_path"] = str(self.source_path)
        data["dest_path"] = str(self.dest_path) if self.dest_path else None
        return data


INVOICE_CODE_RE = re.compile(r"发票代码[:：]?\s*([0-9]{8,12})")
INVOICE_NUMBER_RE = re.compile(r"发票号码[:：]?\s*([0-9]{6,12})")
INVOICE_DATE_RE = re.compile(
    r"开票日期[:：]?\s*([0-9]{4}[.年/-][0-9]{1,2}[.月/-][0-9]{1,2}日?)"
)


class InvoiceProcessor:
    def __init__(self, args: argparse.Namespace) -> None:
        self.source: Path = args.source_dir
        self.target: Path = args.target_dir
        self.duplicates: Path = args.duplicate_dir
        self.dry_run: bool = args.dry_run
        self.copy: bool = args.copy
        self.index_csv: Optional[Path] = args.index_csv
        self.index_json: Optional[Path] = args.index_json

        self.records: Dict[Tuple[str, str], InvoiceRecord] = {}
        self.duplicates_found: List[Path] = []
        self.exceptions: List[Tuple[Path, str]] = []

        logging.basicConfig(level=logging.INFO, format="%(message)s")

    def run(self) -> None:
        if not self.source.exists():
            raise SystemExit(f"Source directory {self.source} does not exist")

        pdf_files = sorted(self.source.rglob("*.pdf"))
        logging.info("Found %d PDF file(s) to process", len(pdf_files))

        for pdf_path in pdf_files:
            self._process_pdf(pdf_path)

        self._export_indexes()
        self._print_summary()

    def _process_pdf(self, pdf_path: Path) -> None:
        logging.info("Processing %s", pdf_path)
        try:
            reader = PdfReader(str(pdf_path))
            text = self._extract_text(reader)
        except Exception as exc:  # pragma: no cover - runtime protection
            message = f"Failed to read PDF: {exc}"
            logging.warning("%s - %s", pdf_path, message)
            self.exceptions.append((pdf_path, message))
            return

        code = self._match_first(INVOICE_CODE_RE, text)
        number = self._match_first(INVOICE_NUMBER_RE, text)
        issue_date = self._normalize_date(self._match_first(INVOICE_DATE_RE, text))

        if not code or not number:
            message = "Missing invoice code or number"
            logging.warning("%s - %s", pdf_path, message)
            self.exceptions.append((pdf_path, message))
            return

        sha256 = self._hash_file(pdf_path)
        key = (code, number)

        if key in self.records:
            existing = self.records[key]
            if existing.sha256 == sha256:
                logging.info("Duplicate detected for %s", pdf_path)
            else:
                logging.info(
                    "Conflict detected for %s (different hash with same invoice key)",
                    pdf_path,
                )
            self._handle_duplicate(pdf_path)
            return

        dest_path = self._determine_destination(pdf_path, issue_date)
        record = InvoiceRecord(
            code=code,
            number=number,
            issue_date=issue_date,
            sha256=sha256,
            source_path=pdf_path,
            dest_path=dest_path,
        )
        self.records[key] = record

        action = "Copying" if self.copy else "Moving"
        logging.info("%s %s -> %s", action, pdf_path, dest_path)
        if not self.dry_run:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if self.copy:
                shutil.copy2(pdf_path, dest_path)
            else:
                shutil.move(pdf_path, dest_path)

    def _determine_destination(self, pdf_path: Path, issue_date: Optional[str]) -> Path:
        if issue_date:
            normalized = issue_date.replace("年", "-").replace("月", "-").replace("日", "")
            normalized = normalized.replace("/", "-").replace(".", "-")
            date_part = normalized
        else:
            date_part = "unknown-date"
        return self.target / date_part / pdf_path.name

    def _handle_duplicate(self, pdf_path: Path) -> None:
        self.duplicates_found.append(pdf_path)
        duplicate_target = self.duplicates / pdf_path.name
        logging.info("Moving duplicate %s -> %s", pdf_path, duplicate_target)
        if not self.dry_run:
            duplicate_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(pdf_path, duplicate_target)

    @staticmethod
    def _hash_file(path: Path) -> str:
        sha256 = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def _extract_text(reader: PdfReader) -> str:
        text_parts = []
        for page in reader.pages:
            try:
                text_parts.append(page.extract_text() or "")
            except Exception:  # pragma: no cover - guard for pypdf edge cases
                continue
        return "\n".join(text_parts)

    @staticmethod
    def _match_first(pattern: re.Pattern[str], text: str) -> Optional[str]:
        match = pattern.search(text)
        return match.group(1).strip() if match else None

    @staticmethod
    def _normalize_date(date_str: Optional[str]) -> Optional[str]:
        if not date_str:
            return None
        cleaned = date_str.strip()
        cleaned = cleaned.replace("年", "-").replace("月", "-").replace("日", "")
        cleaned = cleaned.replace("/", "-").replace(".", "-")
        parts = [p.zfill(2) for p in cleaned.split("-") if p]
        if len(parts) >= 3:
            return "-".join([parts[0], parts[1], parts[2]])
        return cleaned

    def _export_indexes(self) -> None:
        if self.index_csv:
            logging.info("Writing CSV index to %s", self.index_csv)
            if not self.dry_run:
                self.index_csv.parent.mkdir(parents=True, exist_ok=True)
                with self.index_csv.open("w", newline="", encoding="utf-8") as csvfile:
                    writer = csv.DictWriter(
                        csvfile,
                        fieldnames=[
                            "code",
                            "number",
                            "issue_date",
                            "sha256",
                            "source_path",
                            "dest_path",
                        ],
                    )
                    writer.writeheader()
                    for record in self.records.values():
                        writer.writerow(record.as_dict())

        if self.index_json:
            logging.info("Writing JSON index to %s", self.index_json)
            if not self.dry_run:
                self.index_json.parent.mkdir(parents=True, exist_ok=True)
                with self.index_json.open("w", encoding="utf-8") as jsonfile:
                    json.dump(
                        [record.as_dict() for record in self.records.values()],
                        jsonfile,
                        ensure_ascii=False,
                        indent=2,
                    )

    def _print_summary(self) -> None:
        total_processed = len(self.records) + len(self.duplicates_found) + len(self.exceptions)
        logging.info("\nSummary:")
        logging.info("  Total processed: %d", total_processed)
        logging.info("  Unique invoices: %d", len(self.records))
        logging.info("  Duplicates: %d", len(self.duplicates_found))
        logging.info("  Exceptions: %d", len(self.exceptions))
        if self.exceptions:
            logging.info("\nExceptions detail:")
            for path, reason in self.exceptions:
                logging.info("  %s - %s", path, reason)


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process and deduplicate invoice PDFs")
    parser.add_argument("source_dir", type=Path, help="Directory containing the source PDFs")
    parser.add_argument("target_dir", type=Path, help="Directory where processed PDFs will be stored")
    parser.add_argument(
        "duplicate_dir",
        type=Path,
        help="Directory where duplicate PDFs will be moved",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without moving or copying files",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy files instead of moving them to the target directory",
    )
    parser.add_argument(
        "--index-csv",
        type=Path,
        help="Optional path to write a CSV index of processed invoices",
    )
    parser.add_argument(
        "--index-json",
        type=Path,
        help="Optional path to write a JSON index of processed invoices",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> None:
    args = parse_args(argv)
    processor = InvoiceProcessor(args)
    processor.run()


if __name__ == "__main__":
    main()
