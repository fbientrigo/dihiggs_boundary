#include "THDM.h"
#include "SM.h"
#include "Constraints.h"
#include "DecayTable.h"

#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

namespace {

constexpr double kMh = 125.09;
constexpr double kSinBa = 1.0;
constexpr double kLambda7 = 0.0;
constexpr double kHbarCGeVmm = 1.973269804e-13;

double nan_value() {
    return std::numeric_limits<double>::quiet_NaN();
}

std::vector<std::string> split_csv_line(const std::string& line) {
    std::vector<std::string> fields;
    std::string field;
    std::stringstream ss(line);

    while (std::getline(ss, field, ',')) {
        if (!field.empty() && field[field.size() - 1] == '\r') {
            field.erase(field.size() - 1);
        }
        fields.push_back(field);
    }

    if (!line.empty() && line[line.size() - 1] == ',') {
        fields.push_back("");
    }

    return fields;
}

bool parse_double_strict(const std::string& text, double& out) {
    if (text.empty()) {
        return false;
    }

    char* end = NULL;
    errno = 0;
    const double value = std::strtod(text.c_str(), &end);

    if (errno != 0 || end == text.c_str() || *end != '\0') {
        return false;
    }

    out = value;
    return true;
}

int bool_int(bool value) {
    return value ? 1 : 0;
}

struct InputPoint {
    std::string point_id;
    double mH;
    double mA;
    double tan_beta;
    double lambda6;
    double M;
    bool parse_ok;
    std::string parse_error;

    InputPoint()
        : point_id("unknown"),
          mH(nan_value()),
          mA(nan_value()),
          tan_beta(nan_value()),
          lambda6(nan_value()),
          M(nan_value()),
          parse_ok(false),
          parse_error("not_parsed") {}
};

struct OutputRecord {
    std::string point_id;

    double mh;
    double mH;
    double mA;
    double mHp;
    double tan_beta;
    double beta;
    double sin_ba;
    double lambda6_input;
    double lambda7_input;
    double M;
    double M2;
    double m12_sq_input;
    double M2_recomputed;
    double relative_M2_reconstruction_error;

    bool set_param_phys_ok;
    bool positivity_ok;
    bool unitarity_ok;
    bool perturbativity_ok;
    bool stability_ok;
    bool triple_ok;
    bool theory_ok;

    double lambda1;
    double lambda2;
    double lambda3;
    double lambda4;
    double lambda5;
    double lambda6_derived;
    double lambda7_derived;
    double m12_sq_derived;
    double tan_beta_derived;

    double width_bb_H2;
    double width_tautau_H2;
    double width_WW_H2;
    double width_ZZ_H2;
    double width_gammagamma_H2;
    double width_Zgamma_H2;
    double width_gg_H2;
    double width_hh_H2;
    double total_width_H2;
    double br_gammagamma_H2;
    double ctau_mm_H2;

    std::string yukawa_assignment;
    std::string scalar_z2_status;
    int soft_z2_only;
    std::string rejection_stage;
    std::string rejection_reason;

    OutputRecord()
        : point_id("unknown"),
          mh(kMh),
          mH(nan_value()),
          mA(nan_value()),
          mHp(nan_value()),
          tan_beta(nan_value()),
          beta(nan_value()),
          sin_ba(kSinBa),
          lambda6_input(nan_value()),
          lambda7_input(kLambda7),
          M(nan_value()),
          M2(nan_value()),
          m12_sq_input(nan_value()),
          M2_recomputed(nan_value()),
          relative_M2_reconstruction_error(nan_value()),
          set_param_phys_ok(false),
          positivity_ok(false),
          unitarity_ok(false),
          perturbativity_ok(false),
          stability_ok(false),
          triple_ok(false),
          theory_ok(false),
          lambda1(nan_value()),
          lambda2(nan_value()),
          lambda3(nan_value()),
          lambda4(nan_value()),
          lambda5(nan_value()),
          lambda6_derived(nan_value()),
          lambda7_derived(nan_value()),
          m12_sq_derived(nan_value()),
          tan_beta_derived(nan_value()),
          width_bb_H2(nan_value()),
          width_tautau_H2(nan_value()),
          width_WW_H2(nan_value()),
          width_ZZ_H2(nan_value()),
          width_gammagamma_H2(nan_value()),
          width_Zgamma_H2(nan_value()),
          width_gg_H2(nan_value()),
          width_hh_H2(nan_value()),
          total_width_H2(nan_value()),
          br_gammagamma_H2(nan_value()),
          ctau_mm_H2(nan_value()),
          yukawa_assignment("type-I"),
          scalar_z2_status("hard_broken_lambda6"),
          soft_z2_only(0),
          rejection_stage("input_parse"),
          rejection_reason("not_evaluated") {}
};

InputPoint parse_input_row(const std::string& line, int line_number) {
    InputPoint point;
    const std::vector<std::string> fields = split_csv_line(line);

    if (!fields.empty() && !fields[0].empty()) {
        point.point_id = fields[0];
    } else {
        std::ostringstream fallback;
        fallback << "line_" << line_number;
        point.point_id = fallback.str();
    }

    if (fields.size() != 6) {
        std::ostringstream msg;
        msg << "expected_6_fields_got_" << fields.size();
        point.parse_error = msg.str();
        return point;
    }

    point.point_id = fields[0];

    bool ok = true;
    ok = parse_double_strict(fields[1], point.mH) && ok;
    ok = parse_double_strict(fields[2], point.mA) && ok;
    ok = parse_double_strict(fields[3], point.tan_beta) && ok;
    ok = parse_double_strict(fields[4], point.lambda6) && ok;
    ok = parse_double_strict(fields[5], point.M) && ok;

    if (!ok) {
        point.parse_error = "numeric_parse_failed";
        return point;
    }

    if (point.tan_beta <= 0.0) {
        point.parse_error = "tan_beta_must_be_positive";
        return point;
    }

    point.parse_ok = true;
    point.parse_error = "ok";
    return point;
}

std::string first_constraint_failure(const OutputRecord& r) {
    if (!r.set_param_phys_ok) {
        return "set_param_phys";
    }
    if (!r.positivity_ok) {
        return "positivity";
    }
    if (!r.unitarity_ok) {
        return "unitarity";
    }
    if (!r.perturbativity_ok) {
        return "perturbativity";
    }
    if (!r.stability_ok) {
        return "stability";
    }
    return "none";
}

OutputRecord evaluate_point(const InputPoint& p) {
    OutputRecord r;
    r.point_id = p.point_id;

    if (!p.parse_ok) {
        r.rejection_stage = "input_parse";
        r.rejection_reason = p.parse_error;
        return r;
    }

    r.mH = p.mH;
    r.mA = p.mA;
    r.mHp = p.mA;
    r.tan_beta = p.tan_beta;
    r.beta = std::atan(p.tan_beta);
    r.sin_ba = kSinBa;
    r.lambda6_input = p.lambda6;
    r.lambda7_input = kLambda7;
    r.M = p.M;
    r.M2 = p.M * p.M;

    const double sin_beta = std::sin(r.beta);
    const double cos_beta = std::cos(r.beta);
    const double denom = sin_beta * cos_beta;

    r.m12_sq_input = r.M2 * denom;

    if (!std::isfinite(r.m12_sq_input) || !std::isfinite(denom) || denom == 0.0) {
        r.rejection_stage = "derived_parameter";
        r.rejection_reason = "invalid_m12_sq_or_beta";
        return r;
    }

    SM sm;
    THDM model;
    model.set_SM(sm);

    r.set_param_phys_ok = model.set_param_phys(
        r.mh,
        r.mH,
        r.mA,
        r.mHp,
        r.sin_ba,
        r.lambda6_input,
        r.lambda7_input,
        r.m12_sq_input,
        r.tan_beta
    );

    if (!r.set_param_phys_ok) {
        r.rejection_stage = "set_param_phys";
        r.rejection_reason = "set_param_phys_returned_false";
        return r;
    }

    model.set_yukawas_type(1);

    double l1 = nan_value();
    double l2 = nan_value();
    double l3 = nan_value();
    double l4 = nan_value();
    double l5 = nan_value();
    double l6 = nan_value();
    double l7 = nan_value();
    double m12_out = nan_value();
    double tb_out = nan_value();

    model.get_param_gen(l1, l2, l3, l4, l5, l6, l7, m12_out, tb_out);

    r.lambda1 = l1;
    r.lambda2 = l2;
    r.lambda3 = l3;
    r.lambda4 = l4;
    r.lambda5 = l5;
    r.lambda6_derived = l6;
    r.lambda7_derived = l7;
    r.m12_sq_derived = m12_out;
    r.tan_beta_derived = tb_out;

    r.M2_recomputed = r.m12_sq_derived / denom;
    if (r.M2 != 0.0 && std::isfinite(r.M2_recomputed)) {
        r.relative_M2_reconstruction_error = std::fabs(r.M2_recomputed - r.M2) / std::fabs(r.M2);
    }

    Constraints check(model);
    r.positivity_ok = check.check_positivity();
    r.unitarity_ok = check.check_unitarity();
    r.perturbativity_ok = check.check_perturbativity();
    r.stability_ok = check.check_stability();

    r.triple_ok = r.positivity_ok && r.unitarity_ok && r.perturbativity_ok;
    r.theory_ok = r.set_param_phys_ok && r.triple_ok && r.stability_ok;

    DecayTable tab(model);
    r.width_bb_H2 = tab.get_gamma_hdd(2, 3, 3);
    r.width_tautau_H2 = tab.get_gamma_hll(2, 3, 3);
    r.width_WW_H2 = tab.get_gamma_hvv(2, 3);
    r.width_ZZ_H2 = tab.get_gamma_hvv(2, 2);
    r.width_gammagamma_H2 = tab.get_gamma_hgaga(2);
    r.width_Zgamma_H2 = tab.get_gamma_hZga(2);
    r.width_gg_H2 = tab.get_gamma_hgg(2);
    r.width_hh_H2 = tab.get_gamma_hhh(2, 1, 1);
    r.total_width_H2 = tab.get_gammatot_h(2);

    bool width_ok = false;
    if (r.total_width_H2 > 0.0 && std::isfinite(r.total_width_H2)) {
        r.br_gammagamma_H2 = r.width_gammagamma_H2 / r.total_width_H2;
        r.ctau_mm_H2 = kHbarCGeVmm / r.total_width_H2;
        width_ok = true;
    } else {
        r.theory_ok = false;
    }

    const std::string first_failure = first_constraint_failure(r);
    if (first_failure != "none") {
        r.rejection_stage = first_failure;
        r.rejection_reason = first_failure + "_failed";
    } else if (!width_ok) {
        r.rejection_stage = "width";
        r.rejection_reason = "non_positive_or_nonfinite_total_width";
    } else {
        r.rejection_stage = "none";
        r.rejection_reason = "ok";
    }

    return r;
}

void write_header(std::ostream& os) {
    os
        << "point_id,"
        << "mh,mH,mA,mHp,tan_beta,beta,sin_ba,"
        << "lambda6_input,lambda7_input,"
        << "M,M2,m12_sq_input,M2_recomputed,relative_M2_reconstruction_error,"
        << "set_param_phys_ok,positivity_ok,unitarity_ok,perturbativity_ok,stability_ok,"
        << "triple_ok,theory_ok,"
        << "lambda1,lambda2,lambda3,lambda4,lambda5,lambda6_derived,lambda7_derived,"
        << "m12_sq_derived,tan_beta_derived,"
        << "width_bb_H2,width_tautau_H2,width_WW_H2,width_ZZ_H2,"
        << "width_gammagamma_H2,width_Zgamma_H2,width_gg_H2,width_hh_H2,"
        << "total_width_H2,br_gammagamma_H2,ctau_mm_H2,"
        << "yukawa_assignment,scalar_z2_status,soft_z2_only,"
        << "rejection_stage,rejection_reason\n";
}

void write_double(std::ostream& os, double value) {
    os << value;
}

void write_record(std::ostream& os, const OutputRecord& r) {
    os << r.point_id << ",";
    write_double(os, r.mh); os << ",";
    write_double(os, r.mH); os << ",";
    write_double(os, r.mA); os << ",";
    write_double(os, r.mHp); os << ",";
    write_double(os, r.tan_beta); os << ",";
    write_double(os, r.beta); os << ",";
    write_double(os, r.sin_ba); os << ",";
    write_double(os, r.lambda6_input); os << ",";
    write_double(os, r.lambda7_input); os << ",";
    write_double(os, r.M); os << ",";
    write_double(os, r.M2); os << ",";
    write_double(os, r.m12_sq_input); os << ",";
    write_double(os, r.M2_recomputed); os << ",";
    write_double(os, r.relative_M2_reconstruction_error); os << ",";

    os << bool_int(r.set_param_phys_ok) << ","
       << bool_int(r.positivity_ok) << ","
       << bool_int(r.unitarity_ok) << ","
       << bool_int(r.perturbativity_ok) << ","
       << bool_int(r.stability_ok) << ","
       << bool_int(r.triple_ok) << ","
       << bool_int(r.theory_ok) << ",";

    write_double(os, r.lambda1); os << ",";
    write_double(os, r.lambda2); os << ",";
    write_double(os, r.lambda3); os << ",";
    write_double(os, r.lambda4); os << ",";
    write_double(os, r.lambda5); os << ",";
    write_double(os, r.lambda6_derived); os << ",";
    write_double(os, r.lambda7_derived); os << ",";
    write_double(os, r.m12_sq_derived); os << ",";
    write_double(os, r.tan_beta_derived); os << ",";

    write_double(os, r.width_bb_H2); os << ",";
    write_double(os, r.width_tautau_H2); os << ",";
    write_double(os, r.width_WW_H2); os << ",";
    write_double(os, r.width_ZZ_H2); os << ",";
    write_double(os, r.width_gammagamma_H2); os << ",";
    write_double(os, r.width_Zgamma_H2); os << ",";
    write_double(os, r.width_gg_H2); os << ",";
    write_double(os, r.width_hh_H2); os << ",";
    write_double(os, r.total_width_H2); os << ",";
    write_double(os, r.br_gammagamma_H2); os << ",";
    write_double(os, r.ctau_mm_H2); os << ",";

    os << r.yukawa_assignment << ","
       << r.scalar_z2_status << ","
       << r.soft_z2_only << ","
       << r.rejection_stage << ","
       << r.rejection_reason << "\n";
}

int run(const std::string& input_csv, const std::string& output_csv) {
    std::ifstream input(input_csv.c_str());
    if (!input.is_open()) {
        std::cerr << "[DHB][FAIL] Cannot open input CSV: " << input_csv << "\n";
        return 2;
    }

    std::string header;
    if (!std::getline(input, header)) {
        std::cerr << "[DHB][FAIL] Empty input CSV: " << input_csv << "\n";
        return 2;
    }

    if (!header.empty() && header[header.size() - 1] == '\r') {
        header.erase(header.size() - 1);
    }

    const std::string expected_header = "point_id,mH,mA,tan_beta,lambda6,M";
    if (header != expected_header) {
        std::cerr << "[DHB][FAIL] Unexpected input header.\n";
        std::cerr << "[DHB][FAIL] Found:    " << header << "\n";
        std::cerr << "[DHB][FAIL] Expected: " << expected_header << "\n";
        return 2;
    }

    const std::string tmp_output = output_csv + ".tmp";

    std::ofstream output(tmp_output.c_str());
    if (!output.is_open()) {
        std::cerr << "[DHB][FAIL] Cannot open output CSV tmp: " << tmp_output << "\n";
        return 2;
    }

    output << std::scientific << std::setprecision(17);
    write_header(output);

    std::string line;
    int line_number = 1;
    int input_rows = 0;
    int output_rows = 0;

    while (std::getline(input, line)) {
        ++line_number;

        if (line.empty() || line == "\r") {
            continue;
        }

        ++input_rows;
        const InputPoint point = parse_input_row(line, line_number);
        const OutputRecord record = evaluate_point(point);
        write_record(output, record);
        ++output_rows;
    }

    output.close();

    if (!output) {
        std::cerr << "[DHB][FAIL] Failed while writing output CSV tmp: " << tmp_output << "\n";
        std::remove(tmp_output.c_str());
        return 3;
    }

    if (std::rename(tmp_output.c_str(), output_csv.c_str()) != 0) {
        std::cerr << "[DHB][FAIL] Failed to rename tmp output to final output.\n";
        std::cerr << "[DHB][FAIL] tmp:   " << tmp_output << "\n";
        std::cerr << "[DHB][FAIL] final: " << output_csv << "\n";
        std::remove(tmp_output.c_str());
        return 3;
    }

    std::cerr << "[DHB] evaluate_point completed: input_rows="
              << input_rows << " output_rows=" << output_rows << "\n";

    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "Usage: " << argv[0] << " input.csv output.csv\n";
        return 1;
    }

    return run(argv[1], argv[2]);
}
