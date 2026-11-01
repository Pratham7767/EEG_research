function psd_report_style_2b
% PSD_REPORT_STYLE_2B  PSD of C3 and C4 for every BCI IV 2b subject, drawn in the
% same layout as the Gelo PSD figure in the report (eeg_ratio_batch.m style):
%   top-left  : C3 PSD (dB/Hz) with its peak marked (red dot), "C3 (peak x Hz)"
%   top-right : C4 PSD, same
%   bottom    : overlay of both, peaks as black dots, legend top-right
%   title     : hand | subject | trials | window | C3/C4 ratio
% One figure per subject and hand (18 figures).
%
% Data and windows are the same as erd_ers_2b_stroke_method.m / psd_2b_stroke_method.m:
%   all 5 sessions, C3 = X(:,1), C4 = X(:,3), imagery window 0-4 s after the cue
%   (cue = trial + 3 s). Artefact-flagged trials kept, NaN trials dropped.
% PSD: pwelch, 2 s Hamming window, 50 % overlap (0.5 Hz bins, as in the report),
%   one PSD per trial, averaged over the trials of that hand, then 10*log10.
%   The 2b data are in microvolts; they are converted to volts first, so the
%   dB/Hz values are on the same scale as the Gelo figure (dB re 1 V^2/Hz).
% Peak: highest PSD between 4 and 40 Hz (below 4 Hz is slow drift / eye movement).
% Ratio: C3 power / C4 power in 8-30 Hz (linear). Expect > 1 for left hand
%   (C4 drops) and < 1 for right hand (C3 drops).
%
% Outputs: figures_psd_report\B0x_Left_PSD.png, B0x_Right_PSD.png, psd_report_ratios.csv
% Run:  cd D:\trainsvm\experiments\05_bci_iv_2b\erd_ers_stroke_method
%       psd_report_style_2b

dataDir = 'D:\trainsvm\experiments\05_bci_iv_2b\data';
outdir  = 'D:\trainsvm\experiments\05_bci_iv_2b\erd_ers_stroke_method';
figdir  = fullfile(outdir,'figures_psd_report');
if ~exist(figdir,'dir'), mkdir(figdir); end

Fs = 250; nSub = 9; cueN = 3*Fs;
wImag = cueN+1 : cueN+4*Fs;                     % 0..4 s after the cue
win = hamming(2*Fs); nov = Fs; nfft = 2*Fs;     % 2 s window, 50 %, 0.5 Hz bins
pk  = [4 40]; band = [8 30]; showF = [0 60];
cB = [0 0.4470 0.7410]; cO = [0.8500 0.3250 0.0980];   % MATLAB blue / orange
hand = {'Left','Right'};

R = zeros(nSub,2); PK = zeros(nSub,2,2); NT = zeros(nSub,2);
for si = 1:nSub
    name = sprintf('B%02d', si);
    P = {}; lab = [];
    for f = {'T','E'}
        m = load(fullfile(dataDir, [name f{1} '.mat']));
        for k = 1:numel(m.data)
            s = m.data{k}; X = double(s.X(:,[1 3])) * 1e-6;   % uV -> V
            tr = double(s.trial(:)); yy = double(s.y(:));
            for i = 1:numel(tr)
                idx = tr(i) : tr(i)+8*Fs-1;
                if idx(end) > size(X,1), continue; end
                x = X(idx,:); if any(isnan(x(:))), continue; end
                [p, fr] = pwelch(detrend(x(wImag,:),'constant'), win, nov, nfft, Fs);
                P{end+1,1} = p; lab(end+1,1) = yy(i); %#ok<AGROW>
            end
        end
    end
    P = cat(3, P{:});                             % freq x 2 x trials
    for h = 1:2
        sel = lab == h; NT(si,h) = sum(sel);
        mp = mean(P(:,:,sel), 3);                 % freq x 2 (linear)
        db = 10*log10(mp);
        kb = fr >= band(1) & fr <= band(2);
        R(si,h) = trapz(fr(kb), mp(kb,1)) / trapz(fr(kb), mp(kb,2));
        kp = find(fr >= pk(1) & fr <= pk(2));
        [~,j3] = max(db(kp,1)); [~,j4] = max(db(kp,2));
        f3 = fr(kp(j3)); f4 = fr(kp(j4)); PK(si,h,:) = [f3 f4];
        ks = fr >= showF(1) & fr <= showF(2);

        fg = figure('Color','w','Position',[100 100 800 600],'Visible','off');
        ax1 = subplot(2,2,1);
        plot(ax1, fr(ks), db(ks,1), 'Color', cB, 'LineWidth', 1.2); hold(ax1,'on');
        plot(ax1, f3, db(kp(j3),1), 'o', 'MarkerFaceColor','r', 'MarkerEdgeColor','r', 'MarkerSize', 6);
        grid(ax1,'on'); xlim(ax1, showF);
        title(ax1, sprintf('C3 (peak %.2f Hz)', f3)); xlabel(ax1,'Frequency (Hz)'); ylabel(ax1,'PSD (dB/Hz)');

        ax2 = subplot(2,2,2);
        plot(ax2, fr(ks), db(ks,2), 'Color', cO, 'LineWidth', 1.2); hold(ax2,'on');
        plot(ax2, f4, db(kp(j4),2), 'o', 'MarkerFaceColor','r', 'MarkerEdgeColor','r', 'MarkerSize', 6);
        grid(ax2,'on'); xlim(ax2, showF);
        title(ax2, sprintf('C4 (peak %.2f Hz)', f4)); xlabel(ax2,'Frequency (Hz)'); ylabel(ax2,'PSD (dB/Hz)');

        ax3 = subplot(2,2,[3 4]);
        plot(ax3, fr(ks), db(ks,1), 'Color', cB, 'LineWidth', 1.2); hold(ax3,'on');
        plot(ax3, fr(ks), db(ks,2), 'Color', cO, 'LineWidth', 1.2);
        plot(ax3, [f3 f4], [db(kp(j3),1) db(kp(j4),2)], 'ko', 'MarkerFaceColor','k', 'MarkerSize', 4, 'HandleVisibility','off');
        grid(ax3,'on'); xlim(ax3, showF);
        title(ax3, 'Overlay'); xlabel(ax3,'Frequency (Hz)'); ylabel(ax3,'PSD (dB/Hz)');
        legend(ax3, {'C3','C4'}, 'Location','northeast');

        sgtitle(fg, sprintf('%s hand | BCI IV 2b %s | %d trials, 0-4 s after cue | C3/C4 ratio (8-30 Hz) = %.3f', ...
            hand{h}, name, NT(si,h), R(si,h)), 'FontSize', 10);
        exportgraphics(fg, fullfile(figdir, sprintf('%s_%s_PSD.png', name, hand{h})), 'Resolution', 120);
        close(fg);
    end
    fprintf('%s  ratio L %.3f  R %.3f   peaks C3/C4  L %.1f/%.1f  R %.1f/%.1f Hz\n', name, R(si,1), R(si,2), ...
        PK(si,1,1), PK(si,1,2), PK(si,2,1), PK(si,2,2));
end

T = table(arrayfun(@(k) sprintf('B%02d',k), (1:nSub)', 'UniformOutput', false), NT(:,1), NT(:,2), ...
    R(:,1), R(:,2), R(:,1) > R(:,2), PK(:,1,1), PK(:,1,2), PK(:,2,1), PK(:,2,2), ...
    'VariableNames', {'subject','nLeft','nRight','ratio_C3C4_left','ratio_C3C4_right','left_ratio_higher', ...
    'peak_C3_left','peak_C4_left','peak_C3_right','peak_C4_right'});
writetable(T, fullfile(outdir, 'psd_report_ratios.csv'));
fprintf('left-hand ratio > right-hand ratio in %d/%d subjects\n', sum(T.left_ratio_higher), nSub);
end
