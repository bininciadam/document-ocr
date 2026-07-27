"""Tests for fail-closed non-passport extraction assessment."""

from datetime import date

from core.aadhaar_extractor import AadhaarFields
from core.driving_licence_extractor import DrivingLicenceFields
from core.kyc_validation import assess_kyc_extraction
from core.npr_extractor import NprLetterFields
from core.nrega_extractor import NregaFields, NregaMember
from core.ocr_engine import TextRegion
from core.pan_extractor import PanFields
from core.voter_id_extractor import VoterIdFields


def _regions(confidence: float = 0.95) -> list[TextRegion]:
    return [
        TextRegion(
            text="synthetic",
            bbox=[[0, 0], [100, 0], [100, 20], [0, 20]],
            confidence=confidence,
        )
    ]


def test_complete_pan_requires_identifier_name_and_dob():
    result = assess_kyc_extraction(
        "pan",
        PanFields(
            pan_number="ABCPE1234F",
            name="ROHIT SHARMA",
            date_of_birth="15/08/1985",
        ),
        _regions(),
    )

    assert result.complete is True
    assert result.identifier_valid is True
    assert result.confidence >= 0.9


def test_pan_with_only_valid_identifier_is_partial():
    result = assess_kyc_extraction(
        "pan",
        PanFields(pan_number="ABCPE1234F"),
        _regions(),
    )

    assert result.complete is False
    assert result.missing_required_fields == ["name", "dateOfBirth"]
    assert result.confidence <= 0.69


def test_invalid_dl_identifier_fails_closed():
    result = assess_kyc_extraction(
        "driving_licence",
        DrivingLicenceFields(
            dl_number="NOT-A-DL",
            name="TEST DRIVER",
            date_of_birth="01/01/1990",
            issue_date="01/01/2020",
            validity_date="01/01/2040",
        ),
        _regions(),
    )

    assert result.complete is False
    assert result.identifier_valid is False
    assert "INVALID_OR_MISSING_DOCUMENT_IDENTIFIER" in result.errors
    assert result.confidence <= 0.39


def test_dl_date_chronology_must_be_plausible():
    result = assess_kyc_extraction(
        "driving_licence",
        DrivingLicenceFields(
            dl_number="MH1220110012345",
            name="TEST DRIVER",
            date_of_birth="01/01/1990",
            issue_date="01/01/2040",
            validity_date="01/01/2020",
        ),
        _regions(),
    )

    assert result.complete is False
    assert "INVALID_DL_DATE_CHRONOLOGY" in result.errors


def test_dl_issue_date_cannot_be_in_the_future():
    future_year = date.today().year + 1
    result = assess_kyc_extraction(
        "driving_licence",
        DrivingLicenceFields(
            dl_number="MH1220110012345",
            name="TEST DRIVER",
            date_of_birth="01/01/1990",
            issue_date=f"01/01/{future_year}",
            validity_date=f"01/01/{future_year + 10}",
        ),
        _regions(),
    )

    assert result.complete is False
    assert "INVALID_ISSUE_DATE" in result.errors


def test_voter_id_accepts_age_when_dob_is_absent():
    result = assess_kyc_extraction(
        "voter_id",
        VoterIdFields(
            epic_number="ABC1234567",
            name="TEST ELECTOR",
            age="34",
        ),
        _regions(),
    )

    assert result.complete is True
    assert result.identifier_valid is True


def test_voter_id_rejects_implausible_age():
    result = assess_kyc_extraction(
        "voter_id",
        VoterIdFields(
            epic_number="ABC1234567",
            name="TEST ELECTOR",
            age="7",
        ),
        _regions(),
    )

    assert result.complete is False
    assert "INVALID_AGE" in result.errors


def test_aadhaar_front_requires_demographic_fields():
    result = assess_kyc_extraction(
        "aadhaar",
        AadhaarFields(
            aadhaar_number="9998 8877 7669",
            name="TEST RESIDENT",
            date_of_birth="01/01/1990",
            gender="FEMALE",
            checksum_valid=True,
        ),
        _regions(),
    )

    assert result.complete is True
    assert result.identifier_valid is True


def test_masked_aadhaar_can_be_complete_but_is_not_checksum_validated():
    result = assess_kyc_extraction(
        "aadhaar",
        AadhaarFields(
            name="TEST RESIDENT",
            year_of_birth="1990",
            gender="MALE",
            aadhaar_masked=True,
            aadhaar_last4="9012",
        ),
        _regions(),
    )

    assert result.complete is True
    assert result.identifier_valid is None
    assert "MASKED_AADHAAR_CHECKSUM_UNAVAILABLE" in result.warnings


def test_aadhaar_back_requires_identifier_address_and_pincode():
    result = assess_kyc_extraction(
        "aadhaar",
        AadhaarFields(
            aadhaar_number="9998 8877 7669",
            address="1 TEST ROAD, TEST CITY",
            pincode="110001",
            checksum_valid=True,
        ),
        _regions(),
    )

    assert result.complete is True
    assert result.identifier_valid is True


def test_low_ocr_confidence_reduces_assessment_confidence():
    strong = assess_kyc_extraction(
        "pan",
        PanFields(
            pan_number="ABCPE1234F",
            name="ROHIT SHARMA",
            date_of_birth="15/08/1985",
        ),
        _regions(0.98),
    )
    weak = assess_kyc_extraction(
        "pan",
        PanFields(
            pan_number="ABCPE1234F",
            name="ROHIT SHARMA",
            date_of_birth="15/08/1985",
        ),
        _regions(0.35),
    )

    assert weak.confidence < strong.confidence
    assert weak.complete is False
    assert "LOW_OCR_CONFIDENCE" in weak.errors


def test_zero_confidence_required_fields_cannot_return_success():
    result = assess_kyc_extraction(
        "pan",
        PanFields(
            pan_number="ABCPE1234F",
            name="ROHIT SHARMA",
            date_of_birth="15/08/1985",
        ),
        _regions(0.0),
    )

    assert result.complete is False
    assert result.confidence <= 0.49
    assert "LOW_OCR_CONFIDENCE" in result.errors


def test_alternate_model_readings_count_one_physical_region_for_confidence():
    same_box = [[0, 0], [100, 0], [100, 20], [0, 20]]
    regions = [
        TextRegion(
            text=text,
            bbox=same_box,
            confidence=confidence,
        )
        for text, confidence in (
            ("PERMANENT ACCOUNT NUMBER", 0.95),
            ("स्थायी खाता संख्या", 0.10),
            ("நிரந்தர கணக்கு எண்", 0.10),
            ("శాశ్వత ఖాతా సంఖ్య", 0.10),
        )
    ]

    result = assess_kyc_extraction(
        "pan",
        PanFields(
            pan_number="ABCPE1234F",
            name="ROHIT SHARMA",
            date_of_birth="15/08/1985",
        ),
        regions,
    )

    assert result.complete is True
    assert "LOW_OCR_CONFIDENCE" not in result.errors


def test_high_confidence_unrelated_regions_cannot_hide_zero_confidence_boxes():
    required_regions = [
        TextRegion(
            text=text,
            bbox=[[0, y], [100, y], [100, y + 20], [0, y + 20]],
            confidence=0.0,
        )
        for text, y in (
            ("ABCPE1234F", 0),
            ("ROHIT SHARMA", 30),
            ("15/08/1985", 60),
        )
    ]
    unrelated_regions = [
        TextRegion(
            text=f"unrelated-{index}",
            bbox=[
                [200, index * 30],
                [300, index * 30],
                [300, index * 30 + 20],
                [200, index * 30 + 20],
            ],
            confidence=1.0,
        )
        for index in range(9)
    ]

    result = assess_kyc_extraction(
        "pan",
        PanFields(
            pan_number="ABCPE1234F",
            name="ROHIT SHARMA",
            date_of_birth="15/08/1985",
        ),
        required_regions + unrelated_regions,
    )

    assert result.complete is False
    assert "LOW_OCR_CONFIDENCE" in result.errors


def test_nrega_requires_valid_identifier_name_and_location():
    result = assess_kyc_extraction(
        "nrega_job_card",
        NregaFields(
            job_card_number="RJ-27-001-002-0008147/00",
            head_of_household="SITA DEVI",
            gram_panchayat="RAMPUR",
            registration_date="14/03/2019",
            validity_from="01/04/2019",
            validity_to="31/03/2024",
        ),
        _regions(),
    )

    assert result.complete is True
    assert result.identifier_valid is True


def test_nrega_member_can_supply_household_name_but_bad_validity_fails():
    result = assess_kyc_extraction(
        "nrega_job_card",
        NregaFields(
            job_card_number="RJ-27-001-002-0008147/00",
            members=[NregaMember(name="SITA DEVI")],
            district="JAIPUR",
            validity_from="31/03/2024",
            validity_to="01/04/2019",
        ),
        _regions(),
    )

    assert result.complete is False
    assert "INVALID_NREGA_VALIDITY_CHRONOLOGY" in result.errors


def test_nrega_registration_date_cannot_be_in_the_future():
    result = assess_kyc_extraction(
        "nrega_job_card",
        NregaFields(
            job_card_number="RJ-27-001-002-0008147/00",
            head_of_household="SITA DEVI",
            district="JAIPUR",
            registration_date=f"01/01/{date.today().year + 1}",
        ),
        _regions(),
    )

    assert result.complete is False
    assert "INVALID_REGISTRATION_DATE" in result.errors


def test_npr_letter_requires_name_and_address_without_claiming_authenticity():
    result = assess_kyc_extraction(
        "npr_letter",
        NprLetterFields(
            reference_number="NPR/DL/2024/004217",
            name="ASHA VERMA",
            address="14 LAKE VIEW ROAD, NEW DELHI 110019",
            pincode="110019",
            issue_date="14/03/2024",
        ),
        _regions(),
    )

    assert result.complete is True
    assert result.identifier_valid is None
    assert "IDENTIFIER_NOT_OFFLINE_VERIFIABLE" in result.warnings


def test_npr_letter_rejects_invalid_optional_metadata():
    result = assess_kyc_extraction(
        "npr_letter",
        NprLetterFields(
            name="ASHA VERMA",
            address="NEW DELHI",
            pincode="000001",
            issue_date="not a date",
        ),
        _regions(),
    )

    assert result.complete is False
    assert "INVALID_PINCODE" in result.errors
    assert "INVALID_ISSUE_DATE" in result.errors
