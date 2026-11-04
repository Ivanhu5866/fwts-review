import glob
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "spec_lookup.sh"


def run(*args, **env):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True,
                          text=True, env={**os.environ, **env})


def test_acpi_heading(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "05_Tables.rst").write_text(
        "Intro\n=====\n\ntext\n\n"
        "IO Remapping Table\n------------------\n\n"
        "The IORT signature is 'IORT'.\n")
    r = run("acpi", "iort signature", ACPI_SPEC_DIR=str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == \
        "05_Tables.rst:9 [IO Remapping Table] The IORT signature is 'IORT'."


def test_actbl(tmp_path):
    inc = tmp_path / "src/acpica/source/include"
    inc.mkdir(parents=True)
    (inc / "actbl2.h").write_text(
        "typedef struct acpi_table_foo\n{\n    UINT32 A;\n} ACPI_TABLE_FOO;\n\n"
        "typedef struct acpi_table_bar\n{\n} ACPI_TABLE_BAR;\n\n"
        "typedef struct acpi_foo_node\n{\n    UINT8 Type;\n} ACPI_FOO_NODE;\n")
    r = run("actbl", "FOO", FWTS_REPO=str(tmp_path))
    assert "ACPI_TABLE_FOO" in r.stdout and "ACPI_FOO_NODE" in r.stdout
    assert "BAR" not in r.stdout


def test_paged_text_page_numbers(tmp_path):
    d = tmp_path / "docs/TPM"
    d.mkdir(parents=True)
    (d / "spec.txt").write_text("page one\n\fpage two\n  TPM2 Start Method\n")
    r = run("pdf", "TPM", "start method", SPEC_DOC_DIR=str(tmp_path / "docs"),
            SPEC_CACHE_DIR=str(tmp_path / "cache"))
    assert r.stdout.strip() == "spec.txt p.2: TPM2 Start Method"


def test_docx_and_glob(tmp_path):
    d = tmp_path / "docs/ACPI"
    d.mkdir(parents=True)
    with zipfile.ZipFile(d / "SPCR(SPCR).docx", "w") as z:
        z.writestr("word/document.xml",
                   "<w:document><w:p><w:r><w:t>Intro</w:t></w:r></w:p>"
                   "<w:p><w:r><w:t>Interface Type &amp; Baud</w:t></w:r></w:p>"
                   "</w:document>")
    (d / "other.txt").write_text("Interface Type here too\n")
    r = run("pdf", "ACPI", "interface type", "*SPCR*",
            SPEC_DOC_DIR=str(tmp_path / "docs"),
            SPEC_CACHE_DIR=str(tmp_path / "cache"))
    assert r.stdout.strip() == "SPCR(SPCR).docx l.2: Interface Type & Baud"


REAL = glob.glob(os.path.expanduser(
    "~/CloudStation/Document/ACPI/TCG_ACPIGeneralSpecification*.pdf"))


@pytest.mark.skipif(not REAL, reason="TCG ACPI spec PDF not available")
def test_real_pdf(tmp_path):
    r = run("pdf", "ACPI", "start method", "*TCG_ACPI*",
            SPEC_CACHE_DIR=str(tmp_path / "cache"))
    assert " p." in r.stdout


def test_pdf_max_stops_converting(tmp_path):
    d = tmp_path / "docs/UEFI"
    d.mkdir(parents=True)
    (d / "spec_b.txt").write_text("GetVariable one\nGetVariable two\n")
    (d / "spec_a.txt").write_text("GetVariable three\n")
    cache = tmp_path / "cache"
    r = run("pdf", "UEFI", "getvariable", SPEC_DOC_DIR=str(tmp_path / "docs"),
            SPEC_CACHE_DIR=str(cache), MAX="1")
    assert r.stdout == "spec_b.txt p.1: GetVariable one\n"
    assert len(list(cache.iterdir())) == 1
