/*
 * central_heatpump FMU — FMI 2.0 Model Exchange
 *
 * Algebraic model (no continuous states). Heats the loop fluid based on
 * nominal power and COP, modulated by control signal.
 *
 * VR mapping:
 *   0: nominal_power_kW  (parameter, Real)
 *   1: COP_nominal        (parameter, Real)
 *   2: source_type        (parameter, String)
 *   3: hydr_in_T          (input, Real) [K]
 *   4: hydr_in_mdot       (input, Real) [kg/s]
 *   5: hydr_in_p          (input, Real) [Pa]
 *   6: ctrl_in_signal     (input, Real) [0..1]
 *   7: hydr_out_T         (output, Real) [K]
 *   8: hydr_out_mdot      (output, Real) [kg/s]
 *   9: hydr_out_p         (output, Real) [Pa]
 *  10: elec_out_P         (output, Real) [W]
 *  11: therm_out_Q        (output, Real) [W]
 */

#include "fmi2_common.h"

#define VR_NOM_POWER   0
#define VR_COP         1
#define VR_SRC_TYPE    2
#define VR_IN_T        3
#define VR_IN_MDOT     4
#define VR_IN_P        5
#define VR_CTRL        6
#define VR_OUT_T       7
#define VR_OUT_MDOT    8
#define VR_OUT_P       9
#define VR_ELEC_P     10
#define VR_THERM_Q    11

#define N_REALS       12

typedef struct {
    fmi2Real r[N_REALS];
    char     source_type[32];
    fmi2Real time;
    fmi2CallbackFunctions cb;
} ModelInstance;

static void update_outputs(ModelInstance *m) {
    double nom_W = m->r[VR_NOM_POWER] * 1000.0;
    double ctrl  = m->r[VR_CTRL];
    if (ctrl < 0.0) ctrl = 0.0;
    if (ctrl > 1.0) ctrl = 1.0;

    double Q = nom_W * ctrl;
    double COP = m->r[VR_COP];
    if (COP < 1.0) COP = 1.0;

    double P_elec = Q / COP;
    double mdot = m->r[VR_IN_MDOT];
    double T_in = m->r[VR_IN_T];

    double T_out = T_in;
    if (mdot > 0.001) {
        T_out = T_in + Q / (mdot * CP_WATER);
    }

    m->r[VR_OUT_T]     = T_out;
    m->r[VR_OUT_MDOT]  = mdot;
    m->r[VR_OUT_P]     = m->r[VR_IN_P];  /* no pressure drop in HP */
    m->r[VR_ELEC_P]    = P_elec;
    m->r[VR_THERM_Q]   = Q;
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
    m->r[VR_NOM_POWER] = 50.0;
    m->r[VR_COP]       = 3.8;
    m->r[VR_CTRL]      = 1.0;  /* fully on by default */
    m->r[VR_IN_T]      = 280.15;
    m->r[VR_IN_MDOT]   = 1.0;
    m->r[VR_IN_P]      = 200000.0;
    strcpy(m->source_type, "ground");
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
        if (vr[i] < N_REALS) value[i] = m->r[vr[i]];
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
    (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2SetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Integer value[]) {
    (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Boolean value[]) {
    (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2SetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Boolean value[]) {
    (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2String value[]) {
    ModelInstance *m = (ModelInstance *)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_SRC_TYPE) value[i] = m->source_type;
        else return fmi2Error;
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2String value[]) {
    ModelInstance *m = (ModelInstance *)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_SRC_TYPE) {
            strncpy(m->source_type, value[i], 31);
            m->source_type[31] = '\0';
        } else return fmi2Error;
    }
    return fmi2OK;
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
    m->r[VR_NOM_POWER] = 50.0;
    m->r[VR_COP]       = 3.8;
    m->r[VR_CTRL]      = 1.0;
    strcpy(m->source_type, "ground");
    return fmi2OK;
}
