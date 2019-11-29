"""
Core implementation of :mod:`gamma.ml.validation`
"""

from abc import abstractmethod
from typing import *

import numpy as np
import pandas as pd
from sklearn.model_selection import BaseCrossValidator
from sklearn.utils import check_random_state

from gamma.common import deprecated

__all__ = ["BootstrapCV", "CircularCV", "StationaryBootstrapCV"]


class _BaseBootstrapCV(BaseCrossValidator):
    """
    Base class for bootstrap cross-validators. Do not instantiate this class directly.
    :param n_splits: Number of splits to generate (default: 100)
    :param random_state: random state to initialise the random generator with (optional)
    """

    def __init__(
        self,
        n_splits: int = 100,
        random_state: Optional[Union[int, np.random.RandomState]] = None,
    ):
        self.n_splits = n_splits
        self.random_state = random_state

    # noinspection PyPep8Naming
    def get_n_splits(
        self,
        X: Optional[Union[np.ndarray, pd.DataFrame]] = None,
        y: Optional[Union[np.ndarray, pd.Series, pd.DataFrame]] = None,
        groups: Sequence = None,
    ) -> int:
        """
        Return the number of splits generated by this cross-validator

        :param X: for compatibility only, not used
        :param y: for compatibility only, not used
        :param groups: for compatibility only, not used
        :return: the number of splits
        """
        return self.n_splits

    # noinspection PyPep8Naming
    def _iter_test_indices(
        self,
        X: Optional[Union[np.ndarray, pd.DataFrame]] = None,
        y: Optional[Union[np.ndarray, pd.Series, pd.DataFrame]] = None,
        groups: Sequence = None,
    ):
        pass

    # noinspection PyPep8Naming
    def split(
        self,
        X: Union[np.ndarray, pd.DataFrame],
        y: Union[np.ndarray, pd.Series, pd.DataFrame] = None,
        groups: Sequence = None,
    ) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        """Generate indices to split data into training and test set.

        :param X: features
        :param y: target
        :param groups: not used
        :return a generator yielding `(train, test)` tuples where train and test are \
            NumPy arrays with train/test indices
        """

        n = len(X)

        if y is not None and n != len(y):
            raise ValueError("args X and y must have the same length")
        if n < 2:
            raise ValueError("args X and y must have a length of at least 2")

        rs = check_random_state(self.random_state)
        indices = np.arange(n)
        for i in range(self.n_splits):
            while True:
                train = self._select_train_indices(n, rs)
                test_mask = np.ones(len(indices), dtype=bool)
                test_mask[train] = False
                test = indices[test_mask]
                # make sure test is not empty, else sample another train set
                if len(test) > 0:
                    yield train, test
                    break

    @abstractmethod
    def _select_train_indices(
        self, n_samples: int, random_state: np.random.RandomState
    ) -> np.ndarray:
        """
        :param n_samples: number of indices to sample
        :param random_state: random state object to be used for random sampling
        :return: an array of integer indices with shape `[n_samples]`
        """
        pass


class BootstrapCV(_BaseBootstrapCV):
    """
    Bootstrapping cross-validation.

    Generates CV splits by random sampling with replacement. The resulting train set
    is the same size as the total sample; the test set consists of all samples not
    included in the training set.

    Permissible as the `cv` argument of :class:`sklearn.model_selection.GridSearchCV`
    object.

    :param n_splits: Number of splits to generate (default: 50)
    :param random_state: random state to initialise the random generator with (optional)
    """

    def __init__(
        self,
        n_splits: int = 100,
        random_state: Optional[Union[int, np.random.RandomState]] = None,
        stratify: Optional[Sequence] = None,
    ) -> None:
        super().__init__(n_splits=n_splits, random_state=random_state)

    def _select_train_indices(
        self, n_samples: int, random_state: np.random.RandomState
    ) -> np.ndarray:
        return random_state.randint(n_samples, size=n_samples)


class StationaryBootstrapCV(_BaseBootstrapCV):
    """
    Bootstrap for stationary time series, based on Politis and Romano (1994).

    This bootstrapping approach samples blocks with exponentially distributed sizes,
    instead of individual random observations as is the case with the regular bootstrap.

    Intended for use with time series that satisfy the stationarity requirement.

    Permissible as the `cv` argument of :class:`sklearn.model_selection.GridSearchCV`
    object.

    :param n_splits: Number of splits to generate (default: 50)
    :param mean_block_size: mean size of coherent blocks to sample.\
        If an `int`, use this as the absolute number of blocks. If a `float`, must be \
        in the range (0.0, 1.0) and denotes a block size relative to the total number \
        samples. (default: 0.5)
    :param random_state: random state to initialise the random generator with (optional)
    """

    def __init__(
        self,
        n_splits: int = 100,
        mean_block_size: Union[int, float] = 0.5,
        random_state: Optional[Union[int, np.random.RandomState]] = None,
    ) -> None:
        super().__init__(n_splits=n_splits, random_state=random_state)
        if isinstance(mean_block_size, int):
            if mean_block_size < 2:
                raise ValueError(
                    f"arg mean_block_size={mean_block_size} must be at least 2"
                )
        elif isinstance(mean_block_size, float):
            if mean_block_size <= 0.0 or mean_block_size >= 1.0:
                raise ValueError(
                    f"arg mean_block_size={mean_block_size} must be > 0.0 and < 1.0"
                )
        else:
            raise TypeError(f"invalid type for arg mean_block_size={mean_block_size}")

        self.mean_block_size = mean_block_size

    def _select_train_indices(
        self, n_samples: int, random_state: np.random.RandomState
    ) -> np.ndarray:

        mean_block_size = self.mean_block_size
        if mean_block_size < 1:
            # if mean block size was set as a percentage, calculate the actual mean
            # block size
            mean_block_size = n_samples * mean_block_size

        p_new_block = 1.0 / mean_block_size

        train = np.empty(n_samples, dtype=np.int64)

        for i in range(n_samples):
            if i == 0 or random_state.uniform() <= p_new_block:
                idx = random_state.randint(n_samples)
            else:
                # noinspection PyUnboundLocalVariable
                idx += 1
                if idx >= n_samples:
                    idx = 0
            train[i] = idx

        return train


class CircularCV(BaseCrossValidator):
    """
    Rolling circular cross-validation.

    Class to generate CV splits of train and test data sets using circular,
    equidistant blocks.

    Permissible as the `cv` argument of :class:`sklearn.model_selection.GridSearchCV`
    object.

    :param test_ratio:  Ratio determining the size of the test set (default=0.2).
    :param n_splits:   Number of splits to generate (default=50).
    """

    @deprecated(
        message="This cross-validator will be removed from a future release. Consider "
        "using BootstrapCV or StationaryBootstrapCV instead."
    )
    def __init__(self, test_ratio: float = 0.2, n_splits: int = 50) -> None:
        super().__init__()

        if not (0 < test_ratio < 1):
            raise ValueError(
                "Expected (0 < test_ratio < 1), but %d was given" % test_ratio
            )

        self.test_ratio = test_ratio
        self.n_splits = n_splits

    # noinspection PyPep8Naming
    def test_split_starts(self, X) -> Generator[int, None, None]:
        """
        Generate the start indices of the test splits.

        :param X: a feature matrix
        :return: generator of the first integer index of each test split
        """
        return (start for start, _ in self._test_split_bounds(self._n_samples(X)))

    def _test_split_bounds(
        self, n_samples: int
    ) -> Generator[Tuple[int, int], None, None]:
        """
        Generate the start and end indices of the test splits.

        :param n_samples: number of samples
        :return: generator of the first and last integer index of each test split
        """
        step = n_samples / self.n_splits
        test_size = max(1.0, n_samples * self.test_ratio)
        for split in range(self.n_splits):
            split_start = split * step
            yield (int(split_start), int(split_start + test_size))

    # noinspection PyPep8Naming
    @staticmethod
    def _n_samples(X=None, y=None) -> int:
        """
        Return the number of samples.

        :return: the number of samples in X and y
        """
        if X is not None:
            if y is not None and len(X) != len(y):
                raise ValueError("X and y must be the same length")
            return len(X)
        elif y is not None:
            return len(y)
        else:
            raise ValueError("Need to specify at least one of X or y")

    # noinspection PyPep8Naming
    def _iter_test_indices(
        self, X=None, y=None, groups=None
    ) -> Generator[np.array, None, None]:
        """
        Generate the indices of the test splits.

        Generator which yields the numpy arrays of the test_split indices.

        :param X: features (need to speficy if y is None)
        :param y: targets (need to specify if X is None)
        :param groups: not used in this implementation, which is solely based on
          num_samples, num_splits, test_ratio
        :return: Iterable (Generator of numpy arrays) of all test-sets
        """
        n_samples = self._n_samples(X, y)

        data_indices = np.arange(n_samples)

        for test_start, test_end in self._test_split_bounds(n_samples):
            data_indices_rolled = np.roll(data_indices, -test_start)
            test_indices = data_indices_rolled[: test_end - test_start]
            yield test_indices

    # noinspection PyPep8Naming
    def get_n_splits(self, X=None, y=None, groups=None) -> int:
        """
        Return the number of splits generated by this cross-validator

        :param X: not used
        :param y: not used
        :param groups: not used
        :return: the number of splits
        """
        return self.n_splits
