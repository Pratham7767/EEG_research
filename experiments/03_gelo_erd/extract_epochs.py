import pandas as pd, numpy as np, glob, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
B = os.path.join(HERE, '..', '..', 'data', 'gelo')   # contains left/ and right/
FS = 250
PRE, POST = int(1.5*FS), int(4.5*FS)   # pad: crop to -1..+4 AFTER filtering+smoothing
CH = ['ch1','ch2','ch3','ch4']  # A1, C3, C4, A2  (verified from headphones.py)

def fstart(p):
    return int(re.search(r'(\d+)_(\d+)', os.path.basename(p)).group(1))

X, meta = [], []
for cls in ['left','right']:
    for path in sorted(glob.glob(os.path.join(B,cls,'*.csv')), key=fstart):
        d = pd.read_csv(path)
        x = d[CH].to_numpy(dtype=np.float64)*1e6      # volts -> microvolts
        m = d['mark'].to_numpy().astype(int)
        fn = os.path.basename(path)
        for mk in range(1,6):
            idx = np.flatnonzero(m==mk)
            if idx.size==0:
                meta.append(dict(cls=cls,file=fn,mark=mk,status='MISSING',n_runs=0,
                                 dur_s=0,pre_rest_s=0,onset=-1)); continue
            onset = int(idx[0])                        # first sample of the click
            n_runs = 1+int((np.diff(idx)>1).sum())
            dur = idx.size/FS
            # how much contiguous mark==0 immediately precedes the onset
            j = onset-1; 
            while j>=0 and m[j]==0: j-=1
            pre_rest = (onset-1-j)/FS
            if onset < PRE or onset+POST > len(x):
                meta.append(dict(cls=cls,file=fn,mark=mk,status='EDGE',n_runs=n_runs,
                                 dur_s=dur,pre_rest_s=pre_rest,onset=onset)); continue
            if pre_rest < 1.5:
                meta.append(dict(cls=cls,file=fn,mark=mk,status='NO_BASELINE',n_runs=n_runs,
                                 dur_s=dur,pre_rest_s=pre_rest,onset=onset)); continue
            X.append(x[onset-PRE:onset+POST,:])        # (1250,4)
            meta.append(dict(cls=cls,file=fn,mark=mk,status='OK',n_runs=n_runs,
                             dur_s=dur,pre_rest_s=pre_rest,onset=onset))

X = np.asarray(X)                                      # (n_ok, 1250, 4)
md = pd.DataFrame(meta)
ok = md[md.status=='OK'].reset_index(drop=True)
np.savez_compressed(os.path.join(HERE, 'epochs.npz'),
                    X=X.astype(np.float32),
                    cls=ok['cls'].to_numpy().astype('U8'),
                    srcfile=ok['file'].to_numpy().astype('U32'),
                    mark=ok['mark'].to_numpy(),
                    fs=FS, pre=PRE, post=POST)
md.to_csv(os.path.join(HERE, 'epoch_meta.csv'), index=False)
print("epoch tensor:", X.shape, " (trials, samples, channels)")
print("\nstatus counts:\n", md.groupby(['cls','status']).size())
print("\nNOT OK:\n", md[md.status!='OK'].to_string(index=False))
print("\nkept per class:\n", ok.groupby('cls').size())
print("\niterations that were split into >1 run (mark toggled mid-trial):")
print(ok[ok.n_runs>1][['cls','file','mark','n_runs','dur_s']].to_string(index=False))
print("\npre-onset rest available (s): min %.2f  median %.2f" % (ok.pre_rest_s.min(), ok.pre_rest_s.median()))
