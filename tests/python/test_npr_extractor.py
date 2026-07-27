"""Synthetic, deterministic tests for the conservative NPR letter extractor."""

from core.npr_extractor import NprLetterFields, extract_npr_letter
from core.ocr_engine import TextRegion


def _bbox(x1, y1, x2, y2):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _r(text, x1, y1, x2, y2, conf=0.95):
    return TextRegion(text=text, bbox=_bbox(x1, y1, x2, y2), confidence=conf)


def test_inline_label_values():
    regions = [
        _r("OFFICE OF THE REGISTRAR GENERAL, INDIA", 40, 20, 620, 50),
        _r("NATIONAL POPULATION REGISTER", 120, 60, 540, 92),
        _r("Reference No: NPR/DL/2024/004217", 40, 120, 560, 148),
        _r("Name of Resident: ASHA VERMA", 40, 165, 500, 193),
        _r(
            "Address of Resident: 14, LAKE VIEW ROAD, NEW DELHI 110019",
            40,
            210,
            760,
            238,
        ),
        _r("Date of Issue: 14/03/2024", 40, 260, 420, 288),
    ]

    fields = extract_npr_letter(regions)

    assert isinstance(fields, NprLetterFields)
    assert fields.reference_number == "NPR/DL/2024/004217"
    assert fields.name == "ASHA VERMA"
    assert fields.address == "14, LAKE VIEW ROAD, NEW DELHI 110019"
    assert fields.pincode == "110019"
    assert fields.issue_date == "14/03/2024"


def test_value_below_labels_and_multiline_address():
    regions = [
        _r("National Population Register", 100, 20, 540, 52),
        _r("Letter Number", 40, 90, 240, 116),
        _r("NPR-UP-2022-8831", 42, 122, 330, 152),
        _r("Name", 40, 175, 130, 201),
        _r("IMRAN KHAN", 42, 207, 280, 237),
        _r("Postal Address", 40, 260, 250, 286),
        _r("HOUSE 82, WARD 4", 42, 294, 360, 322),
        _r("LUCKNOW, UTTAR PRADESH", 42, 328, 470, 356),
        _r("226010", 42, 362, 170, 390),
        _r("Issue Date", 40, 420, 210, 446),
        _r("02-11-2022", 42, 452, 220, 482),
        _r("Authorised Signatory", 40, 510, 300, 540),
    ]

    fields = extract_npr_letter(regions)

    assert fields.reference_number == "NPR-UP-2022-8831"
    assert fields.name == "IMRAN KHAN"
    assert fields.address == (
        "HOUSE 82, WARD 4, LUCKNOW, UTTAR PRADESH, 226010"
    )
    assert fields.pincode == "226010"
    assert fields.issue_date == "02-11-2022"
    assert "Authorised Signatory" not in fields.address


def test_values_to_right_of_separate_labels():
    regions = [
        _r("NATIONAL POPULATION REGISTER", 100, 20, 540, 52),
        _r("Ref. No.", 40, 90, 150, 116),
        _r("RGI/NPR/889900", 175, 90, 410, 116),
        _r("Resident Name", 40, 135, 220, 161),
        _r("NEHA IYER", 245, 135, 430, 161),
        _r("Address", 40, 180, 150, 206),
        _r("9 M G ROAD, PUNE 411001", 175, 180, 560, 206),
        _r("Letter Date", 40, 230, 190, 256),
        _r("7 January 2023", 215, 230, 430, 256),
    ]

    fields = extract_npr_letter(regions)

    assert fields.reference_number == "RGI/NPR/889900"
    assert fields.name == "NEHA IYER"
    assert fields.address == "9 M G ROAD, PUNE 411001"
    assert fields.pincode == "411001"
    assert fields.issue_date == "7 January 2023"


def test_bilingual_hindi_title_and_labels_with_noisy_headers():
    regions = [
        _r("भारत सरकार", 40, 10, 220, 38, conf=0.50),
        _r("राष्ट्रीय जनसंख्या रजिस्टर", 100, 48, 560, 82, conf=0.82),
        _r("OFFICE COPY / कार्यालय प्रति", 40, 88, 410, 114, conf=0.58),
        _r("संदर्भ संख्या : NPR/RJ/77109", 40, 130, 450, 158),
        _r("निवासी का नाम : कविता शर्मा", 40, 175, 460, 203),
        _r("निवासी का पता", 40, 220, 230, 248),
        _r("22 SHANTI NAGAR", 42, 255, 350, 283),
        _r("JAIPUR, RAJASTHAN 302004", 42, 290, 480, 318),
        _r("दिनांक : 09.08.2021", 40, 350, 330, 378),
    ]

    fields = extract_npr_letter(regions)

    assert fields.reference_number == "NPR/RJ/77109"
    assert fields.name == "कविता शर्मा"
    assert fields.address == "22 SHANTI NAGAR, JAIPUR, RAJASTHAN 302004"
    assert fields.pincode == "302004"
    assert fields.issue_date == "09.08.2021"


def test_npr_acronym_requires_recognised_issuer():
    unrelated = [
        _r("NPR MEDIA SERVICES", 40, 20, 360, 50),
        _r("Name: SOME PERSON", 40, 90, 330, 118),
        _r("Address: SOMEWHERE 560001", 40, 130, 430, 158),
    ]

    fields = extract_npr_letter(unrelated)

    assert fields == NprLetterFields()


def test_npr_acronym_with_registrar_general_is_accepted():
    regions = [
        _r("Office of the Registrar General & Census Commissioner, India", 20, 20, 760, 50),
        _r("NPR NAME AND ADDRESS LETTER", 100, 58, 570, 88),
        _r("Name: RAHUL DAS", 40, 120, 320, 148),
        _r("Address: 7 PARK STREET, KOLKATA 700016", 40, 165, 610, 193),
    ]

    fields = extract_npr_letter(regions)

    assert fields.name == "RAHUL DAS"
    assert fields.address == "7 PARK STREET, KOLKATA 700016"
    assert fields.pincode == "700016"


def test_unlabelled_values_are_not_guessed():
    regions = [
        _r("National Population Register", 100, 20, 540, 52),
        _r("PRIYA SINGH", 40, 100, 280, 128),
        _r("44 MARKET ROAD, CHENNAI 600001", 40, 145, 570, 173),
        _r("17/04/2020", 40, 190, 220, 218),
    ]

    fields = extract_npr_letter(regions)

    assert fields == NprLetterFields()


def test_name_and_address_words_in_title_are_not_field_labels():
    regions = [
        _r(
            "NATIONAL POPULATION REGISTER NAME AND ADDRESS LETTER",
            40,
            20,
            680,
            50,
        ),
        _r("Dear Citizen", 40, 70, 240, 98),
        _r("This is a routine informational notice", 40, 110, 540, 138),
        _r("Please retain this letter", 40, 150, 390, 178),
    ]

    assert extract_npr_letter(regions) == NprLetterFields()


def test_pincode_is_not_guessed_from_reference_number():
    regions = [
        _r("National Population Register", 100, 20, 540, 52),
        _r("Reference No: 560001", 40, 90, 330, 118),
        _r("Name: JOSEPH MATHEW", 40, 130, 360, 158),
        _r("Address: BENGALURU, KARNATAKA", 40, 170, 500, 198),
    ]

    fields = extract_npr_letter(regions)

    assert fields.reference_number == "560001"
    assert fields.pincode is None


def test_explicit_pincode_label_is_supported_outside_address():
    regions = [
        _r("National Population Register", 100, 20, 540, 52),
        _r("Name: JOSEPH MATHEW", 40, 90, 360, 118),
        _r("Address: BENGALURU, KARNATAKA", 40, 130, 500, 158),
        _r("PIN Code: 560034", 40, 175, 280, 203),
    ]

    fields = extract_npr_letter(regions)

    assert fields.address == "BENGALURU, KARNATAKA"
    assert fields.pincode == "560034"


def test_invalid_issue_date_is_not_returned():
    regions = [
        _r("National Population Register", 100, 20, 540, 52),
        _r("Issue Date: pending", 40, 90, 320, 118),
    ]

    assert extract_npr_letter(regions).issue_date is None


def test_empty_input_returns_empty_dataclass():
    assert extract_npr_letter([]) == NprLetterFields()


def test_generic_non_npr_letter_returns_no_personal_fields():
    regions = [
        _r("TO WHOM IT MAY CONCERN", 100, 20, 480, 52),
        _r("Reference No: HR/2024/88", 40, 90, 390, 118),
        _r("Name: ANIL KUMAR", 40, 130, 330, 158),
        _r("Address: 12 CENTRAL ROAD 400001", 40, 170, 520, 198),
        _r("Date of Issue: 01/01/2024", 40, 210, 420, 238),
    ]

    assert extract_npr_letter(regions) == NprLetterFields()
