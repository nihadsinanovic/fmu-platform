/*
 * weather_source FMU — FMI 2.0 Model Exchange
 *
 * Generates synthetic weather data (annual temperature cycle, daily solar cycle).
 * No continuous states — outputs are pure functions of time.
 *
 * VR mapping (must match modelDescription.xml):
 *   0: lat                  (parameter, Real)
 *   1: lon                  (parameter, Real)
 *   2: climate_zone         (parameter, String)  — not used in physics
 *   3: therm_out_T_ambient  (output, Real) [K]
 *   4: therm_out_Q_solar    (output, Real) [W/m2]
 *   5: therm_out_humidity   (output, Real) [%]
 *   6: therm_out_wind_speed (output, Real) [m/s]
 */

#include "fmi2_common.h"

/* Value references */
#define VR_LAT            0
#define VR_LON            1
#define VR_CLIMATE_ZONE   2
#define VR_T_AMBIENT      3
#define VR_Q_SOLAR        4
#define VR_HUMIDITY        5
#define VR_WIND_SPEED     6

#define N_REALS   7
#define N_STRINGS 1

typedef struct {
    fmi2Real    r[N_REALS];
    char        climate_zone[64];
    fmi2Real    time;
    fmi2CallbackFunctions cb;
} ModelInstance;

/* ---------- compute outputs from time ---------- */
static void update_outputs(ModelInstance *m) {
    double t = m->time;
    double lat = m->r[VR_LAT];

    /* Annual temperature cycle: mean ~10°C, amplitude ~10°C
       Coldest around Jan 15 (day 15), warmest around Jul 15 (day 196) */
    double day_of_year = fmod(t, YEAR_S) / DAY_S;
    double annual_phase = 2.0 * PI * (day_of_year - 15.0) / 365.0;
    double T_mean = 283.15;  /* 10°C in K */
    double T_amp  = 10.0;    /* +/- 10°C */

    /* Latitude adjustment: higher lat = colder mean, bigger amplitude */
    double lat_factor = fabs(lat) / 45.0;  /* normalize to ~1.0 for 45°N */
    T_mean -= 2.0 * (lat_factor - 1.0);
    T_amp  *= (0.8 + 0.4 * lat_factor);

    /* Daily variation: +/- 3°C */
    double hour_angle = 2.0 * PI * fmod(t, DAY_S) / DAY_S;
    double T_daily = 3.0 * sin(hour_angle - PI * 0.5);  /* coldest at 6am */

    m->r[VR_T_AMBIENT] = T_mean - T_amp * cos(annual_phase) + T_daily;

    /* Solar irradiance: daily bell curve with seasonal amplitude
       Peak ~800 W/m2 in summer, ~200 W/m2 in winter */
    double hour = fmod(t, DAY_S) / 3600.0;
    double solar_daily = 0.0;
    if (hour > 6.0 && hour < 20.0) {
        solar_daily = sin(PI * (hour - 6.0) / 14.0);
    }
    double solar_seasonal = 0.5 + 0.5 * sin(annual_phase - PI * 0.5);
    /* Summer peak after solstice */
    m->r[VR_Q_SOLAR] = solar_daily * (200.0 + 600.0 * solar_seasonal);

    /* Humidity: 50-80%, inverse of temperature */
    m->r[VR_HUMIDITY] = 65.0 - 15.0 * cos(annual_phase) + 5.0 * cos(hour_angle);

    /* Wind speed: 2-6 m/s with daily and seasonal variation */
    m->r[VR_WIND_SPEED] = 4.0 + 1.5 * sin(annual_phase + 1.0) + 1.0 * sin(hour_angle + 0.5);
    if (m->r[VR_WIND_SPEED] < 0.5) m->r[VR_WIND_SPEED] = 0.5;
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
    /* Defaults from manifest */
    m->r[VR_LAT] = 45.19;
    m->r[VR_LON] = 5.72;
    strcpy(m->climate_zone, "H1c");
    m->time = 0.0;
    return (fmi2Component)m;
}

FMI2_EXPORT void fmi2FreeInstance(fmi2Component c) { free(c); }

FMI2_EXPORT fmi2Status fmi2SetupExperiment(fmi2Component c,
    fmi2Boolean tol, fmi2Real tolerance, fmi2Real startTime, fmi2Boolean stopDef, fmi2Real stopTime)
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
    ModelInstance *m = (ModelInstance *)c;
    m->time = time;
    update_outputs(m);
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Real value[]) {
    ModelInstance *m = (ModelInstance *)c;
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
        if (vr[i] == VR_CLIMATE_ZONE) value[i] = m->climate_zone;
        else return fmi2Error;
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2String value[]) {
    ModelInstance *m = (ModelInstance *)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_CLIMATE_ZONE) {
            strncpy(m->climate_zone, value[i], 63);
            m->climate_zone[63] = '\0';
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
FMI2_EXPORT fmi2Status fmi2GetNominalsOfContinuousStates(fmi2Component c, fmi2Real nominals[], size_t nx) {
    (void)c; for (size_t i = 0; i < nx; i++) nominals[i] = 1.0; return fmi2OK;
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
FMI2_EXPORT fmi2Status fmi2CompletedIntegratorStep(fmi2Component c, fmi2Boolean noSetFMUStatePriorToCurrentPoint,
    fmi2Boolean *enterEventMode, fmi2Boolean *terminateSimulation) {
    (void)c; (void)noSetFMUStatePriorToCurrentPoint;
    *enterEventMode = fmi2False;
    *terminateSimulation = fmi2False;
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2Terminate(fmi2Component c) { (void)c; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2Reset(fmi2Component c) {
    ModelInstance *m = (ModelInstance *)c;
    m->time = 0.0;
    m->r[VR_LAT] = 45.19;
    m->r[VR_LON] = 5.72;
    strcpy(m->climate_zone, "H1c");
    update_outputs(m);
    return fmi2OK;
}
