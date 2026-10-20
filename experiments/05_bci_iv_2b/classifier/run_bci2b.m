%% BCI Competition IV 2b - FBCSP replication + improved classifiers
% Train on sessions 01T-03T, test on 04E-05E (session-to-session transfer).
% All model/session/window choices are made with cross-validation on the
% TRAINING data only (held-out folds of session 3). Evaluation labels are
% used only for scoring.
%
% Metrics
%   kappa_trial : single-trial kappa, fixed window after cue, artifact-free eval trials
%   kappa_max   : competition metric - causal sliding window classified every
%                 0.1 s across the trial, kappa at each time point on artifact-free
%                 eval trials, maximum over time (as in the official evaluation)

clearvars -except SUBJ; rng(0);
if ~exist('SUBJ','var'), SUBJ = 1:9; end
root = fullfile(fileparts(mfilename('fullpath')), '..', 'subjectwise');
outdir = fileparts(mfilename('fullpath'));
fs = 250; cue = 3;                         % cue at 3 s from trial start
bands = [4:4:36; 8:4:40]';                 % 9 bands, 4-40 Hz (Ang et al. 2012)
sos = cell(size(bands,1),1);
for b = 1:size(bands,1)
    % causal Chebyshev II; passband = band, stopband 2 Hz outside, 3 dB ripple / 30 dB stop
    Wp = bands(b,:)/(fs/2); Ws = (bands(b,:) + [-2 2])/(fs/2);
    [n,Wn] = cheb2ord(Wp, Ws, 3, 30);
    [z,p,k] = cheby2(n, 30, Wn, 'bandpass');
    sos{b} = zp2sos(z,p,k);
end
wins   = {[0.5 2.5], [0.5 3.5]};           % seconds after cue
models = {'FBCSP-MIBIF-NBPW','FBCSP-sLDA','FBTS-sLDA'};
combos = {[1 2 3],[3],[1 3],[2 3],[1 2]};  % training-session subsets
nF = 10;

pubMIBIF = [0.356 0.171 0.169 0.963 0.850 0.594 0.556 0.856 0.750];
pubMIRSR = [0.400 0.207 0.219 0.950 0.856 0.613 0.550 0.850 0.744];

R = struct();
for sub = SUBJ
    t0 = tic;
    Tr = loadsplit(root, sub, 'training');  Ev = loadsplit(root, sub, 'evaluation');
    FTr = fbfilt(Tr.X, sos);  FEv = fbfilt(Ev.X, sos);
    Ctr = cell(1,numel(wins));
    for w = 1:numel(wins), Ctr{w} = covs(FTr, widx(wins{w}, cue, fs)); end

    % ---------- model selection by CV on held-out session-3 folds ----------
    s3 = find(Tr.sess == 3);
    cvp = cvpartition(Tr.y(s3), 'KFold', nF);
    cvK = nan(numel(models), numel(wins), numel(combos));
    for m = 1:numel(models)
      for w = 1:numel(wins)
        for c = 1:numel(combos)
          yhat = zeros(numel(s3),1);
          for f = 1:nF
            te = s3(test(cvp,f));
            tr = setdiff(find(ismember(Tr.sess, combos{c})), te);
            mdl = trainM(models{m}, Ctr{w}(:,:,tr,:), Tr.y(tr));
            yhat(test(cvp,f)) = predictM(mdl, Ctr{w}(:,:,te,:));
          end
          cvK(m,w,c) = kappa2(Tr.y(s3), yhat);
        end
      end
    end

    % ---------- configurations to evaluate ----------
    cfg = struct('name',{},'m',{},'w',{},'c',{});
    cfg(end+1) = struct('name','Winner FBCSP, all sessions','m',1,'w',1,'c',1);
    [~,cb] = max(squeeze(cvK(1,1,:)));
    cfg(end+1) = struct('name','Winner FBCSP, CV-selected sessions','m',1,'w',1,'c',cb);
    for m = 2:numel(models)
        tmp = squeeze(cvK(m,:,:)); [~,ix] = max(tmp(:)); [wb,cb] = ind2sub(size(tmp),ix);
        cfg(end+1) = struct('name',[models{m} ', CV-selected window+sessions'],'m',m,'w',wb,'c',cb); %#ok<SAGROW>
    end
    [~,ix] = max(cvK(:)); [mb,wb,cb] = ind2sub(size(cvK),ix);
    cfg(end+1) = struct('name','Auto: best CV pipeline per subject','m',mb,'w',wb,'c',cb);

    clean = Ev.art == 0;
    for k = 1:numel(cfg)
        q = cfg(k); w = wins{q.w};
        tr = find(ismember(Tr.sess, combos{q.c}));
        mdl = trainM(models{q.m}, Ctr{q.w}(:,:,tr,:), Tr.y(tr));
        % fixed-window single-trial kappa
        yhat = predictM(mdl, covs(FEv(clean,:,:,:), widx(w, cue, fs)));
        kt = kappa2(Ev.y(clean), yhat);
        % competition-style: causal sliding window, max kappa over time
        L = diff(w); tgrid = L:0.1:8; kc = zeros(size(tgrid));
        for t = 1:numel(tgrid)
            idx = round((tgrid(t)-L)*fs)+1 : round(tgrid(t)*fs);
            kc(t) = kappa2(Ev.y(clean), predictM(mdl, covs(FEv(clean,:,:,:), idx)));
        end
        [km, it] = max(kc);
        R.sub(sub).cfg(k) = struct('name',q.name,'model',models{q.m},'win',w, ...
            'sessions',combos{q.c},'cv_kappa',cvK(q.m,q.w,q.c),'kappa_trial',kt, ...
            'kappa_max',km,'t_max_after_cue',tgrid(it)-cue,'kappa_curve',kc,'tgrid',tgrid-cue);
    end
    R.sub(sub).cvK = cvK;
    fprintf('B%02d done in %.0f s | winner(all) %.3f | winner(sel) %.3f | auto %.3f (%s, %s, sess %s)\n', ...
        sub, toc(t0), R.sub(sub).cfg(1).kappa_max, R.sub(sub).cfg(2).kappa_max, ...
        R.sub(sub).cfg(end).kappa_max, models{mb}, mat2str(wins{wb}), mat2str(combos{cb}));
end

%% ---------- summary tables ----------
if numel(SUBJ) < 9, return; end
names = {R.sub(1).cfg.name};
KM = zeros(9,numel(names)); KT = KM;
for s = 1:9, KM(s,:) = [R.sub(s).cfg.kappa_max]; KT(s,:) = [R.sub(s).cfg.kappa_trial]; end
subj = compose('B%02d',(1:9)'); subj{end+1} = 'Mean';
vn = matlab.lang.makeValidName(names);
Tmax = array2table([KM; mean(KM)], 'VariableNames', vn, 'RowNames', subj);
Tmax.Published_MIBIF = [pubMIBIF'; mean(pubMIBIF)];
Tmax.Published_MIRSR_winner = [pubMIRSR'; mean(pubMIRSR)];
Ttr  = array2table([KT; mean(KT)], 'VariableNames', vn, 'RowNames', subj);
disp('=== Max kappa over time (competition metric), artifact-free eval trials ==='); disp(Tmax);
disp('=== Single-trial kappa, fixed window ==='); disp(Ttr);
sel = strings(9,1);
for s = 1:9
    q = R.sub(s).cfg(end);
    sel(s) = sprintf('%s | %.1f-%.1f s | sessions %s', q.model, q.win, mat2str(q.sessions));
end
disp(table(subj(1:9), sel, 'VariableNames', {'subject','auto_selected_pipeline'}));
writetable(Tmax, fullfile(outdir,'results_kappa_max.csv'), 'WriteRowNames', true);
writetable(Ttr,  fullfile(outdir,'results_kappa_trial.csv'), 'WriteRowNames', true);
save(fullfile(outdir,'results.mat'), 'R', 'Tmax', 'Ttr', 'models', 'wins', 'combos', 'bands');

%% ======================= local functions =======================
function D = loadsplit(root, sub, split)
    L = load(fullfile(root, [upper(split(1)) split(2:end)], 'Left',  sprintf('B%02d_%s_left.mat',  sub, split)));
    Rr = load(fullfile(root, [upper(split(1)) split(2:end)], 'Right', sprintf('B%02d_%s_right.mat', sub, split)));
    D.X = double(cat(1, L.X, Rr.X));
    D.y = [ones(size(L.X,1),1); 2*ones(size(Rr.X,1),1)];
    D.sess = [L.sess; Rr.sess]; D.art = [L.art; Rr.art];
end

function F = fbfilt(X, sos)                % X n x ch x T -> n x ch x T x B (causal)
    [n,ch,T] = size(X); B = numel(sos);
    Y = reshape(permute(X,[3 1 2]), T, n*ch);
    F = zeros(n,ch,T,B,'single');
    for b = 1:B
        Z = sosfilt(sos{b}, Y);
        F(:,:,:,b) = permute(reshape(Z, T, n, ch), [2 3 1]);
    end
end

function idx = widx(w, cue, fs)
    idx = round((cue+w(1))*fs)+1 : round((cue+w(2))*fs);
end

function C = covs(F, idx)                  % -> ch x ch x n x B
    [n,ch,~,B] = size(F); C = zeros(ch,ch,n,B);
    for b = 1:B
        x = permute(double(F(:,:,idx,b)), [2 3 1]);
        C(:,:,:,b) = pagemtimes(x, 'none', x, 'transpose') / numel(idx);
    end
end

function mdl = trainM(type, C, y)
    mdl.type = type; B = size(C,4);
    switch type
        case {'FBCSP-MIBIF-NBPW','FBCSP-sLDA'}
            for b = 1:B
                Cb = C(:,:,:,b) ./ reshape(trace3(C(:,:,:,b)),1,1,[]);
                S1 = mean(Cb(:,:,y==1),3); S2 = mean(Cb(:,:,y==2),3);
                [W,Dg] = eig(S1, S1+S2); [~,o] = sort(diag(Dg),'descend');
                mdl.W{b} = W(:,o([1 end]));
            end
            Fx = cspfeat(mdl, C);
            if strcmp(type,'FBCSP-MIBIF-NBPW')
                I = arrayfun(@(j) mi_parzen(Fx(:,j), y), 1:size(Fx,2));
                [~,o] = sort(I,'descend'); top = o(1:4);
                pairs = unique([2*ceil(top/2)-1, 2*ceil(top/2)]);   % add CSP pair partner
                mdl.sel = pairs; mdl.F = Fx(:,pairs); mdl.y = y;
            else
                mdl.lda = slda_train(Fx, y);
            end
        case 'FBTS-sLDA'
            for b = 1:B
                Cb = regC(C(:,:,:,b));
                Lg = zeros(size(Cb));
                for i = 1:size(Cb,3), Lg(:,:,i) = logmS(Cb(:,:,i)); end
                Cref = expmS(mean(Lg,3));
                mdl.iS{b} = powS(Cref, -0.5);
            end
            mdl.lda = slda_train(tsfeat(mdl, C), y);
    end
end

function yhat = predictM(mdl, C)
    switch mdl.type
        case 'FBCSP-MIBIF-NBPW'
            Fx = cspfeat(mdl, C); Fx = Fx(:,mdl.sel);
            lp = zeros(size(Fx,1),2);
            for w = 1:2
                Fw = mdl.F(mdl.y==w,:); nw = size(Fw,1);
                lp(:,w) = log(nw/numel(mdl.y));
                for j = 1:size(Fx,2)
                    h = (4/(3*nw))^(1/5) * std(Fw(:,j));
                    K = exp(-(Fx(:,j) - Fw(:,j)').^2 / (2*h^2)) / (sqrt(2*pi)*h);
                    lp(:,w) = lp(:,w) + log(mean(K,2) + realmin);
                end
            end
            [~,yhat] = max(lp,[],2);
        case 'FBCSP-sLDA'
            yhat = slda_pred(mdl.lda, cspfeat(mdl, C));
        case 'FBTS-sLDA'
            yhat = slda_pred(mdl.lda, tsfeat(mdl, C));
    end
end

function Fx = cspfeat(mdl, C)
    B = numel(mdl.W); n = size(C,3); Fx = zeros(n, 2*B);
    for b = 1:B
        P = pagemtimes(pagemtimes(mdl.W{b}', C(:,:,:,b)), mdl.W{b});
        d = [squeeze(P(1,1,:)), squeeze(P(2,2,:))];
        Fx(:,2*b-1:2*b) = log(d ./ sum(d,2));
    end
end

function Fx = tsfeat(mdl, C)
    B = numel(mdl.iS); [ch,~,n,~] = size(C);
    iu = find(triu(ones(ch))); wgt = sqrt(2)*ones(ch); wgt(1:ch+1:end) = 1; wgt = wgt(iu);
    Fx = zeros(n, numel(iu)*B);
    for b = 1:B
        Cb = regC(C(:,:,:,b)); iS = mdl.iS{b};
        for i = 1:n
            M = logmS(iS*Cb(:,:,i)*iS);
            Fx(i,(b-1)*numel(iu)+(1:numel(iu))) = (M(iu).*wgt)';
        end
    end
end

function C = regC(C)
    for i = 1:size(C,3), C(:,:,i) = C(:,:,i) + 1e-6*trace(C(:,:,i))*eye(size(C,1)); end
end
function t = trace3(C), t = squeeze(sum(C.*eye(size(C,1)), [1 2])); end
function L = logmS(C), [V,D] = eig((C+C')/2); L = V*diag(log(max(diag(D),realmin)))*V'; end
function E = expmS(L), [V,D] = eig((L+L')/2); E = V*diag(exp(diag(D)))*V'; end
function P = powS(C,p), [V,D] = eig((C+C')/2); P = V*diag(diag(D).^p)*V'; end

function I = mi_parzen(f, y)               % mutual information, Parzen estimate (MIBIF)
    P = [mean(y==1) mean(y==2)]; Hw = -sum(P.*log2(P));
    pf = zeros(numel(f),2);
    for w = 1:2
        fw = f(y==w); h = (4/(3*numel(fw)))^(1/5)*std(fw);
        pf(:,w) = mean(exp(-(f - fw').^2/(2*h^2))/(sqrt(2*pi)*h), 2) * P(w);
    end
    post = pf ./ sum(pf,2);
    I = Hw + mean(sum(post.*log2(post+eps), 2));
end

function M = slda_train(X, y)              % shrinkage LDA (Ledoit-Wolf)
    M.mu = mean(X); M.sd = std(X) + eps; X = (X - M.mu) ./ M.sd;
    m1 = mean(X(y==1,:)); m2 = mean(X(y==2,:));
    Xc = [X(y==1,:)-m1; X(y==2,:)-m2]; [n,d] = size(Xc);
    S = (Xc'*Xc)/n; mu = trace(S)/d; Fm = mu*eye(d);
    d2 = norm(S-Fm,'fro')^2; b2 = 0;
    for i = 1:n, b2 = b2 + norm(Xc(i,:)'*Xc(i,:) - S,'fro')^2; end
    b2 = min(b2/n^2, d2); lam = b2/d2;
    Sig = lam*Fm + (1-lam)*S;
    M.w = Sig \ (m2-m1)'; M.b = -M.w'*(m1+m2)'/2;
end
function yhat = slda_pred(M, X)
    X = (X - M.mu) ./ M.sd; yhat = 1 + ((X*M.w + M.b) > 0);
end

function k = kappa2(y, yhat)
    N = numel(y); C = zeros(2);
    for a = 1:2, for b = 1:2, C(a,b) = sum(y==a & yhat==b); end, end
    po = trace(C)/N; pe = sum(sum(C,2).*sum(C,1)')/N^2;
    k = (po-pe)/(1-pe);
end
