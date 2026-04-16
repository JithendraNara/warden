from warden.adapters.patch import parse_unified_diff, validate_patch


SAMPLE_DIFF = """--- a/src/main.py
+++ b/src/main.py
@@ -1,2 +1,3 @@
+# TODO: handle missing config
 def main():
     print('hello')
"""


def test_parse_unified_diff_reads_headers_and_hunks() -> None:
    patch = parse_unified_diff(SAMPLE_DIFF)
    assert len(patch.files) == 1
    file = patch.files[0]
    assert file.old_path == "src/main.py"
    assert file.new_path == "src/main.py"
    assert len(file.hunks) == 1


def test_validate_patch_rejects_out_of_allowlist() -> None:
    patch = parse_unified_diff(SAMPLE_DIFF)
    report = validate_patch(patch, allowed_paths={"src/other.py"})
    assert not report.ok
    assert any("not in allowlist" in issue for issue in report.issues)


def test_validate_patch_accepts_allowlisted() -> None:
    patch = parse_unified_diff(SAMPLE_DIFF)
    report = validate_patch(patch, allowed_paths={"src/main.py"})
    assert report.ok
    assert report.issues == []


def test_validate_patch_rejects_empty() -> None:
    patch = parse_unified_diff("")
    report = validate_patch(patch)
    assert not report.ok
    assert any("empty" in issue for issue in report.issues)
