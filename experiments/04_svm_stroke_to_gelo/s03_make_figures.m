%% ========================================================================
%  s03_make_figures.m
%
%  Figures for the three-SVM experiment. All written to
%  D:\trainsvm\experiments\04_svm_stroke_to_gelo\figures
%
%    fig1_psd_c3c4.png        class-averaged C3/C4 PSD, train and test
%    fig2_ratio_dist.png      distribution of the C3/C4 ratio by class
%    fig3_domain_shift.png    train vs test feature distributions
%    fig4_confusions.png      all 12 confusion matrices
%    fig5_per_subject.png     per-subject laterality across the 50 subjects
%% ========================================================================
clear; clc;

OUT = 'D:\trainsvm\experiments\04_svm_stroke_to_gelo';
FIG = fullfile(OUT,'figures');
if ~exist(FIG,'dir'), mkdir(FIG); end

Tr  = readtable(fullfile(OUT,'features_train.csv'));
Te  = readtable(fullfile(OUT,'features_test.csv'));
P   = load(fullfile(OUT,'psd_curves.mat'));
R   = readtable(fullfile(OUT,'results_summary.csv'));
CM  = load(fullfile(OUT,'confusion_matrices.mat'));

%% ---------------- FIG 1: PSD at C3 and C4, by class ---------------------
f = figure('Color','w','Position',[80 60 900 640]);
sel = P.train.f >= 4 & P.train.f <= 40;
ttl = {'STROKE (train) - left hand','STROKE (train) - right hand', ...
       'OWN (test) - left hand','OWN (test) - right hand'};
src = {P.train, P.train, P.test, P.test};
cls = [1 2 1 2];
ax  = gobjects(1,4);
for i = 1:4
    ax(i) = subplot(2,2,i);
    S = src{i};
    plot(S.f(sel), 10*log10(S.mean(sel,1,cls(i))), 'r-','LineWidth',1.4); hold on;
    plot(S.f(sel), 10*log10(S.mean(sel,2,cls(i))), 'b-','LineWidth',1.4);
    xline(8,'Color',[.7 .7 .7]); xline(13,'Color',[.85 .85 .85]); xline(30,'Color',[.7 .7 .7]);
    grid on; xlim([4 40]); xticks(5:5:40);
    xlabel('Frequency (Hz)'); ylabel('PSD (dB)');
    title(ttl{i},'FontSize',10);
    legend({'C3','C4'},'Location','northeast','Box','off','FontSize',8);
end
% Shared y-axis WITHIN each row. The two datasets are in different recording
% units - the stroke panels span 1.4 dB, ours span 30 dB - so one global axis
% would squash the stroke curves into about 4% of the height and hide the
% C3-vs-C4 difference the figure exists to show. Row-wise sharing keeps
% left-vs-right directly comparable, which is the comparison that matters.
for r = 0:1
    ii = [1 2] + 2*r;
    yl = [inf -inf];
    for k = ii
        y = ylim(ax(k)); yl = [min(yl(1),y(1)), max(yl(2),y(2))];
    end
    for k = ii, ylim(ax(k), yl); end
end
sgtitle('Class-averaged power spectra at C3 and C4  (8-30 Hz band marked)','FontSize',12);
exportgraphics(f, fullfile(FIG,'fig1_psd_c3c4.png'), 'Resolution', 160);

%% -------- FIG 1b: same spectra, each normalised to its own mean ---------
% Each curve is expressed relative to its own 4-40 Hz average, which removes
% the per-device gain so all four panels can share ONE y-axis honestly.
f = figure('Color','w','Position',[80 60 900 640]);
axn = gobjects(1,4);
for i = 1:4
    axn(i) = subplot(2,2,i);
    S = src{i};
    c3 = 10*log10(S.mean(sel,1,cls(i))); c3 = c3 - mean(c3);
    c4 = 10*log10(S.mean(sel,2,cls(i))); c4 = c4 - mean(c4);
    plot(S.f(sel), c3, 'r-','LineWidth',1.4); hold on;
    plot(S.f(sel), c4, 'b-','LineWidth',1.4);
    xline(8,'Color',[.7 .7 .7]); xline(13,'Color',[.85 .85 .85]); xline(30,'Color',[.7 .7 .7]);
    yline(0,'Color',[.85 .85 .85]);
    grid on; xlim([4 40]); xticks(5:5:40);
    xlabel('Frequency (Hz)'); ylabel('PSD re own mean (dB)');
    title(ttl{i},'FontSize',10);
    legend({'C3','C4'},'Location','northeast','Box','off','FontSize',8);
end
yl = [inf -inf];
for k = 1:4, y = ylim(axn(k)); yl = [min(yl(1),y(1)), max(yl(2),y(2))]; end
for k = 1:4, ylim(axn(k), yl); end
sgtitle('Same spectra, each normalised to its own mean - one shared y-axis','FontSize',12);
exportgraphics(f, fullfile(FIG,'fig1b_psd_normalised.png'), 'Resolution', 160);

%% ---------------- FIG 2: the C3/C4 ratio, the whole of SVM-C ------------
f = figure('Color','w','Position',[80 60 900 380]);

subplot(1,2,1);
histogram(Tr.logC3C4(Tr.label==1), -0.6:0.03:0.6, 'FaceColor','r','FaceAlpha',.45); hold on;
histogram(Tr.logC3C4(Tr.label==2), -0.6:0.03:0.6, 'FaceColor','b','FaceAlpha',.45);
xline(median(Tr.logC3C4(Tr.label==1)),'r-','LineWidth',1.5);
xline(median(Tr.logC3C4(Tr.label==2)),'b-','LineWidth',1.5);
xlabel('log_{10}(P_{C3}/P_{C4})'); ylabel('epochs'); grid on;
title(sprintf('STROKE train (n=%d)\nmedians differ by %.4f', height(Tr), ...
    median(Tr.logC3C4(Tr.label==1))-median(Tr.logC3C4(Tr.label==2))),'FontSize',10);
legend({'left hand','right hand'},'Box','off');

subplot(1,2,2);
histogram(Te.logC3C4(Te.label==1), -0.6:0.06:0.6, 'FaceColor','r','FaceAlpha',.45); hold on;
histogram(Te.logC3C4(Te.label==2), -0.6:0.06:0.6, 'FaceColor','b','FaceAlpha',.45);
xline(median(Te.logC3C4(Te.label==1)),'r-','LineWidth',1.5);
xline(median(Te.logC3C4(Te.label==2)),'b-','LineWidth',1.5);
xlabel('log_{10}(P_{C3}/P_{C4})'); ylabel('epochs'); grid on;
title(sprintf('OWN test (n=%d)\nmedians differ by %.4f', height(Te), ...
    median(Te.logC3C4(Te.label==1))-median(Te.logC3C4(Te.label==2))),'FontSize',10);
legend({'left hand','right hand'},'Box','off');

sgtitle('The single feature SVM-C is built on. Overlap = no information.','FontSize',12);
exportgraphics(f, fullfile(FIG,'fig2_ratio_dist.png'), 'Resolution', 160);

%% ---------------- FIG 3: domain shift, train vs test --------------------
vars = {'C3_mean','C4_mean','C3_kurt','C4_kurt','logC3C4','E_C3_mean'};
lbls = {'C3 mean energy','C4 mean energy','C3 kurtosis','C4 kurtosis', ...
        'log(P_{C3}/P_{C4})','C3 ERD %'};
f = figure('Color','w','Position',[80 60 980 560]);
for i = 1:numel(vars)
    subplot(2,3,i);
    a = Tr.(vars{i}); b = Te.(vars{i});
    lo = min([prctile(a,1) prctile(b,1)]); hi = max([prctile(a,99) prctile(b,99)]);
    ed = linspace(lo,hi,40);
    histogram(a, ed, 'Normalization','pdf','FaceColor',[.2 .4 .8],'FaceAlpha',.5); hold on;
    histogram(b, ed, 'Normalization','pdf','FaceColor',[.9 .5 .1],'FaceAlpha',.5);
    grid on; title(lbls{i},'FontSize',10); xlabel(''); ylabel('density');
    if i==1, legend({'stroke (train)','own (test)'},'Box','off','FontSize',8); end
end
sgtitle('Domain shift: where the training and test features actually sit','FontSize',12);
exportgraphics(f, fullfile(FIG,'fig3_domain_shift.png'), 'Resolution', 160);

%% ---------------- FIG 4: every confusion matrix -------------------------
% Sequential encoding (magnitude): ONE hue, light -> dark, from the validated
% blue ramp. Cells are row-normalised, so each cell reads as that class's
% recall and the two rows are comparable despite 22 vs 50 epochs.
%
% The previous version set the label colour from count/max(count) while the
% cell colour came from count/rowSum - two different quantities - so dark
% labels landed on dark cells and vanished (SVM-C abs: the 50 was black on
% black). Label colour is now derived from the LUMINANCE OF THE CELL IT SITS
% ON, so contrast is correct by construction.
ramp = [205 226 251; 183 211 246; 158 197 244; 134 182 239; 109 167 236; ...
        85 152 231; 57 135 229; 42 120 214; 37 106 191; 28  92 171; ...
        24  79 149; 16  66 129; 13  54 107] / 255;
cmap = interp1(linspace(0,1,size(ramp,1)), ramp, linspace(0,1,256));

fn = fieldnames(CM);
f = figure('Color','w','Position',[40 30 1180 760]);
for i = 1:numel(fn)
    axc = subplot(3,4,i);
    c   = CM.(fn{i});
    prop = c ./ sum(c,2);                      % row-normalised = per-class recall
    imagesc(prop); clim([0 1]); colormap(axc, cmap);
    for a = 1:2
        for b = 1:2
            rgb = interp1(linspace(0,1,256), cmap, max(min(prop(a,b),1),0));
            lin = rgb; lin(lin<=0.03928) = lin(lin<=0.03928)/12.92;
            lin(lin>0.03928) = ((lin(lin>0.03928)+0.055)/1.055).^2.4;
            L = 0.2126*lin(1) + 0.7152*lin(2) + 0.0722*lin(3);
            % pick whichever ink actually contrasts more, rather than a fixed
            % luminance threshold - a threshold leaves mid-ramp cells below AA.
            crW = (1.0 + 0.05) / (L + 0.05);          % white label
            crD = (L + 0.05) / (0.0033 + 0.05);       % near-black label
            if crW >= crD, tc = [1 1 1]; else, tc = [0.043 0.043 0.043]; end
            text(b, a-0.12, sprintf('%d', c(a,b)), 'HorizontalAlignment','center', ...
                'Color', tc, 'FontWeight','bold', 'FontSize', 12);
            text(b, a+0.18, sprintf('%.0f%%', 100*prop(a,b)), 'HorizontalAlignment','center', ...
                'Color', tc, 'FontSize', 8);
        end
    end
    set(axc,'XTick',1:2,'XTickLabel',{'L','R'},'YTick',1:2,'YTickLabel',{'L','R'}, ...
        'FontSize',9,'TickLength',[0 0],'XColor',[.45 .45 .45],'YColor',[.45 .45 .45]);
    xlabel('predicted','FontSize',8); ylabel('actual','FontSize',8);
    nm = strrep(strrep(fn{i},'SVM_','SVM-'),'_',' ');
    title(nm,'FontSize',9,'FontWeight','normal');
    axis square;
end
cb = colorbar('Position',[0.93 0.12 0.014 0.76]);
cb.Label.String = 'share of that actual class (recall)';
cb.Label.FontSize = 9; cb.Ticks = 0:0.25:1;
cb.TickLabels = {'0','25%','50%','75%','100%'};
sgtitle({'Confusion matrices on our own 72 epochs (22 left, 50 right)', ...
    'cell = count and row %; a full dark right-hand column means the model only ever says RIGHT'}, ...
    'FontSize',11);
exportgraphics(f, fullfile(FIG,'fig4_confusions.png'), 'Resolution', 160);

%% ---------------- FIG 5: per-subject laterality -------------------------
subs = unique(Tr.group); d = nan(numel(subs),1); a = nan(numel(subs),1);
for s = 1:numel(subs)
    m = strcmp(Tr.group, subs{s});
    d(s) = median(Tr.logC3C4(m & Tr.label==1)) - median(Tr.logC3C4(m & Tr.label==2));
    [~,~,~,a(s)] = perfcurve(Tr.label(m), Tr.logC3C4(m), 2);
end
[ds, ord] = sort(d);

f = figure('Color','w','Position',[80 60 940 420]);
subplot(1,2,1);
bar(ds, 'FaceColor',[.3 .5 .8]); hold on; yline(0,'k');
xlabel('subject (sorted)'); ylabel('median log(C3/C4): left - right');
title(sprintf('Per-subject laterality\n%d of 50 positive (expected: all)', sum(d>0)),'FontSize',10);
grid on;

subplot(1,2,2);
histogram(a, 0.2:0.05:0.8, 'FaceColor',[.8 .4 .2]); hold on;
xline(0.5,'k-','LineWidth',1.5);
xlabel('within-subject AUC of log(C3/C4)'); ylabel('subjects');
title(sprintf('Within-subject AUC\nmedian %.3f, chance = 0.500', median(a)),'FontSize',10);
grid on;
sgtitle('Is the contralateral effect present in the training data at all?','FontSize',12);
exportgraphics(f, fullfile(FIG,'fig5_per_subject.png'), 'Resolution', 160);

%% ---------------- export the per-subject numbers ------------------------
T = table(subs, d, a, 'VariableNames', {'subject','laterality_left_minus_right','within_subject_AUC'});
writetable(T, fullfile(OUT,'per_subject_laterality.csv'));

fprintf('Wrote 5 figures to %s\n', FIG);
fprintf('Wrote per_subject_laterality.csv\n');
close all;
