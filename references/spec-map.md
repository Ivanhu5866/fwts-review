# Spec map: subject → source

Lookup order: 1) ACPI_spec RST → 2) local document library → 3) URL cited in the fwts source or commit → 4) ask the user (mark the finding **unverified** until then).
Always cross-check table layouts with `spec_lookup.sh actbl <SIG>` (ACPICA `actbl*.h`).

| Subject (how to spot it in the diff) | Source | Lookup |
|---|---|---|
| ACPI tables defined in the ACPI spec: FADT, MADT, DSDT/SSDT, FACS, RSDP/XSDT, BERT, BGRT, CPEP, ECDT, EINJ, ERST, FPDT, GTDT, HEST, MSCT, MPST, NFIT, PCCT, PDTT, PHAT, PMTT, PPTT, RASF, RAS2, RHCT, SBST, SDEV, SLIT, SRAT, SVKL, MISC, CCEL (`src/acpi/<sig>/`, `fwts_acpi_table_<sig>`) | ACPI_spec RST | `spec_lookup.sh acpi '<SIG>'`, then `view` the file at the reported line |
| ACPI objects and methods: `_BST`, `_PSS`, `_CST`, `_OSC`, `_DSM` … (`src/acpi/method/`) | ACPI_spec RST | `spec_lookup.sh acpi '_BST'` |
| ACPI opcodes, operation regions, PCC/FFH/GPIO/SMBus address spaces (`src/libfwtsacpica/`) | ACPI_spec RST (chapters 5, 14 (PCC), 19 (ASL), 20 (AML encoding)) | `spec_lookup.sh acpi 'PCC.*Operation Region'` |
| ASPT (AMD) | `Document/ACPI/AMD/`, `Document/ACPI/` (ASPT2) | `pdf ACPI/AMD '<term>' '*ASPT*'`; `pdf ACPI '<term>' '*ASPT2*'` |
| CEDT (CXL) | `Document/ACPI/` CXL spec | `pdf ACPI '<term>' '*CEDT*'` |
| CDAT | `Document/ACPI/` (newest 1.04) | `pdf ACPI '<term>' '*Coherent*Device*1.04*'` |
| IORT (Arm) | `Document/ACPI/IORT/` (DEN0049, newest rev E.f) | `pdf ACPI/IORT '<term>' '*E.f*'` |
| MPAM (Arm) | `Document/ACPI/` DEN0065 | `pdf ACPI '<term>' '*MPAM*2.0*'` |
| AEST (Arm RAS) | `Document/ACPI/` DEN0085 1.1; `Document/ARM/` DEN0085 2.0 beta | `pdf ACPI '<term>' '*AEST*'`; `pdf ARM '<term>' '*AEST*'` (v2) |
| APMT, PSCI, SBBR/BBR, SMCCC (Arm) | `Document/ARM/` | APMT `pdf ARM '<term>' '*APMT*'`; PSCI `'*DEN0022*'`; BBR `'*DEN0044I*'` (2.2, includes SBBR); SMCCC `'*DEN0028*'` |
| SDEI, BSA (Arm) | **not in library** | URL in source/commit, else ask the user (DEN0054 / DEN0094) |
| SPCR, DBG2, DBGP, WSMT, SLIC, WDAT (Microsoft) | `Document/Microsoft/` (SPCR rev 4) and `Document/ACPI/` (`.docx`/`.odt`) | SPCR `pdf Microsoft '<term>' '*SPCR*'` (the ACPI/ copies are old v1.00/v1.02); others `pdf ACPI '<term>' '*<SIG>*'` |
| TPM2, TCPA (TCG ACPI) | `Document/TPM/` (newest v1.50; ACPI/ copy is obsolete 1.10) | `pdf TPM '<term>' '*ACPI-General*v1.50*'` |
| TPM event log, PCRs, `tpmevlog` | `Document/TPM/` (TCG PC Client Platform Firmware Profile) | `pdf TPM '<term>' '*Firmware*Profile*'` |
| DMAR (Intel VT-d) | `Document/ACPI/vt-directed-io-spec(DMAR).pdf` | `pdf ACPI '<term>' '*DMAR*'` |
| IVRS (AMD IOMMU) | `Document/ACPI/IVRS.pdf.pdf` | `pdf ACPI '<term>' '*IVRS*'` |
| HPET | `Document/ACPI/software-developers-hpet-spec-1-0a.pdf` | `pdf ACPI '<term>' '*hpet*'` |
| MCFG (PCI firmware) | PCI Firmware Spec **not in library**; only an ECN in `Document/ACPI/MCFG/` | `pdf ACPI/MCFG '<term>'`, then `actbl MCFG`; else ask the user |
| iBFT, BDAT, BOOT | `Document/ACPI/` | iBFT `'*iBFT*'`; BDAT `'*BDAT*'`; BOOT `SBF21(Boot Table).doc` is `.doc` (unsupported: `libreoffice --headless --convert-to docx`) |
| SMBIOS types, `dmicheck`, `src/dmi/` | `Document/SMBIOS/` (newest DSP0134) | `pdf SMBIOS '<term>' '*DSP0134_3.9*'` (newest; `list SMBIOS` for older) |
| UEFI variables, runtime services, `src/uefi/`, `uefirt*`, `esrt`, `securebootcert` | `Document/UEFI/` | `pdf UEFI '<term>' '*Final_2.11*'` (newest; `list UEFI` for older) |
| RISC-V boot (BRS) | `Document/RISC-V/` (RHCT is in the ACPI RST) | `pdf RISC-V '<term>' '*brs*'` |
| PCIe (AER, ASPM, `src/pci/`) | `Document/PCIE/`, `Document/PCIE3.0.pdf` | `list PCIE`, then `pdf PCIE '<term>' '<newest glob>'` (always pass a glob: no glob converts every file) |
| Intel-specific (`msr`, `mtrr`, `microcode`) | `Document/Intel/` | `list Intel`, then `pdf Intel '<term>' '<glob>'` |
| AMD-specific | `Document/AMD/` | `list AMD`, then `pdf AMD '<term>' '<glob>'` |

URLs cited in fwts source: run `git -C ~/work/fwts grep -nE 'https?://' -- src/<area>` and fetch them with `web_fetch`. Note that uefi.org returns 403 to both `web_fetch` and `curl`, so use the local copies instead.
