#ifndef fmi2FunctionTypes_h
#define fmi2FunctionTypes_h

#include "fmi2TypesPlatform.h"

/* FMI 2.0 function type definitions */

typedef fmi2Component (*fmi2InstantiateTYPE)(fmi2String, fmi2Type, fmi2String, fmi2String, const fmi2CallbackFunctions*, fmi2Boolean, fmi2Boolean);
typedef void (*fmi2FreeInstanceTYPE)(fmi2Component);
typedef fmi2Status (*fmi2SetupExperimentTYPE)(fmi2Component, fmi2Boolean, fmi2Real, fmi2Real, fmi2Boolean, fmi2Real);
typedef fmi2Status (*fmi2EnterInitializationModeTYPE)(fmi2Component);
typedef fmi2Status (*fmi2ExitInitializationModeTYPE)(fmi2Component);
typedef fmi2Status (*fmi2TerminateTYPE)(fmi2Component);
typedef fmi2Status (*fmi2ResetTYPE)(fmi2Component);
typedef fmi2Status (*fmi2SetRealTYPE)(fmi2Component, const fmi2ValueReference[], size_t, const fmi2Real[]);
typedef fmi2Status (*fmi2GetRealTYPE)(fmi2Component, const fmi2ValueReference[], size_t, fmi2Real[]);
typedef fmi2Status (*fmi2SetIntegerTYPE)(fmi2Component, const fmi2ValueReference[], size_t, const fmi2Integer[]);
typedef fmi2Status (*fmi2GetIntegerTYPE)(fmi2Component, const fmi2ValueReference[], size_t, fmi2Integer[]);
typedef fmi2Status (*fmi2SetStringTYPE)(fmi2Component, const fmi2ValueReference[], size_t, const fmi2String[]);
typedef fmi2Status (*fmi2GetStringTYPE)(fmi2Component, const fmi2ValueReference[], size_t, fmi2String[]);
typedef fmi2Status (*fmi2SetBooleanTYPE)(fmi2Component, const fmi2ValueReference[], size_t, const fmi2Boolean[]);
typedef fmi2Status (*fmi2GetBooleanTYPE)(fmi2Component, const fmi2ValueReference[], size_t, fmi2Boolean[]);
typedef fmi2Status (*fmi2SetTimeTYPE)(fmi2Component, fmi2Real);
typedef fmi2Status (*fmi2SetContinuousStatesTYPE)(fmi2Component, const fmi2Real[], size_t);
typedef fmi2Status (*fmi2GetContinuousStatesTYPE)(fmi2Component, fmi2Real[], size_t);
typedef fmi2Status (*fmi2GetDerivativesTYPE)(fmi2Component, fmi2Real[], size_t);
typedef fmi2Status (*fmi2GetEventIndicatorsTYPE)(fmi2Component, fmi2Real[], size_t);
typedef fmi2Status (*fmi2EnterEventModeTYPE)(fmi2Component);
typedef fmi2Status (*fmi2NewDiscreteStatesTYPE)(fmi2Component, void*);
typedef fmi2Status (*fmi2EnterContinuousTimeModeTYPE)(fmi2Component);
typedef fmi2Status (*fmi2CompletedIntegratorStepTYPE)(fmi2Component, fmi2Boolean, fmi2Boolean*, fmi2Boolean*);

#endif /* fmi2FunctionTypes_h */
