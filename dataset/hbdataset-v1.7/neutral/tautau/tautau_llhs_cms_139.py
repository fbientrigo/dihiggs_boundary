import pandas as pd
import numpy as np
from Higgs.tools.ExclusionLlh import regularizeExclusionLlh, commonRatePlane
from Higgs.tools.ExclusionLlh import commonRatePlane
from Higgs.tools.Inspire import getMetadata
import pickle
import json
import os, sys
from collections import OrderedDict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.getcwd())))
import MassResolutions as resolution


numpoints = 100


# baseurl = "https://www.hepdata.net/download/table/ins2132368/Table%20Aux.%20Figure%20"
# --> Individual download of hepData csv tables does not work, because the files
#     are too large. Instead download all files together by using download-all button
#     and save the tables in a folder called HEPData-ins2132368-v1-csv.
basepath = [
    "HEPData-ins2132368-v1-csv/TableFigure",
    "HEPData-ins2132368-v1-csv/TableAux.Figure"
]

# Create folder for modified datatables
newbasepath = "HEPData-ins2132368mod/"
if not os.path.exists(newbasepath):
    os.makedirs(newbasepath[0:-1])

# Mass hypothesis considered in search
masses_obs = {
    60: "11a",
    80: "41",
    95: "42",
    100: "11b",
    120: "43",
    125: "11c",
    130: "44",
    140: "45",
    160: "11d",
    180: "46",
    200: "47",
    250: "11e",
    300: "48",
    350: "49",
    400: "50",
#   450: "51", # Something goes wrong with this file
    500: "11f",
    600: "52",
    700: "53",
    800: "54",
    900: "55",
    1000: "11g",
    1200: "11h",
    1400: "56",
    1600: "57",
    1800: "58",
    2000: "59",
    2300: "60",
    2600: "61",
    2900: "62",
    3200: "63",
    3500: "11i"
}
masses_exp = {k: v + "Asimov" for k, v in masses_obs.items()}


# Function to read the original data files
def getTable(i):
    if len(i) in [3, 9]:
        df = pd.read_csv(basepath[0] + i + ".csv", comment="#")
    elif len(i) in [2, 8]:
        df = pd.read_csv(basepath[1] + i + ".csv", comment="#")
    return df


# Function to read the data files with regular grids
def getTablenew(a, m):
    df = pd.read_csv(newbasepath + a + "llhscms139" + str(m) + ".csv", comment="#")
    return df


# Creates new datafiles with a regular grid form in gg
# and bb cross sections. If the data is not in the form
# of a regular grid, than HiggsTools gives arrays.
# The new datafiles are obtained by means of
# a linear interpolation of the original data taking
# into account the neighbouring points
def make_regular_grid(dg, mode='obs'):
    df = dg.sort_values(by=['gg', 'bb']) # , inplace=True)
    ggmin = df['gg'].min()
    ggmax = df['gg'].max()
    bbmin = df['bb'].min()
    bbmax = df['bb'].max()
    ggrange = np.linspace(ggmin, ggmax, num=numpoints, endpoint=True)
    bbrange = np.linspace(bbmin, bbmax, num=numpoints, endpoint=True)
    data = []
    for bb in bbrange:
        for gg in ggrange:
            dc = {
                'gg': gg,
                'bb': bb,
                mode: extract_val(gg, bb, df, mode)
            }
            data.append(dc)
    dftemp = pd.DataFrame(data)
    return dftemp


# Extract an interpolated value of the likelyhood from
# the original data by means of a linear interpolation
# of the original data
def extract_val(gg, bb, df, mode):
    ll, gga, bba = extract_val_ll(gg, bb, df, mode)
    hh, ggb, bbb = extract_val_hh(gg, bb, df, mode)
    if ((gga is None) or (ggb is None)):
        y2 = (ll + hh) / 2.
    else:
        x = np.sqrt(gg**2 + bb**2)
        a = np.sqrt(gga**2 + bba**2)
        A = ll
        b = np.sqrt(ggb**2 + bbb**2)
        B = hh
        if not a == b:
            m = (A - B) / (a - b)
            n = (b * A - a * B) / (b - a)
            y2 = m * x + n
        else:
            y2 = ll
    return y2


# Extracts the value of the likelyhood for the
# values of bb and gg just below their values
# at which the interpolated value shoul be extracted
def extract_val_ll(gg, bb, df0, mode):
    df0.sort_values(by=['gg', 'bb'], inplace=True, ascending=True)
    df = df0[df0['gg'] >= gg]
    df = df[df['bb'] >= bb]
    try:
        y = df.iloc[0][mode]
        gga = df.iloc[0]['gg']
        bba = df.iloc[0]['bb']
    except IndexError:
        y = df0[mode].max()
        gga = None
        bba = None
    return y, gga, bba


# Extracts the value of the likelyhood for the
# values of bb and gg just above their values
# at which the interpolated value shoul be extracted
def extract_val_hh(gg, bb, df0, mode):
    df0.sort_values(by=['gg', 'bb'], inplace=True, ascending=False)
    df = df0[df0['gg'] <= gg]
    df = df[df['bb'] <= bb]
    try:
        y = df.iloc[0][mode]
        ggb = df.iloc[0]['gg']
        bbb = df.iloc[0]['bb']
    except IndexError:
        y = df0[mode].max()
        ggb = None
        bbb = None
    return y, ggb, bbb


# A simplified version of the regularization of
# the likelyhood distribution for the cases in
# which vanishing signal rates are excluded.
# This function sets the likelyhood to 1 for
# all signal rates that are:
#    1. Either gg or bb is below the best-fit
#       signal rate 
#    2. At the same time either bb or gg is below
#       the largest bb/gg value within the 
#       original allowed region.
def simpleregularizeExclusionLlh(o):
    obsmin = o["obs"].min()
    obest = o[o["obs"] == obsmin]
    ggbest = obest["gg"].item()
    bbbest = obest["bb"].item()
    otemp = o[o["obs"] < 4.61]
    if ggbest < 1e-5:
        ggbest = otemp["gg"].max()
    if bbbest < 1e-5:
        bbbest = otemp["bb"].max()
    dcs = []
    for i, r in o.iterrows():
        dc = {"gg": r["gg"], "bb": r["bb"]}
        obs = r["obs"]
        if r["obs"] > 2.3:
            if (r["gg"] < ggbest) and (r["bb"] < bbbest):
                obs = 1.
        dc["obs"] = obs
        dcs.append(dc)
    onew = pd.DataFrame(dcs)
    return onew


# Read original datafiles
print("Reading all relevant tables...")
obs = {k: getTable(v) for k, v in masses_obs.items()}
exp = {k: getTable(v) for k, v in masses_exp.items()}


# Transform expected likelyhood data:
#   1. Rename coloumns to HiggsTools convention
#   2. Transform likelyhood to Chisq by multiplication with 2
#   3. Transform data into regular grid
print("Transforming expected likelyhoods...")
expnew = {}
for m, e in exp.items():
    print("  Mass = " + str(m))
    e.rename(
        columns={
            r"$\sigma(gg\phi)B(\phi\rightarrow\tau\tau)$ [pb]": "gg",
            r"$\sigma(bb\phi)B(\phi\rightarrow\tau\tau)$ [pb]": "bb",
            r"$-\Delta\ln\mathcal{L}$ []": "exp",
        },
        inplace=True,
    )
    e.gg = 1e-0 * e.gg
    e.bb = 1e-0 * e.bb
    e["exp"] = 2 * e["exp"]
    e = make_regular_grid(e, mode='exp')
    expnew[m] = e
    expnew[m].to_csv(newbasepath + 'expllhscms139' + str(m) + '.csv')

expx = {m: getTablenew("exp", m) for m in masses_obs}
pickle.dump(expx, open(newbasepath + "exp_llh_CMS_139.p", "wb"))


# Transform observed likelyhood data:
#   1. Rename coloumns to HiggsTools convention
#   2. Transform likelyhood to Chisq by multiplication with 2
#   3. Transform data into regular grid
#   4. If vanishing signal rates are excluded -> regularize
#      Chisq distributions (see above)
print("Transforming observed likelyhoods...")
obsnew = {}
for m, o in obs.items():
    print("  Mass = " + str(m))
    o.rename(
        columns={
            r"$\sigma(gg\phi)B(\phi\rightarrow\tau\tau)$ [pb]": "gg",
            r"$\sigma(bb\phi)B(\phi\rightarrow\tau\tau)$ [pb]": "bb",
            r"$-\Delta\ln\mathcal{L}$ []": "obs",
        },
        inplace=True,
    )
    o.gg = 1e-0 * o.gg
    o.bb = 1e-0 * o.bb
    o["obs"] = 2 * o["obs"]
    o = make_regular_grid(o, mode='obs')
    if o[(o.gg == 0) & (o.bb == 0)].iloc[0].obs > 2.3:
        print("    " + str(o[(o.gg == 0) & (o.bb == 0)].iloc[0].obs))
        print("    regularizing for m = {}".format(m))
        # regularizeExclusionLlh(o, "gg", "bb")
        o = simpleregularizeExclusionLlh(o)
    obsnew[m] = o
    obsnew[m].to_csv(newbasepath + 'obsllhscms139' + str(m) + '.csv')

obsx = {m: getTablenew("obs", m) for m in masses_obs}
pickle.dump(obsx, open(newbasepath + "obs_llh_CMS_139.p", "wb"))


# Read again modified data
obsx = pickle.load(open(newbasepath + "obs_llh_CMS_139.p", "rb"))
expx = pickle.load(open(newbasepath + "exp_llh_CMS_139.p", "rb"))


# Construct data object and set meta data
print("Creating final datafile...")
data = getMetadata("2132368")
data["limitClass"] = "LikelihoodLimit"
data["source"] = "Tab. 11 a-i and Tab. 41-63 (obs) & same but +Asimov (exp)"
data["process"] = [{"channels": [["ggH", "tautau"]]}, {"channels": [["bbH", "tautau"]]}]
data["analysis"] = OrderedDict()
data["analysis"]["massResolution"] = resolution.tautau["default"]

# Save data to data object
stackedGrids = []
for m in expx.keys():
    dat = commonRatePlane(obsx[m], expx[m], ["gg", "bb"])
    dat["mass"] = m
    stackedGrids.append(dat)

# Create final datafile
data["analysis"]["stackedLlhGrid"] = stackedGrids
with open("LLH_LHC13_CMS_139.json", "w") as f:
    json.dump(data, f)
