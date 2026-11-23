# Vendored Capsule wrapper — changes from upstream

Source: `eeg_headphones/Capsule_2.0.59/CapsuleAPI/Windows/Capsule Python/CapsuleClientPython`
DLL: `eeg_headphones/Capsule_2.0.59/CapsuleAPI/Windows/Lib/CapsuleClient.dll` (reports v2.0.40)

Only the modules this app uses were copied. Changes:

1. All intra-package imports made relative (`from Error import` → `from .Error import`).
2. `Emotions.py`: struct fields renamed to match `CEmotions.h`:
   `focus, chill, stress, anger` → `attention, relaxation, cognitiveLoad, cognitiveControl`.
   Layout is unchanged, so values are identical; only the names were wrong.
3. `Calibrator.calibrate()`: called `clCNFBCalibrator_CalibrateIndividualNFBQuick`; now calls
   `clCNFBCalibrator_CalibrateIndividualNFB` as intended.
4. `PSDData.get_band_lower/upper`: the DLL returns the edges swapped; both now return min/max of the pair.
5. `Device.disconnect()`: error struct now passed by reference with argtypes set.
6. `Productivity_Baselines.__init__`: assigned `self.relax` / `self.timestamp`, which are not struct
   fields, so imported relaxation baseline and timestamp silently stayed 0. Now sets
   `relaxation` / `timestampMilli`.

7. `EEGArtifacts.get_eeg_quality`: `restype` was `c_uint8`, but `clCEEGArtifacts_GetEEGQuality`
   returns `float` (CEEGArtifacts.h), so every value was misread (real sessions showed a constant 2).

Not copied: MEMS, PhysiologicalStates, main.py, example.py, docs, non-Windows builds.
