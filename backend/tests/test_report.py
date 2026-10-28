from app.config import DEFAULT_CORPUS_DIR
from app.rag import report


def test_committed_build_report_is_up_to_date(capsys):
    # A corpus or chunker change must commit the regenerated report with it (FAP §5.3).
    assert report.main(["--check"]) == 0, capsys.readouterr().err


def test_report_lists_restricted_chunks_and_registry_status():
    text = (DEFAULT_CORPUS_DIR / report.REPORT_FILE).read_text()
    assert "## Restricted Chunks (review these)" in text
    assert "`eatwell-guide#0079-0081` | `RET-CAL-01`" in text
    assert "## Registry" in text
