/*
 * apartment_thermal_zone FMU — Single-zone RC thermal model of an apartment.
 *
 * Physics (1R1C lumped model):
 *   State: T_room (indoor air temperature)
 *
 *   C_thermal * dT_room/dt = Q_heating + Q_solar_gain + Q_occupant
 *                           - UA_walls * (T_room - T_ambient)
 *                           - UA_windows * (T_room - T_ambient)
 *                           - Q_infiltration
 *
 *   where:
 *     C_thermal = rho_air * cp_air * Volume + C_furniture
 *     UA_walls = U_wall * A_wall_net
 *     UA_windows = U_window * A_window
 *     Q_occupant = n_occupants * 80 W (sensible heat per person)
 *     Q_infiltration = 0.5 ACH * Volume * rho_air * cp_air * (T_room - T_ambient) / 3600
 *     Q_solar_gain = SHGC * A_window * orientation_factor * Q_solar_irradiance
 *
 * Value references:
 *   Parameters: 1=floor_area_m2, 2=ceiling_height_m, 3=U_wall, 4=U_window,
 *               5=window_area_m2, 6=n_occupants, 7=orientation
 *   Inputs:     8=therm_in_Q_heating, 9=therm_in_T_ambient_outdoor, 10=therm_in_Q_solar
 *   Outputs:    11=therm_out_T_room, 12=therm_out_Q_loss, 13=therm_out_Q_total
 */

#include "fmu_common.h"

#define VR_FLOOR_AREA     1
#define VR_CEILING_HEIGHT 2
#define VR_U_WALL         3
#define VR_U_WINDOW       4
#define VR_WINDOW_AREA    5
#define VR_N_OCCUPANTS    6
#define VR_ORIENTATION    7
#define VR_Q_HEATING      8
#define VR_T_AMBIENT      9
#define VR_Q_SOLAR        10
#define VR_T_ROOM         11
#define VR_Q_LOSS         12
#define VR_Q_TOTAL        13

#define N_STATES 1

/* Constants */
#define HEAT_PER_OCCUPANT 80.0    /* W sensible heat per person */
#define ACH_INFILTRATION  0.5     /* air changes per hour */
#define SHGC              0.6     /* solar heat gain coefficient */
#define C_FURNITURE_PER_M2 15000.0 /* J/(K·m²) thermal mass of furniture/walls */
#define WALL_HEIGHT_FACTOR 2.5    /* assume perimeter ≈ 4*sqrt(area), walls = perimeter * height */

typedef struct {
    FMU_BASE_FIELDS

    /* Parameters */
    fmi2Real floor_area_m2;
    fmi2Real ceiling_height_m;
    fmi2Real U_wall;
    fmi2Real U_window;
    fmi2Real window_area_m2;
    fmi2Integer n_occupants;
    char orientation[16];

    /* Inputs */
    fmi2Real therm_in_Q_heating;
    fmi2Real therm_in_T_ambient;
    fmi2Real therm_in_Q_solar;

    /* State */
    fmi2Real T_room;  /* K */

    /* Outputs */
    fmi2Real therm_out_T_room;
    fmi2Real therm_out_Q_loss;
    fmi2Real therm_out_Q_total;

    /* Derived */
    fmi2Real C_thermal;   /* total thermal capacitance [J/K] */
    fmi2Real UA_walls;    /* wall conductance [W/K] */
    fmi2Real UA_windows;  /* window conductance [W/K] */
    fmi2Real UA_infil;    /* infiltration conductance [W/K] */
    fmi2Real orientation_factor;  /* solar orientation multiplier */
} ModelData;


static double get_orientation_factor(const char* orientation) {
    if (strcmp(orientation, "south") == 0) return 1.0;
    if (strcmp(orientation, "east") == 0 || strcmp(orientation, "west") == 0) return 0.7;
    if (strcmp(orientation, "north") == 0) return 0.3;
    if (strcmp(orientation, "southeast") == 0 || strcmp(orientation, "southwest") == 0) return 0.85;
    if (strcmp(orientation, "northeast") == 0 || strcmp(orientation, "northwest") == 0) return 0.5;
    return 0.7;  /* default */
}


static void compute_derived(ModelData* m) {
    double volume = m->floor_area_m2 * m->ceiling_height_m;

    /* Thermal capacitance: air + furniture/internal walls */
    m->C_thermal = RHO_AIR * CP_AIR * volume + C_FURNITURE_PER_M2 * m->floor_area_m2;

    /* Wall area: approximate perimeter * height - window area */
    double perimeter = 4.0 * sqrt(m->floor_area_m2);
    double A_wall_total = perimeter * m->ceiling_height_m;
    double A_wall_net = A_wall_total - m->window_area_m2;
    if (A_wall_net < 0.0) A_wall_net = 0.0;

    m->UA_walls = m->U_wall * A_wall_net;
    m->UA_windows = m->U_window * m->window_area_m2;

    /* Infiltration heat loss coefficient */
    m->UA_infil = ACH_INFILTRATION * volume * RHO_AIR * CP_AIR / 3600.0;

    m->orientation_factor = get_orientation_factor(m->orientation);
}


static void compute_outputs(ModelData* m) {
    m->therm_out_T_room = m->T_room;

    /* Total envelope heat loss */
    double dT = m->T_room - m->therm_in_T_ambient;
    m->therm_out_Q_loss = (m->UA_walls + m->UA_windows + m->UA_infil) * dT;

    /* Net heat balance */
    double Q_solar_gain = SHGC * m->window_area_m2 * m->orientation_factor * m->therm_in_Q_solar;
    double Q_occupant = m->n_occupants * HEAT_PER_OCCUPANT;
    m->therm_out_Q_total = m->therm_in_Q_heating + Q_solar_gain + Q_occupant - m->therm_out_Q_loss;
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

    /* Defaults from manifest */
    m->floor_area_m2 = 50.0;
    m->ceiling_height_m = 2.5;
    m->U_wall = 0.25;
    m->U_window = 1.4;
    m->window_area_m2 = 6.0;
    m->n_occupants = 2;
    strcpy(m->orientation, "south");

    m->therm_in_T_ambient = KELVIN_0C + 10.0;
    m->therm_in_Q_heating = 0.0;
    m->therm_in_Q_solar = 0.0;
    m->T_room = KELVIN_0C + 20.0;  /* initial room temperature */

    compute_derived(m);
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
    compute_derived(m);
    m->initialized = fmi2True;
    compute_outputs(m);
    return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2Terminate(fmi2Component c) { (void)c; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2Reset(fmi2Component c) {
    ModelData* m = (ModelData*)c;
    m->time = 0.0; m->initialized = fmi2False;
    m->T_room = KELVIN_0C + 20.0;
    m->floor_area_m2 = 50.0; m->ceiling_height_m = 2.5;
    m->U_wall = 0.25; m->U_window = 1.4;
    m->window_area_m2 = 6.0; m->n_occupants = 2;
    strcpy(m->orientation, "south");
    compute_derived(m);
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Real value[]) {
    ModelData* m = (ModelData*)c;
    for (size_t i = 0; i < nvr; i++) {
        switch (vr[i]) {
            case VR_FLOOR_AREA:     m->floor_area_m2 = value[i]; break;
            case VR_CEILING_HEIGHT: m->ceiling_height_m = value[i]; break;
            case VR_U_WALL:         m->U_wall = value[i]; break;
            case VR_U_WINDOW:       m->U_window = value[i]; break;
            case VR_WINDOW_AREA:    m->window_area_m2 = value[i]; break;
            case VR_Q_HEATING:      m->therm_in_Q_heating = value[i]; break;
            case VR_T_AMBIENT:      m->therm_in_T_ambient = value[i]; break;
            case VR_Q_SOLAR:        m->therm_in_Q_solar = value[i]; break;
            default: return fmi2Error;
        }
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Real value[]) {
    ModelData* m = (ModelData*)c;
    compute_outputs(m);
    for (size_t i = 0; i < nvr; i++) {
        switch (vr[i]) {
            case VR_FLOOR_AREA:     value[i] = m->floor_area_m2; break;
            case VR_CEILING_HEIGHT: value[i] = m->ceiling_height_m; break;
            case VR_U_WALL:         value[i] = m->U_wall; break;
            case VR_U_WINDOW:       value[i] = m->U_window; break;
            case VR_WINDOW_AREA:    value[i] = m->window_area_m2; break;
            case VR_Q_HEATING:      value[i] = m->therm_in_Q_heating; break;
            case VR_T_AMBIENT:      value[i] = m->therm_in_T_ambient; break;
            case VR_Q_SOLAR:        value[i] = m->therm_in_Q_solar; break;
            case VR_T_ROOM:         value[i] = m->therm_out_T_room; break;
            case VR_Q_LOSS:         value[i] = m->therm_out_Q_loss; break;
            case VR_Q_TOTAL:        value[i] = m->therm_out_Q_total; break;
            default: return fmi2Error;
        }
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Integer value[]) {
    ModelData* m = (ModelData*)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_N_OCCUPANTS) m->n_occupants = value[i];
    }
    return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Integer value[]) {
    ModelData* m = (ModelData*)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_N_OCCUPANTS) value[i] = m->n_occupants;
        else return fmi2Error;
    }
    return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2SetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Boolean value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2GetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Boolean value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }

FMI2_EXPORT fmi2Status fmi2SetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2String value[]) {
    ModelData* m = (ModelData*)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_ORIENTATION) {
            strncpy(m->orientation, value[i], sizeof(m->orientation) - 1);
            m->orientation[sizeof(m->orientation) - 1] = '\0';
        }
    }
    return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2String value[]) {
    ModelData* m = (ModelData*)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_ORIENTATION) value[i] = m->orientation;
        else return fmi2Error;
    }
    return fmi2OK;
}

/* ME functions — 1 state: T_room */
FMI2_EXPORT fmi2Status fmi2SetTime(fmi2Component c, fmi2Real time) {
    ((ModelData*)c)->time = time; return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetContinuousStates(fmi2Component c, const fmi2Real x[], size_t nx) {
    if (nx >= 1) ((ModelData*)c)->T_room = x[0];
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetContinuousStates(fmi2Component c, fmi2Real x[], size_t nx) {
    if (nx >= 1) x[0] = ((ModelData*)c)->T_room;
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetDerivatives(fmi2Component c, fmi2Real dx[], size_t nx) {
    ModelData* m = (ModelData*)c;
    if (nx >= 1) {
        double dT = m->T_room - m->therm_in_T_ambient;
        double Q_loss = (m->UA_walls + m->UA_windows + m->UA_infil) * dT;
        double Q_solar_gain = SHGC * m->window_area_m2 * m->orientation_factor * m->therm_in_Q_solar;
        double Q_occupant = m->n_occupants * HEAT_PER_OCCUPANT;
        double Q_net = m->therm_in_Q_heating + Q_solar_gain + Q_occupant - Q_loss;
        dx[0] = Q_net / m->C_thermal;
    }
    return fmi2OK;
}

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
    (void)c;
    if (nx >= 1) xn[0] = 293.0;  /* nominal ~20°C */
    return fmi2OK;
}
