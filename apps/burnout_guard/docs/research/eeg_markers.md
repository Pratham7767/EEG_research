# EEG markers of fatigue, workload, stress and drowsiness, and how well few-channel dry consumer EEG measures them (scoring engine for a Neiry/Capsule headphone burnout app)

Context: the device has 4 dry channels around the temporal/ear area (about T3/T4 with ear references; C3/C4-A1/A2 variants), sampled at 250 Hz. The existing app computes attention (beta/alpha), load (theta/alpha), relaxation (alpha/beta), stress (20-30 Hz / alpha) and fatigue ((theta+alpha)/beta). Each is relative to a per-session eyes-open baseline, after an eyes-closed calibration that finds the individual alpha peak (IAF).

Research process note: PMC, PubMed and eLife returned CAPTCHA/JS walls or rate limits for several key papers (the burnout EEG review PMC12347992, the test-retest ratio paper PMC12589806, Golonka 2019 PMC6701350, eLife FAA multiverse). Some findings below therefore come from secondary summaries in papers that did load, or from titles only. These are flagged.

## 1. Which spectral indices best track time-on-task mental fatigue, workload and drowsiness?

### Takeaway
The strongest meta-analytic evidence for mental fatigue is an increase in **theta** power, which is large and seen at frontal, central and posterior sites. **Alpha** power also increases, a large effect but more variable. Beta changes are small, so beta-denominator ratios like (theta+alpha)/beta mostly inherit their signal from the theta+alpha numerator. Alpha peak frequency slows and alpha power rises over a session, even in non-fatigue paradigms. Theta/alpha "workload" ratios are widely used but weakly validated.

### Cited Findings
- **Tran et al. 2020 meta-analysis** (Psychophysiology 57(5):e13554):
  - 21 studies of healthy adults doing mentally fatiguing tasks.
  - Mental fatigue gave a medium overall EEG increase (g = 0.68, 95% CI 0.24–1.13).
  - Theta showed a large increase (g = 1.03, CI 0.79–1.60) and alpha a large increase (g = 0.85, CI 0.47–1.43). Delta and beta changed only small-to-moderately.
  - Central regions showed the largest overall change (g = 0.80). Theta rose at frontal, central and posterior sites (all g > 1).
  - The authors propose theta as a "robust biomarker" and alpha as a second-line marker "to account for individual variability."
  - [Tran et al. 2020, Macquarie record](https://researchers.mq.edu.au/en/publications/the-influence-of-mental-fatigue-on-brain-activity-evidence-from-a/)
- **Wascher et al. 2018** (about 54 min of continuous simulated driving, n = 30 in two groups of 14 and 16) — [Frontiers Hum Neurosci 12:205](https://www.frontiersin.org/articles/10.3389/fnhum.2018.00205/full):
  - Over time on task, total 1–30 Hz power rose (frontal η² ≈ 0.18) and relative alpha rose (frontal η² ≈ 0.15, posterior ≈ 0.19).
  - Relative frontal theta *decreased* (η² ≈ 0.32), while absolute frontal theta only trended upward (p = .091).
  - The authors argue that rising broadband power drives absolute-power effects, so relative measures matter. In their reading, relative theta tracks cognitive-control engagement, which falls as people disengage.
  - Implication: the direction of a "theta" effect depends on absolute vs relative normalisation and on task engagement.
- **Benwell et al. 2019** (NeuroImage 192:101–114):
  - Within one session, **alpha peak frequency decreased** and **alpha power increased** with time on task.
  - The two changes were only partly independent. Combined frequency-and-power changes sat mainly in lower alpha (about 8–10 Hz); power-only or frequency-only changes sat mainly in upper alpha (about 9–13 Hz).
  - The authors say this challenges the assumption that spectral content is stable over a typical one-hour session.
  - [Dundee record](https://discovery.dundee.ac.uk/en/publications/frequency-and-power-of-human-alpha-oscillations-drift-systematica/)
- **Workload ratios** — Raufi & Longo 2022, [arXiv 2202.12937](https://arxiv.org/pdf/2202.12937), on the STEW dataset (48 subjects, Emotiv, rest vs SIMKAP multitasking):
  - The authors note "minimal research exists to validate" theta/alpha and alpha/theta as workload indices.
  - On real data, binary workload classification reached about 60% from single bands and about 70% from ratios, with underfitting and poor generalisation.
  - Higher scores (F1 about 82–85%) depended on synthetic data augmentation that may leak subject information.
  - Gains over single bands were not uniform; one ratio was worse than its parts (−10.1%).
- **Borghini et al. 2014** (Neurosci Biobehav Rev, a widely cited review): frontal theta is linked to workload, and theta and alpha are linked to fatigue and drowsiness. This is as cited by [Raufi & Longo 2022](https://arxiv.org/pdf/2202.12937); the original was not fetched. The same theta increase therefore appears under both "workload" and "fatigue," which is a confound.
- **Drowsiness from ear-EEG** — Nakamura et al. 2018, IJCNN, [PDF](https://www.commsp.ee.ic.ac.uk/~mandic/research/EEG_BCI/TN_DPM_et_all_Ear-EEG_Drowsiness_IJCNN_2018.pdf). Setup: 23 adults, normal and sleep-deprived days, daytime naps.
  - In-ear EEG classified Wake vs NREM1 at 80% (κ = 0.53, leave-one-trial-out), compared with 86.8% (κ = 0.72) for scalp C3/C4.
  - NREM1 sensitivity from ear-EEG was only 62–66%. Features were entropy-based, not band ratios.
- **Fatigue from ear-EEG** — Yarici et al. (Imperial, about 2023), [arXiv 2301.06406](https://arxiv.org/pdf/2301.06406). Setup: 10 participants, 1 h monotonous simulated drive.
  - Cross-ear EEG showed a significant theta increase from alert to fatigued (d = 1.3). Alpha did not reach significance at the ear.
  - Beta (15–30 Hz) was **excluded because of EMG noise**.
  - Single-ear and T7/T8 channels were discarded because of motion, EMG and headset artefacts.
  - Accuracy was 70% for ear vs 74% for 3-channel scalp, with likely optimistic bias from tuning hyperparameters on all data.

### Inferences
- For a fatigue score, theta (and possibly alpha) power relative to a personal baseline has the best support. Adding beta in the denominator ((theta+alpha)/beta) contributes little validated signal. At temporal sites it adds EMG-driven noise: tensing the jaw lowers the "fatigue" score and relaxing raises it.
- IAF slowing over a session is a plausible secondary fatigue marker, and the app already estimates IAF. But Benwell shows alpha power and frequency drift with time on task in general, so drift is not specific to "fatigue." The calibration IAF also goes stale over a long session.
- Theta/alpha "cognitive load" and theta-based "fatigue" share the theta numerator and are confounded. The app should not present them as independent constructs.
- Drowsiness (lapses toward sleep onset) is the most detectable state with ear electrodes (about 80% Wake vs N1 accuracy), but mostly in people who are actually sleep-deprived or near sleep onset. Typical office fatigue is subtler.

### Gaps
- No pooled effect sizes for (theta+alpha)/beta or theta/beta specifically in mental fatigue were retrieved. Tran 2020 reports bands, not ratios.
- No quantitative between-person variability figures (e.g., proportion of non-responders) were found. Tran only notes individual variability qualitatively.
- No meta-analysis on frontal-midline theta for workload was retrieved in this session. Note also that frontal-midline theta is recorded at Fz/FCz, which this device does not have.
- Craig et al. 2012 and Arnau et al. papers were not retrieved.

## 2. Evidence for and criticisms of EEG "stress" indices (high-beta/alpha, frontal alpha asymmetry); EMG at temporal sites

### Takeaway
High-beta and gamma power at lateral and temporal sites is dominated by scalp-muscle (EMG) activity. Paralysis studies show contamination begins around 20–25 Hz and is worst at peripheral and lateral sites. A 20–30 Hz / alpha "stress" index at T3/T4 is therefore largely a jaw/temporalis-tension plus alpha-suppression index, not a validated neural stress marker. Frontal alpha asymmetry (FAA) needs frontal electrodes (F3/F4), which this device lacks. FAA is also contested even for depression, where large analyses found no reliable relationship.

### Cited Findings
- **EMG contamination evidence** — Fitzgibbon/Pope group, paralysis study with 6 subjects under cisatracurium, summarised in [PMC9480942 (Brain and Behavior 2022)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9480942):
  - EMG exceeds EEG power 5- to 200-fold in the 50–100 Hz range over much of the scalp.
  - Unprocessed EEG diverges from EMG-free EEG at about 20 Hz. Contamination rises above about 25 Hz and grows with distance from Cz.
  - Beta (13–30 Hz) contamination is about twofold, more away from the centre. Gamma is prominently contaminated everywhere.
  - Even delta and theta showed a distribution resembling muscle contamination.
  - No pruning method fully removed EMG from beta or gamma across the scalp. Gamma stayed "severely contaminated" even after ICA or CCA-SVM.
  - The authors recommend at least 64 channels plus ICA plus a Laplacian. Labs without that should restrict conclusions to "safe frequencies and central locations."
  - Rule of thumb from the authors: if power rises above 25 Hz and the effect grows away from the centre, treat it as EMG-confounded.
  - Seminal earlier paper: Whitham et al. 2007, "Scalp electrical recording during paralysis," [PubMed 17574912](https://pubmed.ncbi.nlm.nih.gov/17574912). A related paper is titled "Thinking activates EMG in scalp electrical recordings" ([Clin Neurophysiol 2008](https://dx.doi.org/10.1016%2Fj.clinph.2008.01.024)). Only titles were retrieved; the title of the second implies cognitive tasks themselves raise EMG, which would confound high-beta changes during work.
- **Consumer validation** — Fedorova/related group, [Frontiers Neurosci 2024, 10.3389/fnins.2024.1326139](https://www.frontiersin.org/articles/10.3389/fnins.2024.1326139):
  - This study tested PSBD Headphones, whose electrodes sit at C3, C4, TP9 and TP10. That layout matches the C3/C4 variant described for this device; whether it is the same hardware as Neiry was not verified.
  - The headphones were "more prone to low-frequency artifacts" but captured alpha changes.
  - NVX (gel) "remained the better choice for high-frequency (beta and gamma) work."
- **Sensors 2024 study** ([MDPI 24(24):8108](https://www.mdpi.com/1424-8220/24/24/8108)):
  - For PSBD Headphones vs BrainProducts at temporal sites: high-beta correlation r = 0.47, alpha 0.72, theta only 0.33.
  - At central sites, only low beta was significant (r = 0.35), and the authors cite muscle-tension noise there.
  - The headphones showed spectral spikes near 16 Hz and 34 Hz, inside the beta/high-beta bands the app uses.
  - Muse frontal channels correlated with the reference only in high beta and gamma, which is consistent with shared non-neural (EMG) signal.
- **Frontal alpha asymmetry:**
  - van der Vinne et al. 2017 meta-analysis, "Frontal alpha asymmetry as a diagnostic marker in depression: Fact or fiction?" ([PubMed 28761811](https://pubmed.ncbi.nlm.nih.gov/28761811/)). Title only retrieved; to my knowledge it concluded FAA lacks diagnostic value, but this was not verified from the abstract.
  - Kołodziej et al. 2021, eLife, titled "No relationship between frontal alpha asymmetry and depressive disorders in a multiverse analysis of five studies" ([eLife 60595](https://elifesciences.org/articles/60595)).

### Inferences
- At T3/T4 or TP9/TP10 with ear references, the 20–30 Hz band sits directly over the temporalis muscle. A "stress" score built on it will mainly respond to clenching, chewing, talking, frowning and jaw posture. This may correlate loosely with tension behaviour, but it is not a neural stress marker and should not be labelled as one.
- A defensible reframe is to measure EMG explicitly (e.g., power above 30–35 Hz excluding mains harmonics, or 70–100 Hz where 250 Hz sampling allows up to 125 Hz). Use it as (a) an artefact flag that blocks beta-based indices and (b) a separately labelled "muscle tension" indicator, not "stress."
- FAA cannot be computed on this montage and is weak evidence anyway. The app should not use it.
- Acute stress is better indexed by peripheral physiology (HRV, EDA) than by scalp EEG. A PPG/HRV channel, if available, would likely be the better stress source. This is general background knowledge and was not sourced in this session.

### Gaps
- No review specifically validating high-beta/alpha as a psychological stress index was found. The absence itself is informative, but a systematic search was not completed.
- No study quantified what fraction of 20–30 Hz power at T3/T4 is EMG; the paralysis data report ratios, not site-specific T7/T8 fractions.

## 3. Reliability and validity of wearable, ear-EEG and few-channel dry systems; day-to-day drift

### Takeaway
Consumer dry systems reproduce **alpha** reasonably well (r ≈ 0.7–0.9 vs gel references, plus eyes-closed alpha reactivity). Theta, delta and beta/gamma are much less reliable because of eye, motion and EMG artefacts. Muse performs worst. Test-retest (day-to-day) reliability for these devices is largely **untested**: both main validation papers list it as a limitation. Ear-EEG detects drowsiness and fatigue-related theta, but at lower accuracy than scalp.

### Cited Findings
- **Sensors 2024** (n = 19; PSBD Headband, PSBD Headphones, Muse S vs BrainProducts ActiChamp mirror montage, 3-min eyes-open and eyes-closed rest) — [MDPI](https://www.mdpi.com/1424-8220/24/24/8108):
  - PSBD Headband correlations vs reference: occipital alpha r = 0.90, temporal alpha 0.80; temporal theta 0.63, temporal high beta 0.40.
  - PSBD Headphones, temporal: alpha 0.72, theta 0.33, low beta 0.58, high beta 0.47; delta and gamma not significant.
  - PSBD Headphones, central: only low beta was significant.
  - Muse temporal data were excluded (17 recordings non-physiological), even though Muse's impedance indicators showed "green."
  - All dry devices showed inflated low-frequency power.
  - The eyes-closed alpha (Berger) effect was present at the headphones' temporal site but absent at central sites.
  - No test-retest analysis was done; minimal preprocessing was used.
- **Frontiers Neurosci 2024** (n = 11 and 13 in two experiments vs NVX-36 gel) — [Frontiers](https://www.frontiersin.org/articles/10.3389/fnins.2024.1326139):
  - Alpha log-PSD correlated r = 0.87 for both PSBD Headband and PSBD Headphones vs gel.
  - The headphones were prone to low-frequency artefacts. Muse showed weaker alpha sensitivity.
  - No ICC or test-retest data. The authors cite earlier work reporting poor day-to-day repeatability for Muse.
- **Ear-EEG performance:** Wake vs N1 classification from in-ear EEG was 80% vs 86.8% for scalp ([Nakamura 2018](https://www.commsp.ee.ic.ac.uk/~mandic/research/EEG_BCI/TN_DPM_et_all_Ear-EEG_Drowsiness_IJCNN_2018.pdf)). Fatigue classification was 70% ear vs 74% scalp ([Yarici et al., arXiv 2301.06406](https://arxiv.org/pdf/2301.06406)). In the second study, single-ear and T7/T8 data were lost to artefacts.
- **Related reliability papers found but not read** (CAPTCHA or rate limits):
  - "Test-Retest Reliability of Single Spectral Power and Spectral Power Ratios in Relative and Absolute Values" ([PMC12589806](https://pmc.ncbi.nlm.nih.gov/articles/PMC12589806/)).
  - Morrone et al. 2025, "The Feasibility and Test-Retest Reliability of Wireless Dry-Electrode EEG During a Dynamic Psychomotor VR Task" ([PMC12034225](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12034225/)).
  - "Beyond the lab: real-world benchmarking of wearable EEGs for passive brain-computer interfaces" ([PubMed 41456250](https://pubmed.ncbi.nlm.nih.gov/41456250/)).
- **Within-session non-stationarity:** alpha frequency and power drift systematically over an hour ([Benwell 2019](https://discovery.dundee.ac.uk/en/publications/frequency-and-power-of-human-alpha-oscillations-drift-systematica/)).

### Inferences
- Alpha (eyes-open vs eyes-closed reactivity, IAF, posterior/temporal alpha power) is the most trustworthy quantity on this hardware. Theta is usable with careful artefact handling. Beta, high-beta and gamma at temporal/ear sites are the least trustworthy.
- Because day-to-day reliability is unknown for this hardware, absolute values should not be compared across days. A per-session baseline (as the app does) is necessary. Cross-day trends should use within-day *changes* (end vs start of day, or slope over the session) rather than raw levels.
- Electrode contact quality varies session to session with dry electrodes (hair, headphone placement). It should be logged and used to weight or discard data. Do not trust vendor "green" indicators blindly (cf. the Muse finding).

### Gaps
- ICC values for spectral ratios, and any test-retest data for Neiry/PSBD headphones, could not be retrieved.
- No study validating Neiry/Capsule specifically against a research system was found under that brand name. The PSBD Headphones layout matches, but identity is unconfirmed.

## 4. Can EEG track chronic burnout or chronic stress?

### Takeaway
Burnout EEG research is sparse, small, cross-sectional and inconsistent. Reported findings include lower resting alpha power, lower alpha peak frequency, reduced beta and altered alpha-band coherence. None is a validated or replicated biomarker, and burnout is confounded with depression. There is a large gap between detecting acute within-session fatigue (moderate evidence) and detecting chronic burnout (no validated EEG method).

### Cited Findings
The prior studies below are as summarised in Kaczmarek-Majer / Golonka-group Frontiers 2025, [Frontiers Hum Neurosci 10.3389/fnhum.2025.1481760](https://frontiersin.org/journals/human-neuroscience/articles/10.3389/fnhum.2025.1481760/full).
- **That 2025 study itself** (98 workers, 49 burnout vs 49 matched controls by MBI-GS, 256-channel EEG):
  - The only significant difference was *reduced alpha3 (11–13 Hz) coherence*, in frontal and midline regions, and only eyes-open.
  - There were no differences in delta, theta, alpha1/2 or beta, and none eyes-closed.
  - The burnout group had mild depressive symptoms.
  - The authors call this a possible neurobiological basis, not a validated biomarker, and caution against single EEG indicators.
- **van Luijtelaar et al. 2010** (J Neuropsychiatry Clin Neurosci, [doi](https://www.doi.org/10.1176/JNP.2010.22.2.208)): reduced P300, and at rest lower alpha peak frequency and reduced beta power in burnout patients.
- **Golonka et al. 2019:** reduced resting eyes-open alpha power in burnout ([PMC6701350](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6701350/); details via the 2025 summary).
- **Tement et al. 2016** (students, eyes-closed): alpha frequency related to depression, alpha power to burnout.
- **Yakovenko et al. 2021:** decreased anterior beta in the exhaustion stage.
- **Harmatiuk 2023:** alpha/gamma connectivity differences in students.
- **Tukaiev 2012/2022:** only gender differences.
- A 2025 mechanistic review of burnout EEG exists ([PMC12347992](https://pmc.ncbi.nlm.nih.gov/articles/PMC12347992)) but could not be read (CAPTCHA).

### Inferences
- The burnout literature points loosely toward slower or lower alpha and reduced beta at rest. That is the *opposite* sign of the app's acute fatigue logic, where alpha rises and beta-relative indices go up with fatigue. Simply accumulating daily "fatigue" scores is therefore not a validated burnout tracker.
- Given the evidence, the app should frame EEG as measuring *acute, within-day load and fatigue patterns and recovery behaviour*, which are plausible risk factors. It should not claim to detect or diagnose burnout.
- A validated questionnaire (e.g., MBI, Burnout Assessment Tool, or the Copenhagen Burnout Inventory) should anchor any chronic-risk view. Longitudinal EEG trends (e.g., resting eyes-closed IAF or alpha reactivity measured at the same time each morning) could be explored as an *experimental* indicator only.
- Burnout overlaps with depression. Any "high risk" output should signpost professional help rather than imply a diagnosis.

### Gaps
- No prospective or longitudinal study showing EEG predicts burnout onset was found.
- No exhaustion-disorder (Swedish clinical) resting-EEG paper was retrieved in this session.
- Chronic-stress EEG beyond burnout (e.g., cortisol-linked alpha changes) was not covered.

## 5. Best practices: normalisation, artefacts, smoothing, self-report, uncertainty

### Takeaway
The evidence supports the following practices:
- Use relative and personalised measures.
- Exclude EMG-dominated frequencies at peripheral sites, or use them only as flags.
- Account for drift within and across sessions.
- Validate against behaviour and self-report rather than trusting raw indices.

Classifier accuracies from wearable studies are modest (about 70–80%) and often optimistically biased, so outputs should be coarse and shown with explicit uncertainty.

### Cited Findings
- Absolute vs relative power can flip conclusions: total power rises with time on task, so absolute theta rises while relative theta falls ([Wascher 2018](https://www.frontiersin.org/articles/10.3389/fnhum.2018.00205/full)).
- **EMG handling:**
  - Treat power above 25 Hz and effects growing away from Cz as EMG.
  - No method fully cleans beta or gamma without dense arrays and a Laplacian.
  - [PMC9480942](https://pmc.ncbi.nlm.nih.gov/articles/PMC9480942)
- Fatigue studies with ear-EEG dropped beta entirely because of EMG and kept delta, theta and alpha plus peak frequencies ([Yarici et al.](https://arxiv.org/pdf/2301.06406)).
- **Amplitude thresholding:** epochs above ±400 µV were rejected in the ear-EEG drowsiness work. The window was 30 s for drowsiness ([Nakamura 2018](https://www.commsp.ee.ic.ac.uk/~mandic/research/EEG_BCI/TN_DPM_et_all_Ear-EEG_Drowsiness_IJCNN_2018.pdf)) and 10 s for fatigue (Yarici).
- **Dry electrodes:** they inflate low-frequency (delta/theta) power and are sensitive to blinks and eye movements, worse with certain reference placements ([Sensors 2024](https://www.mdpi.com/1424-8220/24/24/8108)).
- **Optimistic bias in wearable classifiers:**
  - Hyperparameters tuned on all data and 50%-overlapping epochs (Yarici).
  - 10-fold CV mixing trials of the same subject (Nakamura).
  - Synthetic-data leakage (Raufi & Longo).
- Self-report is preferred over task-load labels as ground truth, because people with different expertise, motivation or fatigue experience the same task differently ([Raufi & Longo 2022](https://arxiv.org/pdf/2202.12937)).
- Tran 2020 recommends combining theta with alpha to accommodate individual variability ([Macquarie](https://researchers.mq.edu.au/en/publications/the-influence-of-mental-fatigue-on-brain-activity-evidence-from-a/)).

### Inferences: practical design implications for the scoring engine
1. **Re-weight indices by evidence:**
   - Make the fatigue score primarily **theta power (log, relative to the session baseline)** plus **alpha power** and **IAF slowing** versus calibration.
   - Drop beta from the fatigue denominator, or at least cap its influence.
   - Use low beta only (about 13–20 Hz, avoiding the 16 Hz device spike reported for PSBD Headphones) if beta is used at all.
2. **Rename or rebuild "stress":**
   - The 20–30 Hz / alpha index at temporal sites is mostly EMG plus alpha suppression.
   - Either relabel it as "muscle tension / arousal (experimental)" or replace it with an explicit EMG metric (e.g., 35–100 Hz power with notch filtering).
   - Use that EMG metric as a gate: when EMG is high, blank or grey out the attention, relaxation and stress indices rather than reporting them.
3. **Merge or de-duplicate confounded indices:**
   - Attention (beta/alpha) and relaxation (alpha/beta) are reciprocals of each other, so they carry the same information.
   - Load (theta/alpha) and fatigue (theta-based) share theta.
   - Show at most 2–3 conceptually distinct dimensions: an alertness/fatigue trend, an engagement/load proxy, and EMG/tension. Do not show five independent-looking gauges.
4. **Normalisation:**
   - Keep the per-session eyes-open baseline. Add a rolling personal reference built from many sessions (median and MAD of baseline-normalised values) to put a day's values in context.
   - Re-estimate IAF periodically, since it drifts within a session.
   - Use log power and z-scores rather than raw ratios, because ratios of noisy small numbers explode.
   - Prefer within-session slopes (change per 30 min) over absolute levels when comparing across days.
5. **Artefact pipeline:**
   - Contact/impedance check, discarding sessions or segments with poor contact.
   - Amplitude and flatline thresholds.
   - Blink and eye detection (large low-frequency deflections) to exclude delta/theta in those epochs.
   - High-frequency EMG gating.
   - Mains notch at 50 Hz (India) plus checks at device-specific spurious peaks.
   - Report the percentage of clean data per session.
6. **Smoothing:**
   - Compute spectra on 2–4 s windows with Welch averaging.
   - Aggregate to 30–60 s for display and to 5–15 min for fatigue trends. Time-on-task effects in the literature unfold over tens of minutes (about 50–60 min sessions).
   - Use median or robust smoothing so short artefacts don't spike scores.
7. **Combine with self-report and behaviour:**
   - Ask brief periodic ratings, e.g., Karolinska Sleepiness Scale, a 1–10 fatigue scale or NASA-TLX-lite, and use them to calibrate per-person mapping and weights.
   - Optionally add keyboard/mouse behaviour or break patterns.
   - Use a validated burnout questionnaire, not EEG, for the chronic-risk view.
8. **Present uncertainty:**
   - Show coarse states (low / typical / elevated relative to *your* usual) with confidence bands or a data-quality indicator, not precise numbers.
   - Grey out when data quality is low.
   - Label everything as wellness and non-diagnostic.
   - Avoid claims that EEG detects burnout; frame it as "patterns associated with fatigue" plus recovery nudges such as break reminders.
9. **Strongest vs weakest evidence summary:**
   - **Strong:** theta increase with mental fatigue (meta-analysis, g ≈ 1); alpha increase with fatigue (g ≈ 0.85, more variable); EMG dominance above about 20–25 Hz at lateral sites (paralysis studies); alpha measurable on dry consumer devices (r ≈ 0.7–0.9).
   - **Moderate:** IAF slowing and alpha power drift with time on task; ear-EEG drowsiness detection at about 80% (Wake vs N1).
   - **Weak or unvalidated:** theta/alpha as a workload index; beta-ratio "attention"; high-beta/alpha "stress"; FAA; any EEG marker of chronic burnout; day-to-day reliability of consumer dry headphones.

### Gaps
- No empirical guidance specific to this device was found on optimal window lengths or on how often to recalibrate IAF.
- No study testing whether EEG-based break nudges reduce fatigue or burnout in office workers was retrieved.
