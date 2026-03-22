/*
 * ambient_loop_segment FMU — FMI 2.0 Model Exchange
 *
 * Pipe segment with thermal inertia. One continuous state: fluid temperature.
 * Models heat loss to ambient and pressure drop.
 *
 * VR mapping:
 *   0: length_m                 (parameter, Real)
 *   1: diameter_mm              (parameter, Real)
 *   2: insulation_thickness_mm  (parameter, Real)
 *   3: hydr_in_T                (input, Real) [K]
 *   4: hydr_in_mdot             (input, Real) [kg/s]
 *   5: hydr_in_p                (input, Real) [Pa]
 *   6: therm_in_T_ambient       (input, Real) [K]
 *   7: hydr_out_T               (output, Real) [K]
 *   8: hydr_out_mdot            (output, Real) [kg/s]
 *   9: hydr_out_p               (output, Real) [Pa]
 *  10: therm_out_Q_loss         (output, Real) [W]
 *
 * State[0] = T_fluid [K]
 */

#include "fmi2_common.h"

#define VR_LENGTH       0
#define VR_DIAMETER     1
#define VR_INSULATION   2
#define VR_IN_T         3
#define VR_IN_MDOT      4
#define VR_IN_P         5
#define VR_T_AMBIENT    6
#define VR_OUT_T        7
#define VR_OUT_MDOT     8
#define VR_OUT_P        9
#define VR_Q_LOSS      10

#define N_REALS        11
#define N_STATES        1

#define K_INSULATION   0.04   /* W/(m·K) typical foam insulation */

typedef struct {
    fmi2Real r[N_REALS];
    fmi2Real state[N_STATES];  /* T_fluid */
    fmi2Real time;
    fmi2CallbackFunctions cb;
} ModelInstance;

static double get_pipe_volume(ModelInstance *m) {
    double d = m->r[VR_DIAMETER] / 1000.0;  /* mm to m */
    double L = m->r[VR_LENGTH];
    return PI * (d / 2.0) * (d / 2.0) * L;
}

static double get_UA_pipe(ModelInstance *m) {
    double d = m->r[VR_DIAMETER] / 1000.0;
    double L = m->r[VR_LENGTH];
    double ins = m->r[VR_INSULATION] / 1000.0;  /* mm to m */

    if (ins < 0.001) ins = 0.001;

    /* Cylindrical insulation: UA = 2*pi*k*L / ln((r+ins)/r) */
    double r = d / 2.0;
    double UA = 2.0 * PI * K_INSULATION * L / log((r + ins) / r);
    return UA;
}

static void update_outputs(ModelInstance *m) {
    m->r[VR_OUT_T]    = m->state[0];
    m->r[VR_OUT_MDOT] = m->r[VR_IN_MDOT];

    /* Simple pressure drop: dp = f * L/D * rho * v^2 / 2
       Simplified: dp proportional to mdot^2 */
    double mdot = m->r[VR_IN_MDOT];
    double d = m->r[VR_DIAMETER] / 1000.0;
    double A = PI * (d / 2.0) * (d / 2.0);
    double v = (A > 1e-6 && mdot > 0.001) ? mdot / (RHO_WATER * A) : 0.0;
    double dp = 0.02 * (m->r[VR_LENGTH] / d) * RHO_WATER * v * v / 2.0;
    m->r[VR_OUT_P] = m->r[VR_IN_P] - dp;

    double UA = get_UA_pipe(m);
    m->r[VR_Q_LOSS] = UA * (m->state[0] - m->r[VR_T_AMBIENT]);
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
    m->r[VR_LENGTH]     = 10.0;
    m->r[VR_DIAMETER]   = 80.0;
    m->r[VR_INSULATION] = 30.0;
    m->r[VR_IN_T]       = 285.15;
    m->r[VR_IN_MDOT]    = 1.0;
    m->r[VR_IN_P]       = 200000.0;
    m->r[VR_T_AMBIENT]  = 283.15;
    m->state[0]         = 285.15;  /* initial fluid temp */
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
    (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2SetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2String value[]) {
    (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK;
}

/* ---- Continuous states: T_fluid ---- */

FMI2_EXPORT fmi2Status fmi2GetContinuousStates(fmi2Component c, fmi2Real x[], size_t nx) {
    ModelInstance *m = (ModelInstance *)c;
    if (nx >= 1) x[0] = m->state[0];
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetContinuousStates(fmi2Component c, const fmi2Real x[], size_t nx) {
    ModelInstance *m = (ModelInstance *)c;
    if (nx >= 1) m->state[0] = x[0];
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetDerivatives(fmi2Component c, fmi2Real dx[], size_t nx) {
    ModelInstance *m = (ModelInstance *)c;
    if (nx < 1) return fmi2OK;

    double T_fluid = m->state[0];
    double T_in    = m->r[VR_IN_T];
    double mdot    = m->r[VR_IN_MDOT];
    double T_amb   = m->r[VR_T_AMBIENT];
    double V       = get_pipe_volume(m);
    double UA      = get_UA_pipe(m);

    double C_fluid = RHO_WATER * CP_WATER * V;
    if (C_fluid < 1.0) C_fluid = 1.0;

    /* dT/dt = (mdot*cp*(T_in - T) - UA*(T - T_amb)) / C */
    dx[0] = (mdot * CP_WATER * (T_in - T_fluid) - UA * (T_fluid - T_amb)) / C_fluid;

    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetNominalsOfContinuousStates(fmi2Component c, fmi2Real nominals[], size_t nx) {
    (void)c;
    if (nx >= 1) nominals[0] = 285.0;
    return fmi2OK;
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
    m->state[0] = 285.15;
    return fmi2OK;
}
