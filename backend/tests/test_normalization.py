from app.graph.normalization import normalize_object_type, stable_object_id


def test_stable_id_preserves_case_and_owner() -> None:
    first = stable_object_id("DB", "PDB", "Sales", "TABLE", "MixedCase")
    second = stable_object_id("DB", "PDB", "SALES", "TABLE", "MixedCase")

    assert first == "DB::PDB::Sales::TABLE::MixedCase"
    assert first != second


def test_stable_id_escapes_separator_in_quoted_identifier() -> None:
    identifier = stable_object_id("DB", "PDB", "SALES", "TABLE", "A::B")

    assert identifier == "DB::PDB::SALES::TABLE::A%3A%3AB"


def test_unknown_oracle_type_is_retained_as_other_category() -> None:
    assert normalize_object_type("JAVA CLASS") == "OTHER"
    assert normalize_object_type("MATERIALIZED VIEW") == "MATERIALIZED_VIEW"
