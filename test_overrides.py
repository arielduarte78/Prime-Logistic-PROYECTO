import pandas as pd
import numpy as np
import logging
from src.bloque3.bayesian_judge import BayesianJudge

logging.basicConfig(level=logging.INFO)

judge = BayesianJudge(prior=None)
# _arc_index requires keys to exist
judge._arc_index = {(100, 200): 0, (300, 400): 1}
judge._alphas = np.ones(2, dtype=np.float32)
judge._betas = np.ones(2, dtype=np.float32)

df = pd.DataFrame({
    "u_rx": [100, 300, 500],
    "v_rx": [200, 400, 600],
    "alpha_degraded": [1.0, 1.0, 1.0],
    "beta_degraded": [50.0, 60.0, 70.0]
})

judge.load_stochastic_overrides(df, {})
