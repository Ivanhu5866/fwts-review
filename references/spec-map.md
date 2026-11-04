# Spec map: subject → source

Lookup order: 1) ACPI_spec RST → 2) local document library → 3) URL cited in the fwts source or commit → 4) ask the user (mark the finding **unverified** until then).
Always cross-check table layouts with `spec_lookup.sh actbl <SIG>` (ACPICA `actbl*.h`).

| Subject (how to spot it in the diff) | Source | Lookup |
|---|---|---|
| ACPI tables defined in the ACPI spec: FADT, MADT, DSDT/SSDT, FACS, RSDP/XSDT, BERT, BGRT, CPEP, ECDT, EINJ, ERST, FPDT, GTDT, HEST, MSCT, MPST, NFIT, PCCT, PDTT, PHAT, PMTT, PPTT, RASF, RAS2, SBST, SDEV, SLIT, SRAT, MISC, CCEL (`src/acpi/<sig>/`, `fwts_acpi_table_<sig>`) | ACPI_spec RST | `spec_lookup.sh acpi '<SIG>'`, then `view` the file at the reported line |
| ACPI objects and methods: `_BST`, `_PSS`, `_CST`, `_OSC`, `_DSM` … (`src/acpi/method/`) | ACPI_spec RST | `spec_lookup.sh acpi '_BST'` |
| ACPI opcodes, operation regions, PCC/FFH/GPIO/SMBus address spaces (`src/libfwtsacpica/`) | ACPI_spec RST (chapters 5 and 19) | `spec_lookup.sh acpi 'PCC.*Operation Region'` |
| ASPT (AMD) | `Document/ACPI/AMD/` | `pdf ACPI/AMD 'ASPT' '*ASPT*'` |
| CEDT (CXL) | `Document/ACPI/` CXL spec | `pdf ACPI '<term>' '*CEDT*'` |
| CDAT | `Document/ACPI/` | `pdf ACPI '<term>' '*CDAT*'` |
| IORT (Arm) | `Document/ACPI/IORT/` (DEN0049, newest rev E.f) | `pdf ACPI/IORT '<term>' '*E.f*'` |
| MPAM (Arm) | `Document/ACPI/` DEN0065 | `pdf ACPI '<term>' '*MPAM*2.0*'` |
| AEST (Arm RAS) | `Document/ACPI/` DEN0085 | `pdf ACPI '<term>' '*AEST*'` |
| APMT, SDEI, BSA, SBBR, PSCI (Arm) | `Document/ARM/` | `list ARM`, then `pdf ARM '<term>' '*<name>*'` |
| SPCR, DBG2, DBGP, WSMT, SLIC, WDAT (Microsoft) | `Document/ACPI/` (`.doc`/`.docx`/`.odt`) and `Document/Microsoft/` | `pdf ACPI '<term>' '*SPCR*'` (`.doc` is unsupported: convert with `libreoffice --headless --convert-to docx`) |
| TPM2, TCPA (TCG ACPI) | `Document/ACPI/TCG_ACPIGeneralSpecification*` and `Document/TPM/` | `pdf ACPI '<term>' '*TCG*'` |
| TPM event log, PCRs, `tpmevlog` | `Document/TPM/` (TCG PC Client Platform Firmware Profile) | `pdf TPM '<term>' '*Firmware*Profile*'` |
| DMAR (Intel VT-d) | `Document/ACPI/vt-directed-io-spec(DMAR).pdf` | `pdf ACPI '<term>' '*DMAR*'` |
| IVRS (AMD IOMMU) | `Document/ACPI/IVRS.pdf.pdf` | `pdf ACPI '<term>' '*IVRS*'` |
| HPET | `Document/ACPI/software-developers-hpet-spec-1-0a.pdf` | `pdf ACPI '<term>' '*hpet*'` |
| MCFG (PCI firmware) | `Document/ACPI/MCFG/`, `Document/PCIE/` | `pdf ACPI/MCFG '<term>'` |
| SVKL (TDX) | `Document/ACPI/TDX*` | `pdf ACPI '<term>' '*SVKL*'` |
| iBFT, BDAT, BOOT | `Document/ACPI/` | `pdf ACPI '<term>' '*iBFT*'` |
| SMBIOS types, `dmicheck`, `src/dmi/` | `Document/SMBIOS/` (newest DSP0134) | `list SMBIOS`, then `pdf SMBIOS '<term>' '*DSP0134*'` |
| UEFI variables, runtime services, `src/uefi/`, `uefirt*`, `esrt`, `securebootcert` | `Document/UEFI/` | `list UEFI`, then `pdf UEFI '<term>' '*UEFI*Spec*'` |
| RISC-V (RHCT, SBI) | `Document/RISC-V/` | `pdf RISC-V '<term>'` |
| PCIe (AER, ASPM, `src/pci/`) | `Document/PCIE/`, `Document/PCIE3.0.pdf` | `pdf PCIE '<term>'` |
| Intel-specific (`msr`, `mtrr`, `microcode`) | `Document/Intel/` | `pdf Intel '<term>'` |
| AMD-specific | `Document/AMD/` | `pdf AMD '<term>'` |

URLs cited in fwts source: run `git -C ~/work/fwts grep -nE 'https?://' -- src/<area>` and fetch them with `web_fetch`. Note that uefi.org returns 403 to both `web_fetch` and `curl`, so use the local copies instead.
