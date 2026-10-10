import json
from pathlib import Path

import pytest

from greenghar.ml.features import ENERGY_FEATURES, FORBIDDEN, VALUE_FEATURES, prepare
from greenghar.ml.train import RANK_FEATURES

MODELS = Path(__file__).resolve().parent.parent / "models"


@pytest.mark.parametrize("features", [ENERGY_FEATURES, VALUE_FEATURES, RANK_FEATURES])
def test_no_forbidden_features(features):
    assert not FORBIDDEN.intersection(features)


def test_prepare_rejects_forbidden():
    import pandas as pd
    with pytest.raises(ValueError):
        prepare(pd.DataFrame({"kwh_24m": [1]}), ["kwh_24m"])


@pytest.mark.parametrize("name", ["energy_hybrid", "ranker", "value_hedonic"])
def test_saved_models_have_clean_feature_lists(name):
    meta = MODELS / f"{name}.json"
    if not meta.exists():
        pytest.skip("models not trained")
    feats = json.loads(meta.read_text())["features"]
    assert not FORBIDDEN.intersection(feats)
    assert "price_inr" not in feats and "score_at_sale" not in feats


def test_splits_are_disjoint():
    import numpy as np
    from greenghar.ml.train import split_ids
    tr, va, te = split_ids(np.array([f"H{i}" for i in range(1000)]))
    assert not (tr & va or tr & te or va & te) and len(tr | va | te) == 1000
