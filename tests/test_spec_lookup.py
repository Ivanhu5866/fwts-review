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


GAWK = "GNU Awk" in subprocess.run(["awk", "--version"], capture_output=True,
                                   text=True).stdout


def _doc(tmp_path, text):
    d = tmp_path / "docs/S"
    d.mkdir(parents=True)
    (d / "s.txt").write_text(text)
    return dict(SPEC_DOC_DIR=str(tmp_path / "docs"),
                SPEC_CACHE_DIR=str(tmp_path / "cache"))


def test_regex_escapes_kept(tmp_path):
    env = _doc(tmp_path, "Call _OSC(Arg0) here.\naxb\na.b\nNo\\Space\n")
    r = run("pdf", "S", r"_OSC\(", **env)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "s.txt p.1: Call _OSC(Arg0) here.\n"
    assert run("pdf", "S", r"a\.b", **env).stdout == "s.txt p.1: a.b\n"
    assert run("pdf", "S", r"No\\S", **env).stdout == "s.txt p.1: No\\Space\n"


@pytest.mark.skipif(not GAWK, reason="\\S is a gawk regex extension")
def test_gawk_escape_case_kept(tmp_path):
    env = _doc(tmp_path, "axb\na b\n")
    assert run("pdf", "S", r"^a\Sb$", **env).stdout == "s.txt p.1: axb\n"


def test_no_match_asks_to_update_spec(tmp_path):
    env = _doc(tmp_path, "nothing here\n")
    r = run("pdf", "S", "startuplocality", **env)
    assert r.returncode == 1 and r.stdout == ""
    assert "UPDATE-SPEC:" in r.stderr and "docs/S" in r.stderr
    r = run("pdf", "S", "x", "*nope*", **env)
    assert r.returncode == 1 and "no document" in r.stderr


def test_bad_regex_exits_2(tmp_path):
    docs = tmp_path / "docs/A"
    docs.mkdir(parents=True)
    (docs / "a.txt").write_text("x\n")
    r = run("pdf", "A", "_OSC(", SPEC_DOC_DIR=str(tmp_path / "docs"),
            SPEC_CACHE_DIR=str(tmp_path / "cache"))
    assert r.returncode == 2
    assert not (tmp_path / "cache").exists()


def test_pdf_missing_subdir_exits_2(tmp_path):
    r = run("pdf", "NOPE", "x", SPEC_DOC_DIR=str(tmp_path))
    assert r.returncode == 2 and "NOPE" in r.stderr and "UPDATE-SPEC:" in r.stderr


def test_list_newest_first_by_basename(tmp_path):
    d = tmp_path / "docs/X"
    (d / "sub").mkdir(parents=True)
    for n in ("X_6_4.txt", "X_6.6.txt", "sub/X_6_5_Aug.txt"):
        (d / n).write_text("x\n")
    r = run("list", "X", SPEC_DOC_DIR=str(tmp_path / "docs"))
    names = [os.path.basename(l) for l in r.stdout.split()]
    assert names == ["X_6.6.txt", "X_6_5_Aug.txt", "X_6_4.txt"]


def test_interrupted_conversion_not_reused(tmp_path):
    d = tmp_path / "docs/U"
    d.mkdir(parents=True)
    (d / "spec.pdf").write_bytes(b"%PDF-fake")
    shim = tmp_path / "bin"
    shim.mkdir()
    fake = shim / "pdftotext"
    env = dict(SPEC_DOC_DIR=str(tmp_path / "docs"),
               SPEC_CACHE_DIR=str(tmp_path / "cache"),
               PATH=f"{shim}:{os.environ['PATH']}")
    # First conversion is killed after writing partial output.
    fake.write_text('#!/bin/sh\necho partial > "$3"\nkill -9 $PPID\n')
    fake.chmod(0o755)
    run("pdf", "U", "zzz", **env)
    fake.write_text('#!/bin/sh\nprintf "partial\\nfull match\\n" > "$3"\n')
    r = run("pdf", "U", "full", **env)
    assert r.stdout == "spec.pdf p.1: full match\n"


ACTBL_H = """\
#define ACPI_SIG_MADT           "APIC"      /* Multiple APIC */
#define ACPI_SIG_FADT           "FACP"      /* Fixed */
#define ACPI_SIG_TCPA           "TCPA"      /* TCPA */
#define ACPI_SIG_RSDP           "RSD PTR "  /* RSDP */
typedef struct acpi_table_madt
{
    UINT32 Address;
} ACPI_TABLE_MADT;

typedef struct acpi_madt_io_apic
{
    UINT8 Id;
} ACPI_MADT_IO_APIC;

typedef struct acpi_table_fadt
{
    UINT32 Facs;
} ACPI_TABLE_FADT;

typedef struct acpi_table_tcpa_hdr
{
    UINT16 PlatformClass;
} ACPI_TABLE_TCPA_HDR;

typedef struct acpi_table_rsdp
{
    char Signature[8];
} ACPI_TABLE_RSDP;
"""


def _actbl(tmp_path, sig):
    inc = tmp_path / "src/acpica/source/include"
    inc.mkdir(parents=True, exist_ok=True)
    (inc / "actbl.h").write_text(ACTBL_H)
    return run("actbl", sig, FWTS_REPO=str(tmp_path))


def test_actbl_signature_aliases(tmp_path):
    apic, madt = _actbl(tmp_path, "APIC"), _actbl(tmp_path, "MADT")
    assert apic.returncode == 0 and apic.stdout == madt.stdout
    assert "ACPI_TABLE_MADT" in apic.stdout and "ACPI_MADT_IO_APIC" in apic.stdout
    assert "ACPI_TABLE_FADT" in _actbl(tmp_path, "FACP").stdout
    assert "ACPI_TABLE_TCPA_HDR" in _actbl(tmp_path, "TCPA").stdout
    assert "ACPI_TABLE_RSDP" in _actbl(tmp_path, "RSD PTR").stdout


def test_actbl_unknown_exits_1(tmp_path):
    r = _actbl(tmp_path, "ZZZZ")
    assert r.returncode == 1 and "no ACPICA struct for ZZZZ" in r.stderr
