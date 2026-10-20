%% ========================================================================
%  s05_native_rate.m
%
%  VARIANT EXPERIMENT: keep each dataset at its own native sampling rate
%  instead of resampling the stroke data 500 -> 250 Hz.
%
%    training (stroke) : 500 Hz, 4 s imagery = 2000 samples
%    test (our own)    : 250 Hz, 4 s imagery = 1000 samples
%
%  The one thing that MUST change versus s01: every window is specified in
%  SECONDS, never in samples. A Welch window of 250 samples means 1 s at
%  250 Hz but only 0.5 s at 500 Hz, which changes the frequency resolution
%  and makes the two datasets' spectra non-comparable. Measured on sub-01:
%  window fixed in seconds -> corr 0.9996 with the resampled version;
%  window fixed in samples -> corr 0.963 plus a systematic offset.
%
%  Writes: features_train_native.csv, features_test_native.csv,
%          results_native.csv
%% ========================================================================
clear; clc;

OUT        = 'D:\trainsvm\experiments\04_svm_stroke_to_gelo';
strokeRoot = 'D:\trainsvm\data\stroke_liu2024\sourcedata\sourcedata';
ownRoot    = 'D:\trainsvm\data\gelo';

BAND=[8 30]; BANDA=[8 13]; BANDB=[13 30]; ORD=2;
PRE_S=1.0; POST_S=4.0; PAD_S=0.5; MINREST_S=1.5; MARKS=1:5;
WELCH_S=1.0; NFFT=1024;

fprintf('=== s05: native sampling rates (stroke 500 Hz, own 250 Hz) ===\n');

%% ------------------------- TRAINING, 500 Hz -----------------------------
fs=500; [b,a]=butter(ORD,BAND*2/fs);
nPre=round(PRE_S*fs); nPost=round(POST_S*fs);
rows={}; nSkip=0;
for s=1:50
    fn=sprintf('%s\\sub-%02d\\sub-%02d_task-motor-imagery_eeg.mat',strokeRoot,s,s);
    S=load(fn); raw=S.eeg.rawdata; lab=S.eeg.label;
    for t=1:size(raw,1)
        mk=squeeze(raw(t,33,:)); o=find(mk==2,1);
        if isempty(o) || o-nPre<1 || o+nPost-1>size(raw,3), nSkip=nSkip+1; continue; end
        x=detrend(squeeze(raw(t,[14 15],:))',0);
        xf=filtfilt(b,a,x);
        F=featrow(xf(o:o+nPost-1,:), xf(o-nPre:o-1,:), x(o:o+nPost-1,:), fs, WELCH_S, NFFT, BAND, BANDA, BANDB);
        F.dataset='stroke'; F.group=sprintf('sub-%02d',s);
        F.item=sprintf('trial%02d',t); F.label=lab(t);
        rows{end+1,1}=F; %#ok<SAGROW>
    end
end
Tr=rowsToTable(rows);
fprintf('train: %d epochs (%d L / %d R), %d skipped at edge\n', height(Tr), sum(Tr.label==1), sum(Tr.label==2), nSkip);
writetable(Tr, fullfile(OUT,'features_train_native.csv'));

%% --------------------------- TEST, 250 Hz -------------------------------
fs=250; [b,a]=butter(ORD,BAND*2/fs);
nPre=round(PRE_S*fs); nPost=round(POST_S*fs);
padPre=round((PRE_S+PAD_S)*fs); padPost=round((POST_S+PAD_S)*fs); crop0=padPre-nPre;
rows={};
for cl=[1 2]
    if cl==1, fold='left'; else, fold='right'; end
    fl=dir(fullfile(ownRoot,fold,'*.csv'));
    for k=1:numel(fl)
        M=readmatrix(fullfile(fl(k).folder,fl(k).name)); M=M(~isnan(M(:,end)),:);
        X=M(:,2:5)*1e6; mk=M(:,end);
        for m=MARKS
            idx=find(mk==m); if isempty(idx), continue; end
            o=idx(1); j=o-1; while j>=1 && mk(j)==0, j=j-1; end
            if o-padPre<1 || o+padPost-1>size(X,1) || (o-1-j)/fs<MINREST_S, continue; end
            ep=detrend(X(o-padPre:o+padPost-1,[2 3]),0);
            epf=filtfilt(b,a,ep);
            rg=crop0+1:crop0+nPre+nPost;
            epf=epf(rg,:); epr=ep(rg,:);
            F=featrow(epf(nPre+1:end,:), epf(1:nPre,:), epr(nPre+1:end,:), fs, WELCH_S, NFFT, BAND, BANDA, BANDB);
            F.dataset='own'; F.group=fl(k).name;
            F.item=sprintf('mark%d',m); F.label=cl;
            rows{end+1,1}=F; %#ok<SAGROW>
        end
    end
end
Te=rowsToTable(rows);
fprintf('test : %d epochs (%d L / %d R)\n', height(Te), sum(Te.label==1), sum(Te.label==2));
writetable(Te, fullfile(OUT,'features_test_native.csv'));

%% ------------------------- SVMs, same 12 configs ------------------------
abs8={'C3_mean','C3_median','C3_skew','C3_kurt','C4_mean','C4_median','C4_skew','C4_kurt'};
erd8={'E_C3_mean','E_C3_median','C3_skew','C3_kurt','E_C4_mean','E_C4_median','C4_skew','C4_kurt'};
FSname={'A','B','C','A','B','C'};
FSflav={'abs','abs','abs','erd','erd','erd'};
FSvars={abs8,[abs8 {'logC3C4'}],{'logC3C4'},erd8,[erd8 {'E_logC3C4'}],{'E_logC3C4'}};
KERN={'linear','rbf'};
subs=unique(Tr.group); nSub=numel(subs); subIdx=zeros(height(Tr),1);
for s=1:nSub, subIdx(strcmp(Tr.group,subs{s}))=s; end
yTr=Tr.label; yTe=Te.label; res={};
fprintf('\n%-22s %-10s %-10s %-10s\n','config','LOSO bal','TEST acc','TEST bal');
for f=1:6
  for k=1:2
    rng(1234);
    X=Tr{:,FSvars{f}}; Xe=Te{:,FSvars{f}};
    mu=mean(X,1); sg=std(X,0,1); sg(sg==0)=1; Z=(X-mu)./sg; Ze=(Xe-mu)./sg;
    pr=zeros(numel(yTr),1);
    for s=1:nSub
      te=subIdx==s; tr=~te;
      pr(te)=predict(fitSVM(Z(tr,:),yTr(tr),KERN{k},1,sqrt(size(Z,2))), Z(te,:));
    end
    lb=balAcc(yTr,pr);
    pte=predict(fitSVM(Z,yTr,KERN{k},1,sqrt(size(Z,2))), Ze);
    ta=mean(pte==yTe); tb=balAcc(yTe,pte);
    res{end+1,1}={FSname{f},FSflav{f},KERN{k},numel(FSvars{f}),lb,ta,tb,mean(pte==2)}; %#ok<SAGROW>
    fprintf('SVM-%-2s %-4s %-7s %10.3f %10.3f %10.3f\n', FSname{f},FSflav{f},KERN{k},lb,ta,tb);
  end
end
R=cell2table(vertcat(res{:}),'VariableNames',{'model','flavour','kernel','nFeatures','LOSO_balanced_accuracy','test_accuracy','test_balanced_accuracy','fraction_predicted_right'});
writetable(R, fullfile(OUT,'results_native.csv'));
fprintf('\nWrote results_native.csv\n');

%% ========================== LOCAL FUNCTIONS =============================
function F = featrow(miF, baseF, miRaw, fs, welchSec, nfft, band, banda, bandb)
% miF/baseF: bandpassed imagery and baseline windows, columns [C3 C4]
% miRaw    : detrended, unfiltered imagery window (for the PSD)
% Windows are given in SECONDS so the two sampling rates stay comparable.
    E=miF.^2; Eb=baseF.^2; base=mean(Eb,1);
    F=struct(); nm={'C3','C4'};
    for c=1:2
        F.([nm{c} '_mean'])=mean(E(:,c));
        F.([nm{c} '_median'])=median(E(:,c));
        F.([nm{c} '_skew'])=skewness(E(:,c));
        F.([nm{c} '_kurt'])=kurtosis(E(:,c));
        F.(['E_' nm{c} '_mean'])=(mean(E(:,c))-base(c))/base(c)*100;
        F.(['E_' nm{c} '_median'])=(median(E(:,c))-base(c))/base(c)*100;
    end
    w=round(welchSec*fs);
    [pxx,f]=pwelch(miRaw, hamming(w), round(w/2), nfft, fs);
    P=bandInt(pxx,f,band); Pa=bandInt(pxx,f,banda); Pb=bandInt(pxx,f,bandb);
    F.logC3C4=log10(P(1)/P(2));
    F.logC3C4_alpha=log10(Pa(1)/Pa(2));
    F.logC3C4_beta=log10(Pb(1)/Pb(2));
    F.E_logC3C4=log10((mean(E(:,1))/base(1))/(mean(E(:,2))/base(2)));
end

function p = bandInt(pxx, f, band)
    sel = f>=band(1) & f<=band(2);
    p = trapz(f(sel), pxx(sel,:), 1);
end

function T = rowsToTable(rows)
    T = struct2table(vertcat(rows{:}));
    T = movevars(T, {'dataset','group','item','label'}, 'Before', 1);
end

function mdl = fitSVM(X, y, kern, C, K)
    if strcmp(kern,'rbf')
        mdl = fitcsvm(X,y,'KernelFunction','rbf','BoxConstraint',C, ...
            'KernelScale',K,'ClassNames',[1 2],'IterationLimit',2e5);
    else
        mdl = fitcsvm(X,y,'KernelFunction','linear','BoxConstraint',C, ...
            'ClassNames',[1 2],'IterationLimit',2e5);
    end
end

function b = balAcc(y, p)
    r1=mean(p(y==1)==1); r2=mean(p(y==2)==2);
    if isnan(r1), r1=0; end
    if isnan(r2), r2=0; end
    b=(r1+r2)/2;
end
