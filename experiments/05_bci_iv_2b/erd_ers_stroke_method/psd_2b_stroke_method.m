function psd_2b_stroke_method
% PSD_2B_STROKE_METHOD  Power spectra (PSD) of C3 and C4 for every subject of
% BCI Competition IV 2b ("BCI 2008", Graz data set B, downloaded from BNCI),
% plus a test of which single number best tells LEFT from RIGHT hand imagery.
%
% Companion of erd_ers_2b_stroke_method.m (same folder): SAME trials, SAME
% channels and SAME time windows as those ERD/ERS plots.
%
% PSD method (same as the PSD plot made before, RUN_ERD_PSD_2b.m psd_spectra):
%   * Welch PSD (pwelch), 0.5 s Hamming window, 50 % overlap, nfft 256
%     -> about 1 Hz resolution at 250 Hz
%   * one PSD per trial and window, then averaged over trials of one hand
%   * baseline = the 1 s just before the cue  (trial time 2..3 s)
%   * imagery  = 0..4 s after the cue         (trial time 3..7 s)
%   * "change" in a title = 8-30 Hz power, imagery vs baseline, in percent
%   (raw signal, mean removed per window; no band-pass needed for a spectrum)
%
% Differentiator test (single trials, no averaging):
%   window 0.5-3.5 s after the cue (the standard 2b imagery window), bands
%   mu 8-13, beta 13-30, broad 8-30 Hz. Six kinds of feature per band:
%     C3 power, C4 power, log(C3/C4) power ratio,
%     ERD C3, ERD C4  (log of imagery power / that trial's baseline power),
%     ERD C3 - ERD C4 (the difference between the two sides)
%   Each feature is scored three ways:
%     AUC       : how well it separates left/right over all trials (0.5 = no)
%     acc_S45   : one threshold learned on sessions 1-3, tested on 4-5
%                 (same subject, unseen days)
%     acc_LOSO  : threshold learned on the other 8 subjects, tested on this
%                 one (a brand-new user, nothing learned from them)
%
% Outputs (in this folder):
%   figures_psd\B0x_PSD.png        one per subject (2 x 2: hand x channel)
%   PSD_2b_grand_average.png       mean over the 9 subjects
%   differentiator_2b.png          accuracy of every feature, per subject
%   differentiator_best.png        the best feature: left vs right histograms
%   differentiator_2b.csv          every feature x subject x score
%   differentiator_summary.csv     mean over subjects, ranked
%   psd_run_log.txt, _PSD_DONE.txt
%
% Run:  cd D:\trainsvm\experiments\05_bci_iv_2b\erd_ers_stroke_method
%       psd_2b_stroke_method

%% ------------------------------------------------------------------ setup
dataDir = 'D:\trainsvm\experiments\05_bci_iv_2b\data';
outdir  = 'D:\trainsvm\experiments\05_bci_iv_2b\erd_ers_stroke_method';
figdir  = fullfile(outdir,'figures_psd');
if ~exist(figdir,'dir'), mkdir(figdir); end
done = fullfile(outdir,'_PSD_DONE.txt'); if exist(done,'file'), delete(done); end
logf = fullfile(outdir,'psd_run_log.txt');
logid = fopen(logf,'w'); cleanup = onCleanup(@() fclose(logid));
pf = @(varargin) [fprintf(varargin{:}), fprintf(logid, varargin{:})];

Fs = 250; C3 = 1; C4 = 3; nSub = 9;
names = arrayfun(@(k) sprintf('B%02d',k), 1:nSub, 'UniformOutput', false);
cueN  = 3*Fs;                                   % cue at trial time 3 s
wBase = cueN-Fs+1      : cueN;                  % -1 .. 0 s
wImag = cueN+1         : cueN+4*Fs;             %  0 .. 4 s   (plots)
wFeat = cueN+0.5*Fs+1  : cueN+3.5*Fs;           %  0.5 .. 3.5 s (features)
win = hamming(round(Fs/2)); nov = round(Fs/4); nfft = 256;
bands = struct('name',{'mu 8-13','beta 13-30','8-30'}, 'lim',{[8 13],[13 30],[8 30]});
showF = [4 40];

pf('PSD + differentiator, BCI IV 2b  (%s)\n', datestr(now,'yyyy-mm-dd HH:MM'));
pf('Welch 0.5 s Hamming, 50%% overlap, nfft %d; baseline -1..0 s, imagery 0..4 s; features 0.5..3.5 s\n\n', nfft);

%% -------------------------------------------------------------- compute
S = struct([]);
tic
for si = 1:nSub
    PB = {}; PI = {}; PF = {}; lab = []; sess = [];
    files = {[names{si} 'T.mat'], [names{si} 'E.mat']};
    sOff = [0 3];
    for fi = 1:2
        m = load(fullfile(dataDir, files{fi}));
        for k = 1:numel(m.data)
            s  = m.data{k};
            X  = double(s.X(:,[C3 C4]));
            tr = double(s.trial(:)); yy = double(s.y(:));
            for i = 1:numel(tr)
                idx = tr(i) : tr(i)+8*Fs-1;
                if idx(end) > size(X,1), continue; end
                x = X(idx,:);
                if any(isnan(x(:))), continue; end
                [pb,fr] = pwelch(detrend(x(wBase,:),'constant'), win, nov, nfft, Fs);
                pi_     = pwelch(detrend(x(wImag,:),'constant'), win, nov, nfft, Fs);
                pfe     = pwelch(detrend(x(wFeat,:),'constant'), win, nov, nfft, Fs);
                PB{end+1,1} = pb; PI{end+1,1} = pi_; PF{end+1,1} = pfe; %#ok<AGROW>
                lab(end+1,1) = yy(i); sess(end+1,1) = sOff(fi)+k;        %#ok<AGROW>
            end
        end
    end
    PB = cat(3,PB{:}); PI = cat(3,PI{:}); PF = cat(3,PF{:});   % freq x 2 ch x trials
    S(si).name = names{si}; S(si).f = fr; S(si).y = lab; S(si).sess = sess;
    S(si).PB = PB; S(si).PI = PI; S(si).PF = PF;
    pf('%s  %d trials  (%.1f s)\n', names{si}, numel(lab), toc);
end
f = S(1).f;

%% ------------------------------------------------------- PSD figures
chN = {'C3','C4'}; hand = {'Left','Right'};
inb = f >= 8 & f <= 30; ks = f >= showF(1) & f <= showF(2);
chg = zeros(nSub,2,2);                                  % subject x hand x channel
for si = 1:nSub
    fg = figure('Color','w','Position',[80 60 1000 700],'Visible','off');
    for h = 1:2
        for c = 1:2
            mb = mean(squeeze(S(si).PB(:,c,S(si).y==h)),2);
            mi = mean(squeeze(S(si).PI(:,c,S(si).y==h)),2);
            chg(si,h,c) = 100*(trapz(f(inb),mi(inb))/trapz(f(inb),mb(inb)) - 1);
            psdPanel(subplot(2,2,(h-1)*2+c), f(ks), mb(ks), mi(ks), ...
                sprintf('MI with %s Hand  -  %s   (8-30 Hz: %+.0f %%)', hand{h}, chN{c}, chg(si,h,c)), 11);
        end
    end
    sgtitle(sprintf('BCI IV 2b  %s  -  PSD at C3/C4, baseline (1 s before cue) vs imagery (0-4 s after cue)', ...
        names{si}), 'FontSize', 12);
    exportgraphics(fg, fullfile(figdir, sprintf('%s_PSD.png', names{si})), 'Resolution',160);
    close(fg);
end

% grand average over subjects (mean of each subject's average spectrum)
fg = figure('Color','w','Position',[80 60 1000 700],'Visible','off');
for h = 1:2
    for c = 1:2
        GB = zeros(numel(f),nSub); GI = GB;
        for si = 1:nSub
            GB(:,si) = mean(squeeze(S(si).PB(:,c,S(si).y==h)),2);
            GI(:,si) = mean(squeeze(S(si).PI(:,c,S(si).y==h)),2);
        end
        mb = mean(GB,2); mi = mean(GI,2);
        g = 100*(trapz(f(inb),mi(inb))/trapz(f(inb),mb(inb)) - 1);
        psdPanel(subplot(2,2,(h-1)*2+c), f(ks), mb(ks), mi(ks), ...
            sprintf('MI with %s Hand  -  %s   (8-30 Hz: %+.0f %%)', hand{h}, chN{c}, g), 11);
    end
end
sgtitle('BCI IV 2b  -  all 9 subjects  -  PSD at C3/C4, baseline vs imagery', 'FontSize', 12);
exportgraphics(fg, fullfile(outdir,'PSD_2b_grand_average.png'), 'Resolution',160);
close(fg);

pf('\n8-30 Hz power change, imagery vs baseline (%%)\n');
pf('subject   Left MI: C3      C4    Right MI: C3      C4\n');
for si = 1:nSub
    pf('%s      %+7.1f %+7.1f        %+7.1f %+7.1f\n', names{si}, chg(si,1,1), chg(si,1,2), chg(si,2,1), chg(si,2,2));
end
pf('median     %+7.1f %+7.1f        %+7.1f %+7.1f\n', median(chg(:,1,1)), median(chg(:,1,2)), median(chg(:,2,1)), median(chg(:,2,2)));

%% ------------------------------------------- single-trial differentiators
% feature list: name, band, function of (imagery power, baseline power)
kinds = {'C3 power','C4 power','log C3/C4','ERD C3','ERD C4','ERD C3 - ERD C4'};
F = {};
for b = 1:numel(bands)
    kb = f >= bands(b).lim(1) & f <= bands(b).lim(2);
    for si = 1:nSub
        bpI = squeeze(trapz(f(kb), S(si).PF(kb,:,:), 1));   % 2 x trials
        bpB = squeeze(trapz(f(kb), S(si).PB(kb,:,:), 1));
        L3 = log(bpI(1,:))'; L4 = log(bpI(2,:))';
        E3 = log(bpI(1,:)./bpB(1,:))'; E4 = log(bpI(2,:)./bpB(2,:))';
        vals = {L3, L4, L3-L4, E3, E4, E3-E4};
        for k = 1:numel(kinds)
            F{b,k,si} = vals{k}; %#ok<AGROW>
        end
    end
end

nB = numel(bands); nK = numel(kinds);
AUC = zeros(nB,nK,nSub); ACC = AUC; LOSO = AUC; PV = AUC;
for b = 1:nB
    for k = 1:nK
        for si = 1:nSub
            x = F{b,k,si}; y = S(si).y; ss = S(si).sess;
            AUC(b,k,si) = aucRank(x, y==2);
            tr = ss <= 3; te = ~tr;
            ACC(b,k,si) = mean(thrClassify(x(tr), y(tr), x(te)) == y(te));
            PV(b,k,si)  = 1 - binocdf(round(ACC(b,k,si)*sum(te))-1, sum(te), 0.5);
            xo = []; yo = [];
            for sj = setdiff(1:nSub, si)
                xo = [xo; F{b,k,sj}]; yo = [yo; S(sj).y]; %#ok<AGROW>
            end
            LOSO(b,k,si) = mean(thrClassify(xo, yo, x) == y);
        end
    end
end

% tables
rows = {}; R = [];
for b = 1:nB
    for k = 1:nK
        for si = 1:nSub
            rows(end+1,:) = {names{si}, bands(b).name, kinds{k}}; %#ok<AGROW>
            R(end+1,:) = [AUC(b,k,si) ACC(b,k,si) PV(b,k,si) LOSO(b,k,si)]; %#ok<AGROW>
        end
    end
end
T = [cell2table(rows,'VariableNames',{'subject','band','feature'}), ...
     array2table(R,'VariableNames',{'AUC','acc_S45','p_S45','acc_LOSO'})];
writetable(T, fullfile(outdir,'differentiator_2b.csv'));

sr = {}; SR = [];
for b = 1:nB
    for k = 1:nK
        a = squeeze(ACC(b,k,:)); l = squeeze(LOSO(b,k,:)); u = squeeze(AUC(b,k,:));
        sr(end+1,:) = {bands(b).name, kinds{k}}; %#ok<AGROW>
        SR(end+1,:) = [mean(abs(u-0.5))+0.5, mean(a), min(a), sum(squeeze(PV(b,k,:))<0.05), mean(l)]; %#ok<AGROW>
    end
end
TS = [cell2table(sr,'VariableNames',{'band','feature'}), ...
      array2table(SR,'VariableNames',{'mean_AUC_dirfree','mean_acc_S45','min_acc_S45','n_subj_p05','mean_acc_LOSO'})];
TS = sortrows(TS, 'mean_acc_S45', 'descend');
writetable(TS, fullfile(outdir,'differentiator_summary.csv'));

pf('\nSingle-trial left/right separation, 0.5-3.5 s after cue, mean over 9 subjects\n');
pf('(acc_S45 = threshold from sessions 1-3, tested on 4-5; LOSO = threshold from the other 8 subjects)\n\n');
pf('%-12s %-17s %8s %9s %9s %7s %9s\n','band','feature','AUC*','acc_S45','min_S45','p<.05','acc_LOSO');
for r = 1:height(TS)
    pf('%-12s %-17s %8.3f %9.3f %9.3f %5d/9 %9.3f\n', TS.band{r}, TS.feature{r}, TS.mean_AUC_dirfree(r), ...
        TS.mean_acc_S45(r), TS.min_acc_S45(r), TS.n_subj_p05(r), TS.mean_acc_LOSO(r));
end
pf('* AUC shown direction-free (0.5 = no separation, 1 = perfect)\n');

%% --------------------------------------------- differentiator figures
% 1) accuracy per feature: bars = mean over subjects, dots = subjects
lbl = {}; M = []; D = [];
for b = 1:nB
    for k = 1:nK
        lbl{end+1} = sprintf('%s, %s', kinds{k}, bands(b).name); %#ok<AGROW>
        M(end+1) = mean(squeeze(ACC(b,k,:))); D(:,end+1) = squeeze(ACC(b,k,:)); %#ok<AGROW>
    end
end
[~, ord] = sort(M, 'descend');
fg = figure('Color','w','Position',[60 60 1150 560],'Visible','off');
bar(100*M(ord), 'FaceColor',[.55 .65 .8], 'EdgeColor','none'); hold on;
for j = 1:numel(ord)
    plot(j + 0.18*(rand(nSub,1)-0.5), 100*D(:,ord(j)), 'k.', 'MarkerSize',8);
end
yline(50, 'k--', 'chance', 'LabelHorizontalAlignment','left');
set(gca,'XTick',1:numel(ord),'XTickLabel',lbl(ord),'XTickLabelRotation',45,'FontSize',9);
ylabel('accuracy on sessions 4-5 (%)'); ylim([30 100]); grid on; box on;
title('Which single number separates left vs right hand imagery? (bar = mean of 9 subjects, dot = one subject)', 'FontSize', 11);
exportgraphics(fg, fullfile(outdir,'differentiator_2b.png'), 'Resolution',150);
close(fg);

% 2) the best feature: left vs right histograms, every subject
[bB, bK] = find(squeeze(mean(ACC,3)) == max(mean(ACC,3),[],'all'), 1);
fg = figure('Color','w','Position',[60 60 1200 820],'Visible','off');
tl = tiledlayout(fg, 3, 3, 'TileSpacing','compact','Padding','compact');
for si = 1:nSub
    ax = nexttile(tl); x = F{bB,bK,si}; y = S(si).y;
    ed = linspace(prctile(x,1), prctile(x,99), 30);
    histogram(ax, x(y==1), ed, 'FaceColor',[0 0 1], 'FaceAlpha',0.45, 'EdgeColor','none'); hold(ax,'on');
    histogram(ax, x(y==2), ed, 'FaceColor',[1 0 0], 'FaceAlpha',0.45, 'EdgeColor','none');
    title(ax, sprintf('%s   acc %.0f %%  (AUC %.2f)', names{si}, 100*ACC(bB,bK,si), AUC(bB,bK,si)), 'FontSize', 10);
    grid(ax,'on'); box(ax,'on');
    if si == 1, legend(ax, {'left hand','right hand'}, 'Location','northwest','Box','off'); end
end
xlabel(tl, sprintf('%s, %s Hz  (single trials, 0.5-3.5 s after cue)', kinds{bK}, bands(bB).name));
ylabel(tl, 'number of trials');
title(tl, sprintf('Best single feature: %s (%s)', kinds{bK}, bands(bB).name), 'FontSize', 12);
exportgraphics(fg, fullfile(outdir,'differentiator_best.png'), 'Resolution',150);
close(fg);

pf('\nBest single feature by mean accuracy on sessions 4-5: %s, %s\n', kinds{bK}, bands(bB).name);
pf('done in %.1f s\n', toc);
fid = fopen(done,'w'); fprintf(fid,'%s\n',datestr(now)); fclose(fid);
end

%% ===================================================== helpers
function psdPanel(ax, f, pb, pi_, ttl, fs)
semilogy(ax, f, pb, '-', 'Color',[.45 .45 .45], 'LineWidth',1.4); hold(ax,'on');
semilogy(ax, f, pi_, '-', 'Color',[.85 .1 .1], 'LineWidth',1.4);
xline(ax, 8,  ':', 'Color',[.5 .5 .5], 'HandleVisibility','off');
xline(ax, 30, ':', 'Color',[.5 .5 .5], 'HandleVisibility','off');
xlim(ax, [f(1) f(end)]); grid(ax,'on'); box(ax,'on');
title(ax, ttl, 'FontSize', fs);
xlabel(ax, 'Frequency (Hz)', 'FontSize', fs); ylabel(ax, 'PSD (\muV^2/Hz)', 'FontSize', fs);
h = legend(ax, {'baseline','imagery'}, 'Location','southwest'); legend(ax,'boxoff'); set(h,'FontSize',8);
end

function a = aucRank(x, pos)
% area under the ROC curve via ranks (Mann-Whitney), ties averaged
r = tiedrank(x(:)); pos = pos(:);
n1 = sum(pos); n0 = sum(~pos);
a = (sum(r(pos)) - n1*(n1+1)/2) / (n1*n0);
end

function yhat = thrClassify(xtr, ytr, xte)
% one threshold half-way between the class means; side learned on train
m1 = mean(xtr(ytr==1)); m2 = mean(xtr(ytr==2));
thr = (m1+m2)/2; s = sign(m2-m1); if s == 0, s = 1; end
yhat = 1 + (s*(xte - thr) > 0);
end
