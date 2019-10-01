import hashlib
import logging
import warnings

import numpy as np
import pandas as pd
from sklearn import datasets

from gamma.ml import Sample
from gamma.ml.predictioncv import RegressorPredictionCV
from gamma.ml.selection import (
    ClassifierRanker,
    ParameterGrid,
    RegressorRanker,
    Validation,
)
from gamma.ml.validation import CircularCV
from gamma.sklearndf.classification import SVCDF
from gamma.sklearndf.pipeline import ClassifierPipelineDF

log = logging.getLogger(__name__)

CHKSUM_SUMMARY_REPORT = "925b6623fa1b10bee69cb179b03a6c52"


def test_model_ranker(
    batch_table: pd.DataFrame, regressor_grids, sample: Sample, n_jobs
) -> None:
    # define the circular cross validator with just 5 splits (to speed up testing)
    circular_cv = CircularCV(test_ratio=0.20, n_splits=5)

    ranker = RegressorRanker(
        grid=regressor_grids, sample=sample, cv=circular_cv, scoring="r2", n_jobs=n_jobs
    )
    assert isinstance(ranker.best_model_predictions, RegressorPredictionCV)

    ranking = ranker.ranking()
    assert len(ranking) > 0
    assert isinstance(ranking[0], Validation)
    assert (
        ranking[0].ranking_score
        >= ranking[1].ranking_score
        >= ranking[2].ranking_score
        >= ranking[3].ranking_score
        >= ranking[4].ranking_score
        >= ranking[-1].ranking_score
    )

    # check if parameters set for estimators actually match expected:
    for validation in ranker.ranking():
        assert set(validation.pipeline.get_params()).issubset(
            validation.pipeline.get_params()
        )

    assert CHKSUM_SUMMARY_REPORT == (
        hashlib.md5(ranker.summary_report().encode("utf-8")).hexdigest()
    )


def test_model_ranker_no_preprocessing(n_jobs) -> None:
    warnings.filterwarnings("ignore", message="numpy.dtype size changed")
    warnings.filterwarnings("ignore", message="numpy.ufunc size changed")
    warnings.filterwarnings("ignore", message="You are accessing a training score")

    # define a yield-engine circular CV:
    cv = CircularCV(test_ratio=0.21, n_splits=50)

    # define parameters and pipeline
    models = [
        ParameterGrid(
            pipeline=ClassifierPipelineDF(
                classifier=SVCDF(gamma="scale"), preprocessing=None
            ),
            learner_parameters={"kernel": ("linear", "rbf"), "C": [1, 10]},
        )
    ]

    #  load sklearn test-data and convert to pd
    iris = datasets.load_iris()
    test_data = pd.DataFrame(
        data=np.c_[iris["data"], iris["target"]],
        columns=iris["feature_names"] + ["target"],
    )
    test_sample: Sample = Sample(observations=test_data, target="target")

    model_ranker: ClassifierRanker = ClassifierRanker(
        grid=models, sample=test_sample, cv=cv, n_jobs=n_jobs
    )

    log.debug(f"\n{model_ranker.summary_report(max_learners=10)}")

    assert (
        model_ranker.ranking()[0].ranking_score >= 0.8
    ), "expected a best performance of at least 0.8"
