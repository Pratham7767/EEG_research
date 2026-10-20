%% plot_rep_trials_v2.m
%  Representative single-trial mu-band activity at C3 and C4 for left- and
%  right-hand motor imagery, with the figure caption rendered on the figure.
%
%  The two trials are NOT the most convincing ones. Each is the trial whose
%  mu lateralization index is closest to the median of its own condition
%  (n = 22 left, 51 right), so they are typical rather than best-case.

clear; clc; close all;

%% ----------------------------- config ---------------------------------
ROOT   = 'D:\trainsvm\data\gelo';
PICK   = { 'left',  fullfile(ROOT,'left', 'Left1_5.csv'),    1
           'right', fullfile(ROOT,'right','right36_40.csv'), 5 };
BAND   = [8 13];      % mu
WIN_S  = 4;           % seconds from trial onset
MASK_S = 15;          % initial amplifier settling transient to neutralise
FIGPNG = fullfile(fileparts(mfilename('fullpath')),'representative_trials_v2.png');

BLUE = [0.145 0.388 0.922];   ORANGE = [0.878 0.388 0.184];
INK  = [0.11 0.11 0.10];      MUT    = [0.54 0.53 0.50];
GRIDC= [0.90 0.89 0.87];      SURF   = [0.988 0.988 0.984];

%% ----------------------------- figure ---------------------------------
f = figure('Color',SURF,'Position',[80 80 1180 520], ...
           'Name','Representative single trials','NumberTitle','off');
tl = tiledlayout(f,1,2,'TileSpacing','compact','Padding','compact');

ax = gobjects(1,2);
for k = 1:size(PICK,1)
    cond = PICK{k,1};  fp = PICK{k,2};  mk = PICK{k,3};

    if ~isfile(fp), error('File not found: %s', fp); end
    T  = readtable(fp,'VariableNamingRule','preserve');
    fs = 1e6/median(diff(T.timestamp));          % timestamps are microseconds

    i1 = find(T.mark == mk, 1, 'first');
    if isempty(i1), error('Mark %d not present in %s', mk, fp); end
    i2 = i1 + round(WIN_S*fs) - 1;
    if i2 > height(T), error('Trial %d in %s is shorter than %g s', mk, fp, WIN_S); end

    [b,a] = butter(4, BAND/(fs/2), 'bandpass');
    nmask = round(MASK_S*fs);

    ax(k) = nexttile; hold(ax(k),'on');
    cols  = {BLUE, ORANGE};  names = {'C3','C4'};  srcs = {'ch2','ch3'};
    for c = 1:2
        x = T.(srcs{c});
        x(1:nmask) = median(x(nmask+1:end));       % kill the startup transient
        y   = filtfilt(b,a,x);                     % zero-phase band-pass
        env = abs(hilbert(y));                     % amplitude envelope
        tt  = (0:(i2-i1))/fs;
        plot(ax(k), tt, y(i1:i2)*1e6,   'Color',[cols{c} 0.45], 'LineWidth',0.9, ...
             'HandleVisibility','off');            % keep thin traces out of the legend
        plot(ax(k), tt, env(i1:i2)*1e6, 'Color',cols{c},        'LineWidth',2.2, ...
             'DisplayName',[names{c} ' envelope']);
    end

    grid(ax(k),'on'); box(ax(k),'off');
    ax(k).GridColor = GRIDC;  ax(k).GridAlpha = 1;
    ax(k).XColor = MUT; ax(k).YColor = MUT; ax(k).Color = SURF;
    xlim(ax(k),[0 WIN_S]);
    xlabel(ax(k),'Time from trial onset (s)');
    [~,nm,ext] = fileparts(fp);
    title(ax(k), sprintf('%s-hand imagery   |   %s%s, trial %d', cond, nm, ext, mk), ...
          'Color',INK,'FontWeight','bold','FontSize',10.5,'Interpreter','none');
    lg = legend(ax(k),'Location','northeast'); lg.Box = 'off'; lg.TextColor = MUT;
end
ylabel(ax(1),'mu-band amplitude (\muV)');
linkaxes(ax,'xy');

title(tl,'Representative single trials - mu band (8-13 Hz) at C3 and C4', ...
      'Color',INK,'FontWeight','bold','FontSize',13.5);

%% ---------------------------- caption ---------------------------------
caption = [ ...
'Figure 1.  Representative single-trial mu-band (8-13 Hz) activity at C3 and C4 during motor imagery.  Left: left-hand imagery ', ...
'(Left1_5.csv, trial 1).  Right: right-hand imagery (right36_40.csv, trial 5).  Each panel shows the first 4 s from trial onset; thin ', ...
'traces are the band-pass filtered signal (4th-order Butterworth, zero-phase via filtfilt) and thick traces the Hilbert amplitude ', ...
'envelope.  Each trial is the one whose mu lateralization index lies closest to the median of its own condition (n = 22 left, 51 right), ', ...
'so both are typical rather than best-case examples.  Sampling rate 250 Hz; the first 15 s of each recording were excluded to avoid the ', ...
'amplifier settling transient.'];

annotation(f,'textbox',[0.015 0.008 0.970 0.125],'String',caption, ...
    'EdgeColor','none','Color',[0.33 0.32 0.31],'FontSize',8.8, ...
    'VerticalAlignment','top','HorizontalAlignment','left', ...
    'FitBoxToText','off','Interpreter','none');
tl.Padding = 'compact';
set(tl,'OuterPosition',[0 0.15 1 0.85]);

fprintf('\n%s\n\n', caption);

exportgraphics(f, FIGPNG, 'Resolution', 200);
fprintf('Figure written to %s\n', FIGPNG);
