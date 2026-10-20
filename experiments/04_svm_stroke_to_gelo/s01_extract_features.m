%% ========================================================================
%  01_extract_features.m
%
%  Builds the feature tables for the three-SVM experiment.
%
%  TRAIN : Liu et al. 2024 acute-stroke MI dataset, 50 subjects
%          D:\trainsvm\data\stroke_liu2024\sourcedata\sourcedata\sub-XX\*.mat
%  TEST  : our own Gelo / LEHeadphones2 recordings, re-cut from raw CSV
%          D:\trainsvm\data\gelo\left\*.csv and D:\trainsvm\data\gelo\right\*.csv
%
%  Writes: features_train.csv, features_test.csv, psd_curves.mat
%          all into D:\trainsvm\experiments\04_svm_stroke_to_gelo
%
%  The two datasets go down the SAME code path after epoching. That is the
%  whole point: any difference in the features is a difference in the brains
%  or the hardware, not in the arithmetic.
%% ========================================================================
clear; clc;

%% ------------------------------ SETTINGS --------------------------------
CFG.outDir      = 'D:\trainsvm\experiments\04_svm_stroke_to_gelo';
CFG.strokeRoot  = 'D:\trainsvm\data\stroke_liu2024\sourcedata\sourcedata';
CFG.ownRoot     = 'D:\trainsvm\data\gelo';          % contains \left and \right

CFG.fsTarget    = 250;                    % everything is brought to 250 Hz
CFG.fsStroke    = 500;                    % the stroke dataset's native rate
CFG.fsOwn       = 250;                    % our headset's native rate

CFG.band        = [8 30];                 % main band, as in the paper
CFG.bandAlpha   = [8 13];                 % saved for later tweaking only
CFG.bandBeta    = [13 30];                % saved for later tweaking only
CFG.order       = 2;                      % Butterworth order (paper uses 2)

CFG.preSec      = 1.0;                    % baseline before onset
CFG.postSec     = 4.0;                    % imagery window after onset
CFG.padSec      = 0.5;                    % margin cut then discarded (own data)
CFG.minRestSec  = 1.5;                    % own data: rest required before onset
CFG.marks       = 1:5;                    % own data: mark values = iterations

CFG.ownC3col    = 2;                      % C3 = column 2 of ch1..ch4
CFG.ownC4col    = 3;                      % C4 = column 3 of ch1..ch4
CFG.strokeC3    = 14;                     % C3 = channel 14 (paper Table 2)
CFG.strokeC4    = 15;                     % C4 = channel 15
CFG.strokeMark  = 33;                     % marker channel
CFG.miMarker    = 2;                      % marker value 2 = motor-imagery onset

CFG.nPre        = round(CFG.preSec  * CFG.fsTarget);   % 250 samples
CFG.nPost       = round(CFG.postSec * CFG.fsTarget);   % 1000 samples

% Welch settings for the PSD (identical for both datasets, at 250 Hz)
CFG.welchWin    = 250;                    % 1 s Hamming
CFG.welchOvl    = 125;                    % 50 %
CFG.welchNfft   = 512;

if ~exist(CFG.outDir,'dir'), mkdir(CFG.outDir); end
[CFG.b, CFG.a] = butter(CFG.order, CFG.band * 2 / CFG.fsTarget);

fprintf('=== 01_extract_features ===\n');
fprintf('target fs %d Hz | band %g-%g Hz | epoch = %.1f s pre + %.1f s imagery\n', ...
    CFG.fsTarget, CFG.band(1), CFG.band(2), CFG.preSec, CFG.postSec);

%% =========================== TRAINING DATA ==============================
fprintf('\n--- stroke dataset (training) ---\n');

rows = {};                     % accumulates feature structs
psdAcc.train = initPsdAcc(CFG);
nSkipEdge = 0;

for s = 1:50
    f = sprintf('%s\\sub-%02d\\sub-%02d_task-motor-imagery_eeg.mat', CFG.strokeRoot, s, s);
    S = load(f);
    raw = S.eeg.rawdata;                       % [40 x 33 x 4000]
    lab = S.eeg.label;                         % 1 = left, 2 = right
    nKept = 0;

    for t = 1:size(raw,1)
        mk = squeeze(raw(t, CFG.strokeMark, :));
        o500 = find(mk == CFG.miMarker, 1);

        % --- reject trials that cannot supply a full baseline + imagery -----
        % (marker 2 lands at sample 2 in a minority of trials in subjects
        %  08,13,14,20,22,24,25,29,30,40,48 - those trials were cut without
        %  the instruction period, so there is no pre-onset second.)
        if isempty(o500) || o500 - CFG.fsStroke/2*2 < 1 || o500 + 1999 > size(raw,3)
            nSkipEdge = nSkipEdge + 1; continue;
        end
        if o500 - 500 < 1
            nSkipEdge = nSkipEdge + 1; continue;
        end

        % --- whole trial, C3 and C4, mean removed ---------------------------
        x = squeeze(raw(t, [CFG.strokeC3 CFG.strokeC4], :))';   % [4000 x 2]
        x = detrend(x, 0);

        % --- 500 -> 250 Hz on the whole trial (resample anti-aliases) -------
        x = resample(x, 1, 2);                                  % [2000 x 2]
        o = round((o500 - 1) / 2) + 1;

        if o - CFG.nPre < 1 || o + CFG.nPost - 1 > size(x,1)
            nSkipEdge = nSkipEdge + 1; continue;
        end

        % --- filter the WHOLE trial, then take the interior windows ---------
        % filtering the full trial keeps filtfilt's edge transients at the
        % trial boundaries, far away from the imagery window.
        xf = filtfilt(CFG.b, CFG.a, x);

        baseF = xf(o - CFG.nPre : o - 1, :);
        miF   = xf(o : o + CFG.nPost - 1, :);
        miRaw = x( o : o + CFG.nPost - 1, :);      % unfiltered, for the PSD

        F = featurize(miF, baseF, miRaw, CFG);
        F.dataset = "stroke";
        F.group   = sprintf('sub-%02d', s);        % grouping unit for CV
        F.item    = sprintf('trial%02d', t);
        F.label   = lab(t);
        rows{end+1,1} = F; %#ok<SAGROW>

        psdAcc.train = accPsd(psdAcc.train, miRaw, lab(t), CFG);
        nKept = nKept + 1;
    end
    if mod(s,10)==0 || s==1
        fprintf('  sub-%02d ... %d trials kept\n', s, nKept);
    end
end

Ttrain = rowsToTable(rows);
fprintf('  TOTAL train epochs: %d  (left %d, right %d) | rejected at edge: %d\n', ...
    height(Ttrain), sum(Ttrain.label==1), sum(Ttrain.label==2), nSkipEdge);
writetable(Ttrain, fullfile(CFG.outDir,'features_train.csv'));

%% ============================= TEST DATA ================================
fprintf('\n--- own recordings (test) ---\n');

rows = {};
psdAcc.test = initPsdAcc(CFG);
meta = {};

for cls = [1 2]
    if cls == 1, folder = 'left'; else, folder = 'right'; end
    files = dir(fullfile(CFG.ownRoot, folder, '*.csv'));
    assert(~isempty(files), 'No CSV in %s', fullfile(CFG.ownRoot, folder));
    fprintf('  %s: %d files\n', folder, numel(files));

    padPre  = round((CFG.preSec  + CFG.padSec) * CFG.fsOwn);   % 375
    padPost = round((CFG.postSec + CFG.padSec) * CFG.fsOwn);   % 1125
    crop0   = padPre - CFG.nPre;                               % 125

    for k = 1:numel(files)
        M = readmatrix(fullfile(files(k).folder, files(k).name));
        M = M(~isnan(M(:,end)), :);
        assert(size(M,2) >= 10, 'Unexpected column count in %s', files(k).name);

        X  = M(:, 2:5) * 1e6;                 % ch1..ch4, volts -> microvolts
        mk = M(:, end);
        nKept = 0;

        for m = CFG.marks
            idx = find(mk == m);
            status = 'OK';
            if isempty(idx)
                status = 'MISSING';
            else
                onset = idx(1);
                j = onset - 1;
                while j >= 1 && mk(j) == 0, j = j - 1; end
                preRest = (onset - 1 - j) / CFG.fsOwn;

                if onset - padPre < 1 || onset + padPost - 1 > size(X,1)
                    status = 'EDGE';
                elseif preRest < CFG.minRestSec
                    status = 'NO_BASELINE';
                else
                    ep = X(onset - padPre : onset + padPost - 1, [CFG.ownC3col CFG.ownC4col]);
                    ep = detrend(ep, 0);
                    epf = filtfilt(CFG.b, CFG.a, ep);

                    rgSel = crop0 + 1 : crop0 + CFG.nPre + CFG.nPost;   % 1250 samples
                    epf = epf(rgSel, :);
                    epr = ep( rgSel, :);

                    baseF = epf(1 : CFG.nPre, :);
                    miF   = epf(CFG.nPre + 1 : end, :);
                    miRaw = epr(CFG.nPre + 1 : end, :);

                    F = featurize(miF, baseF, miRaw, CFG);
                    F.dataset = "own";
                    F.group   = string(files(k).name);     % file = session
                    F.item    = sprintf('mark%d', m);
                    F.label   = cls;
                    rows{end+1,1} = F; %#ok<SAGROW>

                    psdAcc.test = accPsd(psdAcc.test, miRaw, cls, CFG);
                    nKept = nKept + 1;
                end
            end
            meta{end+1,1} = {folder, files(k).name, m, status}; %#ok<SAGROW>
        end
        fprintf('    %-18s %d/%d kept\n', files(k).name, nKept, numel(CFG.marks));
    end
end

Ttest = rowsToTable(rows);
fprintf('  TOTAL test epochs: %d  (left %d, right %d)\n', ...
    height(Ttest), sum(Ttest.label==1), sum(Ttest.label==2));
writetable(Ttest, fullfile(CFG.outDir,'features_test.csv'));

mt = vertcat(meta{:});
Tmeta = cell2table(mt, 'VariableNames', {'class','file','mark','status'});
writetable(Tmeta, fullfile(CFG.outDir,'test_epoch_meta.csv'));

%% ---------------------------- PSD CURVES --------------------------------
psdOut = struct('train', finishPsd(psdAcc.train), 'test', finishPsd(psdAcc.test), 'cfg', CFG);   %% not "psd": that name is a Signal Processing function
save(fullfile(CFG.outDir,'psd_curves.mat'), '-struct', 'psdOut');
fprintf('\nWrote features_train.csv, features_test.csv, test_epoch_meta.csv, psd_curves.mat\n');
fprintf('to %s\n', CFG.outDir);


%% ========================== LOCAL FUNCTIONS =============================

function F = featurize(miF, baseF, miRaw, CFG)
% miF   : [nPost x 2] bandpassed imagery window, columns [C3 C4]
% baseF : [nPre  x 2] bandpassed baseline window
% miRaw : [nPost x 2] detrended, UNfiltered imagery window (for the PSD)
%
% Produces the nine features in two flavours:
%   absolute      - straight from the energy series
%   ERD-normalised- energy expressed as % change from the trial's own baseline
%
% Note on the moments: ERD% is an AFFINE transform of the energy series
% (E - b)/b*100 = E*(100/b) - 100, and skewness and kurtosis are invariant
% under affine transforms. So only mean and median change between the two
% flavours. They are therefore stored once each, not duplicated.

    E    = miF.^2;                       % energy of each point
    Eb   = baseF.^2;                     % baseline energy
    base = mean(Eb, 1);                  % [1 x 2] baseline band power per channel

    F = struct();
    nm = {'C3','C4'};
    for c = 1:2
        F.([nm{c} '_mean'])   = mean(E(:,c));
        F.([nm{c} '_median']) = median(E(:,c));
        F.([nm{c} '_skew'])   = skewness(E(:,c));
        F.([nm{c} '_kurt'])   = kurtosis(E(:,c));
        % ERD-normalised mean / median, in percent change from baseline
        F.(['E_' nm{c} '_mean'])   = (mean(E(:,c))   - base(c)) / base(c) * 100;
        F.(['E_' nm{c} '_median']) = (median(E(:,c)) - base(c)) / base(c) * 100;
    end

    % --- Welch PSD on the unfiltered imagery window -----------------------
    [pxx, f] = pwelch(miRaw, hamming(CFG.welchWin), CFG.welchOvl, CFG.welchNfft, CFG.fsTarget);
    P     = bandInt(pxx, f, CFG.band);
    Pa    = bandInt(pxx, f, CFG.bandAlpha);
    Pb_   = bandInt(pxx, f, CFG.bandBeta);

    F.logC3C4       = log10(P(1)  / P(2));
    F.logC3C4_alpha = log10(Pa(1) / Pa(2));
    F.logC3C4_beta  = log10(Pb_(1)/ Pb_(2));

    % ERD-normalised ratio: each channel's band power divided by its own
    % baseline band power first, so the device gain cancels on both sides.
    F.E_logC3C4 = log10( (mean(E(:,1))/base(1)) / (mean(E(:,2))/base(2)) );
end


function p = bandInt(pxx, f, band)
% Integrated power in a band, per column of pxx.
    sel = f >= band(1) & f <= band(2);
    p   = trapz(f(sel), pxx(sel,:), 1);
end


function A = initPsdAcc(CFG)
    nf = CFG.welchNfft/2 + 1;
    A = struct('f', [], 'sum', zeros(nf, 2, 2), 'n', zeros(1,2));   % [freq x chan x class]
end


function A = accPsd(A, miRaw, label, CFG)
    [pxx, f] = pwelch(miRaw, hamming(CFG.welchWin), CFG.welchOvl, CFG.welchNfft, CFG.fsTarget);
    if isempty(A.f), A.f = f; end
    A.sum(:,:,label) = A.sum(:,:,label) + pxx;
    A.n(label) = A.n(label) + 1;
end


function A = finishPsd(A)
    for c = 1:2
        if A.n(c) > 0, A.sum(:,:,c) = A.sum(:,:,c) / A.n(c); end
    end
    A.mean = A.sum; A = rmfield(A, 'sum');
end


function T = rowsToTable(rows)
    S = vertcat(rows{:});
    T = struct2table(S);
    % put the identifying columns first
    front = {'dataset','group','item','label'};
    T = movevars(T, front, 'Before', 1);
end
