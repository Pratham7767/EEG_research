import numpy as np
import pandas as pd
from gelo_svm import DIR, permutation_test
import os

if __name__ == "__main__":
    null = permutation_test("svm_tangent", 100)
    obs = pd.read_csv(os.path.join(DIR, "svm_results.csv")).query(
        "model == 'svm_tangent' and validation == 'by_file'")["window_bal_acc"].iat[0]
    print(f"observed {obs:.1f} %, null mean {null.mean():.1f} %, 95th pct {np.percentile(null, 95):.1f} %, "
          f"p = {(1 + (null >= obs).sum()) / (1 + len(null)):.3f}")
