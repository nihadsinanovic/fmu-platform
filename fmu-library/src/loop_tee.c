/*
 * loop_tee FMU — FMI 2.0 Model Exchange
 *
 * Flow splitter/mixer. Algebraic (no states).
 * Splits incoming flow equally among N branches, mixes return flows
 * with mass-weighted average temperature.
 *
 * Supports up to MAX_BRANCHES=10 branches.
 * Array ports are expanded: hydr_out_T[0]..hydr_out_T[9], etc.
 *
 * VR mapping (0-based):
 *   0:     n_branches          (parameter, Integer)
 *   1:     hydr_in_T           (input, main supply T)
 *   2:     hydr_in_mdot        (input, main supply mdot)
 *   3:     hydr_in_p           (input, main supply p)
 *   4-13:  hydr_in_T[0..9]     (input, branch return T)
 *  14-23:  hydr_in_mdot[0..9]  (input, branch return mdot)
 *  24-33:  hydr_in_p[0..9]     (input, branch return p)
 *  34-43:  hydr_out_T[0..9]    (output, branch supply T)
 *  44-53:  hydr_out_mdot[0..9] (output, branch supply mdot)
 *  54-63:  hydr_out_p[0..9]    (output, branch supply p)
 *  64:     hydr_return_T       (output, mixed return T)
 *  65:     hydr_return_mdot    (output, mixed return mdot)
 *  66:     hydr_return_p       (output, mixed return p)
 */

#include "fmi2_common.h"

#define MAX_BRANCHES 10

/* VR offsets */
#define VR_N_BRANCHES     0
#define VR_MAIN_IN_T      1
#define VR_MAIN_IN_MDOT   2
#define VR_MAIN_IN_P      3
#define VR_BR_IN_T_BASE   4   /* 4..13 */
#define VR_BR_IN_MDOT_BASE 14 /* 14..23 */
#define VR_BR_IN_P_BASE   24  /* 24..33 */
#define VR_BR_OUT_T_BASE  34  /* 34..43 */
#define VR_BR_OUT_MDOT_BASE 44 /* 44..53 */
#define VR_BR_OUT_P_BASE  54  /* 54..63 */
#define VR_RETURN_T       64
#define VR_RETURN_MDOT    65
#define VR_RETURN_P       66

#define N_REALS           67

typedef struct {
    fmi2Real    r[N_REALS];
    fmi2Integer n_branches;
    fmi2Real    time;
    fmi2CallbackFunctions cb;
} ModelInstance;

static void update_outputs(ModelInstance *m) {
    int nb = m->n_branches;
    if (nb < 1) nb = 1;
    if (nb > MAX_BRANCHES) nb = MAX_BRANCHES;

    double T_in   = m->r[VR_MAIN_IN_T];
    double mdot   = m->r[VR_MAIN_IN_MDOT];
    double p_in   = m->r[VR_MAIN_IN_P];

    /* Split: equal flow to each branch */
    double mdot_per_branch = (mdot > 0.0) ? mdot / nb : 0.0;
    for (int i = 0; i < MAX_BRANCHES; i++) {
        if (i < nb) {
            m->r[VR_BR_OUT_T_BASE + i]    = T_in;
            m->r[VR_BR_OUT_MDOT_BASE + i] = mdot_per_branch;
            m->r[VR_BR_OUT_P_BASE + i]    = p_in;
        } else {
            m->r[VR_BR_OUT_T_BASE + i]    = T_in;
            m->r[VR_BR_OUT_MDOT_BASE + i] = 0.0;
            m->r[VR_BR_OUT_P_BASE + i]    = p_in;
        }
    }

    /* Mix: mass-weighted average temperature of return flows */
    double total_mdot = 0.0;
    double sum_mT     = 0.0;
    double min_p      = 1e12;

    for (int i = 0; i < nb; i++) {
        double br_mdot = m->r[VR_BR_IN_MDOT_BASE + i];
        double br_T    = m->r[VR_BR_IN_T_BASE + i];
        double br_p    = m->r[VR_BR_IN_P_BASE + i];
        total_mdot += br_mdot;
        sum_mT     += br_mdot * br_T;
        if (br_p < min_p) min_p = br_p;
    }

    m->r[VR_RETURN_MDOT] = total_mdot;
    m->r[VR_RETURN_T]    = (total_mdot > 0.001) ? sum_mT / total_mdot : T_in;
    m->r[VR_RETURN_P]    = (min_p < 1e12) ? min_p : p_in;
}

/* ==================== FMI 2.0 API ==================== */

FMI2_EXPORT const char* fmi2GetTypesPlatform(void) { return "default"; }
FMI2_EXPORT const char* fmi2GetVersion(void) { return "2.0"; }

FMI2_EXPORT fmi2Component fmi2Instantiate(
    fmi2String instanceName, fmi2Type fmuType, fmi2String guid,
    fmi2String resourceURI, const fmi2CallbackFunctions *cb,
    fmi2Boolean visible, fmi2Boolean loggingOn)
{
    (void)instanceName; (void)fmuType; (void)guid;
    (void)resourceURI; (void)visible; (void)loggingOn;
    ModelInstance *m = (ModelInstance *)calloc(1, sizeof(ModelInstance));
    if (!m) return NULL;
    m->cb = *cb;
    m->n_branches = 2;
    m->r[VR_MAIN_IN_T]    = 285.15;
    m->r[VR_MAIN_IN_MDOT] = 1.0;
    m->r[VR_MAIN_IN_P]    = 200000.0;
    /* Initialize branch returns to same as supply */
    for (int i = 0; i < MAX_BRANCHES; i++) {
        m->r[VR_BR_IN_T_BASE + i]    = 283.15;
        m->r[VR_BR_IN_MDOT_BASE + i] = 0.5;
        m->r[VR_BR_IN_P_BASE + i]    = 200000.0;
    }
    return (fmi2Component)m;
}

FMI2_EXPORT void fmi2FreeInstance(fmi2Component c) { free(c); }

FMI2_EXPORT fmi2Status fmi2SetupExperiment(fmi2Component c,
    fmi2Boolean tol, fmi2Real tolerance, fmi2Real startTime,
    fmi2Boolean stopDef, fmi2Real stopTime)
{
    (void)tol; (void)tolerance; (void)stopDef; (void)stopTime;
    ((ModelInstance *)c)->time = startTime;
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2EnterInitializationMode(fmi2Component c) { (void)c; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2ExitInitializationMode(fmi2Component c) {
    update_outputs((ModelInstance *)c);
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetTime(fmi2Component c, fmi2Real time) {
    ((ModelInstance *)c)->time = time;
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Real value[]) {
    ModelInstance *m = (ModelInstance *)c;
    update_outputs(m);
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_N_BRANCHES) value[i] = (fmi2Real)m->n_branches;
        else if (vr[i] < N_REALS) value[i] = m->r[vr[i]];
        else return fmi2Error;
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Real value[]) {
    ModelInstance *m = (ModelInstance *)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] < N_REALS) m->r[vr[i]] = value[i];
        else return fmi2Error;
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Integer value[]) {
    ModelInstance *m = (ModelInstance *)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_N_BRANCHES) value[i] = m->n_branches;
        else return fmi2Error;
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Integer value[]) {
    ModelInstance *m = (ModelInstance *)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_N_BRANCHES) m->n_branches = value[i];
        else return fmi2Error;
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Boolean value[]) {
    (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2SetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Boolean value[]) {
    (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2String value[]) {
    (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2SetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2String value[]) {
    (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK;
}

/* No continuous states */
FMI2_EXPORT fmi2Status fmi2GetDerivatives(fmi2Component c, fmi2Real dx[], size_t nx) {
    (void)c; (void)dx; (void)nx; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetContinuousStates(fmi2Component c, fmi2Real x[], size_t nx) {
    (void)c; (void)x; (void)nx; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2SetContinuousStates(fmi2Component c, const fmi2Real x[], size_t nx) {
    (void)c; (void)x; (void)nx; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetNominalsOfContinuousStates(fmi2Component c, fmi2Real n[], size_t nx) {
    (void)c; for (size_t i = 0; i < nx; i++) n[i] = 1.0; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetEventIndicators(fmi2Component c, fmi2Real ind[], size_t ni) {
    (void)c; (void)ind; (void)ni; return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2EnterEventMode(fmi2Component c) { (void)c; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2NewDiscreteStates(fmi2Component c, fmi2EventInfo *info) {
    (void)c;
    info->newDiscreteStatesNeeded           = fmi2False;
    info->terminateSimulation               = fmi2False;
    info->nominalsOfContinuousStatesChanged = fmi2False;
    info->valuesOfContinuousStatesChanged   = fmi2False;
    info->nextEventTimeDefined              = fmi2False;
    info->nextEventTime                     = 0.0;
    return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2EnterContinuousTimeMode(fmi2Component c) { (void)c; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2CompletedIntegratorStep(fmi2Component c, fmi2Boolean noSet,
    fmi2Boolean *enterEventMode, fmi2Boolean *terminateSimulation) {
    (void)c; (void)noSet;
    *enterEventMode = fmi2False;
    *terminateSimulation = fmi2False;
    return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2Terminate(fmi2Component c) { (void)c; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2Reset(fmi2Component c) {
    ModelInstance *m = (ModelInstance *)c;
    m->time = 0.0;
    m->n_branches = 2;
    return fmi2OK;
}
