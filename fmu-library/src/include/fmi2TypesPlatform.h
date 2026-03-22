#ifndef fmi2TypesPlatform_h
#define fmi2TypesPlatform_h

#include <stddef.h>

/* Standard header for FMI 2.0 Type definitions */

#define fmi2TypesPlatform "default"

typedef void*        fmi2Component;
typedef void*        fmi2ComponentEnvironment;
typedef void*        fmi2FMUstate;
typedef unsigned int fmi2ValueReference;
typedef double       fmi2Real;
typedef int          fmi2Integer;
typedef int          fmi2Boolean;
typedef const char*  fmi2String;
typedef char         fmi2Byte;

#define fmi2True  1
#define fmi2False 0

typedef enum {
    fmi2OK,
    fmi2Warning,
    fmi2Discard,
    fmi2Error,
    fmi2Fatal,
    fmi2Pending
} fmi2Status;

typedef enum {
    fmi2ModelExchange,
    fmi2CoSimulation
} fmi2Type;

typedef enum {
    fmi2DoStepStatus,
    fmi2PendingStatus,
    fmi2LastSuccessfulTime,
    fmi2Terminated
} fmi2StatusKind;

typedef void (*fmi2CallbackLogger)(fmi2ComponentEnvironment, fmi2String, fmi2Status, fmi2String, fmi2String, ...);
typedef void* (*fmi2CallbackAllocateMemory)(size_t, size_t);
typedef void (*fmi2CallbackFreeMemory)(void*);
typedef void (*fmi2StepFinished)(fmi2ComponentEnvironment, fmi2Status);

typedef struct {
    const fmi2CallbackLogger         logger;
    const fmi2CallbackAllocateMemory allocateMemory;
    const fmi2CallbackFreeMemory     freeMemory;
    const fmi2StepFinished           stepFinished;
    const fmi2ComponentEnvironment   componentEnvironment;
} fmi2CallbackFunctions;

#endif /* fmi2TypesPlatform_h */
