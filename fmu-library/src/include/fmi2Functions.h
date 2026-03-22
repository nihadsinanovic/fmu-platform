#ifndef fmi2Functions_h
#define fmi2Functions_h

#include "fmi2TypesPlatform.h"
#include "fmi2FunctionTypes.h"

#include <stdlib.h>

/* Export macros */
#if defined(_WIN32) || defined(__CYGWIN__)
  #define FMI2_EXPORT __declspec(dllexport)
#else
  #define FMI2_EXPORT __attribute__((visibility("default")))
#endif

/* Event info structure for fmi2NewDiscreteStates */
typedef struct {
    fmi2Boolean newDiscreteStatesNeeded;
    fmi2Boolean terminateSimulation;
    fmi2Boolean nominalsOfContinuousStatesChanged;
    fmi2Boolean valuesOfContinuousStatesChanged;
    fmi2Boolean nextEventTimeDefined;
    fmi2Real    nextEventTime;
} fmi2EventInfo;

/* Function declarations - implemented by each FMU */
FMI2_EXPORT fmi2Component fmi2Instantiate(
    fmi2String instanceName, fmi2Type fmuType, fmi2String fmuGUID,
    fmi2String fmuResourceLocation, const fmi2CallbackFunctions* functions,
    fmi2Boolean visible, fmi2Boolean loggingOn);

FMI2_EXPORT void fmi2FreeInstance(fmi2Component c);

FMI2_EXPORT fmi2Status fmi2SetupExperiment(
    fmi2Component c, fmi2Boolean toleranceDefined, fmi2Real tolerance,
    fmi2Real startTime, fmi2Boolean stopTimeDefined, fmi2Real stopTime);

FMI2_EXPORT fmi2Status fmi2EnterInitializationMode(fmi2Component c);
FMI2_EXPORT fmi2Status fmi2ExitInitializationMode(fmi2Component c);
FMI2_EXPORT fmi2Status fmi2Terminate(fmi2Component c);
FMI2_EXPORT fmi2Status fmi2Reset(fmi2Component c);

FMI2_EXPORT fmi2Status fmi2SetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Real value[]);
FMI2_EXPORT fmi2Status fmi2GetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Real value[]);
FMI2_EXPORT fmi2Status fmi2SetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Integer value[]);
FMI2_EXPORT fmi2Status fmi2GetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Integer value[]);
FMI2_EXPORT fmi2Status fmi2SetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Boolean value[]);
FMI2_EXPORT fmi2Status fmi2GetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Boolean value[]);
FMI2_EXPORT fmi2Status fmi2SetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2String value[]);
FMI2_EXPORT fmi2Status fmi2GetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2String value[]);

/* Model Exchange specific */
FMI2_EXPORT fmi2Status fmi2SetTime(fmi2Component c, fmi2Real time);
FMI2_EXPORT fmi2Status fmi2SetContinuousStates(fmi2Component c, const fmi2Real x[], size_t nx);
FMI2_EXPORT fmi2Status fmi2GetContinuousStates(fmi2Component c, fmi2Real x[], size_t nx);
FMI2_EXPORT fmi2Status fmi2GetDerivatives(fmi2Component c, fmi2Real dx[], size_t nx);
FMI2_EXPORT fmi2Status fmi2GetEventIndicators(fmi2Component c, fmi2Real indicators[], size_t ni);
FMI2_EXPORT fmi2Status fmi2EnterEventMode(fmi2Component c);
FMI2_EXPORT fmi2Status fmi2NewDiscreteStates(fmi2Component c, fmi2EventInfo* eventInfo);
FMI2_EXPORT fmi2Status fmi2EnterContinuousTimeMode(fmi2Component c);
FMI2_EXPORT fmi2Status fmi2CompletedIntegratorStep(fmi2Component c, fmi2Boolean noSetFMUStatePriorToCurrentPoint, fmi2Boolean* enterEventMode, fmi2Boolean* terminateSimulation);
FMI2_EXPORT fmi2Status fmi2GetNominalsOfContinuousStates(fmi2Component c, fmi2Real x_nominal[], size_t nx);

#endif /* fmi2Functions_h */
