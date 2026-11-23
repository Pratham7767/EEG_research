# Privacy, Ethics and Law for Workplace Use of Consumer EEG / Neurodata (employee-private burnout app)

Scope: desktop burnout-prevention app built in India, used by employees in India / EU / US, reading EEG from headphones, storing scores locally, employee as the only viewer. Current as of 20 Nov 2026. Not legal advice. Items marked **[unverified this session]** come from background knowledge and were not confirmed against a fetched source in this research pass; the report writer should present them as such or omit them.

## India: DPDP Act 2023 and DPDP Rules 2025

### Takeaway
The DPDP Rules 2025 were notified on 13 Nov 2025. The substantive duties (notice, consent, data principal rights, security, breach reporting) apply from 13 May 2027, so in Nov 2026 the main obligations are about six months away. DPDP has no "sensitive" or "health" data category, so EEG gets no special status. Employers can process employee data without consent under the s.7(i) employment "legitimate use", which makes relying on consent a weak basis for anything the employer operates. A truly local app that the employee controls fits best with the consent model and, arguably, with the personal-use carve-out.

### Cited Findings
- MeitY notified the DPDP Rules 2025 on **13 Nov 2025**, in three phases:
  - Immediate: Board and institutional provisions.
  - +12 months (**13 Nov 2026**): consent manager registration.
  - +18 months (**13 May 2027**): substantive obligations, covering notice and consent, fiduciary duties, data principal rights, children's data, cross-border transfers, and the Board's penalty powers. — [AZB & Partners](https://www.azbpartners.com/bank/update-indias-digital-personal-data-protection-framework-comes-into-effect/); also [PIB document](https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf)
- Notice contents:
  - It must stand alone and be clear, so that consent is specific and informed.
  - It must give an itemised description of the personal data, the specified purpose, and the goods or services involved.
  - It must give a link to withdraw consent, exercise rights and complain to the Board. — [AZB](https://www.azbpartners.com/bank/update-indias-digital-personal-data-protection-framework-comes-into-effect/)
- Minimum security safeguards: encryption, masking or tokenisation; access controls; logs and monitoring; backup and continuity; logs kept for one year; security terms in processor contracts. — [AZB](https://www.azbpartners.com/bank/update-indias-digital-personal-data-protection-framework-comes-into-effect/)
- Breach notification: tell the Board and affected principals "without delay", then send the Board a detailed report within 72 hours. CERT-In separately requires notice within 6 hours under the IT rules. — [AZB](https://www.azbpartners.com/bank/update-indias-digital-personal-data-protection-framework-comes-into-effect/)
- Fiduciaries must keep personal data, traffic data and logs for at least 1 year for specified government purposes. Grievances must be answered within an outer limit of 90 days. — [AZB](https://www.azbpartners.com/bank/update-indias-digital-personal-data-protection-framework-comes-into-effect/)
- The AZB summary of the Rules does not discuss any sensitive-data category. Health appears only in exemptions for children's data. — [AZB](https://www.azbpartners.com/bank/update-indias-digital-personal-data-protection-framework-comes-into-effect/)
- Section 7(i) legitimate use:
  - It covers processing "for the purposes of employment or those related to safeguarding the employer from loss or liability". Examples include corporate espionage, trade secrets, IP, and "provision of any service or benefit sought by a data principal who is an employee".
  - It is a lawful ground, not an exemption from the Act. The "service or benefit" limb is triggered by the employee's request.
  - Commentators call consent "the wrong starting point for an employment relationship". — [Sansa Legal](https://www.sansalegal.com/post/how-to-rely-on-the-employment-legitimate-use-under-section-7-i-of-the-dpdp-act); see also [Bar & Bench / NovoJuris](https://www.barandbench.com/law-firms/view-point/navigating-legitimate-use-exemption-employee-data-digital-personal-data-protection-act-2023), [LiveLaw on surveillance clauses](https://www.livelaw.in/articles/employment-surveillance-clauses-void-dpdp-regime-539957)
- **[unverified this session]** Further points from the Act's text:
  - s.6 consent must be "free, specific, informed, unconditional and unambiguous with a clear affirmative action", limited to what is necessary for the purpose, and withdrawable as easily as it was given.
  - s.3(c)(i) excludes personal data processed by an individual for any personal or domestic purpose.
  - The 2023 Act dropped the "sensitive personal data" category (including health and biometric data) found in the 2018/2019 Bills.
  - Penalties go up to ₹250 crore per instance for security-safeguard failures.
  - Data principals have rights to access, correction, erasure and grievance redress, and to nominate someone to act for them.

### Inferences
- Why employee consent is problematic in India:
  - s.7(i) lets an employer process data for employment purposes without consent. Any "consent" an employer collects for brain monitoring is therefore hard to separate from that power, and a court or the Board could doubt it was "free" or "unconditional".
  - s.7(i) was also drafted around protecting the employer, so it is a poor fit for intimate neural monitoring.
  - Either way, an employer-run deployment invites disputes.
- If the app processes everything on the device and the vendor never receives personal data, the vendor may not be a "data fiduciary" for that data at all. The employee using it for themselves arguably falls under the s.3(c)(i) personal/domestic exclusion. Two things break this position:
  - any telemetry, cloud sync, crash logs containing scores, account login, or licence server with identifiers
  - an employer that procures or mandates the app
- Even without a special category, the high sensitivity of EEG favours voluntarily following the DPDP notice and consent format (itemised data list, purpose, withdrawal link). Doing so also future-proofs the app for when a vendor service does touch data.

### Gaps
- I could not fetch the official text of DPDP Act ss.3, 6, 7 or of Rules 3 and 6 (MeitY PDF) this session, so section wording is quoted from secondary sources.
- I found no Indian guidance (Board, MeitY FAQ) specifically on neural, biometric or wellness data. The Data Protection Board's operational status in Nov 2026 was not confirmed.

## GDPR / EU: special category status, employee consent, DPIA, AI Act, and the medical-device boundary

### Takeaway
EEG-derived data is not automatically "special category" data under Art. 9, but regulators treat it as high-risk. It becomes health data when it reveals mental-health information such as burnout or stress-related conditions. It becomes biometric special-category data only when used to identify someone. Consent from employees to an employer is presumed invalid because of the power imbalance. The AI Act's workplace emotion-recognition ban (Art. 5(1)(f)) creates real risk if the app infers emotions such as stress or frustration and is used "in the workplace". Commission guidelines say stress and burnout detection does not fall within the medical exception. Fatigue or "physical state" detection falls outside the ban. Product claims must stay away from diagnosing or treating anything.

### Cited Findings
- ICO (UK GDPR, which mirrors EU GDPR) on special category status:
  - Neurodata collected for medical purposes is likely special-category health data.
  - Neurodata is special-category biometric data only when used to identify or verify a person, which the ICO expects to be rare.
  - Organisations should not assume neurodata is health data just because it comes from the body.
  - Neurodata should be treated as "high impact and high risk" even when it is not special category.
  - Data can move into special category: tracking employee concentration "could reveal mental health information". — [ICO Tech Futures: Neurotechnology – regulatory issues](https://ico.org.uk/about-the-ico/research-and-reports/ico-tech-futures-neurotechnology/regulatory-issues)
- ICO on employment:
  - Organisations must show a clear need for neurodata over other methods.
  - "Because of the power imbalance, consent is likely inappropriate in most cases".
  - Legitimate interests may be hard to justify.
  - The ICO doubts users can give fully informed consent when they don't understand what neurodata reveals. Giving specific guarantees about which inferences are drawn can support valid consent. — [ICO](https://ico.org.uk/about-the-ico/research-and-reports/ico-tech-futures-neurotechnology/regulatory-issues)
- ICO on accuracy and decisions:
  - Inferring emotion is the highest-risk use, and the science behind it is debated.
  - Biased models can discriminate against neurodivergent people.
  - Decisions should not rely on single snapshots, and outputs should be presented as time-specific.
  - Keep only the data needed.
  - Test devices on diverse people, since fit and calibration bias the data.
  - Closed-loop or automated effects on concentration, productivity or sleep raise Art. 22 concerns. — [ICO](https://ico.org.uk/about-the-ico/research-and-reports/ico-tech-futures-neurotechnology/regulatory-issues)
- EDPS and AEPD have published dedicated neurodata analyses: [EDPS TechDispatch #1/2024 – Neurodata](https://www.edps.europa.eu/data-protection/our-work/publications/techdispatch/2024-06-03-techdispatch-12024-neurodata_de) and [AEPD blog on neurodata](https://aepd.es/en/prensa-y-comunicacion/blog/neurodata-privacy-and-protection-of-personal-data-II). The Council of Europe is drafting guidelines on neuroscience data: [CoE T-PD(2025)1 draft](https://rm.coe.int/t-pd-2025-1-draft-guidelines-neuroscience-after-plenary-2025-september/4880287a0c). I could not fetch the full PDF texts.
- AI Act Art. 5(1)(f), scope:
  - It bans AI systems inferring **emotions** (not intentions) of natural persons **from biometric data** in the workplace and education.
  - Biometric data under Art. 3(34) covers "physical, physiological or behavioural characteristics".
  - Recital 18 excludes physical states such as pain or **fatigue**. Fatigue detection for pilots and drivers is expressly outside the ban.
  - The boundaries between emotion, mood and physical state remain unclear.
  - Recital 44 extends the ban to situations "related to" the workplace, which needs case-by-case analysis. — [FPF](https://fpf.org/blog/red-lines-under-eu-ai-act-unpacking-the-prohibition-of-emotion-recognition-in-the-workplace-and-education-institutions/)
- AI Act exceptions and examples:
  - The medical and safety exception is narrow. The medical limb applies only to therapeutic uses (per FPF, CE-marked medical devices). The safety limb covers life and health only.
  - Per FPF's reading of the Guidelines, "the medical exception does not extend to general well-being monitoring, such as stress or burnout detection".
  - Emotion recognition outside workplace and education is high-risk (Annex III 1(c)), not prohibited. — [FPF](https://fpf.org/blog/red-lines-under-eu-ai-act-unpacking-the-prohibition-of-emotion-recognition-in-the-workplace-and-education-institutions/)
  - The Commission Guidelines' emotion examples include happiness, sadness, anger and shame. Detecting pain or fatigue is outside the ban. — [CMS](https://cms.law/en/gbr/legal-updates/eu-commission-issues-guidelines-on-prohibited-ai-practices-part-ii); see also [Wolters Kluwer blog](https://legalblogs.wolterskluwer.com/global-workplace-law-and-policy/the-prohibition-of-ai-emotion-recognition-technologies-in-the-workplace-under-the-ai-act/)
- **[unverified this session]** Further GDPR and AI Act points:
  - Art. 5 AI Act prohibitions have applied since **2 Feb 2025**. Fines go up to €35m or 7% of global turnover. The Commission's Guidelines on prohibited practices were published 4 Feb 2025.
  - GDPR Art. 9(2)(a) requires *explicit* consent for special-category data. Art. 35 and the EDPB/WP29 DPIA criteria (sensitive data, vulnerable data subjects including employees, innovative technology, systematic monitoring) almost certainly trigger a DPIA for any controller of this data.
  - EDPB Guidelines 05/2020 on consent say employee consent to an employer is rarely "freely given" given the imbalance. Exceptions are possible where refusal has no adverse consequences.
  - Art. 88 lets Member States set more specific employment rules, for example German §26 BDSG.
  - Art. 2(2)(c) exempts purely personal or household processing by individuals.
- Medical-device boundary (US, FDA):
  - FDA revised its General Wellness guidance on **6 Jan 2026**.
  - Products may put outputs in the context of "sleep, activity, stress, recovery, or similar wellness domains".
  - A product falls out of the wellness policy if it is intended to diagnose, cure, mitigate, prevent or treat a disease or condition, substitutes for a cleared device, or prompts clinical action.
  - It may suggest seeing a healthcare professional when outputs fall outside wellness ranges. It must not name a specific condition, label outputs "abnormal" or diagnostic, give clinical thresholds, or provide ongoing alerts to manage a disease.
  - Intended use is judged by marketing and promotion. — [Ropes & Gray](https://www.ropesgray.com/en/insights/alerts/2026/01/fda-adapts-with-the-times-on-digital-health-updated-guidances-on-general-wellness-products); [Greenberg Traurig](https://www.gtlaw.com/en/insights/2026/01/fda-updates-two-digital-health-final-guidance-documents)
- The Ropes & Gray summary of the revised guidance gives no EEG or neuro examples. — [Ropes & Gray](https://www.ropesgray.com/en/insights/alerts/2026/01/fda-adapts-with-the-times-on-digital-health-updated-guidances-on-general-wellness-products)
- Chile's ISP concluded in 2024 that the Emotiv Insight EEG headset was not a medical device because it was not intended for diagnosis or treatment (Resolution 3147, 31 May 2024). This shows that claims drive device classification. — [Stanford Law (CodeX)](https://law.stanford.edu/2026/04/27/even-chiles-neurorights-leave-inferred-mental-data-in-a-gray-zone/)
- **[unverified this session]** EU MDR and India:
  - Under the EU MDR, software with a medical intended purpose (diagnosis, prevention, monitoring, prediction, prognosis or treatment of disease) is a device. Rule 11 usually classifies it IIa or higher.
  - "Burnout" is classified in ICD-11 (QD85) as an occupational phenomenon, not a medical condition. Claims to prevent or treat it could still be read as a medical purpose, especially if framed around depression or anxiety.
  - India regulates medical devices, including software, under the Medical Devices Rules 2017 (CDSCO), with a disease-intended-purpose test.

### Inferences
- How the AI Act ban likely applies:
  - The app risks Art. 5(1)(f) if it (a) infers emotions such as "stressed", "frustrated" or "anxious" from EEG (physiological, hence biometric data), (b) is placed on the market or used for or in the workplace, and (c) is not a therapeutic medical device.
  - Self-use and employee consent are **not** listed exceptions, and no source found addresses a self-use, employee-only-viewer app directly.
  - Lowest-risk framing: output physical or physiological states (fatigue, alertness, cognitive load, sleepiness, break-need) rather than emotions. Market it as a personal tool, not a workplace or HR product. Never sell it to employers as a monitoring tool.
  - The CDT and Commission framing ties the ban to power imbalance. An app the employer cannot see reduces the policy concern, but the legal text does not clearly exempt it. Flag this as an unresolved legal question needing EU counsel.
- On GDPR, a purely local app the employee installs and controls likely makes the employee's processing household processing, and the vendor not a controller, *provided no personal data reaches the vendor*. If the employer deploys it, the employer becomes the controller and needs an Art. 9 condition plus a DPIA, and consent will be presumed defective.
- "Burnout" in the product name and marketing is a claims risk under both the FDA and MDR. Prefer "workload and recovery awareness", "focus and break reminders" or "fatigue trends". Avoid "detect burnout", "diagnose", "treat", "prevent burnout", "anxiety" and "depression".

### Gaps
- I could not read the EDPS TechDispatch PDF (fetch failed) or the EDPB consent guidelines this session.
- I found no source on whether the Commission Guidelines classify "stress" as an emotion or a physical state. FPF says stress and burnout detection is outside the *medical exception*, but not whether stress is inside the *definition*.
- No case law or regulator decision on EEG under Art. 5(1)(f) was found.
- The Digital Omnibus proposals (late 2025) to amend the GDPR and AI Act were not researched, and their status in Nov 2026 is unconfirmed.

## Neurorights and soft law: Chile, Colorado, California and other US states, UNESCO, OECD

### Takeaway
Neural data is becoming its own legal category. Chile protects brain activity and "information derived from it" in its constitution. Its Supreme Court ordered Emotiv to delete a user's data in 2023. Colorado, California and Connecticut classify neural data as sensitive data, and Montana extends its genetic privacy law to cover it. UNESCO (Nov 2025) and the OECD (2019) set non-binding norms: freely given consent, data minimisation, no social control or surveillance, and respect for workers' rights.

### Cited Findings
- Chile:
  - Law 21.383 (2021) amended Constitution Art. 19 No. 1 to require that scientific and technological development respect physical and psychic integrity. The law must specially safeguard "brain activity" and "the information derived from it".
  - Supreme Court, **9 Aug 2023** (Rol 105065-2023), Girardi v. Emotiv: the commercialisation and storage of the claimant's brain data violated his physical and psychic integrity and his privacy. Emotiv was ordered to delete all his data. Health and customs authorities were told to check that the device complied.
  - An implementing neurorights bill (Boletín 13.828-19) has passed the Senate and is pending in the Chamber.
  - Scholars note that inferred scores and profiles derived from EEG remain in a "gray zone". — [Stanford Law](https://law.stanford.edu/2026/04/27/even-chiles-neurorights-leave-inferred-mental-data-in-a-gray-zone/); [Diario Financiero](https://www.df.cl/df-lab/transformacion-digital/corte-suprema-acoge-primer-recurso-a-nivel-mundial-en-materia-de)
- US state laws:
  - Colorado HB24-1058, signed 17 Apr 2024, effective 7 Aug 2024. It amends the Colorado Privacy Act. Neural data is "information generated by measuring the activity of the central or peripheral nervous systems that can be processed by or with a device". It sits within "biological data", which is "sensitive data". — [Neurorights Foundation briefing (Vermont legislature)](https://legislature.vermont.gov/Documents/2026/Workgroups/Senate%20Health%20and%20Welfare/Bills/H.814/Witness%20Testimony/H.814~Ashley%20Collins~US%20State%20Legislation%20to%20Protect%20Neural%20Data~4-9-2026.pdf); [leg.colorado.gov](https://leg.colorado.gov/bills/hb24-1058); [signed act](https://leg.colorado.gov/sites/default/files/2024a_1058_signed.pdf)
  - California SB 1223, signed 28 Sep 2024, effective 1 Jan 2025. It amends the CCPA. Neural data is information generated by measuring central or peripheral nervous system activity, "not inferred from nonneural information". It is "sensitive personal information", with rights to know, delete, correct, limit and opt out. — [Neurorights Foundation briefing](https://legislature.vermont.gov/Documents/2026/Workgroups/Senate%20Health%20and%20Welfare/Bills/H.814/Witness%20Testimony/H.814~Ashley%20Collins~US%20State%20Legislation%20to%20Protect%20Neural%20Data~4-9-2026.pdf)
  - Montana SB 163 (effective 1 Oct 2025) extends genetic privacy protections to "neurotechnology data". Connecticut SB 1295 (effective 1 Jul 2026) makes CNS-only neural data sensitive data that needs consent. — [same briefing](https://legislature.vermont.gov/Documents/2026/Workgroups/Senate%20Health%20and%20Welfare/Bills/H.814/Witness%20Testimony/H.814~Ashley%20Collins~US%20State%20Legislation%20to%20Protect%20Neural%20Data~4-9-2026.pdf)
  - Vermont was considering a neural-data bill (H.814) in 2026. — [Vermont legislature](https://legislature.vermont.gov/Documents/2026/Workgroups/Senate%20Health%20and%20Welfare/Bills/H.814/Witness%20Testimony/H.814~Ashley%20Collins~US%20State%20Legislation%20to%20Protect%20Neural%20Data~4-9-2026.pdf)
- **[unverified this session]** Further US points:
  - Under the Colorado Privacy Act, processing sensitive data requires opt-in consent.
  - The CPA and CCPA apply only to businesses above revenue or volume thresholds.
  - The CCPA covers employee data, since the employee exemption expired 1 Jan 2023.
  - A federal "MIND Act" (Management of Individuals' Neural Data) was introduced in the US Senate in Sept 2025, directing the FTC to study neural data. Its status in Nov 2026 is unknown.
- UNESCO:
  - The Recommendation on the Ethics of Neurotechnology was adopted on **12 Nov 2025**. It is non-binding.
  - Principles: proportionality, freedom of thought, privacy, transparency and accountability, equity, protection of children.
  - It calls for oversight to prevent social control or surveillance, and for strong data protection and cybersecurity with data minimisation.
  - Consent must be freely given and informed, and people must be able to choose at any time whether to use neurotechnology.
  - It flags employment risks, says workers' rights must be respected, and calls on states to prohibit direct or indirect pressure to use neuro-enhancement.
  - It bans neural data in manipulative recommender systems and restricts nudging. — [Covington Inside Privacy](https://www.insideprivacy.com/health-privacy/unesco-adopts-first-global-framework-on-neurotechnology-ethics/); [UNESCO UK](https://unesco.org.uk/news/unesco-adopts-first-global-framework-on-neurotechnology-ethics); [final report](https://unesdoc.unesco.org/ark:/48223/pf0000393266)
- OECD: neurodata governance work — [OECD Neurodata governance report](https://www.oecd.org/en/publications/neurodata-governance_0ba61a20-en/full-report/component-5.html). **[unverified this session]** The OECD Recommendation on Responsible Innovation in Neurotechnology (OECD/LEGAL/0457) was adopted 11 Dec 2019. Its nine principles include safeguarding personal brain data, promoting trust and transparency, and anticipating and monitoring potential unintended use and misuse.

### Inferences
- Chile's case shows that a consumer EEG vendor can be ordered to delete data even under ordinary privacy reasoning. A local-only app with easy deletion takes most of this exposure off the table.
- US state laws attach duties to businesses that "collect" or "process" neural data. If raw EEG and scores never leave the device and the vendor cannot access them, the vendor's exposure shrinks considerably. Collecting opt-in consent and offering deletion anyway costs little and fits all four states.
- California's definition *excludes* data "inferred from nonneural information", but EEG-derived scores are inferred *from* neural data and are likely covered. Treat the derived scores as neural data too.

### Gaps
- Full text of the UNESCO Recommendation and the OECD Recommendation not fetched.
- Status of the MIND Act and of other 2026 state bills (Vermont, Massachusetts, Minnesota, etc.) not confirmed.
- Whether Chile's 2024 data-protection reform (Law 21.719) adds neural data provisions was not confirmed.

## Documented cases of employer brain monitoring and lessons

### Takeaway
Workplace EEG is already deployed at scale. SmartCap fatigue caps reportedly have more than 5,000 company customers. Chinese State Grid "emotional surveillance" caps were reported in 2018. Emotiv MN8 and SAP Focus UX offered managers views of employee stress and attention. The lessons: emotion claims are scientifically weak, data flows to employers drive harm and backlash, and safety-framed fatigue detection is the most accepted use.

### Cited Findings
- State Grid Zhejiang Electric Power (2018, reported by SCMP):
  - Employees in factories, the military and on trains wore EEG caps monitoring "sudden changes in their emotional state", with AI looking for depression, anxiety or rage. Businesses adjusted work in response.
  - A profit boost of about ¥2bn ($315m) was claimed. MIT Technology Review called the report sketchy and the profit claim "incredibly doubtful".
  - It noted that the link between scalp EEG and emotion is unclear, and that workers could be reassigned or fired on perceived emotions. — [MIT Technology Review](https://www.technologyreview.com/2018/04/30/143155/with-brain-scanning-hats-china-signals-it-has-no-interest-in-workers-privacy/); [SCMP](https://www.scmp.com/news/china/society/article/2143899/forget-facebook-leak-china-mining-data-directly-workers-brains)
- SmartCap (Brisbane): an EEG device detecting fatigue and microsleeps, with "more than 5,000 companies worldwide" in mining, construction, trucking, aviation and rail. — [Nita Farahany, Duke Magazine](https://dukemag.duke.edu/stories/extent-employee-surveillance-greater-you-know)
- Other employee-facing products and precedents:
  - Emotiv MN8 EEG earbuds track employee stress and attention.
  - SAP Focus UX, built with Emotiv, gives employees *and their managers* feedback on cognitive load, stress and attention.
  - Lockheed Martin's CogC2 assesses workload and fatigue.
  - Tesco used warehouse armbands and the data in advancement decisions, which employees objected to. — [Duke Magazine (Farahany)](https://dukemag.duke.edu/stories/extent-employee-surveillance-greater-you-know)
- The Hungarian DPA's Budapest Bank decision (voice-based emotion analysis) stressed employees' subordinate position. — [FPF](https://fpf.org/blog/red-lines-under-eu-ai-act-unpacking-the-prohibition-of-emotion-recognition-in-the-workplace-and-education-institutions/)
- Farahany's book *The Battle for Your Brain* (2023) argues for a right to "cognitive liberty". **[unverified this session — the Duke article fetched does not use the term]**

### Inferences
- Harm comes from the data reaching the employer and from emotion inference. The design should make employer access technically impossible, not just against policy, and should avoid emotion labels.
- Employees will reasonably distrust any EEG at work because of these precedents. Local-only storage must be verifiable: offline mode, no network calls, ideally open-source or audited code.
- Even employee-only data can be compelled: by subpoena or discovery in litigation, or by employer device seizure when the app runs on an employer laptop. This argues for minimal retention and encryption tied to the employee's own credentials.

### Gaps
- No independent verification of the State Grid program or SmartCap customer numbers beyond the vendor and press.
- No court or regulator decisions specifically on employer EEG monitoring were found.

## Practical design rules (synthesis) and checklist

### Takeaway
Across all jurisdictions, the safest architecture keeps the vendor and employer out of the data path entirely:
- on-device processing
- no raw EEG retention
- encrypted derived scores under the employee's control
- export and delete
- no employer channel
- physical-state (not emotion) outputs
- strictly non-diagnostic wellness wording
- a DPDP/GDPR-grade notice and consent screen, even where the law may not strictly require one

### Cited Findings (basis for rules)
- Minimum security measures (encryption, access controls, logging) — [DPDP Rules via AZB](https://www.azbpartners.com/bank/update-indias-digital-personal-data-protection-framework-comes-into-effect/)
- Data minimisation; time-specific outputs; avoid single-snapshot decisions; test on diverse users; emotion inference is highest-risk — [ICO](https://ico.org.uk/about-the-ico/research-and-reports/ico-tech-futures-neurotechnology/regulatory-issues)
- Fatigue and physical states are outside the AI Act ban; emotions and stress/burnout monitoring in the workplace are risky — [FPF](https://fpf.org/blog/red-lines-under-eu-ai-act-unpacking-the-prohibition-of-emotion-recognition-in-the-workplace-and-education-institutions/)
- No disease names, "abnormal" labels or clinical thresholds; "consider seeing a professional" is allowed — [Ropes & Gray on FDA 2026](https://www.ropesgray.com/en/insights/alerts/2026/01/fda-adapts-with-the-times-on-digital-health-updated-guidances-on-general-wellness-products)
- Freely given consent revocable at any time; no pressure to use; no manipulative nudging with neural data — [UNESCO via Covington](https://www.insideprivacy.com/health-privacy/unesco-adopts-first-global-framework-on-neurotechnology-ethics/)
- Deletion as a remedy for stored brain data — [Chile Supreme Court via Stanford](https://law.stanford.edu/2026/04/27/even-chiles-neurorights-leave-inferred-mental-data-in-a-gray-zone/)

### Inferences — Design requirements checklist
**Architecture and data flow**
- [ ] All EEG signal processing and scoring runs on-device. No cloud inference, sync or backup by default.
- [ ] No telemetry, analytics or crash reports containing EEG, scores or timestamps. Any diagnostics are opt-in, content-free and shown to the user before sending.
- [ ] Works fully offline. Document every network call (updates only) so the claim can be audited.
- [ ] No vendor account is required. If licensing is needed, use an anonymous licence key not linked to identity or employer.
- [ ] No employer dashboard, admin console, API, aggregate or "anonymised team" reports, or MDM-readable files. Employer access is impossible by design, not just by policy.
- [ ] Do not sell or license to employers as a monitoring or HR tool. If employers buy seats, the contract forbids any data access, and the product makes access technically impossible.

**Storage and retention**
- [ ] Raw EEG is discarded after feature extraction (stream processing). No raw retention by default. An optional "research/debug" raw capture needs separate, explicit opt-in, has a visible indicator, and auto-deletes (e.g. after 24 hours).
- [ ] Store only derived, coarse scores (e.g. per-5-minute fatigue or load bands). Apply a default retention limit (e.g. 90 days rolling) that the user can change.
- [ ] Encrypt at rest (e.g. AES-256-GCM) with a key protected by the OS user keystore (Windows DPAPI / macOS Keychain) plus an optional app passcode. Data stays unreadable to other OS users and to IT admins copying files.
- [ ] Warn the user if the app is installed on an employer-managed device, since IT may have device access.

**Employee control (rights)**
- [ ] One-click export in an open format (CSV/JSON) and one-click "delete everything", which removes all scores, models, calibration data and logs. Uninstall offers secure deletion.
- [ ] Pause and stop recording at any time, with a visible recording indicator. Withdrawing consent is as easy as giving it (DPDP s.6, GDPR Art. 7(3)).
- [ ] Personal calibration and baselines stay local and are deleted along with everything else.

**Outputs and wording (AI Act + medical-device boundary)**
- [ ] Output physical and physiological states: "fatigue trend", "alertness", "mental workload", "time since last break". Do **not** label emotions (stressed, anxious, angry, frustrated, sad).
- [ ] No "diagnose", "detect burnout", "treat", "prevent burnout", "clinical", "depression", "anxiety", "disorder" or "abnormal". Use "wellness", "awareness", "suggestions" and "reminders".
- [ ] Present outputs as time-specific, approximate trends with stated uncertainty. Never as a verdict on the person.
- [ ] Allow a gentle "if you're consistently feeling unwell, consider talking to a healthcare professional" message, without naming conditions or thresholds.
- [ ] No closed-loop actions that significantly affect the user without their confirmation. Suggestions only, no manipulative nudges, streaks or dark patterns (UNESCO).
- [ ] Validate on diverse users (hair types, neurodivergent people), document known limits, and disclose that consumer headphone EEG has limited accuracy.

**Notice and consent screen content** (follow the DPDP notice format and GDPR Art. 13 standard)
- [ ] An itemised list of data: raw EEG (processed in memory, discarded), derived scores, timestamps, device ID.
- [ ] The specific purpose: personal wellbeing awareness only. Not for employment decisions, not medical.
- [ ] Where data lives (this device only), who can see it (only you, not your employer, not us), and how long it is kept.
- [ ] What the app infers and what it does **not** infer: no emotions, no health conditions, no identity.
- [ ] Voluntariness: you can refuse or stop at any time with no consequence, your employer cannot require it, and the app has no way to tell anyone whether you use it.
- [ ] Limits and risks: accuracy limits; device seizure or legal-compulsion risk on work laptops; not a medical device.
- [ ] Links to export, delete, withdraw, and a grievance contact. Mention the right to complain to the DPB (India) or the supervisory authority (EU).
- [ ] Separate, unbundled affirmative consent (unticked checkbox) for each optional feature (raw capture, diagnostics).
- [ ] Available in plain language and in local languages (DPDP allows notices in English or Eighth Schedule languages). **[unverified this session]**

**Governance**
- [ ] Do a voluntary DPIA / threat model even if the vendor is not legally a controller, and publish a summary.
- [ ] Re-assess under the AI Act with EU counsel before marketing in the EU, especially the "stress" wording and the "workplace" positioning.
- [ ] If any cloud feature is ever added: DPDP obligations from May 2027 (breach notice to the Board, 72-hour report, CERT-In within 6 hours), GDPR Art. 9 explicit consent plus a DPIA, and opt-in consent under Colorado, California and Connecticut.

### Gaps
- No regulator guidance was found that directly addresses "employee-only, local-only" workplace EEG apps. Whether vendor exposure really drops to near zero under GDPR, DPDP and the US state laws when no data reaches the vendor is an inference, not a confirmed rule.
- The specific retention numbers above (24 hours, 90 days, 5-minute bins) are design suggestions, not legal requirements.
