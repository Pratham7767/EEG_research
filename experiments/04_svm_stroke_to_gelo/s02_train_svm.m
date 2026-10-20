%% ========================================================================
%  s02_train_svm.m
%
%  Trains and evaluates the three SVMs, in two feature flavours and two
%  kernels, on the stroke dataset, then tests them on our own recordings.
%
%    SVM-A : mean, median, skewness, kurtosis of the energy series (8 feats)
%    SVM-B : those eight + log10(P_C3/P_C4)                        (9 feats)
%    SVM-C : log10(P_C3/P_C4) alone                                (1 feat)
%
%  Flavours: 'abs' = absolute energy (as specified)
%            'erd' = energy expressed as % change from the trial's own 1 s
%                    baseline, which cancels the recording gain
%            (skewness and kurtosis are affine-invariant, so they are the
%             same numbers in both flavours - only mean/median/ratio change)
%
%  Every number is reported next to the baseline it must beat.
%
%  Runs in chunks so no single call outlives the tool timeout. Set RUN_SETS
%  in the workspace before running, e.g.  RUN_SETS = 1:2;  then 3:4, 5:6.
%  Results accumulate in results_partial.mat. Omit RUN_SETS to do all six.
%
%  Requires features_train.csv and features_test.csv from s01.
%% ========================================================================
clc;
% A variable named rng in the workspace would shadow the rng() function and
% silently disable all seeding, making this script non-reproducible. This
% script deliberately does not call clear (so RUN_SETS survives), so guard.
if exist('rng','var'), clear rng; end
rng(42);

OUT = 'D:\trainsvm\experiments\04_svm_stroke_to_gelo';
Tr  = readtable(fullfile(OUT,'features_train.csv'));
Te  = readtable(fullfile(OUT,'features_test.csv'));

%% --------------------------- FEATURE SETS -------------------------------
abs8 = {'C3_mean','C3_median','C3_skew','C3_kurt','C4_mean','C4_median','C4_skew','C4_kurt'};
erd8 = {'E_C3_mean','E_C3_median','C3_skew','C3_kurt','E_C4_mean','E_C4_median','C4_skew','C4_kurt'};

FS = struct('name',{},'flavour',{},'vars',{});
FS(1) = struct('name','A','flavour','abs','vars',{abs8});
FS(2) = struct('name','B','flavour','abs','vars',{[abs8 {'logC3C4'}]});
FS(3) = struct('name','C','flavour','abs','vars',{{'logC3C4'}});
FS(4) = struct('name','A','flavour','erd','vars',{erd8});
FS(5) = struct('name','B','flavour','erd','vars',{[erd8 {'E_logC3C4'}]});
FS(6) = struct('name','C','flavour','erd','vars',{{'E_logC3C4'}});

KERNELS = {'linear','rbf'};

if ~exist('RUN_SETS','var') || isempty(RUN_SETS), RUN_SETS = 1:numel(FS); end

fprintf('=== s02_train_svm | feature sets %s ===\n', mat2str(RUN_SETS));
fprintf('train %d epochs (%d L / %d R) from %d subjects\n', height(Tr), ...
    sum(Tr.label==1), sum(Tr.label==2), numel(unique(Tr.group)));
fprintf('test  %d epochs (%d L / %d R) from %d session files\n\n', height(Te), ...
    sum(Te.label==1), sum(Te.label==2), numel(unique(Te.group)));

%% ---------------------- CV PARTITION OVER SUBJECTS ----------------------
subs   = unique(Tr.group);
nSub   = numel(subs);
subIdx = zeros(height(Tr),1);
for s = 1:nSub, subIdx(strcmp(Tr.group, subs{s})) = s; end

permS = randperm(nSub);
foldOfSub = zeros(nSub,1);
for i = 1:nSub, foldOfSub(permS(i)) = mod(i-1,5)+1; end
gridFold = foldOfSub(subIdx);

yTr = Tr.label; yTe = Te.label;

%% ------------------- load whatever is already done ----------------------
pf = fullfile(OUT,'results_partial.mat');
if isfile(pf), L = load(pf); res = L.res; CM = L.CM; else, res = {}; CM = struct(); end

%% ------------------------------- RUN ------------------------------------
% C capped at 10: on features this close to noise, C=100 only memorises the
% training set and costs 8x the compute for a worse honest estimate.
Cs = [0.01 0.1 1 10];

for f = RUN_SETS
  for k = 1:numel(KERNELS)
    kern = KERNELS{k};
    tag  = sprintf('SVM-%s_%s_%s', FS(f).name, FS(f).flavour, kern);
    tw   = tic;
    rng(1234);   % per-config seed: results never depend on chunk order

    Xtr = Tr{:, FS(f).vars};
    Xte = Te{:, FS(f).vars};

    % standardisation fitted on TRAIN ONLY, applied unchanged to TEST
    mu = mean(Xtr,1); sg = std(Xtr,0,1); sg(sg==0) = 1;
    Ztr = (Xtr - mu) ./ sg;
    Zte = (Xte - mu) ./ sg;

    if strcmp(kern,'rbf'), Ks = [0.5 1 2 4] * sqrt(size(Ztr,2)); else, Ks = NaN; end

    % ---------- hyperparameters, chosen on subject-grouped CV -------------
    best = struct('score',-Inf,'C',1,'K',NaN);
    for c = Cs
      for kk = Ks
        acc = zeros(5,1);
        for fo = 1:5
          trM = gridFold ~= fo; teM = ~trM;
          mdl = fitSVM(Ztr(trM,:), yTr(trM), kern, c, kk);
          acc(fo) = balAcc(yTr(teM), predict(mdl, Ztr(teM,:)));
        end
        if mean(acc) > best.score
          best.score = mean(acc); best.C = c; best.K = kk;
        end
      end
    end

    % ---------- leave-one-SUBJECT-out on the training data ----------------
    predLoso = zeros(height(Tr),1);
    for s = 1:nSub
      teM = subIdx == s; trM = ~teM;
      mdl = fitSVM(Ztr(trM,:), yTr(trM), kern, best.C, best.K);
      predLoso(teM) = predict(mdl, Ztr(teM,:));
    end
    losoAcc = mean(predLoso == yTr);
    losoBal = balAcc(yTr, predLoso);

    % ---------- final model on ALL training data, applied to our data -----
    final  = fitSVM(Ztr, yTr, kern, best.C, best.K);
    predTe = predict(final, Zte);
    [teAcc, teBal, teSens, teSpec, teKappa, cm] = evalAll(yTe, predTe);

    % ---------- 22 vs 22 balanced subsample of the test set ---------------
    iL = find(yTe==1); iR = find(yTe==2); nB = min(numel(iL), numel(iR));
    subAcc = zeros(1000,1); subBal = zeros(1000,1);
    for r = 1:1000
      pick = [iL(randperm(numel(iL),nB)); iR(randperm(numel(iR),nB))];
      subAcc(r) = mean(predTe(pick) == yTe(pick));
      subBal(r) = balAcc(yTe(pick), predTe(pick));
    end

    % ---------- permutation test on the test balanced accuracy ------------
    permBal = zeros(1000,1);
    for r = 1:1000
      permBal(r) = balAcc(yTe(randperm(numel(yTe))), predTe);
    end
    pPerm = (1 + sum(permBal >= teBal)) / (1 + numel(permBal));

    CM.(strrep(tag,'-','_')) = cm;
    res{end+1,1} = { FS(f).name, FS(f).flavour, kern, numel(FS(f).vars), ...
        best.C, best.K, losoAcc, losoBal, teAcc, teBal, teSens, teSpec, ...
        teKappa, mean(subAcc), mean(subBal), pPerm, ...
        max(mean(yTe==1),mean(yTe==2)), mean(predTe==2) }; %#ok<SAGROW>

    fprintf('%-22s | LOSO bal %.3f | TEST acc %.3f bal %.3f | 22v22 bal %.3f | p=%.3f | says RIGHT %3.0f%% | %.0f s\n', ...
        tag, losoBal, teAcc, teBal, mean(subBal), pPerm, 100*mean(predTe==2), toc(tw));
  end
end

save(pf, 'res', 'CM');
fprintf('\n%d of 12 configurations done, saved to results_partial.mat\n', numel(res));

%% ---- assemble the summary table once all 12 configurations exist -------
% s03 reads results_summary.csv, so it is written here rather than by hand.
if numel(res) >= 12
    R = cell2table(vertcat(res{:}), 'VariableNames', { ...
        'model','flavour','kernel','nFeatures','BoxConstraint','KernelScale', ...
        'LOSO_accuracy','LOSO_balanced_accuracy', ...
        'test_accuracy','test_balanced_accuracy','test_sensitivity_left', ...
        'test_specificity_right','test_kappa','test_acc_22v22','test_bal_22v22', ...
        'test_permutation_p','test_majority_baseline','fraction_predicted_right'});
    writetable(R, fullfile(OUT,'results_summary.csv'));
    save(fullfile(OUT,'confusion_matrices.mat'), '-struct', 'CM');
    fprintf('Wrote results_summary.csv (%d rows) and confusion_matrices.mat\n', height(R));
    fprintf('Chance = 0.500 balanced. Majority-class baseline on the test set = %.3f\n', ...
        max(mean(yTe==1), mean(yTe==2)));
else
    fprintf('Only %d of 12 configurations done - run the remaining RUN_SETS before s03.\n', numel(res));
end


%% ========================== LOCAL FUNCTIONS =============================

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
% Mean of per-class recall. Immune to class imbalance, unlike plain accuracy.
    r1 = mean(p(y==1) == 1); r2 = mean(p(y==2) == 2);
    if isnan(r1), r1 = 0; end
    if isnan(r2), r2 = 0; end
    b = (r1 + r2) / 2;
end


function [acc, bal, sens, spec, kappa, cm] = evalAll(y, p)
    cm = zeros(2,2);                        % rows = actual, cols = predicted
    for a = 1:2
        for b = 1:2
            cm(a,b) = sum(y==a & p==b);
        end
    end
    acc  = sum(diag(cm)) / sum(cm(:));
    bal  = balAcc(y, p);
    sens = cm(1,1) / max(sum(cm(1,:)),1);    % recall on LEFT
    spec = cm(2,2) / max(sum(cm(2,:)),1);    % recall on RIGHT
    pe   = sum(sum(cm,1) .* sum(cm,2)') / sum(cm(:))^2;
    kappa = (acc - pe) / (1 - pe);
end
