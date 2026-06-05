# Debian Clone Setup

This guide outlines the steps to set up the `dihiggs_boundary` repository on a fresh Debian/Ubuntu system.

## 1. Install System Dependencies
The evaluation workflow relies on a C++ compiler, `make`, and the GNU Scientific Library (GSL) for compiling and linking `2HDMC`. Python 3 is required for driving the boundary scripts.

```bash
sudo apt-get update
sudo apt-get install -y build-essential libgsl-dev python3 python3-pip git
```

## 2. Clone the Repository
```bash
git clone <repository_url> dihiggs_boundary
cd dihiggs_boundary
```

## 3. Configure Local Environment Paths
Create a local `.env.local` file to specify where the boundary data (the "lake") and dependencies reside. See the provided `path_config_example.env` for reference.
```bash
cp path_config_example.env .env.local
# Edit .env.local to match your local paths
```

## 4. Build 2HDMC
The `evaluate_point` binary links against the `2HDMC` library, which must be compiled first.
```bash
cd lib/2HDMC-1.8.0
make
cd ../..
```
*Note: The generated `2HDMC` binaries are ignored via `.git/info/exclude`.*

## 5. Build and Test `evaluate_point`
Compile the main evaluation point program and run a minimal smoke test to confirm readiness.
```bash
./scripts/build_evaluate_point.sh
./scripts/smoke_evaluate_point.sh
```

If the smoke test passes, your environment is correctly set up.
