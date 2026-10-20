%% SVM on ERD% features averaged over N trials - BCI Competition IV 2b
% Features (6 per sample): ERD% at C3, Cz, C4 in the mu (8-13 Hz) and beta (13-30 Hz) bands.
%   ERD% = (mean task power - mean baseline power) / mean baseline power * 100
%   baseline window : 2.0-1.0 s BEFORE the cue (before the warning beep), as in RUN_ERD_PSD_2b.m
%   task window     : 0.5-3.5 s AFTER the cue (same as every other model in this project)
% "Averaging N trials" = power is averaged over N trials of the SAME class first, then ERD% is
% computed (the textbook ERD order of operations). N = 1 is the ordinary single-trial classifier.
%
% Protocol (per subject, standard 2b): train on sessions 1-3, test on sessions 4-5.
% Groups of N are formed INSIDE the training set and INSIDE the test set separately, so no
% trial is ever shared between training and testing. Artifact-flagged trials are excluded.
%   training : 400 random N-trial groups per class (bootstrap of groups, trials unique within a group)
%   testing  : test trials of each class split into non-overlapping groups of N, repeated over
%              20 random splits; accuracy averaged.
% Classifiers: linear SVM and RBF SVM (standardised features, fitcsvm defaults, KernelScale 'auto').

clear; rng(0);
here = fileparts(mfilename('fullpath'));
root = fullfile(here, '..', 'subjectwise');
fs = 250; cue = 3;
baseIdx = round((cue-2.0)*fs)+1 : round((cue-1.0)*fs);
taskIdx = round((cue+0.5)*fs)+1 : round((cue+3.5)*fs);
bands = [8 13; 13 30]; bandNames = {'mu','beta'}; ch = {'C3','Cz','C4'};
Ns = [1 5 10]; nTrainGroups = 400; nRep = 20;
kern = {'linear','rbf'};

acc = nan(9, numel(Ns), numel(kern)); nTest = nan(9, numel(Ns));
for sub = 1:9
    [Ptr_b, Ptr_t, ytr] = bandpowers(root, sub, 'training',   bands, fs, baseIdx, taskIdx);
    [Pte_b, Pte_t, yte] = bandpowers(root, sub, 'evaluation', bands, fs, baseIdx, taskIdx);
    for in = 1:numel(Ns)
        N = Ns(in);
        % ---- training samples ----
        [Xtr, Ytr] = groupERD(Ptr_b, Ptr_t, ytr, N, nTrainGroups, 'random');
        mdl = cell(1,numel(kern));
        for k = 1:numel(kern)
            if strcmp(kern{k},'linear')
                mdl{k} = fitcsvm(Xtr, Ytr, 'KernelFunction','linear', 'Standardize',true);
            else
                mdl{k} = fitcsvm(Xtr, Ytr, 'KernelFunction','rbf', 'KernelScale','auto', 'Standardize',true);
            end
        end
        % ---- test samples, non-overlapping groups, repeated random splits ----
        a = zeros(nRep, numel(kern)); nt = 0;
        for r = 1:nRep
            [Xte, Yte] = groupERD(Pte_b, Pte_t, yte, N, 0, 'partition');
            nt = numel(Yte);
            for k = 1:numel(kern), a(r,k) = mean(predict(mdl{k}, Xte) == Yte); end
            if N == 1, a(2:end,:) = repmat(a(1,:), nRep-1, 1); break; end   % N=1 is deterministic
        end
        acc(sub, in, :) = mean(a, 1); nTest(sub, in) = nt;
    end
    fprintf('B%02d | single-trial lin %.3f rbf %.3f | 5-avg lin %.3f rbf %.3f | 10-avg lin %.3f rbf %.3f\n', ...
        sub, acc(sub,1,1), acc(sub,1,2), acc(sub,2,1), acc(sub,2,2), acc(sub,3,1), acc(sub,3,2));
end

%% summary
rows = compose('B%02d', (1:9)'); rows{end+1} = 'Mean';
vn = {}; M = [];
for in = 1:numel(Ns)
    for k = 1:numel(kern)
        vn{end+1} = sprintf('avg%d_%s', Ns(in), kern{k}); %#ok<SAGROW>
        M = [M, [acc(:,in,k); mean(acc(:,in,k))]]; %#ok<AGROW>
    end
end
T = array2table(M, 'VariableNames', vn, 'RowNames', rows);
T.test_samples_avg10 = [nTest(:,3); mean(nTest(:,3))];
disp('=== Accuracy on sessions 4-5 (chance = 0.50) ==='); disp(T);
writetable(T, fullfile(here, 'erd_svm_accuracy.csv'), 'WriteRowNames', true);

% figure: accuracy vs number of averaged trials
f = figure('Visible','off','Position',[100 100 900 420]);
subplot(1,2,1); hold on;
for k = 1:numel(kern), plot(Ns, squeeze(mean(acc(:,:,k),1)), '-o', 'LineWidth', 2); end
yline(0.5,'--k'); xlabel('trials averaged per decision'); ylabel('mean accuracy (9 subjects)');
legend([strcat(kern,' SVM'), {'chance'}],'Location','southeast'); grid on; xticks(Ns); ylim([0.4 1]);
title('ERD% + SVM, train S1-3, test S4-5');
subplot(1,2,2); bar(squeeze(acc(:,[1 3],1))); yline(0.5,'--k');
xticklabels(rows(1:9)); ylabel('accuracy (linear SVM)'); legend({'single trial','10-trial average'},'Location','southoutside','Orientation','horizontal');
ylim([0 1]); grid on; title('Per subject');
exportgraphics(f, fullfile(here, 'erd_svm_accuracy.png'), 'Resolution', 150); close(f);
save(fullfile(here, 'erd_svm_results.mat'), 'acc', 'Ns', 'kern', 'T', 'bands', 'baseIdx', 'taskIdx');

%% ---------------- local functions ----------------
function [Pb, Pt, y] = bandpowers(root, sub, split, bands, fs, baseIdx, taskIdx)
    sp = [upper(split(1)) split(2:end)];
    L = load(fullfile(root, sp, 'Left',  sprintf('B%02d_%s_left.mat',  sub, split)));
    R = load(fullfile(root, sp, 'Right', sprintf('B%02d_%s_right.mat', sub, split)));
    X = double(cat(1, L.X, R.X)); y = [ones(size(L.X,1),1); 2*ones(size(R.X,1),1)];
    keep = [L.art; R.art] == 0; X = X(keep,:,:); y = y(keep);        % drop artifact trials
    [n, nc, T] = size(X); nb = size(bands,1);
    Pb = zeros(n, nc, nb); Pt = Pb;
    Y = reshape(permute(X, [3 1 2]), T, n*nc);
    for b = 1:nb
        [bb, aa] = butter(4, bands(b,:)/(fs/2), 'bandpass');
        Z = filtfilt(bb, aa, Y).^2;                                   % instantaneous power
        Pb(:,:,b) = reshape(mean(Z(baseIdx,:),1), n, nc);
        Pt(:,:,b) = reshape(mean(Z(taskIdx,:),1), n, nc);
    end
end

function [F, Y] = groupERD(Pb, Pt, y, N, nGroups, mode)
    F = []; Y = [];
    for c = 1:2
        idx = find(y == c);
        switch mode
            case 'random'      % training: many random groups of N distinct trials
                G = zeros(nGroups, N);
                for g = 1:nGroups, G(g,:) = idx(randperm(numel(idx), N)); end
            case 'partition'   % testing: non-overlapping groups covering the trials once
                idx = idx(randperm(numel(idx))); k = floor(numel(idx)/N);
                G = reshape(idx(1:k*N), N, k)';
        end
        for g = 1:size(G,1)
            mb = mean(Pb(G(g,:),:,:), 1); mt = mean(Pt(G(g,:),:,:), 1);
            erd = (mt - mb) ./ mb * 100;                               % 1 x ch x band
            F(end+1,:) = erd(:)'; Y(end+1,1) = c; %#ok<AGROW>
        end
    end
end
