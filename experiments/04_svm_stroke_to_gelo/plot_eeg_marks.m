function out = plot_eeg_marks(csvFile, varargin)
%PLOT_EEG_MARKS  Plot selected EEG channels for labelled task blocks only.
%
%   Reads a CSV with one column per channel plus a marker column, finds the
%   contiguous runs of the marker values you care about, and plots the chosen
%   channels for those runs. Rows outside the wanted markers are excluded, and
%   separate runs are never glued together: a NaN gap is inserted between them.
%
%   OUT = PLOT_EEG_MARKS(CSVFILE) uses the defaults below.
%   OUT = PLOT_EEG_MARKS(CSVFILE, 'Name', Value, ...) overrides them.
%   OUT = PLOT_EEG_MARKS()  opens a file picker.
%
%   Name-value options
%     'Marks'        vector of marker values to keep          (default [1 2 3 4 5])
%     'Channels'     cellstr / string array of column names   (default {'ch2','ch3'})
%     'Labels'       display names, same length as Channels   (default {'C3','C4'}
%                                                              when Channels is the
%                                                              2-channel default,
%                                                              otherwise the column
%                                                              names themselves)
%     'MarkColumn'   name of the marker column                (default 'mark')
%     'TimeColumn'   name of the time column, '' if none      (default 'timestamp')
%     'TimeUnits'    'us' | 'ms' | 's' | 'samples'            (default 'us')
%     'Fs'           sampling rate in Hz; [] derives it from  (default [])
%                    the time column
%     'Plot'         false to compute blocks without figures  (default true)
%     'Figures'      any of {'overview','permark','overlay'}  (default all three)
%     'MinBlockSamples'  drop runs shorter than this          (default 1)
%     'SaveDir'      folder to write PNGs into, '' to skip    (default '')
%     'Verbose'      print the block summary                  (default true)
%
%   Output struct OUT
%     .fs        sampling rate actually used (Hz)
%     .t         time vector, seconds from start of recording
%     .X         [nSamples x nChannels] matrix of the selected channels
%     .channels  column names used
%     .labels    display names used
%     .blocks    table: mark, i1, i2, nSamples, duration, tStart, tEnd
%     .dead      names of channels that carry no signal (constant column)
%     .figures   handles to the figures created
%     .get       function handle: B = OUT.get(k) returns a struct with
%                B.t, B.X, B.mark for block k
%
%   Examples
%     out = plot_eeg_marks('Right1_5.csv');
%     out = plot_eeg_marks('Left2_3.csv', 'Channels', {'ch1','ch2','ch3','ch4'});
%     out = plot_eeg_marks('Right1_5.csv', 'Marks', [1 2], 'Figures', {'permark'});
%     out = plot_eeg_marks('Right1_5.csv', 'Plot', false);   % just the block table
%     b = out.get(3);  plot(b.t, b.X);                       % pull block 3 out

%% ---------------------------- arguments -------------------------------
if nargin < 1 || isempty(csvFile)
    [f, pth] = uigetfile({'*.csv','CSV files'}, 'Select the EEG csv file');
    if isequal(f, 0), error('plot_eeg_marks:noFile','No file selected.'); end
    csvFile = fullfile(pth, f);
end

p = inputParser;
p.FunctionName = 'plot_eeg_marks';
addParameter(p, 'Marks',           [1 2 3 4 5], @(x) isnumeric(x) && ~isempty(x));
addParameter(p, 'Channels',        {'ch2','ch3'});
addParameter(p, 'Labels',          {});
addParameter(p, 'MarkColumn',      'mark',      @(x) ischar(x) || isstring(x));
addParameter(p, 'TimeColumn',      'timestamp');
addParameter(p, 'TimeUnits',       'us',        @(x) any(strcmpi(x, {'us','ms','s','samples'})));
addParameter(p, 'Fs',              [],          @(x) isempty(x) || (isscalar(x) && x > 0));
addParameter(p, 'Plot',            true,        @(x) islogical(x) || isnumeric(x));
addParameter(p, 'Figures',         {'overview','permark','overlay'});
addParameter(p, 'MinBlockSamples', 1,           @(x) isscalar(x) && x >= 1);
addParameter(p, 'SaveDir',         '');
addParameter(p, 'Verbose',         true,        @(x) islogical(x) || isnumeric(x));
parse(p, varargin{:});
o = p.Results;

chans   = cellstr(o.Channels);
figWant = lower(cellstr(o.Figures));
marks   = o.Marks(:).';

if isempty(o.Labels)
    if isequal(chans, {'ch2','ch3'})
        labels = {'C3','C4'};          % the usual motor-imagery pair
    else
        labels = chans;
    end
else
    labels = cellstr(o.Labels);
    if numel(labels) ~= numel(chans)
        error('plot_eeg_marks:labelCount', ...
              'Labels has %d entries but Channels has %d.', numel(labels), numel(chans));
    end
end

if ~isfile(csvFile)
    error('plot_eeg_marks:fileNotFound', 'File not found: %s', csvFile);
end

%% ------------------------------ load ----------------------------------
T = readtable(csvFile, 'VariableNamingRule', 'preserve');
[~, fileTag] = fileparts(csvFile);

missing = chans(~ismember(chans, T.Properties.VariableNames));
if ~isempty(missing)
    error('plot_eeg_marks:missingChannel', ...
          'Column(s) not in %s: %s\nAvailable: %s', ...
          fileTag, strjoin(missing, ', '), strjoin(T.Properties.VariableNames, ', '));
end
if ~ismember(o.MarkColumn, T.Properties.VariableNames)
    error('plot_eeg_marks:missingMark', ...
          'Marker column "%s" not in %s.', o.MarkColumn, fileTag);
end

X  = table2array(T(:, chans));
mk = T.(o.MarkColumn);
n  = size(X, 1);

%% --------------------- time vector and sampling rate ------------------
[t, fs] = buildTime(T, o, n);

%% ------------------------- dead-channel check -------------------------
dead = chans(range0(X));
if ~isempty(dead) && o.Verbose
    warning('plot_eeg_marks:deadChannel', ...
            'Channel(s) carry no signal (constant value): %s', strjoin(dead, ', '));
end

%% ----------------------- find contiguous blocks -----------------------
isTask = ismember(mk, marks);
d      = diff([0; isTask(:); 0]);
i1     = find(d ==  1);
i2     = find(d == -1) - 1;

keep = (i2 - i1 + 1) >= o.MinBlockSamples;
i1 = i1(keep);  i2 = i2(keep);

if isempty(i1)
    warning('plot_eeg_marks:noBlocks', ...
            'No runs of marks [%s] in %s.', num2str(marks), fileTag);
end

blocks = table(mk(i1), i1, i2, i2 - i1 + 1, (i2 - i1 + 1)/fs, t(i1), t(i2), ...
    'VariableNames', {'mark','i1','i2','nSamples','duration','tStart','tEnd'});

if o.Verbose
    fprintf('\n%s : %d samples, fs = %g Hz, %.1f s total\n', fileTag, n, fs, t(end));
    fprintf('%d block(s) for marks [%s]:\n', height(blocks), num2str(marks));
    disp(blocks);
end

%% ------------------------------ output --------------------------------
out = struct('file', csvFile, 'fs', fs, 't', t, 'X', X, ...
             'channels', {chans}, 'labels', {labels}, 'blocks', blocks, ...
             'marks', marks, 'dead', {dead}, 'figures', gobjects(0));
out.get = @(k) getBlock(out, k);

if ~o.Plot, return; end

%% ------------------------------ figures -------------------------------
nCh = numel(chans);
cmapCh = lines(max(nCh, 3));
figs = gobjects(0);

% ---- overview: whole recording, task blocks shaded --------------------
if ismember('overview', figWant)
    f = figure('Name', sprintf('%s - overview', fileTag), ...
               'NumberTitle', 'off', 'Color', 'w');
    ax = gobjects(nCh, 1);
    for c = 1:nCh
        ax(c) = subplot(nCh, 1, c); hold on;
        plot(t, X(:,c), 'LineWidth', 0.5, 'Color', cmapCh(c,:));
        shadeBlocks(ax(c), blocks, marks);
        ylabel(sprintf('%s (%s)', labels{c}, chans{c}));
        title(sprintf('%s - full recording, task blocks shaded', labels{c}));
        grid on; box on;
    end
    xlabel(ax(end), 'Time (s)');
    linkaxes(ax, 'x'); xlim(ax(1), [t(1) t(end)]);
    figs(end+1) = f;
end

% ---- one figure per mark value ----------------------------------------
if ismember('permark', figWant)
    for m = marks
        rows = find(blocks.mark == m);
        if isempty(rows)
            if o.Verbose, fprintf('No data for mark %d - skipped.\n', m); end
            continue
        end

        [tt, YY] = gatherRuns(t, X, blocks(rows,:));

        f = figure('Name', sprintf('%s - mark %d', fileTag, m), ...
                   'NumberTitle', 'off', 'Color', 'w');
        ax = gobjects(nCh, 1);
        for c = 1:nCh
            ax(c) = subplot(nCh, 1, c);
            plot(tt, YY(:,c), 'LineWidth', 0.6, 'Color', cmapCh(c,:));
            ylabel(sprintf('%s (%s)', labels{c}, chans{c}));
            grid on; box on;
            if c == 1
                title(sprintf('Mark %d - %s   [%d block(s), %.2f s]', ...
                      m, labels{c}, numel(rows), sum(blocks.duration(rows))));
            else
                title(sprintf('Mark %d - %s', m, labels{c}));
            end
        end
        xlabel(ax(end), 'Time (s)');
        linkaxes(ax, 'x');
        figs(end+1) = f; %#ok<AGROW>
    end
end

% ---- all channels overlaid with a vertical offset ---------------------
if ismember('overlay', figWant) && nCh > 1
    ref  = X(isTask, 1);
    ref  = ref(~isnan(ref));
    step = 6 * std(ref);
    if ~isfinite(step) || step == 0, step = 1; end

    f = figure('Name', sprintf('%s - channels offset', fileTag), ...
               'NumberTitle', 'off', 'Color', 'w');
    hold on;
    for c = 1:nCh
        for k = 1:height(blocks)
            r = blocks.i1(k):blocks.i2(k);
            plot(t(r), X(r,c) + (c-1)*step, 'Color', cmapCh(c,:), ...
                 'LineWidth', 0.5, 'HandleVisibility', 'off');
        end
        plot(NaN, NaN, 'Color', cmapCh(c,:), 'LineWidth', 1.5, ...
             'DisplayName', sprintf('%s (%s)', labels{c}, chans{c}));
    end
    legend('Location', 'northeast'); grid on; box on;
    xlabel('Time (s)');
    ylabel(sprintf('Amplitude (channels offset by %.3g)', step));
    title(sprintf('%s - task blocks only, channels offset', fileTag));
    figs(end+1) = f;
end

out.figures = figs;

%% ------------------------------- save ---------------------------------
if ~isempty(o.SaveDir)
    if ~isfolder(o.SaveDir), mkdir(o.SaveDir); end
    for k = 1:numel(figs)
        nm = matlab.lang.makeValidName(get(figs(k), 'Name'));
        fp = fullfile(o.SaveDir, [nm '.png']);
        try
            exportgraphics(figs(k), fp, 'Resolution', 150);
        catch
            saveas(figs(k), fp);         % older MATLAB
        end
    end
    if o.Verbose
        fprintf('Saved %d figure(s) to %s\n', numel(figs), o.SaveDir);
    end
end
end

%% ========================= local functions ============================

function [t, fs] = buildTime(T, o, n)
% Build a seconds-from-start time vector and work out the sampling rate.
    hasTime = ~isempty(o.TimeColumn) && ...
              ismember(o.TimeColumn, T.Properties.VariableNames) && ...
              ~strcmpi(o.TimeUnits, 'samples');

    if hasTime
        raw   = double(T.(o.TimeColumn));
        scale = struct('us', 1e-6, 'ms', 1e-3, 's', 1);
        t     = (raw - raw(1)) * scale.(lower(o.TimeUnits));
        if isempty(o.Fs)
            dt = median(diff(t));
            if dt <= 0
                error('plot_eeg_marks:badTime', ...
                      'Time column "%s" is not increasing.', o.TimeColumn);
            end
            fs = 1/dt;
        else
            fs = o.Fs;
        end
    else
        if isempty(o.Fs)
            error('plot_eeg_marks:noFs', ...
                  ['No usable time column, so Fs must be supplied: ' ...
                   'plot_eeg_marks(file, ''Fs'', 250).']);
        end
        fs = o.Fs;
        t  = (0:n-1)'/fs;
    end
    t = t(:);
end

function tf = range0(X)
% True for columns that never change (unwritten / dead channels).
    tf = false(1, size(X,2));
    for c = 1:size(X,2)
        col = X(~isnan(X(:,c)), c);
        tf(c) = isempty(col) || (max(col) - min(col)) == 0;
    end
end

function [tt, YY] = gatherRuns(t, X, blk)
% Concatenate several runs against real recording time, NaN between them,
% so separate blocks are never drawn as one continuous trace.
    tt = []; YY = zeros(0, size(X,2));
    for k = 1:height(blk)
        r  = blk.i1(k):blk.i2(k);
        tt = [tt; t(r);  NaN];                      %#ok<AGROW>
        YY = [YY; X(r,:); nan(1, size(X,2))];       %#ok<AGROW>
    end
end

function shadeBlocks(ax, blocks, marks)
% Translucent band behind each block, without disturbing the y-scale.
    cmap = lines(max(numel(marks), 3));
    yl   = ylim(ax);
    for k = 1:height(blocks)
        ci = find(marks == blocks.mark(k), 1);
        if isempty(ci), ci = 1; end
        x1 = blocks.tStart(k); x2 = blocks.tEnd(k);
        pa = patch(ax, [x1 x2 x2 x1], [yl(1) yl(1) yl(2) yl(2)], cmap(ci,:), ...
                   'FaceAlpha', 0.15, 'EdgeColor', 'none', 'HandleVisibility', 'off');
        uistack(pa, 'bottom');
        text(ax, mean([x1 x2]), yl(2)*0.92, sprintf('%d', blocks.mark(k)), ...
             'HorizontalAlignment', 'center', 'FontWeight', 'bold', ...
             'Color', cmap(ci,:)*0.7, 'Clipping', 'on');
    end
    ylim(ax, yl);
end

function b = getBlock(out, k)
% Pull one block's samples back out of the result struct.
    if k < 1 || k > height(out.blocks)
        error('plot_eeg_marks:badBlock', ...
              'Block %d requested but there are %d.', k, height(out.blocks));
    end
    r = out.blocks.i1(k):out.blocks.i2(k);
    b = struct('t', out.t(r), 'X', out.X(r,:), ...
               'mark', out.blocks.mark(k), 'channels', {out.channels});
end