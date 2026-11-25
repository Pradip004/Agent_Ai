from dataclasses import dataclass, field
from decimal import Decimal
import json
import re
from zipfile import BadZipFile

import pandas as pd
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from lxml.etree import XMLSyntaxError
from openpyxl.utils.exceptions import InvalidFileException
from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError

from .forms import CandidateForm, StudentForm
from .models import Candidate, Student

REQUIRED_COLUMNS = ["roll_number", "full_name", "department"]
OPTIONAL_COLUMNS = ["email", "phone", "class_name", "marks", "attendance", "fees_paid"]
ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
CANDIDATE_REQUIRED_COLUMNS = ["full_name", "position"]
CANDIDATE_COLUMNS = CANDIDATE_REQUIRED_COLUMNS + [
    "email", "phone", "years_experience", "skills", "status",
    "interview_date", "interview_notes",
]
MAX_IMPORT_ROWS = 5000
TRUE_WORDS = {"true", "yes", "y", "1", "paid"}
FALSE_WORDS = {"false", "no", "n", "0", "pending", "unpaid"}
IMPORT_ALIASES = {
    "roll_number": {"rollnumber", "rollno", "studentid", "registrationnumber",
                    "regno", "admissionnumber"},
    "full_name": {"fullname", "name", "studentname"},
    "department": {"department", "dept", "branch"},
    "email": {"email", "emailid"},
    "phone": {"phone", "mobile", "mobilenumber", "contactnumber"},
    "class_name": {"classname", "class", "grade", "semester"},
    "marks": {"marks", "mark", "score", "percentage"},
    "attendance": {"attendance", "attendancepercentage"},
    "fees_paid": {"feespaid", "fees", "feestatus", "paymentstatus"},
    "position": {"position", "jobtitle", "role"},
    "years_experience": {"yearsexperience", "experience", "experienceyears"},
    "skills": {"skills", "skill"},
    "status": {"status", "applicationstatus"},
    "interview_date": {"interviewdate"},
    "interview_notes": {"interviewnotes", "notes"},
}


def apply_filters(filters):
    student_filter_keys = {
        "department", "class_name", "roll_number", "marks_gt", "marks_lt",
        "attendance_gt", "attendance_lt", "fees_paid",
    }
    record_type = filters.get("record_type")
    if record_type is None:
        record_type = "student" if student_filter_keys.intersection(filters) else "candidate"
    if record_type == "candidate":
        return apply_candidate_filters(filters)

    qs = Student.objects.all()
    if "department" in filters:
        qs = qs.filter(department__icontains=filters["department"])
    if "class_name" in filters:
        qs = qs.filter(class_name__icontains=filters["class_name"])
    if "roll_number" in filters:
        qs = qs.filter(roll_number__icontains=filters["roll_number"])
    if "name" in filters:
        qs = qs.filter(full_name__icontains=filters["name"])
    if "marks_gt" in filters:
        qs = qs.filter(marks__gt=Decimal(str(filters["marks_gt"])))
    if "marks_lt" in filters:
        qs = qs.filter(marks__lt=Decimal(str(filters["marks_lt"])))
    if "attendance_gt" in filters:
        qs = qs.filter(attendance__gt=Decimal(str(filters["attendance_gt"])))
    if "attendance_lt" in filters:
        qs = qs.filter(attendance__lt=Decimal(str(filters["attendance_lt"])))
    if "fees_paid" in filters:
        qs = qs.filter(fees_paid=filters["fees_paid"])
    return list(qs.order_by("roll_number")[: filters.get("limit", 50)])


def apply_candidate_filters(filters):
    qs = Candidate.objects.all()
    if "name" in filters:
        qs = qs.filter(full_name__icontains=filters["name"])
    if "email" in filters:
        qs = qs.filter(email__icontains=filters["email"])
    if "phone" in filters:
        qs = qs.filter(phone__icontains=filters["phone"])
    if "position" in filters:
        qs = qs.filter(position__icontains=filters["position"])
    if "skills" in filters:
        qs = qs.filter(skills__icontains=filters["skills"])
    if "status" in filters:
        qs = qs.filter(status=filters["status"])
    if "experience_gt" in filters:
        qs = qs.filter(years_experience__gt=Decimal(str(filters["experience_gt"])))
    if "experience_lt" in filters:
        qs = qs.filter(years_experience__lt=Decimal(str(filters["experience_lt"])))
    return list(qs.order_by("-updated_at", "full_name")[: filters.get("limit", 50)])


class ImportFileError(Exception):
    pass


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list = field(default_factory=list)


def _clean_cell(column, value):
    if value is None:
        return ""
    text = str(value).strip()
    if column in ("roll_number", "phone") and text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _canonical_column(value):
    key = re.sub(r"[^a-z0-9]", "", str(value).lower())
    for column, aliases in IMPORT_ALIASES.items():
        if key == column.replace("_", "") or key in aliases:
            return column
    return None


def _key_value_rows(text):
    current = {}
    rows = []
    for line in text.splitlines():
        match = re.match(r"\s*([^:=]+?)\s*[:=]\s*(.*?)\s*$", line)
        if not match:
            continue
        column = _canonical_column(match.group(1))
        if not column:
            continue
        if column == "roll_number" and current.get("roll_number"):
            rows.append(current)
            current = {}
        current[column] = match.group(2).strip()
    if current:
        rows.append(current)
    if rows and all(
            {"roll_number", "full_name", "department"}.issubset(row) for row in rows):
        columns = list(dict.fromkeys(column for row in rows for column in row))
        return columns, [[row.get(column, "") for column in columns] for row in rows]
    return None


def _pdf_table_rows(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        headers = [cell.strip() for cell in re.split(r"\s{2,}|[\t,|;]", line) if cell.strip()]
        recognized = {_canonical_column(header) for header in headers}
        if not {"roll_number", "full_name", "department"}.issubset(recognized):
            continue
        rows = []
        for data_line in lines[index + 1:]:
            cells = [cell.strip() for cell in
                     re.split(r"\s{2,}|[\t,|;]", data_line) if cell.strip()]
            if len(cells) == len(headers):
                rows.append(cells)
        if rows:
            return headers, rows
    return None


def _document_rows(uploaded_file):
    extension = uploaded_file.name.lower().rsplit(".", 1)[-1]
    uploaded_file.seek(0)
    if extension == "xlsx":
        frame = pd.read_excel(uploaded_file, dtype=str, keep_default_na=False)
        return list(frame.columns), frame.values.tolist()
    if extension == "csv":
        frame = pd.read_csv(uploaded_file, dtype=str, keep_default_na=False)
        return list(frame.columns), frame.values.tolist()
    if extension in ("txt", "md"):
        from io import StringIO

        content = uploaded_file.read().decode("utf-8-sig")
        key_values = _key_value_rows(content)
        if key_values:
            return key_values
        frame = pd.read_csv(
            StringIO(content), dtype=str, keep_default_na=False, sep=None, engine="python",
        )
        return list(frame.columns), frame.values.tolist()
    if extension == "json":
        data = json.loads(uploaded_file.read().decode("utf-8-sig"))
        if isinstance(data, dict) and isinstance(data.get("students"), list):
            data = data["students"]
        records = data if isinstance(data, list) else [data]
        if not records or not all(isinstance(record, dict) for record in records):
            raise ImportFileError(
                "JSON must contain a student object or a list of student objects."
            )
        columns = list(dict.fromkeys(key for record in records for key in record))
        return columns, [[record.get(column, "") for column in columns] for record in records]
    if extension == "docx":
        document = Document(uploaded_file)
        for table in document.tables:
            rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            headers = {_canonical_column(header) for header in rows[0]} if rows else set()
            if {"roll_number", "full_name", "department"}.issubset(headers):
                return rows[0], rows[1:]
        key_values = _key_value_rows(
            "\n".join(paragraph.text for paragraph in document.paragraphs)
        )
        if key_values:
            return key_values
        raise ImportFileError(
            "No student table or Roll Number/Name/Department fields were found in the Word file."
        )
    if extension == "pdf":
        reader = PdfReader(uploaded_file)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        key_values = _key_value_rows(text)
        if key_values:
            return key_values
        table_rows = _pdf_table_rows(text)
        if table_rows:
            return table_rows
        raise ImportFileError(
            "No searchable student details were found in the PDF. Scanned PDFs need OCR."
        )
    raise ImportFileError("This file type is not supported.")


def import_students_from_file(uploaded_file):
    if not uploaded_file.name.lower().endswith((".csv", ".xlsx")):
        raise ImportFileError("Upload a CSV or XLSX file.")
    try:
        columns, rows = _document_rows(uploaded_file)
    except (BadZipFile, FileNotDecryptedError, InvalidFileException, PackageNotFoundError,
            PdfReadError, UnicodeDecodeError, XMLSyntaxError, pd.errors.EmptyDataError,
            pd.errors.ParserError, ValueError, KeyError) as exc:
        raise ImportFileError(
            "Could not read the file. Check that it is a valid, text-based document."
        ) from exc

    canonical_columns = [_canonical_column(column) for column in columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in canonical_columns]
    if missing:
        raise ImportFileError(
            "Missing required column(s): " + ", ".join(missing)
            + ". Required fields are roll number, full name, and department."
        )
    if len(rows) > MAX_IMPORT_ROWS:
        raise ImportFileError(f"Too many rows (maximum {MAX_IMPORT_ROWS}).")

    result = ImportResult()
    for index, values in enumerate(rows):
        cells = {}
        for column, value in zip(canonical_columns, values):
            if column in ALL_COLUMNS:
                cells[column] = _clean_cell(column, value)
        roll = cells.get("roll_number", "")
        if not roll:
            result.errors.append(f"Row {index + 2}: roll_number is blank.")
            continue

        instance = Student.objects.filter(roll_number=roll).first()
        if instance:
            result.skipped += 1
            result.errors.append(
                f"Row {index + 2}: roll number {roll} already exists; skipped."
            )
            continue
        data = {"marks": "0", "attendance": "0", "fees_paid": False}

        fees_error = False
        for column, value in cells.items():
            if value == "":
                continue
            if column == "fees_paid":
                word = value.lower()
                if word in TRUE_WORDS:
                    data[column] = True
                elif word in FALSE_WORDS:
                    data[column] = False
                else:
                    fees_error = True
            else:
                data[column] = value

        if fees_error:
            result.errors.append(f"Row {index + 2}: fees_paid must be Yes/No/Paid/Pending.")
            continue
        form = StudentForm(data)
        if form.is_valid():
            form.save()
            result.created += 1
        else:
            problems = "; ".join(f"{n}: {' '.join(e)}" for n, e in form.errors.items())
            result.errors.append(f"Row {index + 2}: {problems}")
    return result


def import_candidates_from_file(uploaded_file):
    if not uploaded_file.name.lower().endswith((".csv", ".xlsx")):
        raise ImportFileError("Upload a CSV or XLSX file.")
    try:
        columns, rows = _document_rows(uploaded_file)
    except (BadZipFile, FileNotDecryptedError, InvalidFileException, PackageNotFoundError,
            PdfReadError, UnicodeDecodeError, XMLSyntaxError, pd.errors.EmptyDataError,
            pd.errors.ParserError, ValueError, KeyError) as exc:
        raise ImportFileError(
            "Could not read the file. Check that it is a valid CSV or XLSX document."
        ) from exc

    canonical_columns = [_canonical_column(column) for column in columns]
    missing = [column for column in CANDIDATE_REQUIRED_COLUMNS
               if column not in canonical_columns]
    if missing:
        raise ImportFileError(
            "Missing required column(s): " + ", ".join(missing)
            + ". Required fields are full name and position."
        )
    if len(rows) > MAX_IMPORT_ROWS:
        raise ImportFileError(f"Too many rows (maximum {MAX_IMPORT_ROWS}).")

    result = ImportResult()
    for index, values in enumerate(rows):
        data = {
            "years_experience": "0",
            "status": Candidate.ApplicationStatus.NEW,
        }
        for column, value in zip(canonical_columns, values):
            if column in CANDIDATE_COLUMNS:
                cleaned = _clean_cell(column, value)
                if cleaned:
                    data[column] = cleaned.lower() if column == "status" else cleaned

        email = data.get("email", "").strip()
        position = data.get("position", "").strip()
        if email and Candidate.objects.filter(
                email__iexact=email, position__iexact=position).exists():
            result.skipped += 1
            result.errors.append(
                f"Row {index + 2}: candidate {email} for {position} already exists; skipped."
            )
            continue

        form = CandidateForm(data)
        if form.is_valid():
            form.save()
            result.created += 1
        else:
            problems = "; ".join(f"{name}: {' '.join(errors)}"
                                 for name, errors in form.errors.items())
            result.errors.append(f"Row {index + 2}: {problems}")
    return result


def import_students_from_excel(uploaded_file):
    return import_students_from_file(uploaded_file)