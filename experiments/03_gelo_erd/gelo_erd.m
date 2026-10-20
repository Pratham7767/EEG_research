%% ========================================================================
%  GELO_ERD - ERD/ERS plot for the Gelo / LEHeadphones2 recordings
%
%  Reads:  <dataRoot>\left\*.csv  and  <dataRoot>\right\*.csv
%  Writes: matlab_erd_combined.png, matlab_erd_overlay.png,
%          matlab_epoch_meta.csv, epochs_paper_format.mat  -> CFG.outDir
%
%  Full explanation of the method and the data: GELO_ERD_EXPLAINED.txt
%  Requires Signal Processing Toolbox. Statistics and Curve Fitting optional.
%% ========================================================================
clear; clc; close all;

%% ----------------------------- SETTINGS ---------------------------------
% Everything you can change lives in this block.

CFG.dataRoot     = 'D:\trainsvm\data\gelo';      % folder containing \left and \right
CFG.outDir       = 'D:\trainsvm\experiments\03_gelo_erd';  % where figures and files are written
CFG.leftFolder   = 'left';             % subfolder name for left-hand trials
CFG.rightFolder  = 'right';            % subfolder name for right-hand trials

CFG.fs           = 250;                % sampling rate of your recordings, Hz
CFG.band         = [8 30];             % bandpass, Hz
CFG.order        = 2;                  % Butterworth filter order
CFG.zeroPhase    = true;               % false = causal filter (shifts curves in time)

CFG.smoothSec    = 0.4;                % smoothing window, seconds
CFG.smoothMethod = 'moving';           % 'moving' 'sgolay' 'lowess' 'loess' 'rlowess' 'rloess'

CFG.preSec       = 1.0;                % baseline before onset, seconds
CFG.postSec      = 4.0;                % imagery window after onset, seconds
CFG.padSec       = 0.5;                % extra margin cut then discarded, seconds
CFG.minRestSec   = 1.5;                % rest required before an onset, else trial dropped

CFG.c3           = 2;                  % column of C3 within ch1..ch4
CFG.c4           = 3;                  % column of C4 within ch1..ch4
CFG.marks        = 1:5;                % mark values that count as an iteration
CFG.sharedYAxis  = true;               % true = both panels share one y-axis scale

%% --------------------------- (no edits below) ---------------------------
D.smoothN  = round(CFG.smoothSec * CFG.fs);
if mod(D.smoothN,2) == 0, D.smoothN = D.smoothN + 1; end   % odd span: smooth==movmean
D.prePlot  = round(CFG.preSec  * CFG.fs);
D.postPlot = round(CFG.postSec * CFG.fs);
D.padPre   = round((CFG.preSec  + CFG.padSec) * CFG.fs);
D.padPost  = round((CFG.postSec + CFG.padSec) * CFG.fs);
D.crop0    = D.padPre - D.prePlot;
D.nPlot    = D.prePlot + D.postPlot;
CFG.D = D;

CFG.hasCF = license('test','Curve_Fitting_Toolbox') && ~isempty(which('smooth'));
if ~CFG.hasCF && ~strcmp(CFG.smoothMethod,'moving')
    warning('No Curve Fitting Toolbox - using a moving average.');
    CFG.smoothMethod = 'moving';
end

fprintf('Fs %d Hz | band %g-%g Hz | smoothing %d samples (%.2f s, ''%s'') | epoch %d samples\n', ...
    CFG.fs, CFG.band(1), CFG.band(2), D.smoothN, CFG.smoothSec, CFG.smoothMethod, D.nPlot);
if ~exist(CFG.outDir,'dir'), mkdir(CFG.outDir); end

%% ------------------------------ LOAD ------------------------------------
fprintf('\n================ WHERE YOUR DATA COMES FROM ================\n');
[epL, infoL] = loadClass(fullfile(CFG.dataRoot, CFG.leftFolder),  'LEFT  hand', CFG);
[epR, infoR] = loadClass(fullfile(CFG.dataRoot, CFG.rightFolder), 'RIGHT hand', CFG);
fprintf('============================================================\n');
fprintf('POOLED:  left = %d epochs   right = %d epochs\n', size(epL,3), size(epR,3));

info = [infoL; infoR];
writetable(info, fullfile(CFG.outDir,'matlab_epoch_meta.csv'));

%% ------------------ FIGURE 1: left and right panels ---------------------
f1 = figure('Color','w','Position',[100 60 560 680]);
ax1 = subplot(2,1,1); [c3L, c4L] = plotPanel(epL, 'MI with Left Hand',  CFG);
ax2 = subplot(2,1,2); [c3R, c4R] = plotPanel(epR, 'MI with Right Hand', CFG);
if CFG.sharedYAxis                          % one scale, so the panels compare directly
    w  = D.prePlot+1 : D.nPlot;
    sy = [c3L(w); c4L(w); c3R(w); c4R(w)];
    yl = [min(sy)-10, max(sy)+5];
    ylim(ax1, yl); ylim(ax2, yl);
end
sgtitle(sprintf('Gelo BCI  -  C3/C4, %g-%g Hz, Fs = %d Hz, smoothing ''%s''', ...
    CFG.band(1), CFG.band(2), CFG.fs, CFG.smoothMethod), 'FontSize', 12);
exportgraphics(f1, fullfile(CFG.outDir,'matlab_erd_combined.png'), 'Resolution', 160);

%% ------------------ FIGURE 2: all four curves overlaid ------------------
t = ((0:D.nPlot-1) - D.prePlot) / CFG.fs;
f2 = figure('Color','w','Position',[700 200 620 420]); hold on; grid on;
plot(t, c3L, 'r--','LineWidth',1.3); plot(t, c4L, 'b--','LineWidth',1.3);
plot(t, c3R, 'r-', 'LineWidth',1.3); plot(t, c4R, 'b-', 'LineWidth',1.3);
xline(0,'Color',[.6 .6 .6]); yline(0,'Color',[.85 .85 .85]);
xlim([0 CFG.postSec]); xticks(0:CFG.postSec);
xlabel('Time(s)','FontSize',11); ylabel('ERD/ERS %','FontSize',11);
title('Left vs right overlaid  (dashed = left hand, solid = right hand)','FontSize',11);
legend({'C3 left','C4 left','C3 right','C4 right'}, ...
    'Location','southoutside','Orientation','horizontal','Box','off');
exportgraphics(f2, fullfile(CFG.outDir,'matlab_erd_overlay.png'), 'Resolution', 160);

%% -------------------- SIGNIFICANCE TEST (per trial) ---------------------
if license('test','Statistics_Toolbox')
    fprintf('\n=== per-trial mean ERD%% over 0-%g s (negative = activation) ===\n', CFG.postSec);
    fprintf('%-12s %4s %10s %10s %10s %10s\n','task','n','contra','ipsi','diff','p');
    runTest('Left hand',  epL, CFG.c4, CFG.c3, CFG);   % left hand  -> contra = C4
    runTest('Right hand', epR, CFG.c3, CFG.c4, CFG);   % right hand -> contra = C3
    fprintf('\nNeeds diff < 0 AND p < 0.05 in BOTH rows to be a real effect.\n');
else
    fprintf('\n(No Statistics Toolbox - skipping the test.)\n');
end

%% --------------- EXPORT for the authors'  plotERDERS.m ------------------
[datar1, labelr1] = toPaperFormat(epL, epR, CFG);
save(fullfile(CFG.outDir,'epochs_paper_format.mat'), 'datar1', 'labelr1');
fprintf('\nSaved epochs_paper_format.mat : datar1 %s, %d labels\n', ...
    mat2str(size(datar1)), numel(labelr1));
fprintf('Figures written to %s\n', CFG.outDir);


%% ========================= LOCAL FUNCTIONS ==============================

function [EP, info] = loadClass(folder, label, CFG)
% Cuts one padded epoch per iteration from every CSV in `folder`.
% EP: [samples x 4 channels x trials].  info: one row per iteration.
D = CFG.D;
files = dir(fullfile(folder,'*.csv'));
assert(~isempty(files), 'No CSV files found in %s', folder);

fprintf('\n%s   <-   %s\n', label, folder);
fprintf('  %-18s %-32s %s\n','file','mark 1..5','kept');

EP = zeros(D.padPre + D.padPost, 4, 0);
fileC = {}; markC = []; durC = []; restC = []; statC = {};

for k = 1:numel(files)
    M = readmatrix(fullfile(files(k).folder, files(k).name));
    M = M(~isnan(M(:,end)), :);
    assert(size(M,2) >= 10, 'Unexpected column count in %s', files(k).name);

    X  = M(:, 2:5) * 1e6;                       % ch1..ch4, volts -> microvolts
    mk = M(:, end);                             % mark column
    tags = strings(1, numel(CFG.marks)); nkept = 0;

    for ii = 1:numel(CFG.marks)
        m = CFG.marks(ii);
        idx = find(mk == m);
        status = 'OK'; dur = 0; preRest = 0;

        if isempty(idx)
            status = 'MISSING';
        else
            onset = idx(1);                     % first sample carrying this mark
            dur   = numel(idx) / CFG.fs;

            j = onset - 1;                      % count contiguous rest before onset
            while j >= 1 && mk(j) == 0, j = j - 1; end
            preRest = (onset - 1 - j) / CFG.fs;

            if onset - D.padPre < 1 || onset + D.padPost - 1 > size(X,1)
                status = 'EDGE';
            elseif preRest < CFG.minRestSec
                status = 'NO_BASELINE';
            else
                EP(:,:,end+1) = X(onset - D.padPre : onset + D.padPost - 1, :); %#ok<AGROW>
                nkept = nkept + 1;
            end
        end

        switch status
            case 'OK',          tags(ii) = sprintf('%d:ok  ', m);
            case 'MISSING',     tags(ii) = sprintf('%d:--  ', m);
            case 'NO_BASELINE', tags(ii) = sprintf('%d:nobl', m);
            case 'EDGE',        tags(ii) = sprintf('%d:edge', m);
        end
        fileC{end+1,1} = files(k).name; markC(end+1,1) = m;  %#ok<AGROW>
        durC(end+1,1)  = dur; restC(end+1,1) = preRest;      %#ok<AGROW>
        statC{end+1,1} = status;                             %#ok<AGROW>
    end
    fprintf('  %-18s %-32s %d/%d\n', files(k).name, strjoin(tags,' '), nkept, numel(CFG.marks));
end

fprintf('  %-18s %-32s %d epochs from %d files\n', 'TOTAL', '', size(EP,3), numel(files));
[~, cls] = fileparts(folder);
info = table(repmat({cls},numel(markC),1), fileC, markC, durC, restC, statC, ...
    'VariableNames', {'class','file','mark','dur_s','pre_rest_s','status'});
end


function y = smoothCurve(x, CFG)
if CFG.hasCF
    y = smooth(x, CFG.D.smoothN, CFG.smoothMethod);
else
    y = movmean(x, CFG.D.smoothN);
end
end


function y = erdCurve(EP, ch, CFG)
% bandpass -> square -> average over trials -> smooth -> crop -> percent.
D = CFG.D;
[b,a] = butter(CFG.order, CFG.band * 2 / CFG.fs);
acc = zeros(size(EP,1),1);
for i = 1:size(EP,3)
    if CFG.zeroPhase, x = filtfilt(b,a,EP(:,:,i)); else, x = filter(b,a,EP(:,:,i)); end
    acc = acc + x(:,ch).^2;
end
avg  = smoothCurve(acc / size(EP,3), CFG);
avg  = avg(D.crop0 + 1 : D.crop0 + D.nPlot);            % discard the padding
base = mean(avg(1 : D.prePlot));                        % baseline mean
y    = (avg - base) / base * 100;
end


function v = trialErd(EP, ch, CFG)
% Same as erdCurve but one number per trial, for the significance test.
D = CFG.D;
[b,a] = butter(CFG.order, CFG.band * 2 / CFG.fs);
v = zeros(size(EP,3),1);
for i = 1:size(EP,3)
    x = filtfilt(b,a,EP(:,:,i));
    p = smoothCurve(x(:,ch).^2, CFG);
    p = p(D.crop0 + 1 : D.crop0 + D.nPlot);
    base = mean(p(1 : D.prePlot));
    v(i) = mean((p(D.prePlot+1:end) - base) / base * 100);
end
end


function [c3, c4] = plotPanel(EP, ttl, CFG)
D  = CFG.D;
t  = ((0:D.nPlot-1) - D.prePlot) / CFG.fs;
c3 = erdCurve(EP, CFG.c3, CFG);
c4 = erdCurve(EP, CFG.c4, CFG);
plot(t, c3, 'r--','LineWidth',1.1); hold on;
plot(t, c4, 'b-', 'LineWidth',1.1);
xline(0,'Color',[.6 .6 .6]); yline(0,'Color',[.85 .85 .85]);
seg = [c3(D.prePlot+1:end); c4(D.prePlot+1:end)];
xlim([0 CFG.postSec]); xticks(0:CFG.postSec);
ylim([min(seg)-10, max(seg)+5]);
title(sprintf('%s  (n = %d)', ttl, size(EP,3)), 'FontSize', 12);
xlabel('Time(s)','FontSize',12); ylabel('ERD/ERS %','FontSize',12);
h = legend({'C3','C4'},'Location','southwest','Orientation','horizontal');
legend('boxoff'); set(h,'FontSize',8);
end


function runTest(name, EP, chContra, chIpsi, CFG)
a = trialErd(EP, chContra, CFG);
b = trialErd(EP, chIpsi,   CFG);
[~, p] = ttest(a, b);
fprintf('%-12s %4d %10.2f %10.2f %10.2f %10.4f\n', name, numel(a), mean(a), mean(b), mean(a-b), p);
end


function [datar1, labelr1] = toPaperFormat(epL, epR, CFG)
% [samples x 15 channels x trials] with C3 at ch14 and C4 at ch15.
% labelr1: 1 = left hand, 2 = right hand.
D = CFG.D; nL = size(epL,3); nR = size(epR,3);
datar1 = zeros(D.nPlot, 15, nL + nR);
rng = D.crop0 + 1 : D.crop0 + D.nPlot;
for i = 1:nL
    datar1(:,14,i) = epL(rng, CFG.c3, i);
    datar1(:,15,i) = epL(rng, CFG.c4, i);
end
for i = 1:nR
    datar1(:,14,nL+i) = epR(rng, CFG.c3, i);
    datar1(:,15,nL+i) = epR(rng, CFG.c4, i);
end
labelr1 = [ones(nL,1); 2*ones(nR,1)];
end
