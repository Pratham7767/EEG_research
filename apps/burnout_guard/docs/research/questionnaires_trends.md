# Self-report instruments for burnout, exhaustion, sleepiness and recovery; burnout trajectory and trend metrics (for a free desktop app)

## Licensing and availability: which instruments can a free desktop app embed?

### Takeaway
Three instruments are clearly free to embed. The BAT is explicitly non-proprietary and can be used free without permission, provided it is not modified and is cited. The CBI's original release carries no licence restriction and is widely redistributed. NFR is a public research subscale. The MBI cannot practically be embedded: it is a paid per-administration licence for research only, with no individual feedback and no open-web access. The PSS needs a free permission request through Mapi ePROVIDE before embedding. WHO-5 is free with attribution.

### Cited Findings
- **BAT (all versions):** the official site describes the BAT as "non-proprietary" and says it may be used free of charge without asking the authors for permission. Conditions: "the instrument should not be modified", and Schaufeli, Desart & De Witte (2020), *IJERPH* 17:9495 must be cited. The site does not mention commercial use or fees. — [burnoutassessmenttool.be](https://burnoutassessmenttool.be/en/)
- **Conflict to note:** the BAT User Manual v2.0 PDF carries a standard "all rights reserved… without prior written permission of the authors" notice. The website's later, explicit non-proprietary statement is the operative licence for administering the questionnaire. Reproducing the manual document itself is a separate matter. — [BAT Manual v2.0 (ANZSOM copy)](https://www.anzsom.org.au/static/uploads/files/journal-club-2022-user-manual-bat-version-2-0-wfyrofkargol.pdf); [burnoutassessmenttool.be](https://burnoutassessmenttool.be/en/)
- **CBI:** the original first-edition document from the Danish National Institute of Occupational Health (NFA) shows the full item text and scoring with no licence, copyright restriction or terms of use, only the authors' affiliation and a February 2004 date. — [NFA, CBI first edition](https://nfa.dk/media/hl5nbers/cbi-first-edition.pdf)
- **MBI (Mind Garden):** the licence to reproduce costs $2.75 per copy at a 50-copy minimum, falling to $0.39 at 50,000 copies, and is "not sold individually". The licence is for "research data collection only, not for providing individual feedback to participants". Online use requires controlled access: "The instrument may not be made available via the open web." Each opening of the survey counts as one paid administration, and the survey must be removed after data collection. Emailing the instrument is prohibited. — [Mind Garden MBI License to Reproduce](https://www.mindgarden.com/173-mbi-license-to-reproduce.html)
  - This confirms the MBI cannot be embedded in a free, openly distributed, individual-feedback desktop app.
- **PSS:** Mind Garden offers a free download of the PSS form but states "Mind Garden does not publish the PSS" and "Copyright © 1994 by Sheldon Cohen". — [Mind Garden PSS](https://mindgarden.com/132-perceived-stress-scale)
  - Cohen's CMU lab directs permission requests to Mapi Research Trust's ePROVIDE platform. Submitting a request "is completely free of charge" and "does not commit you to purchasing a questionnaire". — [CMU Stress, Immunity & Disease Lab scales page](https://www.cmu.edu/dietrich/psychology/stress-immunity-disease-lab/scales)
  - The lab states that a validated 4-item version (PSS-4) exists and that "The Perceived Stress Scale is not a diagnostic instrument; there are no score cut-offs." — [CMU lab](https://www.cmu.edu/dietrich/psychology/stress-immunity-disease-lab/scales)
- **WHO-5:** PsyToolkit says it may be used if its authors and Topp et al. (2015) are acknowledged. — [PsyToolkit WHO-5](https://www.psytoolkit.org/survey-library/who5.html)
- **OLBI:** NovoPsych hosts the OLBI on its own platform, credits Demerouti (1999), and gives no licence statement. — [NovoPsych OLBI](https://novopsych.com/assessments/well-being/oldenburg-burnout-inventory-olbi/)
- **BAT4 data handling:** the BAT4 authors suggest reporting group-level aggregates to organisations and disclosing individual scores only to the individual. — [Hadzibajramović, Schaufeli & De Witte 2024, PLoS ONE](https://www.wilmarschaufeli.nl/publications/Schaufeli/607.pdf)

### Inferences
- Safest core set for a free app:
  - BAT-12, as the primary validated burnout measure with published individual cut-offs
  - BAT4 as a frequent pulse
  - CBI personal and work-related burnout as an alternative or complement with a 0–100 metric
  - NFR-11 for recovery
  - WHO-5 for general wellbeing
- Add PSS-4 only after filing the free ePROVIDE request. Exclude the MBI entirely.
- Because the BAT may not be modified, the app should present BAT items verbatim, with the original scale and order. Custom pulse items must be clearly separated and not labelled "BAT".
- The app should keep the individual's data local and not report it to employers by default. This matches the BAT4 authors' guidance and also suits a desktop-first privacy model.

### Gaps
- **OLBI licence:** I found no authoritative licence page. It is widely described as freely available in the literature, but I could not verify this from a primary source. Contact Demerouti or treat it as optional.
- **Karolinska Sleepiness Scale (KSS; Åkerstedt & Gillberg 1990):** I did not retrieve a licence page. Background knowledge, unverified in this session:
  - It is a single item, rated 1–9 from "extremely alert" to "very sleepy, great effort to keep awake, fighting sleep", reporting state sleepiness over the last ~5–10 minutes.
  - It is commonly treated as free for research use, and scores of 7 or more are often used to denote meaningful sleepiness.
  - Verify the licence before embedding.
- **Recovery Experience Questionnaire (Sonnentag & Fritz 2007, *JOHP*):** 16 items across four subscales (psychological detachment, relaxation, mastery, control), rated 1–5. This is background knowledge, not verified this session. The licence is unknown; an academic article copyright may restrict reproducing the items. Treat it as "describe, don't embed" until permission is confirmed.
- **Single-item burnout measures:** not verified this session (background knowledge only). Rohland et al. 2004 uses a 5-option self-defined burnout item, and the Dolan / Mini-Z version has a cut-off of 3 or more. These are freely circulated, but I found no primary licence statement.
- **WHO-5 licence:** I did not confirm the current licence wording on the official WHO publication page. Some editions are published under a CC BY-NC-SA IGO licence, which needs checking.

## Instrument details: items, scales, scoring, cut-offs, recall, frequency, reliability

### Takeaway
- **BAT-12:** 1–5 frequency scale; the mean of the 12 items gives a traffic-light score (green up to 2.53, orange 2.54–2.95, red 2.96 and above).
- **CBI:** 0–100 scale; 50 or more counts as "high".
- **NFR-11:** yes/no items scaled to 0–100; 54.5 or more (6 or more "yes") means high need for recovery.
- **WHO-5:** score ×4 gives 0–100; 50 or below warrants further checking.
- **BAT4:** no cut-off exists, so use it only for within-person trends.

### Cited Findings

**BAT (Schaufeli, De Witte & Desart)** — source: [BAT Manual v2.0](https://www.anzsom.org.au/static/uploads/files/journal-club-2022-user-manual-bat-version-2-0-wfyrofkargol.pdf)
- **Response scale:** 1 = Never, 2 = Rarely, 3 = Sometimes, 4 = Often, 5 = Always. The instruction asks how often each statement applies and specifies no fixed recall window.
- **BAT-23 core structure:** exhaustion (8 items), mental distance (5 in the work version, 4 in the general version), cognitive impairment (5), emotional impairment (5). There are also 10 secondary-symptom items: sleep problems, worry, tension, anxiety, noise sensitivity, palpitations, stomach complaints, headaches, muscle pain and frequent illness.
- **BAT-12:** 3 items per core dimension.
- **Scoring:** scale score = mean of its items (range 1–5). Total core score = sum ÷ 23 for the full version or ÷ 12 for the short version.
- **Cut-offs (Flemish employees, total core score):**

| Zone | BAT-23 | BAT-12 |
|---|---|---|
| Green (no risk) | 1.00–2.58 | 1.00–2.53 |
| Orange (at risk) | 2.59–3.01 | 2.54–2.95 |
| Red (very high risk) | 3.02–5.00 | 2.96–5.00 |

- For individual use, the manual recommends only the BAT-12 total, because the subscale red cut-offs have low sensitivity. Cut-offs for the general (non-work) short version are missing.

**BAT4 (Hadzibajramović, Schaufeli & De Witte, 2024, *PLoS ONE* 19(2):e0297843)** — source: [PDF](https://www.wilmarschaufeli.nl/publications/Schaufeli/607.pdf)
- **Items (one per dimension, taken from the BAT-12), quoted as published:**
  - Exhaustion: "At work, I feel mentally exhausted"
  - Mental distance: "I struggle to find any enthusiasm for my work"
  - Cognitive impairment: "When I'm working, I have trouble concentrating"
  - Emotional impairment: "At work I may overreact unintentionally"
- **Response scale:** never / rarely / sometimes / often / always.
- **Reliability:** Rasch Person Separation Index of 0.72 in the pooled sample, ranging from 0.64 (Ireland) to 0.77 (Japan).
- **Cut-offs:** none established.
- **Intended use:** screening at group or organisational level, not diagnosis. The authors recommend the BAT-23 for clinical use.
- **Validity:** the scale met Rasch criteria in 6 of 8 countries; Austria and Japan were the exceptions.

**CBI (Kristensen et al.; NFA first edition 2004)** — source: [NFA CBI](https://nfa.dk/media/hl5nbers/cbi-first-edition.pdf)
- **Personal burnout (6 items, frequency scale):**
  - How often do you feel tired?
  - How often are you physically exhausted?
  - How often are you emotionally exhausted?
  - How often do you think: "I can't take it anymore"?
  - How often do you feel worn out?
  - How often do you feel weak and susceptible to illness?
- **Work-related burnout (7 items).** Items 1–3 use a degree scale (to a very high degree … to a very low degree):
  - Is your work emotionally exhausting?
  - Do you feel burnt out because of your work?
  - Does your work frustrate you?
- Items 4–7 use the frequency scale:
  - Do you feel worn out at the end of the working day?
  - Are you exhausted in the morning at the thought of another day at work?
  - Do you feel that every working hour is tiring for you?
  - Do you have enough energy for family and friends during leisure time? (reverse-scored)
- **Scoring:** Always/To a very high degree = 100, then 75, 50, 25, down to 0. The scale score is the mean of the items.
  - The extracted text confirmed these values for the frequency scale; applying the same 100/75/50/25/0 values to the degree anchors is standard CBI practice but was not explicit in the extracted text.
  - A respondent counts as a non-responder with fewer than 3 personal or 4 work items answered.
- **Cut-off and norms:** "high burnout" is 50 or more. In the PUMA study of human-service workers, 22.2% were high on personal and 19.8% high on work-related burnout.
  - Danish representative sample, personal burnout: mean 32.7 (SD 15.7); employed participants: mean 31.7 (SD 14.8).
  - PUMA work-related burnout: mean 33.0 (SD 17.7).
- **Reliability:** α 0.87 for both the personal and work-related scales in PUMA; α 0.80 for personal burnout in the representative sample.
- **Recall period:** not specified.

**Need for Recovery (VBBA subscale; Van Veldhoven & Broersen 2003)** — source: [van der Starre et al. 2013, BMC Public Health (PMC3890611)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3890611)
- 11 yes/no items, each coded 0 or 1.
- Sample items: "I find it hard to relax at the end of a working day"; "When I get home, people should leave me alone for some time."
- **Scoring:** sum ÷ number answered × 100. At least 8 of 11 items must be valid.
- **Cut-off:** high NFR is 54.5 or more, which equals 6 or more "yes" answers (cut-off taken from Broersen et al.).
- **Reliability:** α = 0.85.

**WHO-5** — source: [PsyToolkit WHO-5](https://www.psytoolkit.org/survey-library/who5.html); review: [Topp et al. 2015, Psychother Psychosom](https://pubmed.ncbi.nlm.nih.gov/25831962/)
- **Items** (each prefaced "Over the past two weeks…"):
  - I have felt cheerful in good spirits
  - I have felt calm and relaxed
  - I have felt active and vigorous
  - I woke up feeling fresh and rested
  - My daily life has been filled with things that interest me
- **Response scale:** 0 = At no time to 5 = All of the time.
- **Scoring:** sum × 4 gives 0–100.
- **Cut-off:** 50 or below suggests possible depression and warrants further checks.
- **Recall period:** 2 weeks, which implies administering it no more than every 2 weeks.

**OLBI (Demerouti)** — source: [NovoPsych OLBI](https://novopsych.com/assessments/well-being/oldenburg-burnout-inventory-olbi/)
- 16 items with two subscales of 8 items each. Exhaustion is items 2, 4, 5, 8, 10, 12, 14 and 16; disengagement is the rest. Each subscale ranges from 8 to 32.
- NovoPsych uses raw thresholds of 23 or more for exhaustion and 22 or more for disengagement. These are platform norms and not verified against primary sources.

**PSS**
- 10-item version; a validated 4-item version also exists.
- Norms: Cohen & Williamson 1988 (US) and Warttig et al. 2013 (UK).
- No cut-offs. — [CMU lab](https://www.cmu.edu/dietrich/psychology/stress-immunity-disease-lab/scales)

### Inferences
Suggested administration cadence, aligned to each instrument's recall window:
- **BAT4:** weekly (about 30 seconds).
- **BAT-12:** monthly (about 2 minutes), as the "anchored" assessment with valid cut-offs.
- **NFR-11:** every 2 to 4 weeks, or weekly if the user opts in.
- **WHO-5:** every 2 weeks, matching its recall period.
- **CBI personal and work-related:** monthly, as an alternative to BAT-12. Avoid running both monthly, to limit burden.
- **KSS:** at the start of a session and optionally at the end, as a state measure.

### Gaps
- I did not retrieve test–retest data or minimal-important-change values for BAT, CBI or NFR, so I found no evidence-based "meaningful change" thresholds. The trend view has to use statistical (personal-baseline) thresholds instead.
- I found no validated cut-offs for India or South Asia for any instrument. All cut-offs come from Danish, Flemish or Dutch samples.

## EMA / experience sampling: frequency, burden, compliance

### Takeaway
Mobile EMA averages about 82% compliance. In non-clinical adults, 1–3 prompts per day gives the best compliance (87%), compared with 4–5 per day (77%). Prompts longer than about 26 items lose compliance. A desktop app should use 1–3 very short momentary check-ins per workday.

### Cited Findings
- **Pooled compliance:** 81.9% (95% CI 79.1–84.4) across 68 data sets, with very high heterogeneity (I² = 98%). — [Williams et al. 2021, JMIR 23(3):e17023](https://www.jmir.org/2021/3/e17023)
- **Prompt frequency (non-clinical samples):** 1–3 prompts per day gave 87% compliance, 4–5 gave 76.9%, and 6 or more gave 79.4%. The overall model was not significant (p = .07). — [Williams et al. 2021](https://www.jmir.org/2021/3/e17023)
- **Prompt length:** prompts with more than 26 items had the lowest compliance (63%). — [Williams et al. 2021](https://www.jmir.org/2021/3/e17023)
- **Study duration:** compliance rose with longer monitoring, from 77.4% under 7 days to 85.3% over 14 days in non-clinical samples. The authors also found "no compelling relationship" between burden features and compliance overall. — [Williams et al. 2021](https://www.jmir.org/2021/3/e17023)
- **Caveat:** pooled rates may be inflated by publication bias and by studies excluding low-compliance participants. — [Williams et al. 2021](https://www.jmir.org/2021/3/e17023)

### Inferences
- **Default design:** 1 prompt at session start (KSS plus an energy slider) and 1 at end of day (fatigue, stress and "did you take breaks"), each taking under 30 seconds. Make a mid-day prompt optional.
- Compliance in a voluntary, unpaid, long-running app will likely be lower than in research studies. The trend views should tolerate missing days, for example by requiring at least 3 of 5 workdays before showing a weekly mean.

### Gaps
- I did not retrieve EMA studies specific to workplace burnout or fatigue, or evidence on long-term (months-long) compliance decay.

## Burnout trajectory, early warning signs and the ICD-11 definition

### Takeaway
ICD-11 frames burnout as an occupational phenomenon, not a medical condition, with three dimensions: exhaustion, mental distance/cynicism, and reduced efficacy. The best-supported developmental order is that exhaustion comes first and leads to cynicism (Leiter & Maslach), with cynicism feeding back. However, the effects are small and unfold over months to a year, so week-scale burnout "prediction" from self-report is weak. Rising exhaustion and need for recovery are the most defensible early signals.

### Cited Findings
- **ICD-11 definition:** "Burn-out is a syndrome conceptualized as resulting from chronic workplace stress that has not been successfully managed." Its three dimensions are:
  - "feelings of energy depletion or exhaustion"
  - "increased mental distance from one's job, or feelings of negativism or cynicism related to one's job"
  - "reduced professional efficacy"
- ICD-11 states it "refers specifically to phenomena in the occupational context" and is "not classified as a medical condition". It sits in the chapter "Factors influencing health status or contact with health services". — [WHO, 28 May 2019](https://www.who.int/news/item/28-05-2019-burn-out-an-occupational-phenomenon-international-classification-of-diseases)
- **Taris et al. (2005, *Work & Stress* 19(3):238–255)** compared three developmental models in two Dutch panels (218 oncology staff over three yearly waves; 967 teachers over two waves). — [Taris et al. 2005](https://scispace.com/pdf/are-there-causal-relationships-between-the-dimensions-of-the-1676bbh7l6.pdf)
  - **Leiter & Maslach (1988):** exhaustion leads to depersonalization, which leads to reduced accomplishment.
  - **Golembiewski:** depersonalization comes first and exhaustion last. This model fit poorly.
  - **Lee & Ashforth:** exhaustion leads to depersonalization and also lowers accomplishment directly.
  - **Best fit:** an integration of Leiter & Maslach and Lee & Ashforth, with depersonalization feeding back on the other dimensions.
  - **Key result:** high exhaustion predicted higher depersonalization one year later (β .18 and .15).
  - **Caveat:** the authors note the effects are "not large enough to be of practical use in the recognition of burnout", and earlier longitudinal studies mostly showed stability effects (each dimension predicting itself).
- **Other evidence:** a 6-month longitudinal study found workload predicted later exhaustion and low reward predicted later cynicism. The authors suggest burnout is relatively stable and that 6 months may be too short to show change. — [Jimenez & Dunkl 2017, Front Psychol 8:12](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2017.00012/pdf)
- **Recovery signals:** NFR captures difficulty unwinding after work, for example "hard to relax at the end of a working day". Its high-risk cut-off (54.5 or more) is used in occupational cohorts. — [van der Starre et al. 2013](https://pmc.ncbi.nlm.nih.gov/articles/PMC3890611)
- **Secondary symptoms:** the BAT treats sleep problems, worry, tension, psychosomatic complaints and frequent illness as secondary burnout symptoms. — [BAT Manual v2.0](https://www.anzsom.org.au/static/uploads/files/journal-club-2022-user-manual-bat-version-2-0-wfyrofkargol.pdf)

### Inferences
- The app should treat sustained rises in exhaustion, need for recovery and sleepiness as early-warning signals, and rising mental distance or cynicism as an escalation signal. Cognitive and emotional impairment, the extra BAT dimensions, are also late or core features.
- **Behavioural proxies:** longer sessions, late-evening work and skipped breaks can be logged objectively by a desktop app. These should be presented as workload context, not as burnout indicators. I found no validated thresholds for them in this session.
- **Timescale:** burnout develops over months, so weekly views should be framed as "strain and recovery balance", with monthly BAT-12 as the burnout-level anchor.

### Gaps
- I did not retrieve primary evidence quantifying early warning from need for recovery (for example, NFR predicting later sickness absence or burnout). Such studies are known to exist (Dutch Maastricht Cohort, e.g. de Croon / Sluiter), but they were not fetched.
- I found no evidence-based thresholds for weekly working hours or skipped breaks as burnout predictors.
- I found no validated "seek help" threshold beyond each instrument's cut-offs: BAT red zone, CBI 50 or more, NFR 54.5 or more, WHO-5 50 or below.

## Trend analytics and burnout-risk indicator design

### Takeaway
No validated individual burnout-risk algorithm combining session data and self-report was found. The defensible design is:
- anchor risk zones to published cut-offs (BAT-12, NFR, WHO-5)
- detect change against a personal baseline built from rolling means
- require persistence across several weeks before flagging, to reduce false alarms
- use non-diagnostic language throughout

### Cited Findings
- BAT-12 total-score cut-offs are the recommended basis for individual decisions; subscale cut-offs are not. — [BAT Manual v2.0](https://www.anzsom.org.au/static/uploads/files/journal-club-2022-user-manual-bat-version-2-0-wfyrofkargol.pdf)
- The BAT4 has no cut-off and is meant for screening, not diagnosis. — [Hadzibajramović et al. 2024](https://www.wilmarschaufeli.nl/publications/Schaufeli/607.pdf)
- The PSS has no cut-offs and is "not a diagnostic instrument". — [CMU lab](https://www.cmu.edu/dietrich/psychology/stress-immunity-disease-lab/scales)
- Burnout dimensions are largely stable over time, and cross-lagged effects are small. — [Taris et al. 2005](https://scispace.com/pdf/are-there-causal-relationships-between-the-dimensions-of-the-1676bbh7l6.pdf)

### Inferences
These design defaults are my synthesis, not validated algorithms.
- **Daily view:** KSS and end-of-day fatigue and stress (0–10), shown with a 7-day rolling mean. Overlay objective session minutes, breaks taken and last-activity time.
- **Weekly view:** BAT4 mean (1–5) and an optional NFR, plotted against the personal baseline, which is the median of the first 4 weeks.
  - Flag "elevated" when the 2-week mean exceeds baseline by 0.5 points on the 1–5 scale, or by about 1 SD of the person's own weekly variability, for 2 or more consecutive weeks.
- **Monthly anchor:** BAT-12 traffic light (green, orange, red), using the published cut-offs.
- **Composite risk indicator:** show three levels (OK / watch / talk to someone) rather than a single opaque number.
  - **Watch:** BAT-12 orange, or NFR 54.5 or more, or a 2-week sustained rise in weekly BAT4 or fatigue above baseline.
  - **Talk to someone:** BAT-12 red, or WHO-5 50 or below, or watch-level signals persisting for 4 or more weeks.
- **Objective data's role:** session data (hours, late work, skipped breaks) should only adjust explanatory text ("your work hours rose 20% while energy fell"). It should never raise the risk level by itself.
- **Avoiding false alarms and medicalisation:**
  - Use language such as "strain signals" and "may be worth talking to someone", never "you have burnout".
  - Require minimum data before flagging.
  - Let users snooze or adjust prompts.
  - Keep data local by default.
- **Change detection:** an EWMA or CUSUM on weekly scores against the personal baseline is a reasonable approach. No burnout-specific validation was found.

### Gaps
- I found no published validation of personal-baseline or change-point methods for burnout self-report.
- I found no evidence on false-positive rates of repeated burnout screening for individuals.

## Safety: what the app must say or do when scores are high

### Takeaway
The app must not diagnose; WHO does not classify burnout as a medical condition. At high scores it should signpost to professional help, including India's free government tele-mental-health helpline Tele-MANAS (14416 or 1-800-891-4416). WHO-5 at 50 or below should specifically prompt suggesting a check-up, because it may indicate depression.

### Cited Findings
- Burnout is "not classified as a medical condition" and applies only to the occupational context. — [WHO 2019](https://www.who.int/news/item/28-05-2019-burn-out-an-occupational-phenomenon-international-classification-of-diseases)
- A WHO-5 score of 50 or below may indicate depression and warrants further checks. — [PsyToolkit WHO-5](https://www.psytoolkit.org/survey-library/who5.html)
- The BAT4 is not a diagnostic tool; the BAT-23 is recommended for clinical settings. — [Hadzibajramović et al. 2024](https://www.wilmarschaufeli.nl/publications/Schaufeli/607.pdf)
- **Tele-MANAS:** toll-free numbers 14416 or 1-800-891-4416, launched by the Government of India in October 2022 "to enhance mental health service delivery nationwide". It offers multi-language support through 51 Tele-MANAS cells across all States and Union Territories. — [PIB press release](https://pib.gov.in/PressReleasePage.aspx?PRID=2022057)
  - The PIB page did not state 24x7 availability. It is widely described as 24x7 (e.g., [IIT Kanpur counselling page](https://iitk.ac.in/counsel/TeleManas.php)), but I did not verify this directly.

### Inferences
- **On a red or "talk to someone" result**, show:
  - a plain-language explanation of what the score means
  - a reminder that it is not a diagnosis
  - suggestions: talk to a GP or doctor, the company EAP if available, or a mental-health professional
  - Tele-MANAS 14416
  - for crises, emergency number 112
- If the app adds any mood or distress items, it should show crisis resources immediately when a self-harm-related response is given. None of the recommended instruments include a self-harm item.
- Never share individual scores with the employer without explicit opt-in.

### Gaps
- I did not retrieve formal regulatory guidance (e.g., India's CDSCO or EU MDR) on when a wellbeing app becomes a medical device. Non-diagnostic framing is the standard mitigation, but this was not verified.
- I did not verify the precise operating hours and language list for Tele-MANAS from a primary page.
