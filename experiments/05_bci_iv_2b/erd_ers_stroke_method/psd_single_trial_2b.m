function psd_single_trial_2b
% PSD_SINGLE_TRIAL_2B  Single-trial PSD of C3 and C4 for BCI IV 2b, drawn exactly like the
% GELO single-trial figures in the report (Figs 6.14 / 6.15), so the two can be compared.
%
% Same settings as the GELO analysis (report Section 6.2 / 6.5.2):
%   - one trial, 4 s window starting at the cue (imagery onset)
%   - Welch PSD, 256-sample Hamming window, 50 % overlap, nfft 500 (0.5 Hz bins), Fs 250 Hz
%   - no extra filtering (2b is already 0.5-100 Hz band-pass + 50 Hz notch from the amplifier)
%   - data converted uV -> V so dB/Hz is on the same scale as the GELO plots (dB re 1 V^2/Hz)
%   - ratio = C3 power / C4 power in 8-30 Hz (linear band power)
%   - peak = highest PSD between 4 and 40 Hz
%
% Which trial is plotted: for every subject and hand, the trial whose C3/C4 ratio is the
% MEDIAN of that hand's trials (a typical trial, not a hand-picked one). The trial-averaged
% PSD is in psd_report_style_2b.m (Figs 6.7 / 6.8).
%
% Also writes psd_single_trial_2b.csv with, per subject: number of trials, median single-trial
% ratio per hand, peak frequencies of the plotted trials, and the single-trial AUC of
% log(C3/C4) (0.5 = no separation; the report gives 0.51 for the 72 GELO trials).
%
% Outputs: figures_psd_single_trial\B0x_Left_single.png, B0x_Right_single.png, psd_single_trial_2b.csv

dataDir = 'D:\trainsvm\experiments\05_bci_iv_2b\data';
outdir  = 'D:\trainsvm\experiments\05_bci_iv_2b\erd_ers_stroke_method';
figdir  = fullfile(outdir, 'figures_psd_single_trial');
if ~exist(figdir, 'dir'), mkdir(figdir); end

Fs = 250; cueN = 3*Fs; wImag = cueN+1 : cueN+4*Fs;      % 0-4 s after the cue
win = hamming(256); nov = 128; nfft = 500;              % as in the GELO analysis
band = [8 30]; pk = [4 40]; showF = [0 60];
cB = [0 0.4470 0.7410]; cO = [0.8500 0.3250 0.0980];
hand = {'Left','Right'};
sessName = {'01T','02T','03T','04E','05E'};

rows = {};
for si = 1:9
    name = sprintf('B%02d', si);
    P = {}; lab = []; info = zeros(0,4);              % info: session, trial no., first, last sample
    sess = 0;
    for f = {'T','E'}
        m = load(fullfile(dataDir, [name f{1} '.mat']));
        for k = 1:numel(m.data)
            sess = sess + 1;
            s = m.data{k}; X = double(s.X(:,[1 3])) * 1e-6;     % C3, C4 in volts
            tr = double(s.trial(:)); yy = double(s.y(:));
            for i = 1:numel(tr)
                idx = tr(i) + wImag - 1;
                if idx(end) > size(X,1), continue; end
                x = X(idx,:); if any(isnan(x(:))), continue; end
                [p, fr] = pwelch(detrend(x,'constant'), win, nov, nfft, Fs);
                P{end+1,1} = p; lab(end+1,1) = yy(i);                     %#ok<AGROW>
                info(end+1,:) = [sess i idx(1) idx(end)];                 %#ok<AGROW>
            end
        end
    end
    P = cat(3, P{:});
    kb = fr >= band(1) & fr <= band(2);
    bp = squeeze(trapz(fr(kb), P(kb,:,:), 1));      % 2 x trials
    ratio = bp(1,:)' ./ bp(2,:)';
    [~,~,~,auc] = perfcurve(lab, log10(ratio), 1);

    pkF = zeros(2,2); medR = zeros(1,2); nT = zeros(1,2);
    for h = 1:2
        id = find(lab == h); nT(h) = numel(id);
        [~, o] = sort(ratio(id)); j = id(o(ceil(numel(o)/2)));   % median-ratio trial
        medR(h) = ratio(j);
        db = 10*log10(P(:,:,j));
        kp = find(fr >= pk(1) & fr <= pk(2));
        [~,j3] = max(db(kp,1)); [~,j4] = max(db(kp,2));
        f3 = fr(kp(j3)); f4 = fr(kp(j4)); pkF(h,:) = [f3 f4];
        ks = fr >= showF(1) & fr <= showF(2);

        fg = figure('Color','w','Position',[100 100 800 600],'Visible','off');
        ax1 = subplot(2,2,1);
        plot(ax1, fr(ks), db(ks,1), 'Color', cB, 'LineWidth', 1.0); hold(ax1,'on');
        plot(ax1, f3, db(kp(j3),1), 'o', 'MarkerFaceColor','r','MarkerEdgeColor','r','MarkerSize',6);
        grid(ax1,'on'); xlim(ax1, showF);
        title(ax1, sprintf('C3 (peak %.2f Hz)', f3)); xlabel(ax1,'Frequency (Hz)'); ylabel(ax1,'PSD (dB/Hz)');

        ax2 = subplot(2,2,2);
        plot(ax2, fr(ks), db(ks,2), 'Color', cO, 'LineWidth', 1.0); hold(ax2,'on');
        plot(ax2, f4, db(kp(j4),2), 'o', 'MarkerFaceColor','r','MarkerEdgeColor','r','MarkerSize',6);
        grid(ax2,'on'); xlim(ax2, showF);
        title(ax2, sprintf('C4 (peak %.2f Hz)', f4)); xlabel(ax2,'Frequency (Hz)'); ylabel(ax2,'PSD (dB/Hz)');

        ax3 = subplot(2,2,[3 4]);
        plot(ax3, fr(ks), db(ks,1), 'Color', cB, 'LineWidth', 1.0); hold(ax3,'on');
        plot(ax3, fr(ks), db(ks,2), 'Color', cO, 'LineWidth', 1.0);
        plot(ax3, [f3 f4], [db(kp(j3),1) db(kp(j4),2)], 'ko', 'MarkerFaceColor','k','MarkerSize',4,'HandleVisibility','off');
        grid(ax3,'on'); xlim(ax3, showF);
        title(ax3, 'Overlay'); xlabel(ax3,'Frequency (Hz)'); ylabel(ax3,'PSD (dB/Hz)');
        legend(ax3, {'C3','C4'}, 'Location','northeast');

        sgtitle(fg, sprintf('%s | BCI IV 2b %s | session %s, trial %d | samples %d-%d | C3/C4 ratio = %.3f (median %s trial of %d)', ...
            hand{h}, name, sessName{info(j,1)}, info(j,2), info(j,3), info(j,4), ratio(j), lower(hand{h}), nT(h)), 'FontSize', 9);
        exportgraphics(fg, fullfile(figdir, sprintf('%s_%s_single.png', name, hand{h})), 'Resolution', 120);
        close(fg);
    end
    fprintf('%s  median single-trial ratio L %.3f  R %.3f | peaks L %.1f/%.1f  R %.1f/%.1f Hz | AUC %.2f\n', ...
        name, medR(1), medR(2), pkF(1,1), pkF(1,2), pkF(2,1), pkF(2,2), auc);
    rows(end+1,:) = {name, nT(1), nT(2), medR(1), medR(2), pkF(1,1), pkF(1,2), pkF(2,1), pkF(2,2), auc}; %#ok<AGROW>
end
T = cell2table(rows, 'VariableNames', {'subject','nLeft','nRight','median_ratio_left','median_ratio_right', ...
    'peak_C3_left','peak_C4_left','peak_C3_right','peak_C4_right','AUC_logratio'});
writetable(T, fullfile(outdir, 'psd_single_trial_2b.csv'));
fprintf('Figures in %s\n', figdir);
end
