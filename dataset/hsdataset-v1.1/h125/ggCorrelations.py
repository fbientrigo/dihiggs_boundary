#%%
import pandas as pd
import numpy as np


def corr2017():
    """
    The correlation matrix of the ggF theory uncertainties between different
    STXS bins in the 2017 scheme from
    http://dgillber.web.cern.ch/dgillber/ggF_uncertainty_2017/.
    """
    bins = [
        ">=1j",
        ">=1j_>120",
        ">=1j_>60",
        ">=1j_>200",
        ">=1j_120_200",
        ">=1j_60_200",
        ">=2j",
        "1j",
        ">=2j_>200",
        ">=2j_120_200",
        ">=2j_60_120",
        ">=2j_0_60",
        "1j_>200",
        "1j_120_200",
        "1j_60_120",
        "1j_0_60",
        "0j",
        "VBF_3j",
        "VBF_3jv",
    ]

    dat = [
        [100, -30, 0, 1, -2, -1, 0, 1, 0, 0, 0, 0, 7, 2, 2, 0, 2, 2, 4],
        [-30, 100, 0, -1, -1, 4, 5, 0, 0, 3, 4, 0, 8, 6, 11, 4, 6, 9, 5],
        [0, 0, 100, -16, -16, -12, -9, 12, 13, 11, 9, -18, 13, -3, 4, 6, -2, 4, -7],
        [1, -1, -16, 100, 74, 36, 27, 9, 0, -15, -18, 93, -3, 46, 2, -9, 41, -1, 76],
        [-2, -1, -16, 74, 100, 77, 61, -9, -1, 6, 8, 93, -1, 73, 36, 21, 69, 32, 77],
        [-1, 4, -12, 36, 77, 100, 90, -17, -1, 35, 42, 64, 8, 70, 70, 57, 71, 68, 58],
        [0, 5, -9, 27, 61, 90, 100, -15, -1, 36, 57, 51, 11, 59, 67, 72, 63, 70, 48],
        [1, 0, 12, 9, -9, -17, -15, 100, 97, 75, 60, 0, 93, 52, 47, 47, 53, 48, 53],
        [0, 0, 13, 0, -1, -1, -1, 97, 100, 87, 73, -1, 98, 63, 64, 61, 65, 64, 55],
        [0, 3, 11, -15, 6, 35, 36, 75, 87, 100, 92, -2, 92, 71, 91, 87, 76, 91, 51],
        [0, 4, 9, -18, 8, 42, 57, 60, 73, 92, 100, -2, 81, 66, 88, 98, 72, 93, 45],
        [0, 0, -18, 93, 93, 64, 51, 0, -1, -2, -2, 100, -1, 65, 24, 10, 60, 20, 82],
        [7, 8, 13, -3, -1, 8, 11, 93, 98, 92, 81, -1, 100, 66, 73, 71, 69, 74, 56],
        [2, 6, -3, 46, 73, 70, 59, 52, 63, 71, 66, 65, 66, 100, 83, 70, 100, 81, 91],
        [2, 11, 4, 2, 36, 70, 67, 47, 64, 91, 88, 24, 73, 83, 100, 90, 87, 99, 62],
        [0, 4, 6, -9, 21, 57, 72, 47, 61, 87, 98, 10, 71, 70, 90, 100, 76, 95, 49],
        [2, 6, -2, 41, 69, 71, 63, 53, 65, 76, 72, 60, 69, 100, 87, 76, 100, 86, 89],
        [2, 9, 4, -1, 32, 68, 70, 48, 64, 91, 93, 20, 74, 81, 99, 95, 86, 100, 59],
        [4, 5, -7, 76, 77, 58, 48, 53, 55, 51, 45, 82, 56, 91, 62, 49, 89, 59, 100],
    ]
    dat = np.array(dat)
    assert np.all(dat == dat.T)
    assert np.all(dat.diagonal() == 100)
    return pd.DataFrame(
        index=bins[::-1], columns=bins[::-1], data=np.round(1e-2 * dat, 2)
    )


def ggTheoryCorrMat(binMapping, corrmatExp):
    """
    Create a correlation matrix with the same shape and bin-names as the
    provided corrmatExp, where for all bins specified in the binMapping, the
    corresponding entries are taken from the corr2017 theory correlation matrix.
    The binMapping is a dictionary where the keys are the bin names in the
    corrmatExp and the values are the corresponding bin names in the corr2017
    matrix.
    """
    corrmatTheo = pd.DataFrame(
        np.identity(len(corrmatExp)), index=corrmatExp.index, columns=corrmatExp.columns
    )

    corrmatTheo = pd.DataFrame(
        index=corrmatExp.index,
        columns=corrmatExp.index,
        data=np.identity(len(corrmatExp.index)),
    )
    corrmatTheo.loc[binMapping.keys(), binMapping.keys()] = (
        corr2017().loc[binMapping.values(), binMapping.values()].to_numpy()
    )
    return corrmatTheo


# %%
