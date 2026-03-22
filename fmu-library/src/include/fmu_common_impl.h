/*
 * Common FMI 2.0 function implementations shared by all FMUs.
 *
 * These are functions that PyFMI expects but that don't need per-model logic:
 * - fmi2GetTypesPlatform / fmi2GetVersion
 * - fmi2SetDebugLogging
 * - FMU state serialization (unsupported, returns fmi2Error)
 * - Directional derivatives (unsupported, returns fmi2Error)
 *
 * Each .c file should #include this ONCE at the bottom, after all other
 * function implementations.
 */

#ifndef FMU_COMMON_IMPL_H
#define FMU_COMMON_IMPL_H

#include "fmi2Functions.h"

FMI2_EXPORT const char* fmi2GetTypesPlatform(void) {
    return fmi2TypesPlatform;
}

FMI2_EXPORT const char* fmi2GetVersion(void) {
    return "2.0";
}

FMI2_EXPORT fmi2Status fmi2SetDebugLogging(fmi2Component c, fmi2Boolean loggingOn,
    size_t nCategories, const fmi2String categories[])
{
    (void)c; (void)loggingOn; (void)nCategories; (void)categories;
    return fmi2OK;
}

/* FMU state management — not supported */
FMI2_EXPORT fmi2Status fmi2GetFMUstate(fmi2Component c, fmi2FMUstate* FMUstate) {
    (void)c; (void)FMUstate; return fmi2Error;
}
FMI2_EXPORT fmi2Status fmi2SetFMUstate(fmi2Component c, fmi2FMUstate FMUstate) {
    (void)c; (void)FMUstate; return fmi2Error;
}
FMI2_EXPORT fmi2Status fmi2FreeFMUstate(fmi2Component c, fmi2FMUstate* FMUstate) {
    (void)c; (void)FMUstate; return fmi2Error;
}
FMI2_EXPORT fmi2Status fmi2SerializedFMUstateSize(fmi2Component c, fmi2FMUstate FMUstate, size_t* size) {
    (void)c; (void)FMUstate; (void)size; return fmi2Error;
}
FMI2_EXPORT fmi2Status fmi2SerializeFMUstate(fmi2Component c, fmi2FMUstate FMUstate, fmi2Byte serializedState[], size_t size) {
    (void)c; (void)FMUstate; (void)serializedState; (void)size; return fmi2Error;
}
FMI2_EXPORT fmi2Status fmi2DeSerializeFMUstate(fmi2Component c, const fmi2Byte serializedState[], size_t size, fmi2FMUstate* FMUstate) {
    (void)c; (void)serializedState; (void)size; (void)FMUstate; return fmi2Error;
}

/* Directional derivatives — not supported */
FMI2_EXPORT fmi2Status fmi2GetDirectionalDerivative(fmi2Component c,
    const fmi2ValueReference vUnknown_ref[], size_t nUnknown,
    const fmi2ValueReference vKnown_ref[], size_t nKnown,
    const fmi2Real dvKnown[], fmi2Real dvUnknown[])
{
    (void)c; (void)vUnknown_ref; (void)nUnknown;
    (void)vKnown_ref; (void)nKnown; (void)dvKnown; (void)dvUnknown;
    return fmi2Error;
}

#endif /* FMU_COMMON_IMPL_H */
