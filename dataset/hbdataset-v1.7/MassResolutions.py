# The mass uncertainties given in this file are either obtained from the rare
# papers where the needed information is given (see comments) or best guesses.
# It would be really nice to have better numbers for this, but that would
# require a policy change on the experimental side...


def massRes(absolute, relative):
    return {"absolute": absolute, "relative": relative}


mumu = {
    # from 1805.04865 Fig. 1 for m in [20,60]
    # also consistent with Fig 8 in 1802.01122 (assuming emu is similar)
    "light": massRes(0.1, 3e-2),
    # from 1506.00424 p. 3 for m in [0.25, 3.55]
    "veryLight": massRes(0.13, 0.065),
    # from 1903.06248, approximate since it seems to grow for high masses
    "highMass": massRes(1, 0.1),
}

tautau = {"default": massRes(5, 0.15)}

bb = {
    # from 1805.12191 Fig 3 and 1907.02749 p 15 for m in [400, 1400]
    "highMass": massRes(15, 0.15),
    # from  1310.3687 p. 7 for m in [100, 200],
    "medMass": massRes(5, 0.1),
}

gamgam = {
    # from CMS-PAS-HIG-13-001 Tab 2 for m=125
    "125": massRes(1.5, 0.0),
    "default": massRes(0.1, 0.015),
}

inv = {
    # wild guess, it's probably worse than this
    "default": massRes(5, 0.25)
}

WW = {
    # from CMS-PAS-HIG-13-022
    "2l2nu": massRes(1, 0.05),
    # from Fig 5 in CMS-PAS-HIG-13-027
    # conservative estimate (lower absolute res) for the resolution of 1509.00389
    "qqlnu": massRes(5, 0.1),
}

ZZ = {
    # from Fig 17 in 1312.5353 + Gustav's thesis work
    "4l": massRes(0.1, 2e-2)
}

Zgam = {
    # from Fig 5 in 1307.5515
    "default": massRes(1, 0.05)
}

cb = {
    # esimate from Fig 2 in 1808.06575
    "default": {"absolute": 5, "relative": 0.15}
}

cs = {
    # esimate from Fig 5 in 1510.04252
    "default": {"absolute": 5, "relative": 0.15}
}

taunu = {
    # estimate from Fig 3 1508.077
    "tauh": {"absolute": 5, "relative": 0.2}
}

tb = {
    # estimate based on 2001.07763 (140 @ 1TeV)
    "default": {"absolute": 20, "relative": 0.12}
}

LEPZH = {"absolute": 3, "relative": 0}  # from hep-ex/0602042

tt = {
    # estimate based on 2211.01136
    "tttt": massRes(50, 0.1)
}

