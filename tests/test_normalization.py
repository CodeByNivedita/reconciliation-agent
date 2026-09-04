from backend.rules_engine.normalization import normalize_ref


def test_exact_match():
    assert normalize_ref("ORD-000123") == "ORD-123"


def test_no_hyphen_variant():
    assert normalize_ref("ORD000123") == normalize_ref("ORD-000123")


def test_lowercase_variant():
    assert normalize_ref("ord-000123") == normalize_ref("ORD-000123")


def test_leading_zero_variant():
    assert normalize_ref("ORD-00123") == normalize_ref("ORD-000123")


def test_none_and_blank():
    assert normalize_ref(None) is None
    assert normalize_ref("") is None


def test_unparseable_reference():
    assert normalize_ref("UNSPECIFIED") is None
    assert normalize_ref("garbage!!") is None


def test_genuinely_different_order_does_not_match():
    assert normalize_ref("ORD-000124") != normalize_ref("ORD-000123")
