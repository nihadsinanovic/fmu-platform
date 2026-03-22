#ifndef fmi2TypesPlatform_h
#define fmi2TypesPlatform_h

/* Standard FMI 2.0 type definitions */

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

#endif /* fmi2TypesPlatform_h */
