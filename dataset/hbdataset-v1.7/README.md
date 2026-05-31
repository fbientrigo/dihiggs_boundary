# HiggsBounds Dataset

This repository contains the dataset of experimental searches implemented in [HiggsBounds]. 

## Status

This dataset contains implementations for a large number of limits from BSM
searches at LEP and at the LHC. All relevant and usable results except for those
discussed in #7 are implemented. The implementation status of new ATLAS searches
is tracked in #9 and for CMS searches in #8. We try to implement new results as
soon as they are published (i.e. have at least e-print status).

Compared to [HiggsBounds-5], this dataset is much closer to being complete, in
particular where exotic final states, or scalar searches that did not explicitly
target Higgs bosons are concerned. At the same time, pure 7TeV LHC result (which
are mostly superseded by combined 7+8TeV results anyway) as well as all Tevatron
limits are no longer implemented since they were rarely relevant. 

## Usage
For now, please simply clone or download this repository to a path of your
choice and supply that path to [HiggsBounds]. In the future there will be
versioned releases of this dataset that are also optimized for faster load times
and smaller download sizes.

## Limit File Format and Implementation
In contrast to [HiggsBounds-5], where limits were hard-coded into the Fortran
code, this new implementation fully defines each limit through a single file in
the json format. The format is formally defined and documented in detail in the
[HiggsTools api documentation]. All of the limit files in this repository are
validated against this json schema in the CI.

In addition to the json files that implement the limits. This repository also
contains the ipython notebooks that were used to implement and validate every
limit. The output is included in the notebooks, so that the validation plots for
every limit can be viewed directly. Running the notebooks requires the
[HiggsTools] python module. Whenever possible, the scripts directly download the
required data from HepData/twiki.


[HiggsBounds-5]: https://gitlab.com/higgsbounds/higgsbounds
[HiggsBounds]: https://gitlab.com/higgsbounds/higgstools
[HiggsTools api documentation]: https://higgsbounds.gitlab.io/higgstools/Datafile.html
