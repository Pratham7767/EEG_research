function erd_ers_2b_stroke_method
% ERD_ERS_2B_STROKE_METHOD  ERD/ERS at C3 and C4 for every subject of
% BCI Competition IV 2b ("BCI 2008", Graz data set B, downloaded from BNCI),
% computed with the recipe used for the stroke patients in
%     D:\trainsvm\data\stroke_liu2024\ERD_ERS\erd_ers_all_subjects.m
% (Technical Validation section of the stroke dataset paper), so that the
% 2b plots and the stroke plots can be put side by side.
%
%   1) band-pass C3 and C4, 8-30 Hz, Butterworth order 2, filtfilt (zero
%      phase). The filter runs over the 8 s trial plus 0.5 s on each side,
%      and the padding is cut off afterwards, so filter edge effects never
%      reach the plotted 0..8 s.
%   2) square each trial
%   3) average the squared trials within each class (left / right hand),
%      plain mean, then SMOOTH with the paper's smoothing (smoothMA.m =
%      smooth(y,span); 200 samples at 500 Hz = 0.4 s = 100 samples at
%      250 Hz -> 99 used: smooth() makes an even span odd by -1, exactly as
%      200 -> 199 in the stroke run).
%   4) ERD/ERS% = (X - M)/M * 100, M = mean of the 1 s just before the cue
%      (trial time 2..3 s = -1..0 s from the cue), X = every sample.
%
% PLOTS show the whole trial, 0..8 s, like the timing figure of the
% BCI 2008 paper (Leeb et al., Graz data set B): cue at 3 s (dashed line),
% so you see before and after the cue. The summary numbers use the same
% windows as before: 0..4 s after the cue, and 0.5..3.5 s after the cue.
%
% What is different for 2b is only the DATA, not the method:
%   * Fs 250 Hz instead of 500 -> 1 s = 250 samples
%   * cue = `trial` + 3 s  (2b has no marker channel; `trial` is the trial
%     START, the cue comes 3 s later - see CLAUDE.md)
%   * channels: X(:,1) = C3, X(:,3) = C4 (bipolar). Cz and EOG not used.
%   * all 5 sessions pooled (T file = sessions 1-3, E file = 4-5),
%     about 360 trials per hand instead of 20
%   * trials with NaN (lost samples) are dropped (the stroke data had none).
%     Trials flagged as artefacts by the dataset are KEPT, because the stroke
%     recipe has no artefact rejection; they are counted.
%   NOTE: in 2b the warning beep is at 2 s (-1 s from the cue), i.e. at the
%   START of the baseline. Same window as the stroke recipe on purpose.
%
% Outputs (in this folder):
%   figures\B0x_ERD_ERS.png            one per subject, 0..8 s, cue at 3 s
%   ERD_ERS_2b_all_subjects.png        all 9 subjects on one page
%   ERD_ERS_2b_summary.csv             one row per subject
%   ERD_ERS_2b_stroke_method.mat       all curves (smoothed, 0..8 s)
%   run_log.txt, _DONE.txt
%
% Run:  cd D:\trainsvm\experiments\05_bci_iv_2b\erd_ers_stroke_method
%       erd_ers_2b_stroke_method

%% ------------------------------------------------------------------ setup
dataDir = 'D:\trainsvm\experiments\05_bci_iv_2b\data';
outdir  = 'D:\trainsvm\experiments\05_bci_iv_2b\erd_ers_stroke_method';
strokeDir = 'D:\trainsvm\data\stroke_liu2024\ERD_ERS';     % for smoothMA.m
addpath(strokeDir);
figdir  = fullfile(outdir,'figures');
if ~exist(figdir,'dir'),  mkdir(figdir);  end
done = fullfile(outdir,'_DONE.txt'); if exist(done,'file'), delete(done); end
logf = fullfile(outdir,'run_log.txt'); if exist(logf,'file'), delete(logf); end
logid = fopen(logf,'w'); cleanup = onCleanup(@() fclose(logid));
pf = @(varargin) [fprintf(varargin{:}), fprintf(logid, varargin{:})];   % console + run_log.txt

Fs      = 250;           % 2b sampling rate (Hz)
C3      = 1;             % column of C3 in X
C4      = 3;             % column of C4 in X
cueSec  = 3;             % cue = trial + 3 s
trialN  = 8*Fs;          % plotted trial: 0..8 s
padN    = round(0.5*Fs); % extra 0.5 s each side, only for the filter
band    = [8 30];
smoothN = 100;           % 0.4 s; smoothMA uses 99 samples (odd), like smooth()
nSub    = 9;
names   = arrayfun(@(k) sprintf('B%02d',k), 1:nSub, 'UniformOutput', false);

[b,a] = butter(2, band/(Fs/2), 'bandpass');
tt   = (0:trialN-1)/Fs;                         % trial time, s (cue at 3 s)
bIdx = (cueSec-1)*Fs+1 : cueSec*Fs;             % baseline: 1 s before the cue
aIdx = cueSec*Fs+1     : (cueSec+4)*Fs;         % 0..4 s after the cue
tA   = (0:numel(aIdx)-1)/Fs;                    % time from cue in that segment
mi   = tA >= 0.5 & tA < 3.5;                    % 0.5..3.5 s after the cue
erdf = @(c) (c - mean(c(bIdx))) / mean(c(bIdx)) * 100;

pf('ERD/ERS, BCI IV 2b, stroke method  (%s)\n', datestr(now,'yyyy-mm-dd HH:MM'));
pf('8-30 Hz Butterworth-2 filtfilt, square, mean, smooth 0.4 s, baseline = 1 s before cue, plot 0..8 s\n\n');

%% -------------------------------------------------------------- compute
ERD_all = struct([]);
M_L_C3 = zeros(nSub,trialN); M_L_C4 = M_L_C3; M_R_C3 = M_L_C3; M_R_C4 = M_L_C3;
summ = zeros(nSub,8); pow = zeros(nSub,4); mean05 = zeros(nSub,4);
nL = zeros(nSub,1); nR = nL; nNaN = nL; nEdge = nL; nArt = nL;

tic
for si = 1:nSub
    P3 = {}; P4 = {}; lab = []; art = [];
    files = {[names{si} 'T.mat'], [names{si} 'E.mat']};
    for fi = 1:2
        m = load(fullfile(dataDir, files{fi}));
        for k = 1:numel(m.data)
            s  = m.data{k};
            X  = double(s.X(:,[C3 C4]));
            tr = double(s.trial(:));  yy = double(s.y(:));  aa = double(s.artifacts(:));
            for i = 1:numel(tr)
                idx = tr(i)-padN : tr(i)+trialN-1+padN;
                if idx(1) < 1 || idx(end) > size(X,1), nEdge(si) = nEdge(si)+1; continue; end
                x = X(idx,:);
                if any(isnan(x(:))), nNaN(si) = nNaN(si)+1; continue; end
                xf = filtfilt(b, a, x);              % filter trial + padding
                xf = xf(padN+1 : padN+trialN, :);    % keep 0..8 s of the trial
                P3{end+1,1} = xf(:,1)'.^2;           %#ok<AGROW> square
                P4{end+1,1} = xf(:,2)'.^2;           %#ok<AGROW>
                lab(end+1,1) = yy(i);                %#ok<AGROW>
                art(end+1,1) = aa(i);                %#ok<AGROW>
            end
        end
    end
    P3 = cell2mat(P3);  P4 = cell2mat(P4);
    isL = lab==1;  isR = lab==2;
    L3 = smoothMA(mean(P3(isL,:),1), smoothN);  L4 = smoothMA(mean(P4(isL,:),1), smoothN);
    R3 = smoothMA(mean(P3(isR,:),1), smoothN);  R4 = smoothMA(mean(P4(isR,:),1), smoothN);

    e = struct('subject',names{si}, ...
        'L_C3',erdf(L3),'L_C4',erdf(L4),'R_C3',erdf(R3),'R_C4',erdf(R4), ...
        'baseline',[mean(L3(bIdx)) mean(L4(bIdx)) mean(R3(bIdx)) mean(R4(bIdx))], ...
        'nLeft',sum(isL),'nRight',sum(isR),'nArtifactKept',sum(art==1), ...
        'nNaNDropped',nNaN(si),'nEdgeDropped',nEdge(si));
    if isempty(ERD_all), ERD_all = e; else, ERD_all(si) = e; end

    M_L_C3(si,:) = e.L_C3;  M_L_C4(si,:) = e.L_C4;
    M_R_C3(si,:) = e.R_C3;  M_R_C4(si,:) = e.R_C4;
    sL3 = e.L_C3(aIdx); sL4 = e.L_C4(aIdx); sR3 = e.R_C3(aIdx); sR4 = e.R_C4(aIdx);
    summ(si,:) = [median(sL3) median(sL4) median(sR3) median(sR4) ...
                  mean(sL3)   mean(sL4)   mean(sR3)   mean(sR4)];
    pow(si,:)  = [mean(L3(aIdx)) mean(L4(aIdx)) mean(R3(aIdx)) mean(R4(aIdx))];
    mean05(si,:) = [mean(sL3(mi)) mean(sL4(mi)) mean(sR3(mi)) mean(sR4(mi))];
    nL(si) = e.nLeft; nR(si) = e.nRight; nArt(si) = e.nArtifactKept;
    pf('%s  %3d left  %3d right  (dropped: %d NaN, %d edge; %d artefact-flagged kept)  %.1f s\n', ...
        names{si}, nL(si), nR(si), nNaN(si), nEdge(si), nArt(si), toc);
end

%% ---------------------------------------------------------------- figures
% Plain report style, same look as experiments\03_gelo_erd\gelo_erd.m:
% C3 red dashed, C4 blue solid, no shading, no Cz, one y-scale for both
% panels, whole trial 0..8 s with the cue marked at 3 s.
for si = 1:nSub
    e = ERD_all(si);
    subjFig(tt, e.L_C3, e.L_C4, e.R_C3, e.R_C4, cueSec, ...
        sprintf('BCI IV 2b  %s  -  C3/C4, %d-%d Hz, Fs = %d Hz, smoothing 0.4 s, cue at %d s', ...
                e.subject, band(1), band(2), Fs, cueSec), ...
        fullfile(figdir, sprintf('%s_ERD_ERS.png', e.subject)));
end

% all subjects on one page, same style (2 subjects per row: L | R | L | R)
fg = figure('Color','w','Position',[50 50 1500 1150],'Visible','off');
tl = tiledlayout(fg, 5, 4, 'TileSpacing','compact','Padding','compact');
for si = 1:nSub
    e  = ERD_all(si);
    yl = sharedYlim([e.L_C3 e.L_C4 e.R_C3 e.R_C4]);
    for c = 1:2
        ax = nexttile(tl);
        if c == 1, y3 = e.L_C3; y4 = e.L_C4; hand = 'Left'; else, y3 = e.R_C3; y4 = e.R_C4; hand = 'Right'; end
        drawPanel(ax, tt, y3, y4, cueSec, sprintf('%s  MI with %s Hand', e.subject, hand), yl, 9);
        if ~(si == 1 && c == 1), legend(ax,'off'); end
        if si < 8, xlabel(ax,''); end
    end
end
title(tl, sprintf('BCI IV 2b  -  C3/C4, %d-%d Hz, Fs = %d Hz, smoothing 0.4 s, cue at %d s', ...
      band(1), band(2), Fs, cueSec), 'FontSize', 12);
exportgraphics(fg, fullfile(outdir,'ERD_ERS_2b_all_subjects.png'), 'Resolution',130);
close(fg);

%% ------------------------------------------------------------------ save
okL = mean05(:,2) < mean05(:,1);     % left-hand MI : C4 drops more than C3
okR = mean05(:,3) < mean05(:,4);     % right-hand MI: C3 drops more than C4
T = table(names', nL, nR, nNaN+nEdge, nArt, ...
    summ(:,1),summ(:,2),summ(:,3),summ(:,4), summ(:,5),summ(:,6),summ(:,7),summ(:,8), ...
    pow(:,1),pow(:,2),pow(:,3),pow(:,4), ...
    mean05(:,1),mean05(:,2),mean05(:,3),mean05(:,4), okL, okR, ...
    'VariableNames',{'subject','nLeft','nRight','nExcluded','nArtifactKept', ...
    'med_L_C3','med_L_C4','med_R_C3','med_R_C4', ...
    'mean_L_C3','mean_L_C4','mean_R_C3','mean_R_C4', ...
    'pow_L_C3','pow_L_C4','pow_R_C3','pow_R_C4', ...
    'm05_35_L_C3','m05_35_L_C4','m05_35_R_C3','m05_35_R_C4', ...
    'left_MI_C4_drops_more','right_MI_C3_drops_more'});
writetable(T, fullfile(outdir,'ERD_ERS_2b_summary.csv'));
t = tt;   % trial time, s (cue at 3 s)
save(fullfile(outdir,'ERD_ERS_2b_stroke_method.mat'), 'ERD_all','t','cueSec', ...
    'M_L_C3','M_L_C4','M_R_C3','M_R_C4','smoothN', ...
    'summ','pow','mean05','T','band','Fs');

%% ------------------------------------------------------- printed summary
pf('\nMean ERD/ERS %% over 0.5-3.5 s after the cue (smoothed 0.4 s)\n');
pf('subject   Left MI: C3      C4    Right MI: C3      C4    opposite side drops more?\n');
for si = 1:nSub
    pf('%s      %+7.1f %+7.1f        %+7.1f %+7.1f     L:%s R:%s\n', names{si}, mean05(si,:), ...
        yn(okL(si)), yn(okR(si)));
end
pf('median     %+7.1f %+7.1f        %+7.1f %+7.1f\n', median(mean05,1));
pf('\nStroke-script columns (median over 0..4 s after the cue), group medians:\n');
pf('Left-hand MI :  C3 %+.1f%%   C4 %+.1f%%\n', median(summ(:,1)), median(summ(:,2)));
pf('Right-hand MI:  C3 %+.1f%%   C4 %+.1f%%\n', median(summ(:,3)), median(summ(:,4)));
pf('opposite side drops more (0.5-3.5 s): %d/%d cases\n', sum(okL)+sum(okR), 2*nSub);
pf('\ndone in %.1f s. Output: %s\n', toc, outdir);
fid = fopen(done,'w'); fprintf(fid,'%s\n',datestr(now)); fclose(fid);
end

function s = yn(v), if v, s = 'yes'; else, s = 'NO '; end, end

function subjFig(t, L3, L4, R3, R4, cueSec, ttl, fname)
% one subject: left-hand MI on top, right-hand MI below (gelo_erd.m style)
fg = figure('Color','w','Position',[100 60 1000 620],'Visible','off');
yl = sharedYlim([L3 L4 R3 R4]);
drawPanel(subplot(2,1,1), t, L3, L4, cueSec, 'MI with Left Hand',  yl, 12);
drawPanel(subplot(2,1,2), t, R3, R4, cueSec, 'MI with Right Hand', yl, 12);
sgtitle(ttl, 'FontSize', 12);
exportgraphics(fg, fname, 'Resolution',160);
close(fg);
end

function drawPanel(ax, t, c3, c4, cueSec, ttl, yl, fs)
plot(ax, t, c3, 'r--', 'LineWidth',1.1); hold(ax,'on');
plot(ax, t, c4, 'b-',  'LineWidth',1.1);
yline(ax, 0, 'Color',[.85 .85 .85], 'HandleVisibility','off');
xline(ax, cueSec, 'k--', 'cue', 'LineWidth',0.8, 'FontSize', max(fs-3,7), ...
      'LabelVerticalAlignment','top', 'LabelOrientation','horizontal', 'HandleVisibility','off');
xlim(ax, [0 t(end)]); xticks(ax, 0:8); ylim(ax, yl);
title(ax, ttl, 'FontSize', fs);
xlabel(ax, 'Time(s)', 'FontSize', fs); ylabel(ax, 'ERD/ERS %', 'FontSize', fs);
h = legend(ax, {'C3','C4'}, 'Location','southwest', 'Orientation','horizontal');
legend(ax, 'boxoff'); set(h, 'FontSize', 8);
end

function yl = sharedYlim(y)
% one y-scale for both panels so left and right can be compared by eye
yl = [floor(min(y)/10)*10 - 5, ceil(max(y)/10)*10 + 5];
end
