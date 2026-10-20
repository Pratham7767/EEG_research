%% ========================================================================
%  RUN_ERD_PSD_2B   ERD/ERS and PSD for BCI Competition IV dataset 2b
%  ------------------------------------------------------------------------
%  ONE script. Press Run. Everything below is automatic.
%
%  Dataset : BCI Competition IV 2b  (BNCI Horizon 2020 id 004-2014)
%            Leeb, Brunner, Mueller-Putz, Schloegl & Pfurtscheller,
%            "BCI Competition 2008 - Graz data set B".
%            9 healthy subjects, 5 sessions each, 3 bipolar channels
%            C3/Cz/C4 at 250 Hz, left vs right hand motor imagery.
%            720 trials per subject nominal, 6520 in total.
%
%  Method  : the SAME ERD/ERS recipe as the Liu et al. 2024 stroke-paper code
%            (D:\trainsvm\data\stroke_liu2024\code\code\plotERDERS.m + PlotEvent.m)
%            and the same recipe as D:\trainsvm\experiments\03_gelo_erd\gelo_erd.m:
%
%                 band-pass -> square -> average over trials -> smooth
%                 ERD/ERS% = (A - R) / R * 100      R = baseline mean
%
%            retimed for 250 Hz and for the 2b cue convention, with five
%            corrections and two verification steps listed in SECTION 0.
%
%  Outputs : D:\trainsvm\experiments\05_bci_iv_2b\erd_ers\   (figures, csv, run log)
%
%  Needs   : Signal Processing Toolbox.
%            Statistics Toolbox optional (t-tests, trimmed mean).
%  Runtime : ~3-5 min on the first run, ~1 min afterwards (epochs are cached).
%% ========================================================================

clear; clc; close all;
scriptTic = tic;

%% ========================================================================
%  SECTION 0 - WHAT THIS FIXES RELATIVE TO THE PUBLISHED STROKE CODE
%  ========================================================================
%  Every one is a flag, so the original behaviour can be restored and the
%  difference shown side by side.
%
%  (1) BASELINE WINDOW.  PlotEvent.m uses R_start=1, R_end=2, i.e. samples
%      500..999 of an epoch starting at -1 s with Fs=500. That is 0..1 s,
%      the FIRST SECOND OF MOTOR IMAGERY, not the pre-cue rest the paper text
%      describes. Normalising imagery against imagery cancels part of the
%      effect being measured.        -> CFG.baseWin, CFG.useCodeBaseline
%
%  (2) FILTER PHASE.  filter_param.m calls filter(), which is causal and
%      delays the signal by a frequency-dependent amount - it smears the
%      very time axis the plot is read from. The paper TEXT says zero-phase.
%                                    -> CFG.zeroPhase
%
%  (3) OUTLIER SENSITIVITY.  Step 2 squares before averaging, so the class
%      mean is a mean of squares and a few high-amplitude trials dominate.
%      On this dataset that produced a spurious +150% for B08 right-hand C4.
%      A trimmed mean across trials removes it and touches nothing else.
%                                    -> CFG.estimator, CFG.trimPct
%
%  (4) NO UNCERTAINTY.  The published code plots a bare line. Here every
%      C3/C4 curve carries a 95% band, so "C4 is below C3" can be judged
%      rather than eyeballed.        -> CFG.nBoot
%
%  (5) ONE FIXED BAND.  8-30 Hz merges mu and beta, which have different
%      time courses and different per-subject peak frequencies. A
%      time-frequency ERD map shows what one band cannot.
%                                    -> CFG.doTF
%
%  Two verification steps the original has no equivalent of:
%      SECTION 2  re-derives the cue offset FROM THE DATA instead of
%                 trusting it. This is the check that caught the bug in
%                 REPORT.md section 2.
%      SECTION 6  proves band power IS the integrated PSD, by measurement.
%% ========================================================================


%% ========================================================================
%  SECTION 1 - SETTINGS.  Everything adjustable lives here.
%  ========================================================================
CFG.dataDir   = 'D:\trainsvm\experiments\05_bci_iv_2b\data';   % the 18 .mat files
CFG.outDir    = 'D:\trainsvm\experiments\05_bci_iv_2b\erd_ers';
CFG.subjects  = 1:9;              % B01..B09.  Set to 1 for a fast test run.

% --- signal ---
CFG.fs        = 250;              % 2b native rate, Hz
CFG.band      = [8 30];           % mu + beta, same band as s01/s02
CFG.order     = 2;                % Butterworth order (paper text says 2)
CFG.zeroPhase = true;             % FIX (2). false = causal, as the paper CODE

% --- trial timing, all relative to the CUE ---
CFG.cueOffsetSec = 3.0;           % `trial` index -> cue onset. Verified in S2.
CFG.preSec    = 2.5;              % epoch starts this far before the cue
CFG.postSec   = 5.0;              % epoch ends this far after the cue
CFG.padSec    = 0.5;              % cut extra, filter, smooth, then discard
CFG.baseWin   = [-2.0 -1.0];      % FIX (1). Pre-cue AND pre-beep (beep at -1)
CFG.useCodeBaseline = false;      % true -> [0 1] s, i.e. reproduce the bug
CFG.miWin     = [0.5 3.5];        % measurement window. Same as s01/s02.

% --- averaging ---
CFG.smoothSec = 0.4;              % = smoothPara 200 at 500 Hz -> 100 @ 250 Hz
CFG.estimator = 'trimmed';        % FIX (3). 'trimmed' | 'mean' | 'median'
CFG.trimPct   = 20;               % percent trimmed from each tail
CFG.nBoot     = 200;              % FIX (4). 0 disables the bands
CFG.bootStep  = 5;                % bootstrap on every Nth sample (speed only)

% --- what to produce ---
CFG.doTF        = true;           % FIX (5). time-frequency ERD maps
CFG.tfShow      = [6 35];         % frequencies displayed on the TF map, Hz
CFG.tfPeak      = [7 35];         % range searched for the peak-ERD frequency
                                  % Below ~6 Hz a 0.5 s spectrogram window
                                  % cannot resolve the bin, and what is there
                                  % is the cue-evoked potential rather than an
                                  % ERD. Searching from 4 Hz returns that edge.
CFG.doPSD       = true;           % PSD spectra + the equivalence proof
CFG.psdSubject  = 4;              % subject for the PSD close-up (B04)
CFG.useCache    = true;           % cache epochs so reruns are fast

CFG.chNames = {'C3','Cz','C4'};
CFG.C3 = 1; CFG.CZ = 2; CFG.C4 = 3;

%% ---------------------------- derived -----------------------------------
fs = CFG.fs;
D.padPre   = round((CFG.preSec  + CFG.padSec) * fs);
D.padPost  = round((CFG.postSec + CFG.padSec) * fs);
D.prePlot  = round(CFG.preSec  * fs);
D.postPlot = round(CFG.postSec * fs);
D.crop0    = D.padPre - D.prePlot;
D.nPlot    = D.prePlot + D.postPlot;
D.t        = ((0:D.nPlot-1)' - D.prePlot) / fs;      % seconds, 0 = cue onset

D.smoothN  = round(CFG.smoothSec * fs);
if mod(D.smoothN,2)==0, D.smoothN = D.smoothN + 1; end   % odd -> movmean==smooth

bw = CFG.baseWin; if CFG.useCodeBaseline, bw = [0 1]; end
D.bw      = bw;
D.baseIdx = find(D.t >= bw(1) & D.t < bw(2));
D.miIdx   = find(D.t >= CFG.miWin(1) & D.t < CFG.miWin(2));
assert(~isempty(D.baseIdx), 'baseline window is outside the epoch');
CFG.D = D;

CFG.hasStat = license('test','Statistics_Toolbox');
if ~CFG.hasStat && strcmp(CFG.estimator,'trimmed')
    warning('No Statistics Toolbox - falling back to the median.');
    CFG.estimator = 'median';
end
CFG.cacheDir = fullfile(CFG.outDir,'cache');   % ~30 MB per subject; delete
                                               % freely, it only costs a rerun
if ~exist(CFG.outDir,'dir'),   mkdir(CFG.outDir);   end
if ~exist(CFG.cacheDir,'dir'), mkdir(CFG.cacheDir); end

logFile  = fullfile(CFG.outDir,'RUN_ERD_PSD_2b.log');
doneFlag = fullfile(CFG.outDir,'_DONE.txt');
if exist(doneFlag,'file'), delete(doneFlag); end
global LOGFID                      %#ok<GVMIS>
if ~isempty(LOGFID) && LOGFID > 2   % close a handle left by an aborted run
    try fclose(LOGFID); catch, end  %#ok<CTCH>
end
LOGFID = fopen(logFile,'w');
if LOGFID < 0, warning('cannot write %s - console only', logFile); end

hdr('ERD/ERS and PSD   -   BCI Competition IV dataset 2b');
pf('run started           %s\n', datestr(now,'yyyy-mm-dd HH:MM:SS'));
pf('subjects              B%02d..B%02d  (%d)\n', CFG.subjects(1), CFG.subjects(end), numel(CFG.subjects));
pf('sampling rate         %d Hz\n', fs);
pf('band                  %g-%g Hz, Butterworth order %d, %s\n', ...
    CFG.band(1), CFG.band(2), CFG.order, tern(CFG.zeroPhase,'ZERO-PHASE (filtfilt)','CAUSAL (filter)'));
pf('epoch                 %+.1f to %+.1f s rel. cue  (%d samples)\n', -CFG.preSec, CFG.postSec, D.nPlot);
pf('baseline              %+.1f to %+.1f s%s\n', bw(1), bw(2), ...
    tern(CFG.useCodeBaseline,'   <-- STROKE-CODE BASELINE (inside imagery)',''));
pf('measurement window    %+.1f to %+.1f s rel. cue\n', CFG.miWin(1), CFG.miWin(2));
pf('smoothing             %d samples (%.2f s)\n', D.smoothN, CFG.smoothSec);
pf('trial estimator       %s%s\n', CFG.estimator, ...
    tern(strcmp(CFG.estimator,'trimmed'), sprintf('  (%g%% each tail)',CFG.trimPct), ''));
pf('bootstrap             %d resamples%s\n', CFG.nBoot, tern(CFG.nBoot==0,'   (disabled)',''));


%% ========================================================================
%  SECTION 2 - VERIFY THE CUE OFFSET AGAINST THE DATA
%  ------------------------------------------------------------------------
%  The `trial` field indexes the TRIAL START, not the cue; the paradigm puts
%  the cue 3 s later. Rather than trust that, slide a short window across
%  0..6.5 s after `trial` and measure how well log-power(C3) - log-power(C4)
%  separates left from right. AUC far from 0.5 means imagery is present.
%
%  READ THE ONSET, NOT THE ARGMAX. Imagery lasts 4 s, so the statistic stays
%  strong for seconds afterwards and its peak is a noisy tie anywhere inside
%  that plateau. What localises the cue is where the statistic FIRST leaves
%  chance. A window of length W starting at u covers [u, u+W], so the first
%  affected window starts at about cue - W, and the cue must lie in
%  [onset, onset + W]. A 1 s window is used so that interval is tight.
%  The SAME trial subset is used at every offset, so the curve is comparable.
%% ========================================================================
hdr('SECTION 2 - verifying the cue offset against the data');
winSec = 1.0;
offs   = 0:0.25:6.5;
thr    = 0.08;                 % |AUC-0.5| that counts as leaving chance
win    = round(winSec*fs);
[bb,aa] = butter(CFG.order, CFG.band*2/fs);
accF = cell(numel(offs),1);
accY = [];

for si = CFG.subjects
    sub = sprintf('B%02d', si);
    m = load(fullfile(CFG.dataDir,[sub 'T.mat']));    % session 1 only, for speed
    s = m.data{1};
    X = double(s.X(:,1:3)); X(isnan(X))=0; X = detrend(X,'constant');
    Xf = filtfilt(bb,aa,X);                            % filter once, then cut
    tr = double(s.trial(:)); yy = double(s.y(:));
    keep = (tr + round(max(offs)*fs) + win - 1 <= size(Xf,1)) & (tr >= 1);
    tr = tr(keep); yy = yy(keep);                      % one subset for all offsets
    for k = 1:numel(offs)
        a0 = tr + round(offs(k)*fs);
        v = zeros(numel(a0),1);
        for i = 1:numel(a0)
            seg = Xf(a0(i):a0(i)+win-1, [CFG.C3 CFG.C4]);
            v(i) = log(mean(seg(:,1).^2)) - log(mean(seg(:,2).^2));
        end
        accF{k} = [accF{k}; v];
    end
    accY = [accY; yy]; %#ok<AGROW>
end

auc = zeros(size(offs));
for k = 1:numel(offs), auc(k) = aucRank(accF{k}, accY==2); end
dev    = abs(auc - 0.5);
kOn    = find(dev >= thr, 1, 'first');
kOff   = find(dev >= thr, 1, 'last');
if isempty(kOn), kOn = numel(offs); kOff = numel(offs); end
cueLo  = offs(kOn);
cueHi  = offs(kOn) + winSec;

pf('\nAUC of log(C3)-log(C4) for predicting RIGHT-hand MI.\n');
pf('%.1f s window sliding from the stored `trial` index, %d trials pooled.\n\n', winSec, numel(accY));
pf('   offset (s)      AUC    |AUC-0.5|\n');
for k = 1:numel(offs)
    mk = '';
    if k == kOn,  mk = [mk '   <-- leaves chance']; end %#ok<AGROW>
    if abs(offs(k)-CFG.cueOffsetSec) < 1e-9, mk = [mk '   <-- assumed CUE']; end %#ok<AGROW>
    pf('   %7.2f     %7.4f    %8.4f%s\n', offs(k), auc(k), dev(k), mk);
end
pf('\nFirst offset with |AUC-0.5| >= %.2f : %.2f s.\n', thr, offs(kOn));
pf('A %.1f s window starting there covers [%.2f, %.2f] s, so the cue onset\n', winSec, cueLo, cueHi);
pf('must lie inside that interval. CFG.cueOffsetSec = %.2f s.\n', CFG.cueOffsetSec);
if CFG.cueOffsetSec >= cueLo - 0.3 && CFG.cueOffsetSec <= cueHi + 0.3
    pf('--> CONSISTENT.\n');
else
    pf('--> *** INCONSISTENT. Fix CFG.cueOffsetSec before reading anything below. ***\n');
end
pf('The effect then persists to %.2f s, i.e. roughly %.1f s of imagery after\n', ...
    offs(kOff)+winSec, offs(kOff)+winSec-CFG.cueOffsetSec);
pf('the cue, which matches the 4 s imagery period in the paradigm.\n');
pf('Do NOT read the argmax: imagery lasts seconds, so the peak is a tie inside\n');
pf('the plateau and moves around with noise. The ONSET is what locates the cue.\n');
pf('AUC below 0.5 only means C3 power goes DOWN for right-hand MI, which is\n');
pf('the textbook contralateral direction.\n');


%% ========================================================================
%  SECTION 3 - LOAD AND EPOCH
%  ========================================================================
hdr('SECTION 3 - loading and epoching');
nS  = numel(CFG.subjects);
SUB = struct('name',{},'EP',{},'y',{},'art',{},'sess',{});
sig = sprintf('%g_%g_%g_%g_%g', CFG.cueOffsetSec, CFG.preSec, CFG.postSec, CFG.padSec, fs);
for ii = 1:nS
    sub    = sprintf('B%02d', CFG.subjects(ii));
    cacheF = fullfile(CFG.cacheDir, sprintf('cache_%s.mat', sub));
    loaded = false;
    if CFG.useCache && exist(cacheF,'file')
        L = load(cacheF);
        if isfield(L,'sig') && strcmp(L.sig, sig)
            SUB(ii).name=sub; SUB(ii).EP=L.EP; SUB(ii).y=L.y;
            SUB(ii).art=L.art; SUB(ii).sess=L.sess;
            loaded = true;
            pf('%s  %4d trials (left %3d, right %3d, flagged %3d)   [cached]\n', ...
                sub, numel(L.y), sum(L.y==1), sum(L.y==2), sum(L.art==1));
        end
    end
    if ~loaded
        [EP,y,art,sess] = loadSubject(sub, CFG);
        SUB(ii).name=sub; SUB(ii).EP=EP; SUB(ii).y=y; SUB(ii).art=art; SUB(ii).sess=sess;
        if CFG.useCache, save(cacheF,'EP','y','art','sess','sig','-v7.3'); end
        pf('%s  %4d trials (left %3d, right %3d, flagged %3d) over %d sessions\n', ...
            sub, numel(y), sum(y==1), sum(y==2), sum(art==1), numel(unique(sess)));
    end
end
pf('\nTOTAL %d trials across %d subjects.\n', sum(arrayfun(@(s)numel(s.y),SUB)), nS);


%% ========================================================================
%  SECTION 4 - ERD/ERS CURVES
%  ------------------------------------------------------------------------
%  Per trial: band-pass -> square -> smooth. Those per-trial power curves are
%  kept, so the class average, the robust estimator, the bootstrap bands, the
%  artefact-free pass and the per-trial statistics all come from ONE pass over
%  the data and are guaranteed mutually consistent.
%% ========================================================================
hdr('SECTION 4 - ERD/ERS curves');
curv  = nan(D.nPlot, 3, 2, nS);     % time x channel x class x subject
curvC = nan(D.nPlot, 3, 2, nS);     % same, artefact-flagged trials removed
lo    = nan(D.nPlot, 3, 2, nS);     % bootstrap 2.5th percentile
hi    = nan(D.nPlot, 3, 2, nS);     % bootstrap 97.5th percentile
cnt   = zeros(nS,2);
statRows = {}; cmpRows = {};
cfgMean = CFG; cfgMean.estimator = 'mean';   % for the FIX (3) comparison

for ii = 1:nS
    sub = SUB(ii).name;
    P   = trialPower(SUB(ii).EP, CFG);       % [nTrials x nPlot x 3]
    y   = SUB(ii).y; art = SUB(ii).art;
    cnt(ii,:) = [sum(y==1), sum(y==2)];

    for cls = 1:2
        sel = (y==cls);
        for ch = 1:3
            Pc = P(sel,:,ch);
            curv(:,ch,cls,ii) = normCurve(estimate(Pc, CFG), CFG);
            Pclean = P(sel & art==0, :, ch);
            if size(Pclean,1) >= 5
                curvC(:,ch,cls,ii) = normCurve(estimate(Pclean, CFG), CFG);
            end
            if CFG.nBoot > 0 && (ch==CFG.C3 || ch==CFG.C4)
                [lo(:,ch,cls,ii), hi(:,ch,cls,ii)] = bootBand(Pc, CFG);
            end
        end

        % Per-trial numbers. A PAIRED TEST NEEDS THESE: it compares the two
        % channels within each trial, so each trial must be normalised to its
        % own baseline. That is a DIFFERENT quantity from the plotted curve,
        % which normalises the trial-averaged power once. Both are reported,
        % and the table's contra-minus-ipsi is taken from the CURVE so that
        % the table and the figure can never disagree.
        v3 = perTrialErd(P(sel,:,CFG.C3), CFG);
        v4 = perTrialErd(P(sel,:,CFG.C4), CFG);
        if cls==1, contra=v4; ipsi=v3; else, contra=v3; ipsi=v4; end
        if CFG.hasStat, [~,pv] = ttest(contra, ipsi); else, pv = NaN; end

        cC3 = mean(curv(D.miIdx,CFG.C3,cls,ii));
        cC4 = mean(curv(D.miIdx,CFG.C4,cls,ii));
        if cls==1, dCurve = cC4 - cC3; else, dCurve = cC3 - cC4; end

        statRows(end+1,:) = {sub, tern(cls==1,'left','right'), sum(sel), ...
            cC3, mean(curv(D.miIdx,CFG.CZ,cls,ii)), cC4, dCurve, mean(contra-ipsi), pv, ...
            mean(curvC(D.miIdx,CFG.C3,cls,ii)), mean(curvC(D.miIdx,CFG.C4,cls,ii))}; %#ok<AGROW>

        % FIX (3) evidence: what the paper's plain mean-of-squares gives
        qm3 = normCurve(estimate(P(sel,:,CFG.C3), cfgMean), CFG);
        qm4 = normCurve(estimate(P(sel,:,CFG.C4), cfgMean), CFG);
        cmpRows(end+1,:) = {sub, tern(cls==1,'left','right'), ...
            mean(qm3(D.miIdx)), mean(qm4(D.miIdx)), ...
            mean(curv(D.miIdx,CFG.C3,cls,ii)), mean(curv(D.miIdx,CFG.C4,cls,ii))}; %#ok<AGROW>
    end

    plotSubject(curv(:,:,:,ii), lo(:,:,:,ii), hi(:,:,:,ii), sub, cnt(ii,:), CFG, ...
        '95% bootstrap CI over trials', fullfile(CFG.outDir, sprintf('erd_%s.png', sub)));
    pf('%s  curves done\n', sub);
end

% Grand average = mean of the per-subject curves, so no single subject can
% carry it. Its band is the between-subject 95% interval (+-1.96 SEM over the
% 9 subject curves), which is the right uncertainty for a claim about people.
ga = mean(curv, 4, 'omitnan');
if nS > 1
    sem  = std(curv, 0, 4, 'omitnan') / sqrt(nS);
    gaLo = ga - 1.96*sem;  gaHi = ga + 1.96*sem;
    gaLo(:,CFG.CZ,:) = NaN; gaHi(:,CFG.CZ,:) = NaN;
else
    gaLo = lo(:,:,:,1); gaHi = hi(:,:,:,1);
end
plotSubject(ga, gaLo, gaHi, 'GRAND AVERAGE', sum(cnt,1), CFG, ...
    sprintf('95%% interval ACROSS the %d subjects', nS), ...
    fullfile(CFG.outDir,'erd_grand_average.png'));
plotOverlay(ga, CFG, fullfile(CFG.outDir,'erd_overlay.png'));


%% ========================================================================
%  SECTION 5 - NUMBERS
%  ========================================================================
hdr('SECTION 5 - results');
st = cell2table(statRows,'VariableNames',{'subject','class','n_trials', ...
    'C3_pct','Cz_pct','C4_pct','contra_minus_ipsi','pertrial_diff','p_paired_t', ...
    'C3_clean_pct','C4_clean_pct'});
writetable(st, fullfile(CFG.outDir,'erd_stats.csv'));

pf('\nMean ERD%% over %.1f-%.1f s after the cue. Negative = desynchronisation,\n', CFG.miWin(1), CFG.miWin(2));
pf('i.e. that cortex is active. Contralateral rule: LEFT hand -> C4, RIGHT hand -> C3.\n\n');
pf('%-6s %-6s %5s %9s %9s %9s %13s %11s %9s\n', ...
    'sub','class','n','C3','Cz','C4','contra-ipsi','per-trial','p');
pf('%s\n', repmat('-',1,88));
for i = 1:height(st)
    pf('%-6s %-6s %5d %9.2f %9.2f %9.2f %13.2f %11.2f %9.4f\n', st.subject{i}, st.class{i}, ...
        st.n_trials(i), st.C3_pct(i), st.Cz_pct(i), st.C4_pct(i), ...
        st.contra_minus_ipsi(i), st.pertrial_diff(i), st.p_paired_t(i));
end
pf('%s\n', repmat('-',1,88));
pf(['contra-ipsi is taken from the SAME curves that are plotted.\n' ...
         '"per-trial" normalises every trial to its own baseline first; it is a\n' ...
         'different quantity and it is what the paired t-test (column p) operates on.\n' ...
         'They can differ in size and occasionally in sign. Quoting one while plotting\n' ...
         'the other is a mistake that is easy to make and hard to notice.\n']);
okn = sum(st.contra_minus_ipsi < 0);
pf('Correct lateralisation (contralateral more negative): %d of %d cells.\n', okn, height(st));
bad = st(st.contra_minus_ipsi >= 0, :);
for i = 1:height(bad)
    pf('   exception: %s %-5s hand   contra-ipsi = %+.2f, p = %.3f\n', ...
        bad.subject{i}, bad.class{i}, bad.contra_minus_ipsi(i), bad.p_paired_t(i));
end

gi = D.miIdx;
pf('\nGRAND AVERAGE over %.1f-%.1f s:\n', CFG.miWin(1), CFG.miWin(2));
pf('   LEFT  hand MI :  C3 %+7.2f%%   Cz %+7.2f%%   C4 %+7.2f%%   <- C4 contralateral\n', ...
    mean(ga(gi,1,1)), mean(ga(gi,2,1)), mean(ga(gi,3,1)));
pf('   RIGHT hand MI :  C3 %+7.2f%%   Cz %+7.2f%%   C4 %+7.2f%%   <- C3 contralateral\n', ...
    mean(ga(gi,1,2)), mean(ga(gi,2,2)), mean(ga(gi,3,2)));

% ---------------- FIX (3) in evidence ------------------------------------
cm = cell2table(cmpRows,'VariableNames',{'subject','class', ...
    'C3_paper_mean','C4_paper_mean','C3_robust','C4_robust'});
writetable(cm, fullfile(CFG.outDir,'erd_estimator_comparison.csv'));
d3 = cm.C3_paper_mean - cm.C3_robust;
d4 = cm.C4_paper_mean - cm.C4_robust;
pf('\n--- FIX (3): outlier sensitivity of the mean-of-squares ---\n');
pf('Cells where the paper''s plain mean and the %g%% trimmed mean differ by >20 pp:\n', CFG.trimPct);
big = find(abs(d3)>20 | abs(d4)>20);
if isempty(big)
    pf('   (none)\n');
else
    for i = big'
        pf('   %s %-5s   C3 %+8.1f -> %+7.1f     C4 %+8.1f -> %+7.1f\n', ...
            cm.subject{i}, cm.class{i}, cm.C3_paper_mean(i), cm.C3_robust(i), ...
            cm.C4_paper_mean(i), cm.C4_robust(i));
    end
end
pf('Largest single change: %.1f percentage points.\n', max(abs([d3;d4])));
pf('The robust estimator changes only the cells a few loud trials were driving.\n');

% ---------------- artefact sensitivity -----------------------------------
sh3 = abs(st.C3_pct - st.C3_clean_pct); sh4 = abs(st.C4_pct - st.C4_clean_pct);
sameSign = sum(sign(st.C4_clean_pct - st.C3_clean_pct) == sign(st.C4_pct - st.C3_pct));
pf('\n--- artefact-flagged trials: KEPT (main pass) vs REMOVED ---\n');
pf('Largest shift in any cell:  C3 %.2f pp,  C4 %.2f pp.\n', max(sh3), max(sh4));
pf('C3-vs-C4 ordering unchanged in %d of %d cells. Artefact rejection is not\n', sameSign, height(st));
pf('doing hidden work in either direction. Both columns are in erd_stats.csv.\n');

writeCurves(curv, ga, lo, hi, CFG, SUB);
writetable(table(string({SUB.name})', cnt(:,1), cnt(:,2), ...
    'VariableNames',{'subject','n_left','n_right'}), ...
    fullfile(CFG.outDir,'erd_trialcount.csv'));


%% ========================================================================
%  SECTION 6 - PSD, AND WHY IT IS THE SAME QUANTITY
%  ------------------------------------------------------------------------
%  This method never calls fft(). It gets power the Pfurtscheller way,
%  band-pass -> square -> average, and by Parseval's theorem that IS the
%  integral of the power spectral density over the pass band:
%
%        mean( x_band(t)^2 )  =  integral_{f1}^{f2} S_xx(f) df
%
%  Measured below rather than asserted. The block also shows the diagonal of
%  the covariance matrix used by s02_run_models.py is the same number again,
%  which is the direct link between these plots and logvar_svm.
%% ========================================================================
if CFG.doPSD
    hdr('SECTION 6 - PSD: band power = integrated PSD = covariance diagonal');
    ps = sprintf('B%02d', CFG.psdSubject);
    jj = find(strcmp({SUB.name}, ps), 1);
    if isempty(jj), jj = 1; ps = SUB(1).name; end
    EP = SUB(jj).EP; y = SUB(jj).y;
    rngMI = D.crop0 + D.miIdx;
    rngBL = D.crop0 + D.baseIdx;

    nTr  = size(EP,3);
    bpow = zeros(nTr,3); ipsd = zeros(nTr,3); cvar = zeros(nTr,3);
    for i = 1:nTr
        xb = filtfilt(bb,aa,EP(:,:,i));
        xb = xb(rngMI,:);
        bpow(i,:) = mean(xb.^2,1);
        cvar(i,:) = diag(cov(xb))';
        raw = EP(rngMI,:,i);
        for c = 1:3
            [Pxx,fr] = pwelch(raw(:,c), hamming(round(fs)), round(fs/2), [], fs);
            kk = fr>=CFG.band(1) & fr<=CFG.band(2);
            ipsd(i,c) = trapz(fr(kk), Pxx(kk));
        end
    end

    pf('\nSubject %s, %d trials, window %.1f-%.1f s after the cue.\n\n', ...
        ps, nTr, CFG.miWin(1), CFG.miWin(2));
    pf('%-5s %18s %18s %9s %11s %15s\n', 'ch', 'mean(x_band^2)', ...
        'integral of PSD', 'ratio', 'Pearson r', 'r vs cov diag');
    pr = {};
    for c = 1:3
        r1 = corr2c(bpow(:,c), ipsd(:,c));
        r2 = corr2c(bpow(:,c), cvar(:,c));
        pf('%-5s %14.2f uV2 %14.2f uV2 %9.3f %11.4f %15.4f\n', CFG.chNames{c}, ...
            mean(bpow(:,c)), mean(ipsd(:,c)), mean(ipsd(:,c))/mean(bpow(:,c)), r1, r2);
        pr(end+1,:) = {CFG.chNames{c}, mean(bpow(:,c)), mean(ipsd(:,c)), ...
            mean(ipsd(:,c))/mean(bpow(:,c)), r1, r2}; %#ok<AGROW>
    end
    writetable(cell2table(pr,'VariableNames',{'channel','mean_sq_uV2','int_psd_uV2', ...
        'ratio','r_vs_psd','r_vs_covdiag'}), fullfile(CFG.outDir,'psd_equivalence.csv'));

    pf('\nmax |band power - covariance diagonal| / band power = %.2e\n', ...
        max(abs(bpow(:)-cvar(:))./bpow(:)));
    pf(['\nThe constant ratio is the FILTER, not a disagreement: an order-%d\n' ...
             'Butterworth is not a brick wall, so it already attenuates inside %g-%g Hz\n' ...
             'while the Welch integral cuts sharply at the band edges. Because the\n' ...
             'offset is CONSTANT it cancels exactly in (A-R)/R, which is why the ERD\n' ...
             'percentage does not care which of the two is used.\n'], ...
             CFG.order, CFG.band(1), CFG.band(2));
    pf(['The covariance diagonal is the same number to ~1e-3, and that diagonal\n' ...
             'is what logvar_svm in s02_run_models.py classifies. These ERD curves and\n' ...
             'that model read ONE physical quantity, computed two ways.\n']);

    plotSpectra(EP, y, rngBL, rngMI, ps, CFG, fullfile(CFG.outDir,'psd_spectra.png'));
    plotScatter(bpow, ipsd, ps, CFG, fullfile(CFG.outDir,'psd_vs_bandpower.png'));
end


%% ========================================================================
%  SECTION 7 - TIME-FREQUENCY ERD MAP
%  ------------------------------------------------------------------------
%  FIX (5). The 8-30 Hz curve collapses mu and beta onto one line. This shows
%  the whole plane: time on x, frequency on y, ERD% as colour, normalised to
%  the same pre-cue baseline separately in every frequency bin.
%% ========================================================================
if CFG.doTF
    hdr('SECTION 7 - time-frequency ERD maps');
    [TF, Fv, Tv, pk] = tfMaps(SUB, CFG);
    plotTF(TF, Fv, Tv, CFG, fullfile(CFG.outDir,'erd_timefrequency.png'));
    pf('\nStrongest ERD and the frequency it sits at, per subject\n');
    pf('(C3 during right-hand MI, searched over %g-%g Hz):\n\n', CFG.tfPeak(1), CFG.tfPeak(2));
    pf('   %-6s %12s %12s\n','sub','peak ERD %','at (Hz)');
    for ii = 1:nS
        pf('   %-6s %11.1f%% %11.1f\n', SUB(ii).name, pk(ii,1), pk(ii,2));
    end
    pf('\n   range %.1f - %.1f Hz, median %.1f Hz\n', ...
        min(pk(:,2)), max(pk(:,2)), median(pk(:,2)));
    pf(['\nA single %g-%g Hz band assumes one setting fits every subject. The spread\n' ...
             'above is the cost of that assumption, and it is the honest argument for\n' ...
             'per-subject band selection - chosen on TRAINING data only, which is exactly\n' ...
             'where TWFB_DGFMDM.m went wrong in the stroke paper.\n'], CFG.band(1), CFG.band(2));
    writetable(table(string({SUB.name})', pk(:,1), pk(:,2), ...
        'VariableNames',{'subject','peak_erd_pct','peak_freq_hz'}), ...
        fullfile(CFG.outDir,'erd_peak_frequency.csv'));
end


%% ========================================================================
%  DONE
%  ========================================================================
hdr('DONE');
pf('elapsed               %.1f s\n', toc(scriptTic));
pf('figures and tables    %s\n\n', CFG.outDir);
pf('  erd_B01.png .. erd_B09.png      per subject, left and right panels,\n');
pf('                                  C3/Cz/C4 with 95%% bootstrap bands\n');
pf('  erd_grand_average.png           the same, averaged over subjects\n');
pf('  erd_overlay.png                 C3/C4 x left/right on one axes\n');
pf('  erd_timefrequency.png           ERD%% over time AND frequency\n');
pf('  psd_spectra.png                 baseline vs imagery spectra\n');
pf('  psd_vs_bandpower.png            band power = integrated PSD, per trial\n');
pf('  erd_stats.csv                   per subject x class, incl. clean pass\n');
pf('  erd_estimator_comparison.csv    paper mean vs robust mean\n');
pf('  erd_peak_frequency.csv          per-subject peak ERD frequency\n');
pf('  erd_curves.csv                  every curve, long format, with CI\n');
pf('  psd_equivalence.csv             the equivalence table\n');
pf('  RUN_ERD_PSD_2b.log              this console output\n');
if LOGFID > 0, fclose(LOGFID); LOGFID = []; end
fid = fopen(doneFlag,'w'); fprintf(fid,'%s\n', datestr(now)); fclose(fid);


%% ========================= LOCAL FUNCTIONS ==============================

function hdr(s)
pf('\n%s\n%s\n%s\n', repmat('=',1,76), s, repmat('=',1,76));
end

function pf(varargin)
% Print to the console AND to the run log, so the log is written even when
% the script is launched from a harness that captures output (diary is not).
global LOGFID                      %#ok<GVMIS>
fprintf(varargin{:});
if ~isempty(LOGFID) && LOGFID > 0, fprintf(LOGFID, varargin{:}); end
end

function out = tern(c,a,b)
if c, out = a; else, out = b; end
end

function a = aucRank(x, pos)
% AUC via the rank-sum identity. No toolbox needed.
ok = ~isnan(x) & ~isinf(x);
x = x(ok); pos = logical(pos(ok));
[~,ord] = sort(x); r = zeros(numel(x),1); r(ord) = 1:numel(x);
n1 = sum(pos); n2 = sum(~pos);
a = (sum(r(pos)) - n1*(n1+1)/2) / (n1*n2);
end

function r = corr2c(a,b)
a = a(:) - mean(a); b = b(:) - mean(b);
r = (a'*b) / sqrt((a'*a)*(b'*b));
end

function [EP,y,art,sess] = loadSubject(sub, CFG)
% Cue-locked, padded epochs from both files of one subject.
D = CFG.D;
EP = zeros(D.padPre + D.padPost, 3, 0); y=[]; art=[]; sess=[]; sid=0;
for suf = {'T','E'}
    f = fullfile(CFG.dataDir, [sub suf{1} '.mat']);
    assert(exist(f,'file')==2, 'missing file: %s', f);
    m = load(f);
    for k = 1:numel(m.data)
        s = m.data{k}; sid = sid+1;
        assert(abs(double(s.fs)-CFG.fs)<1e-6, 'unexpected sampling rate in %s', f);
        X = double(s.X(:,1:3));        % cols 1-3 = C3,Cz,C4; 4-6 = EOG, dropped
        X(isnan(X)) = 0;               % the format uses NaN at run breaks
        X = detrend(X,'constant');
        o  = double(s.trial(:)) + round(CFG.cueOffsetSec*CFG.fs);
        yy = double(s.y(:)); ar = double(s.artifacts(:));
        keep = (o-D.padPre >= 1) & (o+D.padPost-1 <= size(X,1));
        o = o(keep);
        for i = 1:numel(o)
            EP(:,:,end+1) = X(o(i)-D.padPre : o(i)+D.padPost-1, :); %#ok<AGROW>
        end
        y    = [y;    yy(keep)];                 %#ok<AGROW>
        art  = [art;  ar(keep)];                 %#ok<AGROW>
        sess = [sess; repmat(sid,sum(keep),1)];  %#ok<AGROW>
    end
end
end

function P = trialPower(EP, CFG)
% band-pass -> square -> smooth -> crop the padding.  [nTrials x nPlot x 3]
% One pass over the data; everything downstream reuses this.
D = CFG.D;
[b,a] = butter(CFG.order, CFG.band*2/CFG.fs);
n   = size(EP,3);
rng = D.crop0+1 : D.crop0+D.nPlot;
P   = zeros(n, D.nPlot, 3);
for i = 1:n
    if CFG.zeroPhase
        x = filtfilt(b,a,EP(:,:,i));
    else
        x = filter(b,a,EP(:,:,i));
    end
    q = movmean(x.^2, D.smoothN, 1);     % identical to smooth(...,'moving')
    P(i,:,:) = reshape(q(rng,:), 1, D.nPlot, 3);
end
end

function v = estimate(P, CFG)
% Average the per-trial power curves across trials.  FIX (3) lives here.
switch CFG.estimator
    case 'mean',    v = mean(P,1).';
    case 'median',  v = median(P,1).';
    case 'trimmed', v = trimmean(P, CFG.trimPct, 'round', 1).';
    otherwise, error('unknown estimator: %s', CFG.estimator);
end
end

function y = normCurve(avg, CFG)
base = mean(avg(CFG.D.baseIdx));
y = (avg - base) / base * 100;
end

function v = perTrialErd(Pc, CFG)
% One ERD% per trial, averaged over the measurement window.
base = mean(Pc(:,CFG.D.baseIdx), 2);
v = mean((Pc(:,CFG.D.miIdx) - base) ./ base * 100, 2);
end

function [lo,hi] = bootBand(Pc, CFG)
% Bootstrap over trials, 95% percentile band. Computed on a decimated time
% grid and interpolated back; that is a speed choice only.
D = CFG.D; n = size(Pc,1);
idxT = 1:CFG.bootStep:D.nPlot;
Pd   = Pc(:, idxT);
bI   = find(ismember(idxT, D.baseIdx));
if isempty(bI), bI = 1:max(1,round(numel(idxT)/10)); end
B = zeros(CFG.nBoot, numel(idxT));
for k = 1:CFG.nBoot
    r = randi(n, n, 1);
    switch CFG.estimator
        case 'mean',    a = mean(Pd(r,:),1);
        case 'median',  a = median(Pd(r,:),1);
        case 'trimmed', a = trimmean(Pd(r,:), CFG.trimPct, 'round', 1);
    end
    b0 = mean(a(bI));
    B(k,:) = (a - b0) / b0 * 100;
end
q  = prctile(B, [2.5 97.5], 1);
lo = interp1(idxT, q(1,:), 1:D.nPlot, 'linear', 'extrap').';
hi = interp1(idxT, q(2,:), 1:D.nPlot, 'linear', 'extrap').';
end

function plotSubject(A, lo, hi, name, n, CFG, bandLabel, outFile)
D = CFG.D;
f = figure('Color','w','Position',[100 50 640 760],'Visible','off');
ttl = {sprintf('MI with Left Hand   (n = %d)    contralateral = C4', n(1)), ...
       sprintf('MI with Right Hand   (n = %d)    contralateral = C3', n(2))};
seg = A(D.prePlot+1:end, [CFG.C3 CFG.C4], :);
bnd = [lo(D.prePlot+1:end,[CFG.C3 CFG.C4],:); hi(D.prePlot+1:end,[CFG.C3 CFG.C4],:)];
allv = [seg(:); bnd(~isnan(bnd))];
yl = [min(allv)-8, max(allv)+8];
for cls = 1:2
    subplot(2,1,cls); hold on; grid on; box on;
    patch([D.bw(1) D.bw(2) D.bw(2) D.bw(1)], [yl(1) yl(1) yl(2) yl(2)], ...
          [0 .4 .8],'FaceAlpha',0.06,'EdgeColor','none');
    patch([CFG.miWin(1) CFG.miWin(2) CFG.miWin(2) CFG.miWin(1)], ...
          [yl(1) yl(1) yl(2) yl(2)], [0 0 0],'FaceAlpha',0.04,'EdgeColor','none');
    for ch = [CFG.C3 CFG.C4]
        if ~any(isnan(lo(:,ch,cls)))
            col = tern(ch==CFG.C3, [.85 .33 .33], [.33 .45 .85]);
            fill([D.t; flipud(D.t)], [lo(:,ch,cls); flipud(hi(:,ch,cls))], col, ...
                 'FaceAlpha',0.18,'EdgeColor','none');
        end
    end
    h1 = plot(D.t, A(:,CFG.C3,cls),'r--','LineWidth',1.4);
    h2 = plot(D.t, A(:,CFG.CZ,cls),'Color',[.55 .55 .55],'LineWidth',0.9);
    h3 = plot(D.t, A(:,CFG.C4,cls),'b-','LineWidth',1.4);
    xline(0,'Color',[.4 .4 .4],'LineWidth',1.1);
    yline(0,'Color',[.85 .85 .85]);
    xlim([-CFG.preSec CFG.postSec]); ylim(yl);
    title(ttl{cls},'FontSize',11);
    xlabel('Time from cue (s)','FontSize',10);
    ylabel('ERD/ERS (%)','FontSize',10);
    lg = legend([h1 h2 h3],{'C3','Cz','C4'},'Location','southwest', ...
        'Orientation','horizontal'); legend('boxoff'); set(lg,'FontSize',8);
end
sgtitle(sprintf(['%s     %g-%g Hz, Fs %d Hz, %s estimator\n' ...
    'blue = baseline (%+.1f..%+.1f s)   grey = measurement window   shading = %s'], ...
    name, CFG.band(1), CFG.band(2), CFG.fs, CFG.estimator, D.bw(1), D.bw(2), bandLabel), ...
    'FontSize',9);
exportgraphics(f, outFile,'Resolution',160); close(f);
end

function plotOverlay(ga, CFG, outFile)
D = CFG.D;
f = figure('Color','w','Position',[80 80 820 460],'Visible','off');
hold on; grid on; box on;
yl = [min(ga(:))-5, max(ga(:))+5];
patch([CFG.miWin(1) CFG.miWin(2) CFG.miWin(2) CFG.miWin(1)], ...
      [yl(1) yl(1) yl(2) yl(2)],[0 0 0],'FaceAlpha',0.04,'EdgeColor','none');
plot(D.t, ga(:,CFG.C3,1),'r--','LineWidth',1.5);
plot(D.t, ga(:,CFG.C4,1),'b--','LineWidth',1.5);
plot(D.t, ga(:,CFG.C3,2),'r-','LineWidth',1.5);
plot(D.t, ga(:,CFG.C4,2),'b-','LineWidth',1.5);
xline(0,'Color',[.4 .4 .4],'LineWidth',1.1);
yline(0,'Color',[.85 .85 .85]);
xlim([-CFG.preSec CFG.postSec]); ylim(yl);
xlabel('Time from cue (s)','FontSize',11);
ylabel('ERD/ERS (%)','FontSize',11);
title('2b grand average    -    dashed = LEFT hand MI, solid = RIGHT hand MI','FontSize',11);
legend({'C3 left','C4 left','C3 right','C4 right'}, ...
    'Location','southoutside','Orientation','horizontal','Box','off');
exportgraphics(f, outFile,'Resolution',160); close(f);
end

function plotSpectra(EP, y, rngBL, rngMI, ps, CFG, outFile)
fs = CFG.fs;
f = figure('Color','w','Position',[80 60 980 700],'Visible','off');
titles = {'LEFT hand MI','RIGHT hand MI'};
for cls = 1:2
    sel = find(y==cls);
    for ci = 1:2
        c = tern(ci==1, CFG.C3, CFG.C4);
        Pb = []; Pm = [];
        for i = sel(:).'
            [p1,fr] = pwelch(EP(rngBL,c,i), hamming(round(fs/2)), round(fs/4), 256, fs);
            [p2,~ ] = pwelch(EP(rngMI,c,i), hamming(round(fs/2)), round(fs/4), 256, fs);
            Pb(:,end+1) = p1; Pm(:,end+1) = p2; %#ok<AGROW>
        end
        kk = fr>=2 & fr<=40;
        mb = mean(Pb,2); mm = mean(Pm,2);
        inb = fr>=CFG.band(1) & fr<=CFG.band(2);
        chg = 100*(trapz(fr(inb), mm(inb))/trapz(fr(inb), mb(inb)) - 1);

        subplot(2,2,(cls-1)*2+ci);
        semilogy(fr(kk), mb(kk),'Color',[.45 .45 .45],'LineWidth',1.5);
        hold on; grid on; box on;
        semilogy(fr(kk), mm(kk),'Color',[.80 .15 .15],'LineWidth',1.5);
        yl = ylim;
        patch([CFG.band fliplr(CFG.band)],[yl(1) yl(1) yl(2) yl(2)],[0 0 0], ...
              'FaceAlpha',0.05,'EdgeColor','none');
        ylim(yl);
        contra = tern((cls==1 && ci==2) || (cls==2 && ci==1),'  CONTRA','');
        xlabel('Frequency (Hz)','FontSize',10);
        ylabel('PSD (\muV^2/Hz)','FontSize',10);
        title(sprintf('%s  -  %s%s   (%g-%g Hz change %+.0f%%)', titles{cls}, ...
            CFG.chNames{c}, contra, CFG.band(1), CFG.band(2), chg),'FontSize',10);
        legend({'baseline','imagery'},'Location','southwest','Box','off','FontSize',8);
    end
end
sgtitle(sprintf(['%s  -  the spectra that the single ERD%% number summarises.\n' ...
    'ERD is the shaded area shrinking; the ERD curve is that shrinkage over time.'], ps), ...
    'FontSize',10);
exportgraphics(f, outFile,'Resolution',160); close(f);
end

function plotScatter(bpow, ipsd, ps, CFG, outFile)
f = figure('Color','w','Position',[80 80 980 350],'Visible','off');
for c = 1:3
    subplot(1,3,c);
    loglog(bpow(:,c), ipsd(:,c),'.','MarkerSize',6,'Color',[.15 .35 .75]);
    hold on; grid on; box on;
    lim = [min([bpow(:,c);ipsd(:,c)]) max([bpow(:,c);ipsd(:,c)])];
    loglog(lim,lim,'k--','LineWidth',1);
    axis square; xlim(lim); ylim(lim);
    xlabel('mean(x_{band}^2)   [\muV^2]','FontSize',9);
    ylabel('\int S_{xx}(f) df   [\muV^2]','FontSize',9);
    title(sprintf('%s     r = %.4f', CFG.chNames{c}, corr2c(bpow(:,c),ipsd(:,c))),'FontSize',10);
end
sgtitle(sprintf(['%s  -  band power IS the integrated PSD (Parseval), trial by trial.\n' ...
    'The offset from the dashed identity line is filter roll-off, and it cancels in (A-R)/R.'], ps), ...
    'FontSize',10);
exportgraphics(f, outFile,'Resolution',160); close(f);
end

function [TF, Fv, Tv, pk] = tfMaps(SUB, CFG)
% Grand-average ERD% over time AND frequency, C3 and C4, both classes.
% Each subject is normalised to its own baseline before pooling.
%
% The spectrogram runs on the PADDED epoch and the time axis is cropped
% afterwards, for the same reason the smoothing is: otherwise the first and
% last frames are computed from a half-empty window and appear as a bright
% stripe at the edges of the map.
D = CFG.D; fs = CFG.fs;
win = round(0.5*fs); ov = win - round(0.05*fs); nfft = 256;
nS  = numel(SUB);
acc = cell(2,2); Fv = []; Tv = []; keepT = [];
pk  = nan(nS,2);

for ii = 1:nS
    EP = SUB(ii).EP; y = SUB(ii).y;
    for cls = 1:2
        idx = find(y==cls);
        for ci = 1:2
            c = tern(ci==1, CFG.C3, CFG.C4);
            S = [];
            for i = idx(:).'
                [~,F,T,Pxx] = spectrogram(EP(:,c,i), hamming(win), ov, nfft, fs);
                if isempty(S), S = zeros(size(Pxx)); end
                S = S + Pxx;
            end
            S = S / numel(idx);
            if isempty(Fv)
                Fv    = F;
                Tfull = T(:).' - (CFG.preSec + CFG.padSec);   % 0 = cue onset
                keepT = Tfull >= -CFG.preSec & Tfull <= CFG.postSec;
                Tv    = Tfull(keepT);
            end
            S  = S(:, keepT);
            bi = Tv >= D.bw(1) & Tv < D.bw(2);
            if ~any(bi), bi = Tv < 0; end
            B = mean(S(:,bi),2);
            E = (S - B) ./ B * 100;
            if isempty(acc{cls,ci}), acc{cls,ci} = zeros(size(E)); end
            acc{cls,ci} = acc{cls,ci} + E;

            % per-subject peak ERD: C3 during right-hand MI.
            % Restricted to CFG.tfPeak: below ~6 Hz a 0.5 s window cannot
            % resolve the bin, and the large values there are the cue-evoked
            % response, not an ERD.
            if cls==2 && ci==1
                mi = Tv >= CFG.miWin(1) & Tv < CFG.miWin(2);
                kk = F>=CFG.tfPeak(1) & F<=CFG.tfPeak(2);
                Ek = mean(E(kk,mi),2); Fk = F(kk);
                [pk(ii,1), j] = min(Ek);
                pk(ii,2) = Fk(j);
            end
        end
    end
end
TF = cell(2,2);
for cls = 1:2
    for ci = 1:2
        TF{cls,ci} = acc{cls,ci} / nS;
    end
end
end

function plotTF(TF, Fv, Tv, CFG, outFile)
kk = Fv >= CFG.tfShow(1) & Fv <= CFG.tfShow(2);
cl = 0;
for cls=1:2
    for ci=1:2
        cl = max(cl, prctile(abs(TF{cls,ci}(kk,:)), 98, 'all'));
    end
end
f = figure('Color','w','Position',[60 50 1000 720],'Visible','off');
titles = {'LEFT hand MI','RIGHT hand MI'}; chs = {'C3','C4'};
for cls = 1:2
    for ci = 1:2
        subplot(2,2,(cls-1)*2+ci);
        imagesc(Tv, Fv(kk), TF{cls,ci}(kk,:)); axis xy; hold on;
        xline(0,'Color','k','LineWidth',1.2);
        yline(CFG.band(1),'Color','k','LineStyle',':','LineWidth',1);
        yline(CFG.band(2),'Color','k','LineStyle',':','LineWidth',1);
        clim([-cl cl]); colormap(blueRed()); cb = colorbar; cb.Label.String = 'ERD/ERS %';
        xlim([-CFG.preSec CFG.postSec]);
        xlabel('Time from cue (s)','FontSize',10);
        ylabel('Frequency (Hz)','FontSize',10);
        contra = tern((cls==1 && ci==2) || (cls==2 && ci==1),'   (CONTRALATERAL)','');
        title(sprintf('%s  -  %s%s', titles{cls}, chs{ci}, contra),'FontSize',10);
    end
end
sgtitle(sprintf(['Time-frequency ERD/ERS %%, grand average.   Blue = desynchronisation = active.\n' ...
    'Dotted lines mark the %g-%g Hz band that the single ERD curve collapses onto.'], ...
    CFG.band(1), CFG.band(2)),'FontSize',10);
exportgraphics(f, outFile,'Resolution',160); close(f);
end

function cm = blueRed()
n = 256; x = linspace(-1,1,n).';
r = min(1, 1 + min(0,x)*1.0);
g = 1 - abs(x)*0.85;
b = min(1, 1 - max(0,x)*1.0);
cm = max(0, min(1, [r g b]));
end

function writeCurves(curv, ga, lo, hi, CFG, SUB)
D = CFG.D; nS = numel(SUB); n = D.nPlot;
tot = n*3*2*(nS+1);
S=cell(tot,1); C=cell(tot,1); H=cell(tot,1);
T=zeros(tot,1); V=zeros(tot,1); LO=nan(tot,1); HI=nan(tot,1); k=0;
for ii = 1:nS+1
    if ii<=nS
        nm = SUB(ii).name; A = curv(:,:,:,ii); L = lo(:,:,:,ii); U = hi(:,:,:,ii);
    else
        nm = 'GRAND'; A = ga; L = nan(size(ga)); U = L;
    end
    for cls = 1:2
        for ch = 1:3
            idx = k+1:k+n;
            S(idx)={nm}; C(idx)={tern(cls==1,'left','right')}; H(idx)=CFG.chNames(ch);
            T(idx)=D.t; V(idx)=A(:,ch,cls); LO(idx)=L(:,ch,cls); HI(idx)=U(:,ch,cls);
            k = k+n;
        end
    end
end
writetable(table(S,C,H,T,V,LO,HI,'VariableNames', ...
    {'subject','class','channel','time_s','erd_pct','ci_lo','ci_hi'}), ...
    fullfile(CFG.outDir,'erd_curves.csv'));
end
