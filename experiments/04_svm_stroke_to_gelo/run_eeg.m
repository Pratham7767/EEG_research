%% run_eeg_batch.m
%  Pick one or more CSV files from a dialog box and plot them.
%  Remembers the last folder you browsed to, so the dialog reopens there.

clear; clc; close all;

%% ---------------------- pick the file(s) ------------------------------
% Start the dialog wherever you were last time, else the current folder.
startDir = getpref('plotEegMarks', 'lastDir', pwd);
if ~isfolder(startDir), startDir = pwd; end

[fnames, pathName] = uigetfile( ...
    {'*.csv', 'CSV files (*.csv)'; '*.*', 'All files (*.*)'}, ...
    'Select one or more EEG csv files', ...
    fullfile(startDir, filesep), ...
    'MultiSelect', 'on');

if isequal(fnames, 0)
    fprintf('Cancelled - nothing selected.\n');
    return
end

fnames = cellstr(fnames);                       % one file comes back as a char row
setpref('plotEegMarks', 'lastDir', pathName);   % remember for next time

fprintf('Selected %d file(s) from %s\n', numel(fnames), pathName);

%% ------------------------- plot each one ------------------------------
results = struct('file', {}, 'out', {});

for k = 1:numel(fnames)
    fp = fullfile(pathName, fnames{k});
    fprintf('\n===== %s =====\n', fnames{k});

    try
        r = plot_eeg_marks(fp);          % add options here, see examples below
        results(end+1).file = fnames{k}; %#ok<SAGROW>
        results(end).out    = r;
    catch ME
        warning('Skipped %s: %s', fnames{k}, ME.message);
    end
end

fprintf('\nDone - %d of %d file(s) plotted.\n', numel(results), numel(fnames));

%% ======================= variations ===================================
% Everything below is commented out. Uncomment what you need.

%% ---- pick a whole FOLDER instead of individual files ------------------
% folder = uigetdir(startDir, 'Select the folder holding the CSV files');
% if isequal(folder, 0), return; end
% setpref('plotEegMarks','lastDir',folder);
% files = dir(fullfile(folder, '*.csv'));
% for k = 1:numel(files)
%     r = plot_eeg_marks(fullfile(files(k).folder, files(k).name), ...
%                        'SaveDir', fullfile(folder,'figs'));
%     close(r.figures);                  % keep the numbers, drop the windows
% end

%% ---- different channels / subset of marks -----------------------------
% r = plot_eeg_marks(fullfile(pathName, fnames{1}), ...
%                    'Channels', {'ch1','ch2','ch3','ch4'}, ...
%                    'Labels',   {'FC3','C3','C4','FC4'}, ...
%                    'Marks',    [1 2]);

%% ---- no figures, just the block table ---------------------------------
% r = plot_eeg_marks(fullfile(pathName, fnames{1}), 'Plot', false);
% disp(r.blocks);

%% ---- one combined block table across everything you loaded ------------
% allBlocks = table();
% for k = 1:numel(results)
%     b = results(k).out.blocks;
%     b.file = repmat(string(results(k).file), height(b), 1);
%     allBlocks = [allBlocks; b];       %#ok<AGROW>
% end
% disp(allBlocks);
% writetable(allBlocks, fullfile(pathName, 'block_summary.csv'));

%% ---- pull one block out for your own processing -----------------------
% b = results(1).out.get(1);            % struct with .t, .X, .mark, .channels
% figure; plot(b.t, b.X); legend(b.channels);
% xlabel('Time (s)'); title(sprintf('Block 1, mark %d', b.mark));