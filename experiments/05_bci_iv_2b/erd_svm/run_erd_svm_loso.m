%% ERD% + linear SVM, 10-trial averaging, LEAVE-ONE-SUBJECT-OUT - BCI Competition IV 2b
% Train on 8 subjects (all 5 sessions), test on the 9th subject (all 5 sessions), rotate 9 times.
% The test subject's data is never seen in training. Artifact-flagged trials are excluded.
%
% Features (6 per sample): ERD% at C3, Cz, C4 x {mu 8-13 Hz, beta 13-30 Hz}
%   baseline 2.0-1.0 s before cue, task 0.5-3.5 s after cue,
%   ERD% = (mean task power - mean baseline power) / mean baseline power * 100,
%   with power averaged over the N trials of one group first.
% Groups: N trials of the SAME subject and SAME class.
%   training : 300 random groups per class per training subject
%   testing  : held-out subject's trials split into non-overlapping groups of N (per class);
%              confusion matrix from one fixed split, accuracy averaged over 20 random splits.

clear; rng(1);
here = fileparts(mfilename('fullpath')); root = fullfile(here, '..', 'subjectwise');
fs = 250; cue = 3;
baseIdx = round((cue-2.0)*fs)+1 : round((cue-1.0)*fs);
taskIdx = round((cue+0.5)*fs)+1 : round((cue+3.5)*fs);
bands = [8 13; 13 30];
Ns = [1 10]; nTrainGroups = 300; nRep = 20;
featNames = {'C3_mu','Cz_mu','C4_mu','C3_beta','Cz_beta','C4_beta'};

% band power per trial, all subjects, both splits merged
P = struct();
for s = 1:9
    [b1,t1,y1] = bandpowers(root, s, 'training',   bands, fs, baseIdx, taskIdx);
    [b2,t2,y2] = bandpowers(root, s, 'evaluation', bands, fs, baseIdx, taskIdx);
    P(s).b = cat(1,b1,b2); P(s).t = cat(1,t1,t2); P(s).y = [y1; y2];
end

res = struct();
for in = 1:numel(Ns)
    N = Ns(in); CM = zeros(2); acc = zeros(9,1); nDec = zeros(9,1); CMs = zeros(2,2,9);
    for test = 1:9
        Xtr = []; Ytr = [];
        for s = setdiff(1:9, test)
            if N == 1, [F,Y] = groupERD(P(s).b, P(s).t, P(s).y, 1, 0, 'partition');
            else,      [F,Y] = groupERD(P(s).b, P(s).t, P(s).y, N, nTrainGroups, 'random'); end
            Xtr = [Xtr; F]; Ytr = [Ytr; Y]; %#ok<AGROW>
        end
        mdl = fitcsvm(Xtr, Ytr, 'KernelFunction','linear', 'Standardize', true);
        a = zeros(nRep,1);
        for r = 1:nRep
            [Xte, Yte] = groupERD(P(test).b, P(test).t, P(test).y, N, 0, 'partition');
            yhat = predict(mdl, Xte); a(r) = mean(yhat == Yte);
            if r == 1
                C = confusionmat(Yte, yhat, 'Order', [1 2]); CMs(:,:,test) = C; CM = CM + C; nDec(test) = numel(Yte);
            end
            if N == 1, a(:) = a(1); break; end
        end
        acc(test) = mean(a);
    end
    res(in).N = N; res(in).CM = CM; res(in).CMs = CMs; res(in).acc = acc; res(in).nDec = nDec;
    w = mdl.Beta ./ mdl.Sigma';   % last fold, weights in original units (for interpretation)
    fprintf('\n===== N = %d trials averaged per decision =====\n', N);
    fprintf('Per test subject accuracy: %s\n', sprintf('B%02d %.2f  ', [1:9; acc']));
    fprintf('Mean accuracy %.3f | decisions per subject ~%d\n', mean(acc), round(mean(nDec)));
    fprintf('Pooled confusion matrix (rows = true, cols = predicted; 1 = Left, 2 = Right):\n');
    disp(array2table(CM, 'VariableNames', {'pred_Left','pred_Right'}, 'RowNames', {'true_Left','true_Right'}));
    fprintf('Left recall %.3f | Right recall %.3f\n', CM(1,1)/sum(CM(1,:)), CM(2,2)/sum(CM(2,:)));
end
fprintf('\nLinear SVM weights (standardised, last fold): %s\n', strjoin(compose('%s %+.2f', string(featNames'), mdl.Beta), ' | '));

% outputs
f = figure('Visible','off','Position',[100 100 1000 430]);
for in = 1:numel(Ns)
    subplot(1,2,in);
    cc = confusionchart(res(in).CM, {'Left','Right'}, 'RowSummary','row-normalized', 'ColumnSummary','column-normalized');
    cc.Title = sprintf('%s: LOSO, all 9 test subjects pooled (acc %.1f%%)', ...
        ternary(res(in).N==1,'Single trial','10-trial average'), 100*mean(res(in).acc));
end
exportgraphics(f, fullfile(here, 'confusion_loso.png'), 'Resolution', 150); close(f);
T = table(compose('B%02d',(1:9)'), res(1).acc, res(2).acc, res(2).nDec, ...
    squeeze(res(2).CMs(1,1,:)), squeeze(res(2).CMs(1,2,:)), squeeze(res(2).CMs(2,1,:)), squeeze(res(2).CMs(2,2,:)), ...
    'VariableNames', {'test_subject','acc_single','acc_avg10','decisions_avg10','LL','LR','RL','RR'});
writetable(T, fullfile(here, 'loso_results.csv'));
save(fullfile(here, 'loso_results.mat'), 'res', 'featNames');

%% ---------------- local functions ----------------
function out = ternary(c, a, b), if c, out = a; else, out = b; end, end

function [Pb, Pt, y] = bandpowers(root, sub, split, bands, fs, baseIdx, taskIdx)
    sp = [upper(split(1)) split(2:end)];
    L = load(fullfile(root, sp, 'Left',  sprintf('B%02d_%s_left.mat',  sub, split)));
    R = load(fullfile(root, sp, 'Right', sprintf('B%02d_%s_right.mat', sub, split)));
    X = double(cat(1, L.X, R.X)); y = [ones(size(L.X,1),1); 2*ones(size(R.X,1),1)];
    keep = [L.art; R.art] == 0; X = X(keep,:,:); y = y(keep);
    [n, nc, T] = size(X); nb = size(bands,1); Pb = zeros(n,nc,nb); Pt = Pb;
    Y = reshape(permute(X, [3 1 2]), T, n*nc);
    for b = 1:nb
        [bb, aa] = butter(4, bands(b,:)/(fs/2), 'bandpass');
        Z = filtfilt(bb, aa, Y).^2;
        Pb(:,:,b) = reshape(mean(Z(baseIdx,:),1), n, nc);
        Pt(:,:,b) = reshape(mean(Z(taskIdx,:),1), n, nc);
    end
end

function [F, Y] = groupERD(Pb, Pt, y, N, nGroups, mode)
    F = []; Y = [];
    for c = 1:2
        idx = find(y == c);
        switch mode
            case 'random'
                G = zeros(nGroups, N);
                for g = 1:nGroups, G(g,:) = idx(randperm(numel(idx), N)); end
            case 'partition'
                idx = idx(randperm(numel(idx))); k = floor(numel(idx)/N);
                G = reshape(idx(1:k*N), N, k)';
        end
        mb = zeros(size(G,1), size(Pb,2)*size(Pb,3)); mt = mb;
        for g = 1:size(G,1)
            b = mean(Pb(G(g,:),:,:), 1); t = mean(Pt(G(g,:),:,:), 1);
            mb(g,:) = b(:)'; mt(g,:) = t(:)';
        end
        F = [F; (mt - mb) ./ mb * 100]; Y = [Y; c*ones(size(G,1),1)]; %#ok<AGROW>
    end
end
