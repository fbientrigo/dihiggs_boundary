#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

mkdir -p "${DHB_BUILD_ROOT}/smoke" "${DHB_BUILD_ROOT}/logs"

cat > "${DHB_BUILD_ROOT}/smoke/test_2hdmc_link.cpp" <<'CPP'
#include "THDM.h"
#include "SM.h"
#include "Constraints.h"
#include "DecayTable.h"

#include <cmath>
#include <iomanip>
#include <iostream>

int main() {
    const double mh = 125.09;
    const double mH = 200.0;
    const double mA = 300.0;
    const double mHp = 300.0;
    const double sin_ba = 1.0;
    const double lambda6 = 0.1;
    const double lambda7 = 0.0;
    const double tan_beta = 100.0;

    const double beta = std::atan(tan_beta);
    const double sb = std::sin(beta);
    const double cb = std::cos(beta);

    const double M = 100.0;
    const double m12_sq = M * M * sb * cb;

    SM sm;
    THDM model;
    model.set_SM(sm);

    const bool set_ok = model.set_param_phys(
        mh, mH, mA, mHp,
        sin_ba, lambda6, lambda7,
        m12_sq, tan_beta
    );

    std::cout << std::scientific << std::setprecision(17);
    std::cout << "set_param_phys_ok=" << (set_ok ? 1 : 0) << "\n";

    if (!set_ok) {
        return 0;
    }

    model.set_yukawas_type(1);

    Constraints check(model);
    const bool pos = check.check_positivity();
    const bool uni = check.check_unitarity();
    const bool per = check.check_perturbativity();
    const bool sta = check.check_stability();

    DecayTable tab(model);
    const double width_tot = tab.get_gammatot_h(2);
    const double width_gaga = tab.get_gamma_hgaga(2);
    const double br_gaga = width_tot > 0.0 ? width_gaga / width_tot : 0.0;

    double l1, l2, l3, l4, l5, l6, l7, m12_out, tb_out;
    model.get_param_gen(l1, l2, l3, l4, l5, l6, l7, m12_out, tb_out);

    std::cout << "positivity_ok=" << (pos ? 1 : 0) << "\n";
    std::cout << "unitarity_ok=" << (uni ? 1 : 0) << "\n";
    std::cout << "perturbativity_ok=" << (per ? 1 : 0) << "\n";
    std::cout << "stability_ok=" << (sta ? 1 : 0) << "\n";
    std::cout << "lambda1=" << l1 << "\n";
    std::cout << "lambda2=" << l2 << "\n";
    std::cout << "lambda3=" << l3 << "\n";
    std::cout << "lambda4=" << l4 << "\n";
    std::cout << "lambda5=" << l5 << "\n";
    std::cout << "lambda6=" << l6 << "\n";
    std::cout << "lambda7=" << l7 << "\n";
    std::cout << "m12_sq_in=" << m12_sq << "\n";
    std::cout << "m12_sq_out=" << m12_out << "\n";
    std::cout << "tan_beta_out=" << tb_out << "\n";
    std::cout << "width_tot_H2=" << width_tot << "\n";
    std::cout << "width_gammagamma_H2=" << width_gaga << "\n";
    std::cout << "br_gammagamma_H2=" << br_gaga << "\n";

    return 0;
}
CPP

g++ -std=c++11 -Wall -O2 \
  -I"${DHB_2HDMC_INCLUDE}" \
  "${DHB_BUILD_ROOT}/smoke/test_2hdmc_link.cpp" \
  "${DHB_2HDMC_LIB}" \
  $(gsl-config --libs) \
  -o "${DHB_BUILD_ROOT}/smoke/test_2hdmc_link" \
  2>&1 | tee "${DHB_BUILD_ROOT}/logs/test_2hdmc_link_build.log"

"${DHB_BUILD_ROOT}/smoke/test_2hdmc_link" \
  2>&1 | tee "${DHB_BUILD_ROOT}/logs/test_2hdmc_link_run.log"
