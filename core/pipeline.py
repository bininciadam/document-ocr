"""
Passport OCR pipeline — single entry point.

Orchestrates: preprocessing → page classification → targeted OCR →
MRZ parsing → validation.
"""

from __future__ import annotations

import time
import re
from dataclasses import dataclass, field, fields as dataclass_fields
from pathlib import Path
from typing import Optional, Union

from .aadhaar_extractor import AadhaarFields, extract_aadhaar
from .back_page_extractor import BackPageFields, extract_back_page
from .document_classifier import classify_document
from .driving_licence_extractor import DrivingLicenceFields, extract_driving_licence
from .kyc_ocr import run_kyc_ocr
from .kyc_validation import (
    MIN_OCR_GEOMETRY_CONFIDENCE_FOR_SUCCESS,
    assess_kyc_extraction,
)
from .mrz_parser import MRZResult, parse_mrz
from .npr_extractor import NprLetterFields, extract_npr_letter
from .nrega_extractor import NregaFields, extract_nrega
from .ocr_engine import TextRegion, run_ocr
from .page_classifier import classify_passport_page
from .pan_extractor import PanFields, extract_pan
from .preprocessor import ImageQualityError, preprocess
from .validator import validate, find_visual_field, find_visual_value_near
from .voter_id_extractor import VoterIdFields, extract_voter_id

TARGETED_CROP_TOP_RATIO = 0.45


@dataclass
class PassportFields:
    surname: Optional[str] = None
    given_names: Optional[str] = None
    full_name: Optional[str] = None
    passport_number: Optional[str] = None
    nationality: Optional[str] = None
    date_of_birth: Optional[str] = None
    sex: Optional[str] = None
    expiry_date: Optional[str] = None
    issue_date: Optional[str] = None
    place_of_birth: Optional[str] = None
    country_code: Optional[str] = None


@dataclass
class DocumentScanResult:
    status: str
    document_type: str
    page_type: str
    confidence: float
    fields: Optional[PassportFields] = None
    back_page_fields: Optional[BackPageFields] = None
    pan_fields: Optional[PanFields] = None
    aadhaar_fields: Optional[AadhaarFields] = None
    driving_licence_fields: Optional[DrivingLicenceFields] = None
    voter_id_fields: Optional[VoterIdFields] = None
    nrega_job_card_fields: Optional[NregaFields] = None
    npr_letter_fields: Optional[NprLetterFields] = None
    mrz_raw: Optional[tuple[str, str]] = None
    mrz_valid: bool = False
    low_confidence: bool = False
    unsupported_reason: Optional[str] = None
    identifier_valid: Optional[bool] = None
    missing_required_fields: list[str] = field(default_factory=list)
    probe_text: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    processing_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "documentType": self.document_type,
            "pageType": self.page_type,
            "confidence": self.confidence,
            "fields": _fields_to_dict(self.fields),
            "backPageFields": _back_page_fields_to_dict(self.back_page_fields),
            "panFields": _dataclass_to_camel_dict(self.pan_fields),
            "aadhaarFields": _dataclass_to_camel_dict(self.aadhaar_fields),
            "drivingLicenceFields": _dataclass_to_camel_dict(self.driving_licence_fields),
            "voterIdFields": _dataclass_to_camel_dict(self.voter_id_fields),
            "nregaJobCardFields": _dataclass_to_camel_dict(self.nrega_job_card_fields),
            "nprLetterFields": _dataclass_to_camel_dict(self.npr_letter_fields),
            "mrzRaw": list(self.mrz_raw) if self.mrz_raw else None,
            "mrzValid": self.mrz_valid,
            "lowConfidence": self.low_confidence,
            "unsupportedReason": self.unsupported_reason,
            "identifierValid": self.identifier_valid,
            "missingRequiredFields": self.missing_required_fields,
            "probeText": self.probe_text,
            "errors": self.errors,
            "warnings": self.warnings,
            "processingMs": self.processing_ms,
        }


def scan(image_input: Union[str, bytes, Path]) -> DocumentScanResult:
    """Run the full passport OCR pipeline."""
    start = time.monotonic()

    try:
        prep = preprocess(image_input)
    except ImageQualityError as exc:
        return DocumentScanResult(
            status="failure",
            document_type="unknown",
            page_type="unknown",
            confidence=0.0,
            errors=[str(exc)],
            processing_ms=_elapsed_ms(start),
        )

    regions = _extract_targeted_regions(prep.image)
    if not regions:
        # The cheap probe uses a bottom crop. A non-passport document can have
        # all useful text elsewhere, especially with an explicitly configured
        # Indic recognition model. Confirm a strongly identified KYC document
        # from the full page before preserving the existing no-text failure.
        full_kyc_regions = run_kyc_ocr(prep.image)
        if full_kyc_regions:
            full_kyc_cls = classify_document(full_kyc_regions)
            if _is_strong_non_passport_classification(full_kyc_cls):
                return _scan_non_passport(
                    prep,
                    None,
                    start,
                    full_regions=full_kyc_regions,
                    doc_cls=full_kyc_cls,
                )
        return DocumentScanResult(
            status="failure",
            document_type="unknown",
            page_type="unknown",
            confidence=0.0,
            errors=["NO_TEXT_DETECTED"],
            warnings=prep.warnings,
            processing_ms=_elapsed_ms(start),
        )

    classification = classify_passport_page(regions)
    if classification.page_type == "passport_non_biodata":
        # Run full-page OCR for back page extraction (not just bottom crop)
        full_regions = run_ocr(prep.image)
        back_fields = extract_back_page(full_regions)
        return DocumentScanResult(
            status="success",
            document_type="passport",
            page_type="passport_non_biodata",
            confidence=classification.confidence,
            back_page_fields=back_fields,
            probe_text=classification.probe_text,
            warnings=prep.warnings + classification.reasons,
            processing_ms=_elapsed_ms(start),
        )

    if classification.page_type != "passport_biodata":
        # Not a passport per the cheap bottom-crop probe — route to the other
        # supported document types using full-page OCR.
        return _scan_non_passport(prep, classification, start)

    mrz = parse_mrz(regions)
    validation = validate(mrz, regions)

    # MRZ için alt bölgedeki targeted OCR yeterli,
    # fakat ad/soyad, issue date gibi görsel alanlar için
    # tüm pasaport sayfasını OCR'dan geçiriyoruz.
    full_regions = run_ocr(prep.image)

    fields = _build_fields(
        mrz,
        full_regions if full_regions else regions
    )

    if _needs_full_page_fallback(mrz, validation, fields):
        fallback_regions = run_ocr(prep.image)
        if fallback_regions:
            fallback_mrz = parse_mrz(fallback_regions)
            fallback_validation = validate(fallback_mrz, fallback_regions)
            fallback_fields = _build_fields(fallback_mrz, fallback_regions)

            if _candidate_score(
                fallback_mrz,
                fallback_validation,
                fallback_fields
            ) > _candidate_score(
                mrz,
                validation,
                fields,
            ):
                regions = fallback_regions
                mrz = fallback_mrz
                validation = fallback_validation
                fields = fallback_fields

    mrz_valid = mrz.overall_checksum_valid if mrz else False

    all_warnings = prep.warnings.copy()
    all_errors = validation.errors.copy()

    if mrz and mrz.errors:
        all_warnings.extend(mrz.errors)
    elif mrz is None:
        all_warnings.append("MRZ_NOT_DETECTED")

    all_warnings.extend(validation.warnings)

    overall_confidence = round(
        min(max((validation.confidence * 0.85) + (classification.confidence * 0.15), 0.0), 1.0),
        3,
    )
    low_confidence = 0.3 <= overall_confidence < 0.7

    if mrz_valid and fields.passport_number and fields.surname and overall_confidence >= 0.7:
        return DocumentScanResult(
            status="success",
            document_type="passport",
            page_type="passport_biodata",
            confidence=overall_confidence,
            fields=fields,
            mrz_raw=mrz.raw_lines if mrz else None,
            mrz_valid=mrz_valid,
            low_confidence=low_confidence,
            probe_text=classification.probe_text,
            errors=all_errors,
            warnings=all_warnings,
            processing_ms=_elapsed_ms(start),
        )

    return DocumentScanResult(
        status="failure",
        document_type="passport",
        page_type="passport_biodata",
        confidence=overall_confidence,
        fields=fields if _has_meaningful_fields(fields) else None,
        mrz_raw=mrz.raw_lines if mrz else None,
        mrz_valid=mrz_valid,
        low_confidence=low_confidence,
        probe_text=classification.probe_text,
        errors=all_errors or ["LOW_CONFIDENCE_EXTRACTION"],
        warnings=all_warnings,
        processing_ms=_elapsed_ms(start),
    )


# Maps a classified document type to (result attribute, extractor function).
_NON_PASSPORT_EXTRACTORS = {
    "pan": ("pan_fields", extract_pan),
    "aadhaar": ("aadhaar_fields", extract_aadhaar),
    "driving_licence": ("driving_licence_fields", extract_driving_licence),
    "voter_id": ("voter_id_fields", extract_voter_id),
    "nrega_job_card": ("nrega_job_card_fields", extract_nrega),
    "npr_letter": ("npr_letter_fields", extract_npr_letter),
}

_STRONG_NON_PASSPORT_REASON_PREFIXES = {
    "pan": ("PAN_KEYWORDS_",),
    "aadhaar": ("AADHAAR_KEYWORDS_",),
    "driving_licence": ("DL_KEYWORDS_",),
    "voter_id": ("VOTER_KEYWORDS_",),
    "nrega_job_card": ("NREGA_",),
    "npr_letter": ("NPR_",),
}


def _is_strong_non_passport_classification(classification) -> bool:
    prefixes = _STRONG_NON_PASSPORT_REASON_PREFIXES.get(
        classification.document_type
    )
    return bool(
        prefixes
        and classification.confidence >= 0.86
        and any(
            reason.startswith(prefixes)
            for reason in classification.reasons
        )
    )


def _scan_non_passport(
    prep,
    _passport_classification,
    start: float,
    *,
    full_regions=None,
    doc_cls=None,
) -> DocumentScanResult:
    """Classify and extract a non-passport KYC document from full-page OCR."""
    if full_regions is None:
        full_regions = run_kyc_ocr(prep.image)
    if not full_regions:
        return DocumentScanResult(
            status="failure",
            document_type="unknown",
            page_type="unknown",
            confidence=0.0,
            errors=["NO_TEXT_DETECTED"],
            warnings=prep.warnings,
            processing_ms=_elapsed_ms(start),
        )

    if doc_cls is None:
        doc_cls = classify_document(full_regions)
    extractor_entry = _NON_PASSPORT_EXTRACTORS.get(doc_cls.document_type)

    if extractor_entry is None:
        # Passport missed by the cheap probe, or an unsupported/unknown document.
        return DocumentScanResult(
            status="unsupported_page",
            document_type=doc_cls.document_type,
            page_type="unknown",
            confidence=doc_cls.confidence,
            unsupported_reason="UNSUPPORTED_DOCUMENT",
            probe_text=[],
            warnings=prep.warnings + doc_cls.reasons,
            processing_ms=_elapsed_ms(start),
        )

    attr, extractor_fn = extractor_entry
    trusted_regions = [
        region
        for region in full_regions
        if region.confidence >= MIN_OCR_GEOMETRY_CONFIDENCE_FOR_SUCCESS
    ]
    fields = extractor_fn(trusted_regions)
    assessment = assess_kyc_extraction(
        doc_cls.document_type,
        fields,
        trusted_regions,
    )
    confidence = round(
        (doc_cls.confidence * 0.4) + (assessment.confidence * 0.6),
        3,
    )
    if not assessment.complete:
        confidence = min(confidence, 0.69)

    result = DocumentScanResult(
        status="success" if assessment.complete else "failure",
        document_type=doc_cls.document_type,
        page_type=doc_cls.document_type,
        confidence=confidence,
        low_confidence=0.3 <= confidence < 0.7,
        identifier_valid=assessment.identifier_valid,
        missing_required_fields=assessment.missing_required_fields,
        probe_text=[],
        errors=assessment.errors,
        warnings=prep.warnings + doc_cls.reasons + assessment.warnings,
        processing_ms=_elapsed_ms(start),
    )
    setattr(result, attr, fields)
    return result


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _fields_to_dict(fields: Optional[PassportFields]) -> Optional[dict]:
    if fields is None:
        return None
    return {
        "surname": fields.surname,
        "givenNames": fields.given_names,
        "fullName": fields.full_name,
        "passportNumber": fields.passport_number,
        "nationality": fields.nationality,
        "dateOfBirth": fields.date_of_birth,
        "sex": fields.sex,
        "expiryDate": fields.expiry_date,
        "issueDate": fields.issue_date,
        "placeOfBirth": fields.place_of_birth,
        "countryCode": fields.country_code,
    }


def _snake_to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


def _dataclass_to_camel_dict(obj) -> Optional[dict]:
    """Serialise a per-document field dataclass to a camelCase dict (or None)."""
    if obj is None:
        return None
    return {
        _snake_to_camel(f.name): _serialise_dataclass_value(getattr(obj, f.name))
        for f in dataclass_fields(obj)
    }


def _serialise_dataclass_value(value):
    """Recursively serialise nested extractor dataclasses and collections."""
    if hasattr(value, "__dataclass_fields__"):
        return _dataclass_to_camel_dict(value)
    if isinstance(value, list):
        return [_serialise_dataclass_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialise_dataclass_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _serialise_dataclass_value(item)
            for key, item in value.items()
        }
    return value


def _back_page_fields_to_dict(fields: Optional[BackPageFields]) -> Optional[dict]:
    if fields is None:
        return None
    return {
        "fatherName": fields.father_name,
        "motherName": fields.mother_name,
        "spouseName": fields.spouse_name,
        "address": fields.address,
        "pincode": fields.pincode,
        "city": fields.city,
        "state": fields.state,
        "fileNumber": fields.file_number,
        "oldPassportNumber": fields.old_passport_number,
        "oldPassportDateOfIssue": fields.old_passport_date_of_issue,
        "oldPassportPlaceOfIssue": fields.old_passport_place_of_issue,
    }


def _extract_targeted_regions(image) -> list[TextRegion]:
    height = image.shape[0]
    crop_top = int(height * TARGETED_CROP_TOP_RATIO)
    if height <= crop_top:
        return []

    targeted_regions = run_ocr(image[crop_top:, :])
    return _offset_regions(targeted_regions, y_offset=crop_top)


def _offset_regions(regions: list[TextRegion], *, x_offset: int = 0, y_offset: int = 0) -> list[TextRegion]:
    offset_regions: list[TextRegion] = []
    for region in regions:
        bbox = [[point[0] + x_offset, point[1] + y_offset] for point in region.bbox]
        offset_regions.append(TextRegion(text=region.text, bbox=bbox, confidence=region.confidence))
    return offset_regions


def _needs_full_page_fallback(
    mrz: Optional[MRZResult],
    validation,
    fields: PassportFields,
) -> bool:
    return (
        mrz is None
        or not mrz.overall_checksum_valid
        or fields.passport_number is None
        or fields.surname is None
    )


def _candidate_score(
    mrz: Optional[MRZResult],
    validation,
    fields: PassportFields,
) -> float:
    score = validation.confidence
    if mrz:
        score += 0.15
    if mrz and mrz.overall_checksum_valid:
        score += 0.2
    if fields.passport_number:
        score += 0.1
    if fields.surname:
        score += 0.1
    if fields.date_of_birth:
        score += 0.05
    return score


def _has_meaningful_fields(fields: PassportFields) -> bool:
    return any(
        value is not None
        for value in (
            fields.surname,
            fields.given_names,
            fields.passport_number,
            fields.nationality,
            fields.date_of_birth,
            fields.expiry_date,
        )
    )


def _build_fields(
    mrz: Optional[MRZResult],
    regions: list[TextRegion],
) -> PassportFields:
    fields = PassportFields()

    # Önce MRZ değerlerini al
    if mrz:
        fields.surname = mrz.surname.value
        fields.given_names = mrz.given_names.value
        fields.passport_number = mrz.passport_number.value
        fields.nationality = mrz.nationality.value
        fields.date_of_birth = mrz.date_of_birth.value
        fields.sex = mrz.sex.value
        fields.expiry_date = mrz.expiry_date.value
        fields.country_code = mrz.country_code.value

    # ---------------------------------------------------------
    # VISUAL NAME EXTRACTION
    # ---------------------------------------------------------

    visual_surname = _extract_visual_field(
        regions,
        [
            "SURNAME",
            "SOYADI",
            "SOYADI / SURNAME",
            "SOYADI/SURNAME",
        ],
    )

    visual_given_names = _extract_visual_field(
        regions,
        [
            "GIVEN NAMES",
            "GIVEN NAME",
            "ADI",
            "ADI / GIVEN NAMES",
            "ADI/GIVEN NAMES",
        ],
    )

    visual_surname = _clean_name_value(visual_surname)
    visual_given_names = _clean_name_value(visual_given_names)

    # Görsel OCR ile MRZ birbirine yakınsa görsel değeri tercih et.
    # Örn: MRZ ASAN, görsel ASLAN -> ASLAN
    if visual_surname:
        if (
            not fields.surname
            or _names_are_similar(fields.surname, visual_surname)
        ):
            fields.surname = visual_surname

    if visual_given_names:
        if (
            not fields.given_names
            or _names_are_similar(fields.given_names, visual_given_names)
        ):
            fields.given_names = visual_given_names

    # Ad Soyad'ı nihai değerlerden tekrar oluştur
    if fields.surname and fields.given_names:
        fields.full_name = f"{fields.given_names} {fields.surname}"
    elif fields.surname:
        fields.full_name = fields.surname
    elif fields.given_names:
        fields.full_name = fields.given_names
        
    # ---------------------------------------------------------
    # ISSUE DATE
    # ---------------------------------------------------------

    raw_issue_date = _extract_visual_date_after_label(
        regions,
        [
            "DATE OF ISSUE",
            "ISSUE DATE",
            "DUZENLEME TARIHI",
            "DÜZENLEME TARİHİ",
        ],
    )

    fields.issue_date = _normalize_visual_date(raw_issue_date)

    # ---------------------------------------------------------
    # PLACE OF BIRTH
    # ---------------------------------------------------------

    fields.place_of_birth = _extract_visual_field(
        regions,
        [
            "PLACE OF BIRTH",
            "BIRTHPLACE",
            "DOGUM YERI",
            "DOĞUM YERİ",
        ],
    )

    return fields

def _clean_name_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    value = value.upper().strip()

    # İsimlerde beklenmeyen karakterleri temizle
    value = re.sub(r"[^A-ZÇĞİÖŞÜ\s\-']", "", value)

    # Birden fazla boşluğu teke indir
    value = re.sub(r"\s+", " ", value).strip()

    # OCR yanlışlıkla label'ı value olarak döndürmüşse kullanma
    forbidden = [
        "SURNAME",
        "SOYADI",
        "GIVEN NAME",
        "DATE OF",
        "PASSPORT",
        "NATIONALITY",
        "SEX",
    ]

    if any(word in value for word in forbidden):
        return None

    if len(value) < 2:
        return None

    return value


def _names_are_similar(a: str, b: str) -> bool:
    if not a or not b:
        return False

    a = _normalize_name_for_compare(a)
    b = _normalize_name_for_compare(b)

    if a == b:
        return True

    # Uzunluk farkı 1 ve sadece tek karakterlik OCR hatası varsa
    # görsel alanı kabul et.
    if abs(len(a) - len(b)) <= 1:
        return _levenshtein_distance(a, b) <= 1

    return False


def _normalize_name_for_compare(value: str) -> str:
    return (
        value.upper()
        .replace("İ", "I")
        .replace("Ş", "S")
        .replace("Ğ", "G")
        .replace("Ü", "U")
        .replace("Ö", "O")
        .replace("Ç", "C")
        .replace(" ", "")
    )


def _levenshtein_distance(a: str, b: str) -> int:
    if len(a) < len(b):
        return _levenshtein_distance(b, a)

    if len(b) == 0:
        return len(a)

    previous_row = list(range(len(b) + 1))

    for i, char_a in enumerate(a):
        current_row = [i + 1]

        for j, char_b in enumerate(b):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (char_a != char_b)

            current_row.append(
                min(insertions, deletions, substitutions)
            )

        previous_row = current_row

    return previous_row[-1]
def _extract_visual_date_after_label(
    regions: list[TextRegion],
    labels: list[str],
) -> Optional[str]:

    label_region = find_visual_field(regions, labels)

    if label_region is None:
        return None

    # Label'ın üst koordinatı
    label_y = min(point[1] for point in label_region.bbox)

    candidates = []

    for region in regions:
        text = region.text.strip()

        # İçinde rakam olmayan satırlar tarih olamaz
        if not re.search(r"\b\d{1,2}\b", text):
            continue

        region_y = min(point[1] for point in region.bbox)

        # Label'ın üstünde bulunan değerleri alma
        if region_y < label_y:
            continue

        distance = region_y - label_y

        candidates.append((distance, text))

    if not candidates:
        return None

    # Label'a en yakın satır önce
    candidates.sort(key=lambda x: x[0])

    for _, text in candidates:

        normalized = _normalize_visual_date(text)

        # Gerçekten YYYY-MM-DD formatına çevrilebildiyse kabul et
        if normalized and re.match(
            r"^\d{4}-\d{2}-\d{2}$",
            normalized
        ):
            return text

    return None

def _extract_visual_field(
    regions: list[TextRegion],
    labels: list[str],
) -> Optional[str]:
    label_region = find_visual_field(regions, labels)
    if label_region is None:
        return None
    value_region = find_visual_value_near(regions, label_region)
    if value_region is None:
        return None
    return value_region.text.strip()


def _normalize_visual_date(value: Optional[str]) -> Optional[str]:
    """
    Convert passport visual dates to ISO YYYY-MM-DD.

    Examples:
        23 EKI/OCT 2023 -> 2023-10-23
        25 SUB/FEB 1966 -> 1966-02-25
        14 HAZ/JUN 2024 -> 2024-06-14
        23 OCT 2023     -> 2023-10-23
    """

    if not value:
        return None

    text = value.upper().strip()

    # OCR sometimes produces Turkish characters without accents.
    text = (
        text
        .replace("İ", "I")
        .replace("Ş", "S")
        .replace("Ğ", "G")
        .replace("Ü", "U")
        .replace("Ö", "O")
        .replace("Ç", "C")
    )

    month_map = {
        # January
        "JAN": 1,
        "OCA": 1,

        # February
        "FEB": 2,
        "SUB": 2,

        # March
        "MAR": 3,

        # April
        "APR": 4,
        "NIS": 4,

        # May
        "MAY": 5,

        # June
        "JUN": 6,
        "HAZ": 6,

        # July
        "JUL": 7,
        "TEM": 7,

        # August
        "AUG": 8,
        "AGU": 8,

        # September
        "SEP": 9,
        "EYL": 9,

        # October
        "OCT": 10,
        "EKI": 10,

        # November
        "NOV": 11,
        "KAS": 11,

        # December
        "DEC": 12,
        "ARA": 12,
    }

    # First try numeric formats such as:
    # 23/10/2023
    # 23.10.2023
    # 23-10-2023
    numeric_match = re.search(
        r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b",
        text
    )

    if numeric_match:
        day = int(numeric_match.group(1))
        month = int(numeric_match.group(2))
        year = int(numeric_match.group(3))

        try:
            from datetime import date
            return date(year, month, day).isoformat()
        except ValueError:
            return value.strip()

    # Text formats such as:
    # 23 EKI/OCT 2023
    # 23 OCT 2023
    # 23 EKI 2023
    text_match = re.search(
        r"\b(\d{1,2})\s+([A-Z]{3,})(?:/([A-Z]{3,}))?\s+(\d{4})\b",
        text
    )

    if not text_match:
        return value.strip()

    day = int(text_match.group(1))
    month_token_1 = text_match.group(2)
    month_token_2 = text_match.group(3)
    year = int(text_match.group(4))

    month = month_map.get(month_token_1)

    if month is None and month_token_2:
        month = month_map.get(month_token_2)

    if month is None:
        return value.strip()

    try:
        from datetime import date
        return date(year, month, day).isoformat()
    except ValueError:
        return value.strip()
