"""
ERD/ERS following Liu et al. 2024 + their plotERDERS.m / PlotEvent.m,
with parameters rescaled from 500 Hz to 250 Hz, plus the validity checks
the paper's own code does not do.
"""
import os
import numpy as np, pandas as pd
from scipy.signal import butter, filtfilt, lfilter
from scipy import stats
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

FS=250
PAD_PRE, PAD_POST = int(1.5*FS), int(4.5*FS)   # what was extracted
PRE, POST = 1*FS, 4*FS                          # what we plot: -1..+4 s
CROP0 = PAD_PRE - PRE                           # crop offset into padded epoch
BAND=(8.,30.); ORDER=2
SMOOTH_N = int(round(0.4*FS))                   # 200 @500Hz -> 0.4 s -> 100 @250Hz
C3, C4 = 1, 2                                   # ch2=C3, ch3=C4 (A1,C3,C4,A2)

def bandpass(x, zero_phase=True):
    b,a = butter(ORDER, [BAND[0]*2/FS, BAND[1]*2/FS], btype="band")
    return filtfilt(b,a,x,axis=0) if zero_phase else lfilter(b,a,x,axis=0)

def movmean(x,n):
    n = int(n) + (1-int(n)%2)
    half=n//2; out=np.empty(len(x))
    for i in range(len(x)):
        w=min(i-max(0,i-half), min(len(x),i+half+1)-1-i)
        out[i]=x[i-w:i+w+1].mean()
    return out

def curve(epochs, ch, zero_phase=True, baseline="paper"):
    """Returns the ERD/ERS % curve cropped to -1..+4 s."""
    acc=np.zeros(epochs.shape[1])
    for tr in epochs: acc += bandpass(tr,zero_phase)[:,ch]**2
    avg = movmean(acc/len(epochs), SMOOTH_N)
    avg = avg[CROP0:CROP0+PRE+POST]             # crop AFTER filter+smooth
    M = avg[:PRE].mean() if baseline=="paper" else avg[PRE:PRE+FS].mean()
    return (avg-M)/M*100.0

def trial_erd(epochs, ch):
    """Per-trial mean ERD% over 0-4 s -> lets us test the effect statistically."""
    out=[]
    for tr in epochs:
        p = movmean(bandpass(tr)[:,ch]**2, SMOOTH_N)[CROP0:CROP0+PRE+POST]
        M = p[:PRE].mean()
        out.append((p[PRE:].mean()-M)/M*100.0)
    return np.array(out)

def panel(ax, ep, title, **kw):
    t=(np.arange(PRE+POST)-PRE)/FS
    c3,c4 = curve(ep,C3,**kw), curve(ep,C4,**kw)
    ax.plot(t,c3,"r--",lw=1.1,label="C3"); ax.plot(t,c4,"b-",lw=1.1,label="C4")
    ax.axvline(0,color=".6",lw=.8,zorder=0); ax.axhline(0,color=".85",lw=.8,zorder=0)
    m=np.r_[c3[PRE:],c4[PRE:]]
    ax.set_xlim(0,4); ax.set_ylim(m.min()-10,m.max()+5); ax.set_xticks([0,1,2,3,4])
    ax.set_title(f"{title}  (n={len(ep)})",fontsize=11)
    ax.set_xlabel("Time(s)",fontsize=11); ax.set_ylabel("ERD/ERS %",fontsize=11)
    ax.legend(loc="lower left",ncol=2,frameon=False,fontsize=8)
    return c3,c4

def figure(L,R,fn,sup,**kw):
    fig,ax=plt.subplots(2,1,figsize=(5.2,6.4))
    a=panel(ax[0],L,"MI with Left Hand",**kw); b=panel(ax[1],R,"MI with Right Hand",**kw)
    fig.suptitle(sup,fontsize=12); fig.tight_layout(rect=[0,0,1,.97])
    fig.savefig(fn,dpi=160); plt.close(fig); return a,b

HERE = os.path.dirname(os.path.abspath(__file__))
z=np.load(os.path.join(HERE, "epochs.npz"))
X,cls,src = z["X"].astype(float), z["cls"], z["srcfile"]
L,R = X[cls=="left"], X[cls=="right"]
print(f"epochs: left {L.shape}, right {R.shape}; smoothing {SMOOTH_N} samples = 0.4 s")

# ---------- 1. main figure, paper's method ----------
(c3l,c4l),(c3r,c4r) = figure(L,R,os.path.join(HERE, "erd_pooled.png"),
        "Gelo BCI - C3/C4, 8-30 Hz, paper's method (Fs=250 Hz)")

# ---------- 2. is the contralateral pattern real? ----------
print("\n=== per-trial mean ERD% over 0-4 s (negative = activation) ===")
res=[]
for nm,ep,contra,ipsi in [("Left hand",L,C4,C3),("Right hand",R,C3,C4)]:
    a,b = trial_erd(ep,contra), trial_erd(ep,ipsi)   # contra, ipsi
    d = a-b                                           # expect < 0
    t,p = stats.ttest_rel(a,b)
    w = stats.wilcoxon(a,b).pvalue
    res.append(dict(task=nm,n=len(ep),contra_mean=a.mean(),ipsi_mean=b.mean(),
                    diff=d.mean(),t=t,p_ttest=p,p_wilcoxon=w))
df=pd.DataFrame(res)
print(df.to_string(index=False,float_format=lambda v:f"{v:9.3f}"))
print("\nA real contralateral ERD needs diff < 0 AND p < 0.05 in BOTH rows.")

# ---------- 3. laterality index: can it separate the two classes at all? ----------
li_L = trial_erd(L,C3)-trial_erd(L,C4)
li_R = trial_erd(R,C3)-trial_erd(R,C4)
u,pu = stats.mannwhitneyu(li_L,li_R)
print(f"\n=== laterality index (C3-C4) per trial ===")
print(f"left-hand trials : {li_L.mean():7.2f} +/- {li_L.std():.2f}")
print(f"right-hand trials: {li_R.mean():7.2f} +/- {li_R.std():.2f}")
print(f"Mann-Whitney U p = {pu:.4f}   (expect left > right if contralateral holds)")

# ---------- 4. paper-text baseline vs their code's baseline ----------
figure(L,R,os.path.join(HERE, "erd_codebaseline.png"),
       "Same data, baseline as in PlotEvent.m (0-1 s) instead of -1..0 s",
       baseline="code")
# ---------- 5. zero-phase vs the causal filter their code actually uses ----------
figure(L,R,os.path.join(HERE, "erd_causal.png"),
       "Same data, causal filter() as in filter_param.m (not zero-phase)",
       zero_phase=False)

# ---------- 6. per-session ----------
fig,axes=plt.subplots(5,2,figsize=(10,15))
lf=sorted(set(src[cls=="left"].tolist())); rf=sorted(set(src[cls=="right"].tolist()))
for i in range(5):
    panel(axes[i,0], X[(cls=="left")&(src==lf[i])], f"Left - {lf[i]}")
    panel(axes[i,1], X[(cls=="right")&(src==rf[i])], f"Right - {rf[i]}")
fig.suptitle("Per-session ERD/ERS (first 5 sessions each)",fontsize=13)
fig.tight_layout(rect=[0,0,1,.975]); fig.savefig(os.path.join(HERE, "erd_per_session.png"),dpi=140)
plt.close(fig)
df.to_csv(os.path.join(HERE, "erd_stats.csv"),index=False)
print("\nwrote erd_pooled.png, erd_codebaseline.png, erd_causal.png, erd_per_session.png, erd_stats.csv")
