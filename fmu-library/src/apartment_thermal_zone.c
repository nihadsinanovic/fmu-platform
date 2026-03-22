/*
 * apartment_thermal_zone FMU — FMI 2.0 Model Exchange
 *
 * Single-zone RC thermal model. One continuous state: room temperature.
 * Accounts for wall/window losses, heating input, solar gains, occupancy gains.
 *
 * VR mapping (must match modelDescription.xml):
 *   0: floor_area_m2             (parameter, Real)
 *   1: ceiling_height_m          (parameter, Real)
 *   2: U_wall                    (parameter, Real) [W/(m2·K)]
 *   3: U_window                  (parameter, Real) [W/(m2·K)]
 *   4: window_area_m2            (parameter, Real)
 *   5: n_occupants               (parameter, Integer)
 *   6: orientation               (parameter, String)
 *   7: therm_in_Q_heating        (input, Real) [W]
 *   8: therm_in_T_ambient_outdoor(input, Real) [K]
 *   9: therm_in_Q_solar          (input, Real) [W/m2]
 *  10: therm_out_T_room          (output, Real) [K]
 *  11: therm_out_Q_loss          (output, Real) [W]
 *  12: therm_out_Q_total         (output, Real) [W]
 *
 * State[0] = T_room [K]
 */

#include "fmi2_common.h"

/* Value references */
#define VR_FLOOR_AREA     0
#define VR_CEIL_HEIGHT    1
#define VR_U_WALL         2
#define VR_U_WINDOW       3
#define VR_WIN_AREA       4
#define VR_N_OCCUPANTS    5
#define VR_ORIENTATION    6
#define VR_Q_HEATING      7
#define VR_T_AMBIENT      8
#define VR_Q_SOLAR        9
#define VR_T_ROOM        10
#define VR_Q_LOSS        11
#define VR_Q_TOTAL       12

#define N_REALS   13
#define N_STATES   1
#define Q_PER_OCCUPANT 80.0   /* W per person */
#define SHGC           0.4    /* Solar heat gain coefficient */

typedef struct {
    fmi2Real    r[N_REALS];
    fmi2Integer n_occupants;
    char        orientation[32];
    fmi2Real    state[N_STATES];   /* T_room */
    fmi2Real    time;
    fmi2CallbackFunctions cb;
} ModelInstance;

/* Compute derived quantities */
static double get_wall_area(ModelInstance *m) {
    double side = sqrt(m->r[VR_FLOOR_AREA]);
    double perimeter = 4.0 * side;
    double gross_wall = perimeter * m->r[VR_CEIL_HEIGHT];
    double net_wall = gross_wall - m->r[VR_WIN_AREA];
    return net_wall > 0.0 ? net_wall : 0.0;
}

static double get_UA_total(ModelInstance *m) {
    double UA_wall   = m->r[VR_U_WALL]   * get_wall_area(m);
    double UA_window = m->r[VR_U_WINDOW]  * m->r[VR_WIN_AREA];
    /* Infiltration: ~0.5 ACH equivalent */
    double V = m->r[VR_FLOOR_AREA] * m->r[VR_CEIL_HEIGHT];
    double UA_infil = 0.5 * V * RHO_AIR * CP_AIR / 3600.0;
    return UA_wall + UA_window + UA_infil;
}

static double get_thermal_mass(ModelInstance *m) {
    double V = m->r[VR_FLOOR_AREA] * m->r[VR_CEIL_HEIGHT];
    /* Air + ~200 kg/m2 building mass (furniture, walls) at ~1000 J/(kg·K) */
    double C_air = RHO_AIR * CP_AIR * V;
    double C_mass = m->r[VR_FLOOR_AREA] * 200.0 * 1000.0;
    return C_air + C_mass;
}

static void update_outputs(ModelInstance *m) {
    double T_room = m->state[0];
    double T_amb  = m->r[VR_T_AMBIENT];
    double UA = get_UA_total(m);

    m->r[VR_T_ROOM] = T_room;
    m->r[VR_Q_LOSS] = UA * (T_room - T_amb);

    double Q_solar = m->r[VR_Q_SOLAR] * m->r[VR_WIN_AREA] * SHGC;
    double Q_int   = m->n_occupants * Q_PER_OCCUPANT;
    m->r[VR_Q_TOTAL] = m->r[VR_Q_HEATING] + Q_solar + Q_int - m->r[VR_Q_LOSS];
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
    /* Defaults */
    m->r[VR_FLOOR_AREA]  = 50.0;
    m->r[VR_CEIL_HEIGHT] = 2.5;
    m->r[VR_U_WALL]      = 0.25;
    m->r[VR_U_WINDOW]    = 1.4;
    m->r[VR_WIN_AREA]    = 6.0;
    m->n_occupants       = 2;
    strcpy(m->orientation, "south");
    m->r[VR_T_AMBIENT]   = 283.15;  /* 10°C default */
    m->state[0]          = 293.15;  /* 20°C initial room temp */
    m->r[VR_T_ROOM]      = 293.15;
    return (fmi2Component)m;
}

FMI2_EXPORT void fmi2FreeInstance(fmi2Component c) { free(c); }

FMI2_EXPORT fmi2Status fmi2SetupExperiment(fmi2Component c,
    fmi2Boolean tol, fmi2Real tolerance, fmi2Real startTime,
    fmi2Boolean stopDef, fmi2Real stopTime)
{
    (void)tol; (void)tolerance; (void)stopDef; (void)stopTime;
    ModelInstance *m = (ModelInstance *)c;
    m->time = startTime;
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
        if (vr[i] == VR_N_OCCUPANTS) value[i] = (fmi2Real)m->n_occupants;
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
        if (vr[i] == VR_N_OCCUPANTS) value[i] = m->n_occupants;
        else return fmi2Error;
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Integer value[]) {
    ModelInstance *m = (ModelInstance *)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_N_OCCUPANTS) m->n_occupants = value[i];
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
    ModelInstance *m = (ModelInstance *)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_ORIENTATION) value[i] = m->orientation;
        else return fmi2Error;
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2String value[]) {
    ModelInstance *m = (ModelInstance *)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_ORIENTATION) {
            strncpy(m->orientation, value[i], 31);
            m->orientation[31] = '\0';
        } else return fmi2Error;
    }
    return fmi2OK;
}

/* ---- Continuous states: T_room ---- */

FMI2_EXPORT fmi2Status fmi2GetContinuousStates(fmi2Component c, fmi2Real x[], size_t nx) {
    ModelInstance *m = (ModelInstance *)c;
    if (nx >= 1) x[0] = m->state[0];
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetContinuousStates(fmi2Component c, const fmi2Real x[], size_t nx) {
    ModelInstance *m = (ModelInstance *)c;
    if (nx >= 1) {
        m->state[0] = x[0];
        m->r[VR_T_ROOM] = x[0];
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetDerivatives(fmi2Component c, fmi2Real dx[], size_t nx) {
    ModelInstance *m = (ModelInstance *)c;
    if (nx < 1) return fmi2OK;

    double T_room = m->state[0];
    double T_amb  = m->r[VR_T_AMBIENT];
    double Q_heat = m->r[VR_Q_HEATING];
    double Q_sol  = m->r[VR_Q_SOLAR] * m->r[VR_WIN_AREA] * SHGC;
    double Q_int  = m->n_occupants * Q_PER_OCCUPANT;
    double UA     = get_UA_total(m);
    double C      = get_thermal_mass(m);

    /* dT_room/dt = (Q_in - Q_loss) / C */
    dx[0] = (Q_heat + Q_sol + Q_int - UA * (T_room - T_amb)) / C;

    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetNominalsOfContinuousStates(fmi2Component c, fmi2Real nominals[], size_t nx) {
    (void)c;
    if (nx >= 1) nominals[0] = 293.15; /* nominal room temp */
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetEventIndicators(fmi2Component c, fmi2Real indicators[], size_t ni) {
    (void)c; (void)indicators; (void)ni; return fmi2OK;
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
    m->state[0] = 293.15;
    m->r[VR_T_ROOM] = 293.15;
    return fmi2OK;
}
