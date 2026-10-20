%% ========================================================================
%  s04_round2.m  -  ROUND 2 of the Experiment_svm study
%
%  Follows up the four things round 1 named as the most promising steps:
%    4A  per-subject models      (the paper's own design; their CSP+LDA = 0.5557)
%    4B  models split by hemiplegic side
%    4C  sign-corrected pooling (flip the C3/C4 ratio for one paralysis group)
%    4D  alpha / beta split instead of a single 8-30 Hz ratio
%
%  Also validates the feature extraction two ways:
%    (i)  against the paper's own published per-subject C3>C4 list
%    (ii) against an independent implementation (ERD_ERS_summary.csv)
%
%  Requires features_train.csv / features_test.csv from s01.
%  Writes results_round2.csv and figures/fig6_round2.png
%% ========================================================================
clear; clc;

OUT = 'D:\trainsvm\experiments\04_svm_stroke_to_gelo';
Tr  = readtable(fullfile(OUT,'features_train.csv'));
Te  = readtable(fullfile(OUT,'features_test.csv'));
P   = readtable('D:\trainsvm\data\stroke_liu2024\participants.tsv', ...
        'FileType','text','Delimiter','\t','TextType','string');

% ---- attach hemiplegic side to every training epoch ---------------------
side = strings(height(Tr),1);
for i = 1:height(P)
    side(strcmp(Tr.group, char(P.Participant_ID(i)))) = P.ParalysisSide(i);
end
Tr.side = side;
subs   = unique(Tr.group);
nSub   = numel(subs);
subIdx = zeros(height(Tr),1);
for s = 1:nSub, subIdx(strcmp(Tr.group, subs{s})) = s; end
subSide = strings(nSub,1);
for s = 1:nSub, subSide(s) = Tr.side(find(subIdx==s,1)); end
isLeftPar  = strcmp(subSide,'left');
isRightPar = strcmp(subSide,'right');
fprintf('subjects: %d left-paralysis, %d right-paralysis\n', sum(isLeftPar), sum(isRightPar));

% ---- feature sets, now including the alpha/beta split -------------------
abs8 = {'C3_mean','C3_median','C3_skew','C3_kurt','C4_mean','C4_median','C4_skew','C4_kurt'};
erd8 = {'E_C3_mean','E_C3_median','C3_skew','C3_kurt','E_C4_mean','E_C4_median','C4_skew','C4_kurt'};
ab2  = {'logC3C4_alpha','logC3C4_beta'};
FSname = {'A','B','C','A','B','C','Cab','Bab'};
FSflav = {'abs','abs','abs','erd','erd','erd','abs','abs'};
FSvars = {abs8, [abs8 {'logC3C4'}], {'logC3C4'}, erd8, [erd8 {'E_logC3C4'}], {'E_logC3C4'}, ab2, [abs8 ab2]};
KERN   = {'linear','rbf'};
rows = {};

%% ---- VALIDATION 1: against the paper's own per-subject C3>C4 list ------
paperC3hi = [1 2 3 4 5 8 9 10 11 13 15 18 20 25 28 29 32 36 38 40 44 47 49];
ours = false(nSub,1);
for s = 1:nSub
    m = subIdx==s & Tr.label==1;              % LEFT-hand trials
    ours(s) = median(Tr.logC3C4(m)) > 0;      % C3 power > C4 power
end
pap = false(nSub,1); pap(paperC3hi) = true;
fprintf('\nvalidation vs paper list: ours %d/50, paper %d/50, agreement %d/50 (%.0f%%)\n', ...
    sum(ours), numel(paperC3hi), sum(ours==pap), 100*sum(ours==pap)/nSub);

%% ---- VALIDATION 2: against an independent implementation ---------------
E = readtable('D:\trainsvm\data\stroke_liu2024\ERD_ERS\ERD_ERS_summary.csv');
mineR = nan(nSub,1);
for s = 1:nSub, mineR(s) = median(Tr.logC3C4(subIdx==s & Tr.label==1)); end
indepR = log10(E.pow_L_C3 ./ E.pow_L_C4);
fprintf('vs independent ERD_ERS_summary: Pearson r = %.3f, sign agreement %d/50\n', ...
    corr(mineR,indepR,'rows','complete'), sum((mineR>0)==(indepR>0)));

%% ======================= 4A  PER-SUBJECT MODELS =========================
fprintf('\n--- 4A: per-subject models, 10-fold CV within each subject ---\n');
for f = 1:numel(FSvars)
  for k = 1:numel(KERN)
    rng(1234); accS = nan(nSub,1);
    for s = 1:nSub
      m = subIdx==s; X = Tr{m,FSvars{f}}; y = Tr.label(m);
      mu=mean(X,1); sg=std(X,0,1); sg(sg==0)=1; Z=(X-mu)./sg;
      cv = cvpartition(y,'KFold',10); pr = zeros(numel(y),1);
      for fo = 1:10
        tr = training(cv,fo); te = test(cv,fo);
        mdl = fitSVM(Z(tr,:), y(tr), KERN{k}, 1, sqrt(size(Z,2)));
        pr(te) = predict(mdl, Z(te,:));
      end
      accS(s) = balAcc(y, pr);
    end
    [~,pv] = ttest(accS, 0.5);
    rows{end+1,1} = {'4A_per_subject', FSname{f}, FSflav{f}, KERN{k}, '', ...
        numel(FSvars{f}), mean(accS), sum(accS>0.5), pv, NaN};
    fprintf('  %-4s %-4s %-7s | mean bal %.3f (SD %.3f) | subs>0.5: %2d/50 | p=%.4f\n', ...
        FSname{f}, FSflav{f}, KERN{k}, mean(accS), std(accS), sum(accS>0.5), pv);
  end
end

%% ==================== 4B  SPLIT BY HEMIPLEGIC SIDE ======================
fprintf('\n--- 4B: split by hemiplegic side (LOSO within group) ---\n');
latS = nan(nSub,1);
for s = 1:nSub
    m = subIdx==s;
    latS(s) = median(Tr.logC3C4(m & Tr.label==1)) - median(Tr.logC3C4(m & Tr.label==2));
end
[~,pg] = ttest2(latS(isLeftPar), latS(isRightPar));
fprintf('  laterality by side: left-par mean %+.4f, right-par mean %+.4f, t-test p=%.4f\n', ...
    mean(latS(isLeftPar)), mean(latS(isRightPar)), pg);
grpNames = {'left','right'};
for f = 1:numel(FSvars)
  for k = 1:numel(KERN)
    for g = 1:2
      rng(1234);
      gm = strcmp(Tr.side, grpNames{g}); gsub = find(strcmp(subSide, grpNames{g}));
      X = Tr{gm,FSvars{f}}; y = Tr.label(gm); si = subIdx(gm);
      mu=mean(X,1); sg=std(X,0,1); sg(sg==0)=1; Z=(X-mu)./sg;
      pr = zeros(numel(y),1);
      for s = gsub'
        te = si==s; tr = ~te;
        mdl = fitSVM(Z(tr,:), y(tr), KERN{k}, 1, sqrt(size(Z,2)));
        pr(te) = predict(mdl, Z(te,:));
      end
      lb = balAcc(y, pr);
      mdlF = fitSVM(Z, y, KERN{k}, 1, sqrt(size(Z,2)));
      Zte = (Te{:,FSvars{f}} - mu) ./ sg;
      tb  = balAcc(Te.label, predict(mdlF, Zte));
      rows{end+1,1} = {'4B_hemiplegia_split', FSname{f}, FSflav{f}, KERN{k}, grpNames{g}, ...
          numel(FSvars{f}), lb, numel(gsub), NaN, tb};
      fprintf('  %-4s %-4s %-7s %-6s | LOSO bal %.3f (n=%d) | our-data bal %.3f\n', ...
          FSname{f}, FSflav{f}, KERN{k}, grpNames{g}, lb, numel(gsub), tb);
    end
  end
end

%% ==================== 4C  SIGN-CORRECTED POOLING ========================
fprintf('\n--- 4C: sign-corrected pooling (stroke data only) ---\n');
Tr2 = Tr; flip = strcmp(Tr.side,'right');
for v = {'logC3C4','E_logC3C4','logC3C4_alpha','logC3C4_beta'}
    Tr2.(v{1})(flip) = -Tr2.(v{1})(flip);
end
for f = 1:numel(FSvars)
  for k = 1:numel(KERN)
    rng(1234);
    X = Tr2{:,FSvars{f}}; y = Tr2.label;
    mu=mean(X,1); sg=std(X,0,1); sg(sg==0)=1; Z=(X-mu)./sg;
    pr = zeros(numel(y),1);
    for s = 1:nSub
      te = subIdx==s; tr = ~te;
      mdl = fitSVM(Z(tr,:), y(tr), KERN{k}, 1, sqrt(size(Z,2)));
      pr(te) = predict(mdl, Z(te,:));
    end
    lb = balAcc(y, pr);
    rows{end+1,1} = {'4C_sign_corrected', FSname{f}, FSflav{f}, KERN{k}, '', ...
        numel(FSvars{f}), lb, nSub, NaN, NaN};
    fprintf('  %-4s %-4s %-7s | LOSO bal %.3f\n', FSname{f}, FSflav{f}, KERN{k}, lb);
  end
end

%% ======================= 4D  ALPHA / BETA SPLIT =========================
fprintf('\n--- 4D: alpha/beta split, pooled, round-1 protocol ---\n');
for v = {'logC3C4','logC3C4_alpha','logC3C4_beta','E_logC3C4'}
    [~,~,~,a1] = perfcurve(Tr.label, Tr.(v{1}), 2);
    [~,~,~,a2] = perfcurve(Te.label, Te.(v{1}), 2);
    fprintf('  %-16s train AUC %.3f | our-data AUC %.3f\n', v{1}, a1, a2);
end
for f = [7 8 3 2]
  for k = 1:numel(KERN)
    rng(1234);
    X = Tr{:,FSvars{f}}; y = Tr.label;
    mu=mean(X,1); sg=std(X,0,1); sg(sg==0)=1; Z=(X-mu)./sg;
    pr = zeros(numel(y),1);
    for s = 1:nSub
      te = subIdx==s; tr = ~te;
      mdl = fitSVM(Z(tr,:), y(tr), KERN{k}, 1, sqrt(size(Z,2)));
      pr(te) = predict(mdl, Z(te,:));
    end
    lb = balAcc(y, pr);
    mdlF = fitSVM(Z, y, KERN{k}, 1, sqrt(size(Z,2)));
    Zte = (Te{:,FSvars{f}} - mu) ./ sg;
    tb  = balAcc(Te.label, predict(mdlF, Zte));
    rows{end+1,1} = {'4D_alpha_beta', FSname{f}, FSflav{f}, KERN{k}, '', ...
        numel(FSvars{f}), lb, nSub, NaN, tb};
    fprintf('  %-4s %-4s %-7s | LOSO bal %.3f | our-data bal %.3f\n', ...
        FSname{f}, FSflav{f}, KERN{k}, lb, tb);
  end
end

%% ---- the session confound in our own data ------------------------------
files = unique(Te.group); fm = nan(numel(files),1); fl = nan(numel(files),1);
for i = 1:numel(files)
    m = strcmp(Te.group, files{i});
    fm(i) = median(Te.logC3C4_beta(m)); fl(i) = Te.label(find(m,1));
end
[~,~,~,aucFile] = perfcurve(fl, fm, 2);
[~,ptFile] = ttest2(fm(fl==1), fm(fl==2));
fprintf('\nour data, beta ratio at FILE level: AUC %.3f, p=%.4f (n=%d files)\n', aucFile, ptFile, numel(files));
fprintf('  class is confounded with session here, so this is NOT evidence of laterality.\n');

T = cell2table(vertcat(rows{:}), 'VariableNames', {'experiment','model','flavour', ...
    'kernel','group','nFeatures','stroke_balanced_acc','n_subjects','p_value','our_data_balanced_acc'});
writetable(T, fullfile(OUT,'results_round2.csv'));
fprintf('\nwrote results_round2.csv (%d rows)\n', height(T));


%% ========================= LOCAL FUNCTIONS ==============================
function mdl = fitSVM(X, y, kern, C, K)
    if strcmp(kern,'rbf')
        mdl = fitcsvm(X, y, 'KernelFunction','rbf', 'BoxConstraint', C, ...
            'KernelScale', K, 'ClassNames', [1 2], 'IterationLimit', 2e5);
    else
        mdl = fitcsvm(X, y, 'KernelFunction','linear', 'BoxConstraint', C, ...
            'ClassNames', [1 2], 'IterationLimit', 2e5);
    end
end

function b = balAcc(y, p)
    r1 = mean(p(y==1) == 1); r2 = mean(p(y==2) == 2);
    if isnan(r1), r1 = 0; end
    if isnan(r2), r2 = 0; end
    b = (r1 + r2) / 2;
end
