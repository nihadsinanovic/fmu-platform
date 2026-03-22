/*
 * weather_source FMU — Outdoor weather conditions driver.
 *
 * Generates realistic annual temperature and solar irradiance profiles
 * using sinusoidal models. No continuous states — purely algebraic from time.
 *
 * Temperature model: T = T_mean + T_amp * cos(2π(t - t_coldest) / year)
 * Solar model: Daily cycle modulated by seasonal envelope.
 *
 * Value references (must match modelDescription.xml):
 *   Parameters: 1=lat, 2=lon, 3=climate_zone
 *   Outputs:    4=therm_out_T_ambient, 5=therm_out_Q_solar,
 *               6=therm_out_humidity, 7=therm_out_wind_speed
 */

#include "fmu_common.h"

/* Value reference assignments */
#define VR_LAT              1
#define VR_LON              2
#define VR_CLIMATE_ZONE     3
#define VR_T_AMBIENT        4
#define VR_Q_SOLAR          5
#define VR_HUMIDITY         6
#define VR_WIND_SPEED       7

#define N_STATES 0
#define N_EVENT_INDICATORS 0

typedef struct {
    FMU_BASE_FIELDS

    /* Parameters */
    fmi2Real lat;           /* degrees */
    fmi2Real lon;           /* degrees */
    char climate_zone[64];

    /* Outputs (computed) */
    fmi2Real T_ambient;     /* K */
    fmi2Real Q_solar;       /* W/m² */
    fmi2Real humidity;      /* % */
    fmi2Real wind_speed;    /* m/s */
} ModelData;


static void compute_outputs(ModelData* m) {
    double t = m->time;
    double lat_rad = m->lat * PI / 180.0;

    /* --- Annual temperature cycle ---
     * Assumes coldest day is around Jan 15 (day 15 = 1,296,000 s).
     * T_mean and T_amp depend on latitude (simplified). */
    double T_mean = KELVIN_0C + 12.0 - fabs(m->lat) * 0.3;
    double T_amp  = 8.0 + fabs(m->lat) * 0.15;
    double t_coldest = 15.0 * DAY_S;  /* Jan 15 */
    m->T_ambient = T_mean - T_amp * cos(2.0 * PI * (t - t_coldest) / YEAR_S);

    /* --- Solar irradiance ---
     * Daily cycle: peak at solar noon, zero at night.
     * Seasonal modulation: stronger in summer. */
    double day_of_year = fmod(t, YEAR_S) / DAY_S;
    double hour_of_day = fmod(t, DAY_S) / 3600.0;

    /* Solar declination angle (radians) */
    double declination = 23.45 * PI / 180.0 * sin(2.0 * PI * (day_of_year - 81.0) / 365.0);

    /* Hour angle (radians from solar noon) */
    double hour_angle = (hour_of_day - 12.0) * PI / 12.0;

    /* Solar altitude angle */
    double sin_alt = sin(lat_rad) * sin(declination) +
                     cos(lat_rad) * cos(declination) * cos(hour_angle);

    if (sin_alt > 0.0) {
        /* Clear-sky irradiance model (simplified) */
        double air_mass = 1.0 / (sin_alt + 0.15 * pow(3.885 + asin(sin_alt) * 180.0 / PI, -1.253));
        if (air_mass > 40.0) air_mass = 40.0;
        double I_direct = 1361.0 * 0.7 * pow(0.7, pow(air_mass, 0.678));
        double I_diffuse = 0.1 * 1361.0 * sin_alt;
        m->Q_solar = I_direct * sin_alt + I_diffuse;
    } else {
        m->Q_solar = 0.0;  /* nighttime */
    }

    /* --- Humidity: seasonal sinusoid, higher in winter --- */
    m->humidity = 60.0 + 15.0 * cos(2.0 * PI * (t - t_coldest) / YEAR_S);  /* peaks in winter */

    /* --- Wind speed: daily variation + noise approximation --- */
    double base_wind = 3.0 + 1.5 * sin(2.0 * PI * hour_of_day / 24.0 - PI / 3.0);
    /* Pseudo-random perturbation using sine of large multiple */
    double perturbation = 0.8 * sin(t * 0.0073) + 0.4 * sin(t * 0.0197);
    m->wind_speed = fmax(0.5, base_wind + perturbation);
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
    m->lat = 45.19;
    m->lon = 5.72;
    strcpy(m->climate_zone, "H1c");
    m->time = 0.0;
    m->initialized = fmi2False;

    return (fmi2Component)m;
}

FMI2_EXPORT void fmi2FreeInstance(fmi2Component c) {
    if (c) {
        ModelData* m = (ModelData*)c;
        m->freeMemory(m);
    }
}

FMI2_EXPORT fmi2Status fmi2SetupExperiment(fmi2Component c,
    fmi2Boolean toleranceDefined, fmi2Real tolerance,
    fmi2Real startTime, fmi2Boolean stopTimeDefined, fmi2Real stopTime)
{
    (void)toleranceDefined; (void)tolerance; (void)stopTimeDefined; (void)stopTime;
    ModelData* m = (ModelData*)c;
    m->time = startTime;
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2EnterInitializationMode(fmi2Component c) {
    (void)c;
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2ExitInitializationMode(fmi2Component c) {
    ModelData* m = (ModelData*)c;
    m->initialized = fmi2True;
    compute_outputs(m);
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2Terminate(fmi2Component c) { (void)c; return fmi2OK; }

FMI2_EXPORT fmi2Status fmi2Reset(fmi2Component c) {
    ModelData* m = (ModelData*)c;
    m->time = 0.0;
    m->initialized = fmi2False;
    m->lat = 45.19;
    m->lon = 5.72;
    strcpy(m->climate_zone, "H1c");
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Real value[]) {
    ModelData* m = (ModelData*)c;
    for (size_t i = 0; i < nvr; i++) {
        switch (vr[i]) {
            case VR_LAT: m->lat = value[i]; break;
            case VR_LON: m->lon = value[i]; break;
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
            case VR_LAT:        value[i] = m->lat; break;
            case VR_LON:        value[i] = m->lon; break;
            case VR_T_AMBIENT:  value[i] = m->T_ambient; break;
            case VR_Q_SOLAR:    value[i] = m->Q_solar; break;
            case VR_HUMIDITY:   value[i] = m->humidity; break;
            case VR_WIND_SPEED: value[i] = m->wind_speed; break;
            default: return fmi2Error;
        }
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Integer value[]) {
    (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Integer value[]) {
    (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2SetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Boolean value[]) {
    (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Boolean value[]) {
    (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2String value[]) {
    ModelData* m = (ModelData*)c;
    for (size_t i = 0; i < nvr; i++) {
        switch (vr[i]) {
            case VR_CLIMATE_ZONE:
                strncpy(m->climate_zone, value[i], sizeof(m->climate_zone) - 1);
                m->climate_zone[sizeof(m->climate_zone) - 1] = '\0';
                break;
            default: return fmi2Error;
        }
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2String value[]) {
    ModelData* m = (ModelData*)c;
    for (size_t i = 0; i < nvr; i++) {
        switch (vr[i]) {
            case VR_CLIMATE_ZONE: value[i] = m->climate_zone; break;
            default: return fmi2Error;
        }
    }
    return fmi2OK;
}

/* Model Exchange — no continuous states for weather_source */
FMI2_EXPORT fmi2Status fmi2SetTime(fmi2Component c, fmi2Real time) {
    ModelData* m = (ModelData*)c;
    m->time = time;
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetContinuousStates(fmi2Component c, const fmi2Real x[], size_t nx) {
    (void)c; (void)x; (void)nx; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetContinuousStates(fmi2Component c, fmi2Real x[], size_t nx) {
    (void)c; (void)x; (void)nx; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetDerivatives(fmi2Component c, fmi2Real dx[], size_t nx) {
    (void)c; (void)dx; (void)nx; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetEventIndicators(fmi2Component c, fmi2Real indicators[], size_t ni) {
    (void)c; (void)indicators; (void)ni; return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2EnterEventMode(fmi2Component c) { (void)c; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2NewDiscreteStates(fmi2Component c, fmi2EventInfo* eventInfo) {
    (void)c;
    eventInfo->newDiscreteStatesNeeded = fmi2False;
    eventInfo->terminateSimulation = fmi2False;
    eventInfo->nominalsOfContinuousStatesChanged = fmi2False;
    eventInfo->valuesOfContinuousStatesChanged = fmi2False;
    eventInfo->nextEventTimeDefined = fmi2False;
    eventInfo->nextEventTime = 0.0;
    return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2EnterContinuousTimeMode(fmi2Component c) { (void)c; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2CompletedIntegratorStep(fmi2Component c,
    fmi2Boolean noSetFMUStatePriorToCurrentPoint,
    fmi2Boolean* enterEventMode, fmi2Boolean* terminateSimulation)
{
    (void)c; (void)noSetFMUStatePriorToCurrentPoint;
    *enterEventMode = fmi2False;
    *terminateSimulation = fmi2False;
    return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetNominalsOfContinuousStates(fmi2Component c, fmi2Real x_nominal[], size_t nx) {
    (void)c;
    for (size_t i = 0; i < nx; i++) x_nominal[i] = 1.0;
    return fmi2OK;
}

/* Common FMI 2.0 function stubs (debug logging, state serialization, etc.) */
#include "fmu_common_impl.h"
