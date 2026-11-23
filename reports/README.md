# reports/

All written reports for the project, in one place. (Before 2026-11-23 these were spread over
`FINAL REPORT/`, `major_bci_2/`, `_backup_before_bci2b_edit/` and two zips in the repo root.)

```
reports/
├── experiment_report_2026-09/          first plain-English report (stages 01-02, 19 Sep 2026)
│   ├── EXPERIMENT_REPORT_2026-09-19.txt / .pdf
│   └── make_report_pdf.py              rebuilds the .pdf from the .txt (C:\Python313\python.exe)
│
└── major_project/                      the college Major Project report (LaTeX / Overleaf)
    ├── Major_phase_4_new_template/     ← LATEST (23 Nov 2026): report moved onto the 2025-26 template.
    │                                     What changed: CHANGES.txt. Overleaf upload: the *_overleaf.zip inside.
    ├── Major_phase_4_draft/            Phase-4 draft (20 Nov 2026), old template. README.txt + *.diff list the edits.
    │   └── _backup_before_gelo_results/  results.tex etc. before the Gelo results were added (10 Nov)
    ├── Major_phase_4_draft.pdf         compiled PDF of the draft (was "Major_phase_4_draft (1).pdf")
    ├── major_bci_2/                    earlier full version (2 Nov 2026), with all figures
    ├── college_template_25_26/         the blank 2025-26 college template (was Updated_major_project_25_26_ReportTemplate__1_)
    ├── backups/
    │   └── major_bci_2_before_bci2b_edit/  .tex files of major_bci_2 before the BCI IV 2b edit (2 Nov)
    └── zips/                           Overleaf zips (NOT on GitHub, *.zip is git-ignored)
```

Each LaTeX folder is self-contained: open `main_report.tex` with pdfLaTeX, or zip the folder and
upload it to Overleaf (New Project → Upload Project). No file refers outside its own folder, so the
folders can be moved or copied freely.

Not in this repo: a newer copy of `major_bci_2` (10 Nov 2026) and `major_bci_2_revised.pdf` /
`major_bci_2_updated.pdf` sit directly in `D:\` on the project PC.
