/*
 * Common FMI 2.0 Model Exchange boilerplate.
 * Each FMU-specific C file includes this, defines its own struct and physics,
 * then includes fmi2_common_impl.h for the generic API function implementations.
 */
#ifndef FMI2_COMMON_H
#define FMI2_COMMON_H

#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdio.h>

/* ---- FMI 2.0 type definitions (inline to avoid external header deps) ---- */

typedef void*        fmi2Component;
typedef void*        fmi2ComponentEnvironment;
typedef void*        fmi2FMUstate;
typedef unsigned int fmi2ValueReference;
typedef double       fmi2Real;
typedef int          fmi2Integer;
typedef int          fmi2Boolean;
typedef const char*  fmi2String;

#define fmi2True  1
#define fmi2False 0

typedef enum {
    fmi2OK      = 0,
    fmi2Warning = 1,
    fmi2Discard = 2,
    fmi2Error   = 3,
    fmi2Fatal   = 4,
    fmi2Pending = 5
} fmi2Status;

typedef enum { fmi2ModelExchange, fmi2CoSimulation } fmi2Type;

typedef void  (*fmi2CallbackLogger)(fmi2ComponentEnvironment, fmi2String, fmi2Status, fmi2String, fmi2String, ...);
typedef void* (*fmi2CallbackAllocateMemory)(size_t, size_t);
typedef void  (*fmi2CallbackFreeMemory)(void*);
typedef void  (*fmi2StepFinished)(fmi2ComponentEnvironment, fmi2Status);

typedef struct {
    fmi2CallbackLogger         logger;
    fmi2CallbackAllocateMemory allocateMemory;
    fmi2CallbackFreeMemory     freeMemory;
    fmi2StepFinished           stepFinished;
    fmi2ComponentEnvironment   componentEnvironment;
} fmi2CallbackFunctions;

typedef struct {
    fmi2Boolean newDiscreteStatesNeeded;
    fmi2Boolean terminateSimulation;
    fmi2Boolean nominalsOfContinuousStatesChanged;
    fmi2Boolean valuesOfContinuousStatesChanged;
    fmi2Boolean nextEventTimeDefined;
    fmi2Real    nextEventTime;
} fmi2EventInfo;

/* ---- Visibility macro ---- */
#ifdef _WIN32
#define FMI2_EXPORT __declspec(dllexport)
#else
#define FMI2_EXPORT __attribute__((visibility("default")))
#endif

/* ---- Physical constants ---- */
#define CP_WATER   4180.0   /* J/(kg·K) */
#define RHO_WATER  1000.0   /* kg/m³    */
#define CP_AIR     1005.0   /* J/(kg·K) */
#define RHO_AIR    1.2      /* kg/m³    */
#define PI         3.14159265358979323846
#define YEAR_S     31536000.0  /* seconds in 365 days */
#define DAY_S      86400.0

#endif /* FMI2_COMMON_H */
