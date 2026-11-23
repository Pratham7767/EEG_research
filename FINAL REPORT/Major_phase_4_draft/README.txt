COMPLETE OVERLEAF PROJECT - revised 20 November 2026

Upload in Overleaf: New Project -> Upload Project -> the zip. Main file is
main_report.tex (pdfLaTeX). Built with latexmk: 0 errors, 88 pages.

THIS ROUND (only results.tex changed, plus one new image):
1. Section 6.3.1: new Figure 6.3, the screens shown to the BCI IV 2b subjects
   (fixation cross, arrow cue, moving smiley), file bci2b_paradigm_gui.png.
2. Section 6.5.3: the results on our own GELO recordings are now in the report.
   - Table 6.6 holds the numbers that were already there (53.9 / 53.7 / 50.2 ...).
     These were measured INSIDE the stroke dataset (one model per patient), not on
     our recordings, so the caption and text now say so.
   - New Table 6.7: the same models trained on the stroke data and tested on our
     72 GELO trials, with accuracy, balanced accuracy, recall per hand and the
     permutation p-value. This replaces the "TODO" placeholder.
3. The sentences that quoted "50 to 54 per cent on the recorded data" (Sections
   6.3, 6.4, 6.7, 6.8) now quote the correct balanced accuracy (about 46-53 %).
See changes_gelo_results.diff for every before/after line.
The previous results.tex is kept in _backup_before_gelo_results/ (not in the zip).
