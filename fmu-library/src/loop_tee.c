/*
 * loop_tee FMU — Flow splitter/mixer for ambient loop branching.
 *
 * Physics:
 *   Supply side (splitting):
 *     mdot_out[i] = mdot_in / n_branches  (equal split)
 *     T_out[i] = T_in                     (no mixing on supply)
 *     p_out[i] = p_in - dp_tee            (small pressure drop)
 *
 *   Return side (mixing):
 *     mdot_return = sum(mdot_in[i])
 *     T_return = sum(mdot_in[i] * T_in[i]) / mdot_return  (mass-weighted average)
 *     p_return = min(p_in[i]) - dp_tee
 *
 * No continuous states — purely algebraic.
 *
 * Array ports use value references offset by branch index:
 *   VR_OUT_T_BASE + i for branch i output temperature, etc.
 *
 * Value references:
 *   Parameter:  1=n_branches
 *   Inputs:     2=hydr_in_T, 3=hydr_in_mdot, 4=hydr_in_p
 *               100+3*i+0 = hydr_in_T[i] (return from branch i)
 *               100+3*i+1 = hydr_in_mdot[i]
 *               100+3*i+2 = hydr_in_p[i]
 *   Outputs:    200+3*i+0 = hydr_out_T[i] (supply to branch i)
 *               200+3*i+1 = hydr_out_mdot[i]
 *               200+3*i+2 = hydr_out_p[i]
 *               5=hydr_return_T, 6=hydr_return_mdot, 7=hydr_return_p
 */

#include "fmu_common.h"

#define VR_N_BRANCHES      1
#define VR_IN_T            2
#define VR_IN_MDOT         3
#define VR_IN_P            4
#define VR_RETURN_T        5
#define VR_RETURN_MDOT     6
#define VR_RETURN_P        7

/* Array port bases */
#define VR_BRANCH_IN_BASE  100  /* return inputs from branches */
#define VR_BRANCH_OUT_BASE 200  /* supply outputs to branches */
#define MAX_BRANCHES       20

/* Pressure drop across tee fitting (Pa) */
#define DP_TEE 2000.0

typedef struct {
    FMU_BASE_FIELDS

    /* Parameters */
    fmi2Integer n_branches;

    /* Supply inlet */
    fmi2Real hydr_in_T;
    fmi2Real hydr_in_mdot;
    fmi2Real hydr_in_p;

    /* Return inputs from each branch */
    fmi2Real branch_in_T[MAX_BRANCHES];
    fmi2Real branch_in_mdot[MAX_BRANCHES];
    fmi2Real branch_in_p[MAX_BRANCHES];

    /* Supply outputs to each branch */
    fmi2Real branch_out_T[MAX_BRANCHES];
    fmi2Real branch_out_mdot[MAX_BRANCHES];
    fmi2Real branch_out_p[MAX_BRANCHES];

    /* Mixed return */
    fmi2Real hydr_return_T;
    fmi2Real hydr_return_mdot;
    fmi2Real hydr_return_p;
} ModelData;


static void compute_outputs(ModelData* m) {
    int n = m->n_branches;
    if (n < 1) n = 1;
    if (n > MAX_BRANCHES) n = MAX_BRANCHES;

    /* --- Supply splitting --- */
    double mdot_per_branch = m->hydr_in_mdot / (double)n;
    for (int i = 0; i < n; i++) {
        m->branch_out_T[i] = m->hydr_in_T;
        m->branch_out_mdot[i] = mdot_per_branch;
        m->branch_out_p[i] = m->hydr_in_p - DP_TEE;
    }

    /* --- Return mixing (mass-weighted temperature average) --- */
    double total_mdot = 0.0;
    double sum_mdot_T = 0.0;
    double min_p = 1e12;

    for (int i = 0; i < n; i++) {
        double md = m->branch_in_mdot[i];
        total_mdot += md;
        sum_mdot_T += md * m->branch_in_T[i];
        if (m->branch_in_p[i] < min_p) min_p = m->branch_in_p[i];
    }

    m->hydr_return_mdot = total_mdot;
    m->hydr_return_T = (total_mdot > 0.001) ? sum_mdot_T / total_mdot : m->hydr_in_T;
    m->hydr_return_p = (min_p < 1e11) ? min_p - DP_TEE : m->hydr_in_p - 2.0 * DP_TEE;
    if (m->hydr_return_p < 0.0) m->hydr_return_p = 0.0;
}


/* ========== FMI 2.0 Interface ========== */

FMI2_EXPORT fmi2Component fmi2Instantiate(
    fmi2String instanceName, fmi2Type fmuType, fmi2String fmuGUID,
    fmi2String fmuResourceLocation, const fmi2CallbackFunctions* functions,
    fmi2Boolean visible, fmi2Boolean loggingOn)
{
    (void)fmuType; (void)fmuGUID; (void)fmuResourceLocation;
    (void)visible; (void)loggingOn;

    ModelData* m = (ModelData*)functions->allocateMemory(1, sizeof(ModelData));
    if (!m) return NULL;
    memset(m, 0, sizeof(ModelData));
    m->allocateMemory = functions->allocateMemory;
    m->freeMemory = functions->freeMemory;
    m->logger = functions->logger;
    m->instanceName = instanceName;

    m->n_branches = 2;
    m->hydr_in_T = KELVIN_0C + 30.0;
    m->hydr_in_mdot = 2.0;
    m->hydr_in_p = 200000.0;

    /* Initialize branch returns to reasonable defaults */
    for (int i = 0; i < MAX_BRANCHES; i++) {
        m->branch_in_T[i] = KELVIN_0C + 25.0;
        m->branch_in_mdot[i] = 0.0;
        m->branch_in_p[i] = 180000.0;
    }

    return (fmi2Component)m;
}

FMI2_EXPORT void fmi2FreeInstance(fmi2Component c) {
    if (c) { ModelData* m = (ModelData*)c; m->freeMemory(m); }
}

FMI2_EXPORT fmi2Status fmi2SetupExperiment(fmi2Component c,
    fmi2Boolean td, fmi2Real tol, fmi2Real start, fmi2Boolean sd, fmi2Real stop)
{
    (void)td; (void)tol; (void)sd; (void)stop;
    ((ModelData*)c)->time = start;
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2EnterInitializationMode(fmi2Component c) { (void)c; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2ExitInitializationMode(fmi2Component c) {
    ModelData* m = (ModelData*)c;
    m->initialized = fmi2True;
    compute_outputs(m);
    return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2Terminate(fmi2Component c) { (void)c; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2Reset(fmi2Component c) {
    ModelData* m = (ModelData*)c;
    m->time = 0.0; m->initialized = fmi2False;
    m->n_branches = 2;
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Real value[]) {
    ModelData* m = (ModelData*)c;
    for (size_t i = 0; i < nvr; i++) {
        fmi2ValueReference v = vr[i];
        if (v == VR_IN_T)          { m->hydr_in_T = value[i]; }
        else if (v == VR_IN_MDOT)  { m->hydr_in_mdot = value[i]; }
        else if (v == VR_IN_P)     { m->hydr_in_p = value[i]; }
        else if (v >= VR_BRANCH_IN_BASE && v < VR_BRANCH_IN_BASE + 3 * MAX_BRANCHES) {
            int idx = (v - VR_BRANCH_IN_BASE) / 3;
            int field = (v - VR_BRANCH_IN_BASE) % 3;
            if (idx < MAX_BRANCHES) {
                switch (field) {
                    case 0: m->branch_in_T[idx] = value[i]; break;
                    case 1: m->branch_in_mdot[idx] = value[i]; break;
                    case 2: m->branch_in_p[idx] = value[i]; break;
                }
            }
        } else {
            return fmi2Error;
        }
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Real value[]) {
    ModelData* m = (ModelData*)c;
    compute_outputs(m);
    for (size_t i = 0; i < nvr; i++) {
        fmi2ValueReference v = vr[i];
        if (v == VR_IN_T)            { value[i] = m->hydr_in_T; }
        else if (v == VR_IN_MDOT)    { value[i] = m->hydr_in_mdot; }
        else if (v == VR_IN_P)       { value[i] = m->hydr_in_p; }
        else if (v == VR_RETURN_T)   { value[i] = m->hydr_return_T; }
        else if (v == VR_RETURN_MDOT){ value[i] = m->hydr_return_mdot; }
        else if (v == VR_RETURN_P)   { value[i] = m->hydr_return_p; }
        else if (v >= VR_BRANCH_IN_BASE && v < VR_BRANCH_IN_BASE + 3 * MAX_BRANCHES) {
            int idx = (v - VR_BRANCH_IN_BASE) / 3;
            int field = (v - VR_BRANCH_IN_BASE) % 3;
            if (idx < MAX_BRANCHES) {
                switch (field) {
                    case 0: value[i] = m->branch_in_T[idx]; break;
                    case 1: value[i] = m->branch_in_mdot[idx]; break;
                    case 2: value[i] = m->branch_in_p[idx]; break;
                }
            }
        }
        else if (v >= VR_BRANCH_OUT_BASE && v < VR_BRANCH_OUT_BASE + 3 * MAX_BRANCHES) {
            int idx = (v - VR_BRANCH_OUT_BASE) / 3;
            int field = (v - VR_BRANCH_OUT_BASE) % 3;
            if (idx < MAX_BRANCHES) {
                switch (field) {
                    case 0: value[i] = m->branch_out_T[idx]; break;
                    case 1: value[i] = m->branch_out_mdot[idx]; break;
                    case 2: value[i] = m->branch_out_p[idx]; break;
                }
            }
        }
        else { return fmi2Error; }
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Integer value[]) {
    ModelData* m = (ModelData*)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_N_BRANCHES) m->n_branches = value[i];
    }
    return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Integer value[]) {
    ModelData* m = (ModelData*)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_N_BRANCHES) value[i] = m->n_branches;
        else return fmi2Error;
    }
    return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2SetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Boolean value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2GetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Boolean value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2SetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2String value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2GetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2String value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }

/* ME functions — no states */
FMI2_EXPORT fmi2Status fmi2SetTime(fmi2Component c, fmi2Real time) { ((ModelData*)c)->time = time; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2SetContinuousStates(fmi2Component c, const fmi2Real x[], size_t nx) { (void)c; (void)x; (void)nx; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2GetContinuousStates(fmi2Component c, fmi2Real x[], size_t nx) { (void)c; (void)x; (void)nx; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2GetDerivatives(fmi2Component c, fmi2Real dx[], size_t nx) { (void)c; (void)dx; (void)nx; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2GetEventIndicators(fmi2Component c, fmi2Real ind[], size_t ni) { (void)c; (void)ind; (void)ni; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2EnterEventMode(fmi2Component c) { (void)c; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2NewDiscreteStates(fmi2Component c, fmi2EventInfo* ei) {
    (void)c;
    ei->newDiscreteStatesNeeded = fmi2False;
    ei->terminateSimulation = fmi2False;
    ei->nominalsOfContinuousStatesChanged = fmi2False;
    ei->valuesOfContinuousStatesChanged = fmi2False;
    ei->nextEventTimeDefined = fmi2False;
    ei->nextEventTime = 0.0;
    return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2EnterContinuousTimeMode(fmi2Component c) { (void)c; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2CompletedIntegratorStep(fmi2Component c, fmi2Boolean b, fmi2Boolean* em, fmi2Boolean* ts) {
    (void)c; (void)b; *em = fmi2False; *ts = fmi2False; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetNominalsOfContinuousStates(fmi2Component c, fmi2Real xn[], size_t nx) {
    (void)c; for (size_t i = 0; i < nx; i++) xn[i] = 1.0; return fmi2OK;
}

/* Common FMI 2.0 function stubs (debug logging, state serialization, etc.) */
#include "fmu_common_impl.h"
