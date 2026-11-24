"""Prepare the Wang et al. (2026) utility workbook for local research.

Source: https://osf.io/4nwgx/
Workbook: https://osf.io/download/7w2tv/
Catch trials: https://osf.io/download/fb7vn/
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

SPREADSHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
COLUMNS = ("Word", "Utility", "Multilex", "GPT_FAM")


def read_workbook(path: Path) -> list[tuple[str, ...]]:
    """Read the four columns of the published, single-sheet XLSX."""
    with ZipFile(path) as archive:
        shared_strings_xml = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        strings = [
            "".join(node.text or "" for node in item.iter(f"{SPREADSHEET_NS}t"))
            for item in shared_strings_xml
        ]
        rows = []
        with archive.open("xl/worksheets/sheet1.xml") as sheet:
            for _, element in ElementTree.iterparse(sheet, events=("end",)):
                if element.tag != f"{SPREADSHEET_NS}row":
                    continue
                values = {}
                for cell in element:
                    column = cell.attrib["r"].rstrip("0123456789")
                    value = cell.findtext(f"{SPREADSHEET_NS}v", default="")
                    values[column] = strings[int(value)] if cell.get("t") == "s" else value
                if values:
                    rows.append(tuple(values.get(column, "") for column in "ABCD"))
                element.clear()
    if not rows or rows[0] != COLUMNS:
        raise ValueError(f"Expected the published workbook columns {COLUMNS}")
    return rows[1:]


def read_controls(path: Path) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        if next(reader, None) != [f"option{index}" for index in range(1, 7)]:
            raise ValueError("Expected the six catch-trial option columns")
        return {value.replace("___", " ").strip().casefold() for row in reader for value in row}


def prepare(workbook: Path, catch_trials: Path, output: Path) -> tuple[int, Counter[str]]:
    rows = read_workbook(workbook)
    controls = read_controls(catch_trials)
    counts = Counter(word.strip().casefold() for word, *_ in rows)
    if not controls or controls.difference(counts):
        raise ValueError("Catch-trial stimuli do not match the workbook")

    drops: Counter[str] = Counter()
    written = 0
    with output.open("x", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        writer.writerow(COLUMNS)
        for row in rows:
            word, utility, _, _ = row
            key = word.strip().casefold()
            if utility in {"", "#N/A"}:
                drops["missing_utility"] += 1
            elif key in controls:
                drops["catch_trial"] += 1
            elif counts[key] > 1:
                drops["duplicate_word"] += 1
            else:
                writer.writerow(row)
                written += 1
    return written, drops


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("catch_trials", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    written, drops = prepare(args.workbook, args.catch_trials, args.output)
    print(f"Wrote {written} rows to {args.output}. Excluded {dict(drops)}.")


if __name__ == "__main__":
    main()
