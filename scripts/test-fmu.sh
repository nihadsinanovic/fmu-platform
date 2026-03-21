#!/bin/bash
# test-fmu.sh — Test FMU execution with PyFMI inside the API container
# Run this on the VPS: bash scripts/test-fmu.sh /path/to/appartment.fmu

set -e

FMU_PATH="${1:-/opt/fmu-platform/appartment.fmu}"
CONTAINER="fmu-platform-api-1"
LICENSE_SERVER="29000@16.16.200.137"

echo "=== FMU Execution Test ==="
echo "FMU:       $FMU_PATH"
echo "Container: $CONTAINER"
echo "License:   $LICENSE_SERVER"
echo ""

# 1. Check the FMU exists
if [ ! -f "$FMU_PATH" ]; then
    echo "ERROR: FMU not found at $FMU_PATH"
    exit 1
fi

# 2. Patch needsExecutionTool flag and copy FMU into container
echo ">>> Patching FMU (needsExecutionTool=true → false)..."
PATCHED_FMU="/tmp/appartment_patched.fmu"
PATCH_DIR="/tmp/fmu_patch_$$"
mkdir -p "$PATCH_DIR"
cp "$FMU_PATH" "$PATCHED_FMU"
cd "$PATCH_DIR"
unzip -q "$PATCHED_FMU"
sed -i 's/needsExecutionTool="true"/needsExecutionTool="false"/g' modelDescription.xml
zip -q -r "$PATCHED_FMU" .
cd /
rm -rf "$PATCH_DIR"
echo "    Patched."

echo ">>> Copying patched FMU into container..."
docker cp "$PATCHED_FMU" "$CONTAINER:/tmp/appartment.fmu"
rm -f "$PATCHED_FMU"
echo "    Done."

# 3. Run the test inside the container
echo ""
echo ">>> Running PyFMI test inside container..."
docker exec -e LMS_LICENSE="$LICENSE_SERVER" \
            -e SIEMENS_LICENSE_FILE="$LICENSE_SERVER" \
            -e LMS_OPT_FILE="" \
            "$CONTAINER" python3 -c "
import sys
print('Python:', sys.version)

# Step 1: Check PyFMI is available
print()
print('--- Step 1: Import check ---')
try:
    import pyfmi
    print(f'PyFMI version: {pyfmi.__version__}')
except ImportError as e:
    print(f'FAIL: PyFMI not available: {e}')
    sys.exit(1)

try:
    import assimulo
    print(f'Assimulo version: {assimulo.__version__}')
except ImportError as e:
    print(f'WARN: Assimulo not available: {e}')
    print('      (needed for Model Exchange FMUs)')

# Step 2: Load the FMU
print()
print('--- Step 2: Load FMU ---')
try:
    from pyfmi import load_fmu
    model = load_fmu('/tmp/appartment.fmu')
    print(f'FMU loaded successfully!')
    print(f'  Type: {model.get_generation_tool()} / {type(model).__name__}')
    print(f'  GUID: {model.get_guid()}')
except Exception as e:
    print(f'FAIL loading FMU: {e}')
    print()
    print('If this is a license error, check:')
    print(f'  - License server reachable: {\"$LICENSE_SERVER\"}')
    print('  - AMESim license available on server')
    sys.exit(1)

# Step 3: Inspect variables
print()
print('--- Step 3: FMU variables ---')
try:
    inputs = model.get_model_variables(causality=2)   # input
    outputs = model.get_model_variables(causality=3)   # output
    print(f'  Inputs ({len(inputs)}):')
    for name in sorted(inputs.keys()):
        print(f'    - {name}')
    print(f'  Outputs ({len(outputs)}):')
    for name in sorted(outputs.keys()):
        print(f'    - {name}')
except Exception as e:
    print(f'WARN: Could not list variables: {e}')

# Step 4: Run a short simulation
print()
print('--- Step 4: Simulate (0 to 10s) ---')
try:
    # Set a constant input (e.g., 40°C heat input)
    input_name = 'amesim_interface.heat_in'

    import numpy as np
    t_input = np.array([0.0, 10.0])
    u_input = np.array([40.0, 40.0])
    input_data = np.column_stack([t_input, u_input])

    opts = model.simulate_options()
    opts['ncp'] = 100  # 100 communication points

    res = model.simulate(
        start_time=0.0,
        final_time=10.0,
        input=([input_name], input_data),
        options=opts
    )

    # Get results
    time = res['time']
    temp = res['amesim_interface.room_temperature']

    print(f'  Simulation completed!')
    print(f'  Time points: {len(time)}')
    print(f'  Room temperature:')
    print(f'    t=0s:  {temp[0]:.2f} °C')
    print(f'    t=5s:  {temp[len(temp)//2]:.2f} °C')
    print(f'    t=10s: {temp[-1]:.2f} °C')
    print()
    print('=== SUCCESS: FMU executed correctly! ===')
except Exception as e:
    print(f'FAIL during simulation: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"

echo ""
echo ">>> Test complete."
