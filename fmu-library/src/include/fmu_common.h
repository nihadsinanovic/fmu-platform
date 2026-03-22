#ifndef fmu_common_h
#define fmu_common_h

/*
 * Common infrastructure for all FMU implementations.
 * Each FMU defines its own ModelData struct and provides:
 *   - MODEL_GUID
 *   - N_STATES, N_EVENT_INDICATORS
 *   - init_model_data(), compute_outputs(), compute_derivatives()
 *   - set/get variable dispatch via value references
 */

#include "fmi2Functions.h"
#include <string.h>
#include <stdio.h>
#include <math.h>

/* Physical constants */
#define CP_WATER   4186.0   /* J/(kg·K) specific heat of water */
#define CP_GLYCOL  3400.0   /* J/(kg·K) specific heat of glycol/water mix */
#define RHO_AIR    1.205    /* kg/m³ density of air at 20°C */
#define CP_AIR     1005.0   /* J/(kg·K) specific heat of air */
#define PI         3.14159265358979323846
#define YEAR_S     31536000.0  /* seconds in a year */
#define DAY_S      86400.0     /* seconds in a day */
#define KELVIN_0C  273.15      /* 0°C in Kelvin */

/* Base instance structure - every FMU model struct starts with these fields.
 * We store a copy of the callback function pointers (not the const struct). */
#define FMU_BASE_FIELDS \
    fmi2CallbackAllocateMemory allocateMemory; \
    fmi2CallbackFreeMemory freeMemory; \
    fmi2CallbackLogger logger; \
    fmi2String instanceName; \
    fmi2Real time; \
    fmi2Boolean initialized;

#endif /* fmu_common_h */
