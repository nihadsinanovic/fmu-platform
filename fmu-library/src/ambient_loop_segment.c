/*
 * ambient_loop_segment FMU — Pipe segment with heat loss and thermal inertia.
 *
 * Physics model:
 *   - Heat loss: Q_loss = UA * (T_fluid - T_ambient)
 *     where UA = 2π * length / ln(r_outer/r_inner) * k_insulation
 *   - Thermal inertia: C_fluid * dT_fluid/dt = mdot*cp*(T_in - T_fluid) - Q_loss
 *   - Pressure drop: Darcy-Weisbach simplified
 *
 * Has 1 continuous state: T_fluid (average fluid temperature in the pipe).
 *
 * Value references:
 *   Parameters: 1=length_m, 2=diameter_mm, 3=insulation_thickness_mm
 *   Inputs:     4=hydr_in_T, 5=hydr_in_mdot, 6=hydr_in_p, 7=therm_in_T_ambient
 *   Outputs:    8=hydr_out_T, 9=hydr_out_mdot, 10=hydr_out_p, 11=therm_out_Q_loss
 */

#include "fmu_common.h"

#define VR_LENGTH          1
#define VR_DIAMETER        2
#define VR_INSULATION      3
#define VR_IN_T            4
#define VR_IN_MDOT         5
#define VR_IN_P            6
#define VR_T_AMBIENT       7
#define VR_OUT_T           8
#define VR_OUT_MDOT        9
#define VR_OUT_P           10
#define VR_Q_LOSS          11

#define N_STATES 1

/* Insulation thermal conductivity W/(m·K) */
#define K_INSULATION 0.04

typedef struct {
    FMU_BASE_FIELDS

    /* Parameters */
    fmi2Real length_m;
    fmi2Real diameter_mm;
    fmi2Real insulation_thickness_mm;

    /* Inputs */
    fmi2Real hydr_in_T;
    fmi2Real hydr_in_mdot;
    fmi2Real hydr_in_p;
    fmi2Real therm_in_T_ambient;

    /* State */
    fmi2Real T_fluid;  /* average fluid temperature in pipe */

    /* Outputs */
    fmi2Real hydr_out_T;
    fmi2Real hydr_out_mdot;
    fmi2Real hydr_out_p;
    fmi2Real therm_out_Q_loss;

    /* Derived constants (computed once at init) */
    fmi2Real UA;        /* overall heat transfer coefficient × area [W/K] */
    fmi2Real C_fluid;   /* thermal capacitance of fluid in pipe [J/K] */
} ModelData;


static void compute_derived(ModelData* m) {
    double r_inner = (m->diameter_mm / 1000.0) / 2.0;        /* m */
    double r_outer = r_inner + m->insulation_thickness_mm / 1000.0;  /* m */

    if (r_outer <= r_inner || r_inner <= 0.0) {
        m->UA = 0.0;
    } else {
        /* Cylindrical insulation heat transfer */
        m->UA = 2.0 * PI * m->length_m * K_INSULATION / log(r_outer / r_inner);
    }

    /* Fluid volume in pipe */
    double volume = PI * r_inner * r_inner * m->length_m;
    double rho_fluid = 1030.0;  /* glycol/water density kg/m³ */
    m->C_fluid = rho_fluid * CP_GLYCOL * volume;
    if (m->C_fluid < 1.0) m->C_fluid = 1.0;  /* safety floor */
}


static void compute_outputs(ModelData* m) {
    /* Output temperature is the fluid state */
    m->hydr_out_T = m->T_fluid;

    /* Mass flow passes through */
    m->hydr_out_mdot = m->hydr_in_mdot;

    /* Pressure drop: simplified Darcy-Weisbach */
    double d = m->diameter_mm / 1000.0;
    double v = 0.0;
    if (m->hydr_in_mdot > 0.001 && d > 0.001) {
        double area = PI * (d / 2.0) * (d / 2.0);
        v = m->hydr_in_mdot / (1030.0 * area);
    }
    double f = 0.02;  /* friction factor (turbulent, typical) */
    double dp = f * (m->length_m / fmax(d, 0.001)) * 0.5 * 1030.0 * v * v;
    m->hydr_out_p = m->hydr_in_p - dp;
    if (m->hydr_out_p < 0.0) m->hydr_out_p = 0.0;

    /* Heat loss */
    m->therm_out_Q_loss = m->UA * (m->T_fluid - m->therm_in_T_ambient);
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

    m->length_m = 10.0;
    m->diameter_mm = 80.0;
    m->insulation_thickness_mm = 30.0;
    m->hydr_in_T = KELVIN_0C + 30.0;
    m->hydr_in_mdot = 2.0;
    m->hydr_in_p = 200000.0;
    m->therm_in_T_ambient = KELVIN_0C + 10.0;
    m->T_fluid = KELVIN_0C + 30.0;

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
    m->T_fluid = m->hydr_in_T;  /* initialize state to inlet temperature */
    m->initialized = fmi2True;
    compute_outputs(m);
    return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2Terminate(fmi2Component c) { (void)c; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2Reset(fmi2Component c) {
    ModelData* m = (ModelData*)c;
    m->time = 0.0; m->initialized = fmi2False;
    m->length_m = 10.0; m->diameter_mm = 80.0; m->insulation_thickness_mm = 30.0;
    m->T_fluid = KELVIN_0C + 30.0;
    compute_derived(m);
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Real value[]) {
    ModelData* m = (ModelData*)c;
    for (size_t i = 0; i < nvr; i++) {
        switch (vr[i]) {
            case VR_LENGTH:     m->length_m = value[i]; break;
            case VR_DIAMETER:   m->diameter_mm = value[i]; break;
            case VR_INSULATION: m->insulation_thickness_mm = value[i]; break;
            case VR_IN_T:       m->hydr_in_T = value[i]; break;
            case VR_IN_MDOT:    m->hydr_in_mdot = value[i]; break;
            case VR_IN_P:       m->hydr_in_p = value[i]; break;
            case VR_T_AMBIENT:  m->therm_in_T_ambient = value[i]; break;
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
            case VR_LENGTH:     value[i] = m->length_m; break;
            case VR_DIAMETER:   value[i] = m->diameter_mm; break;
            case VR_INSULATION: value[i] = m->insulation_thickness_mm; break;
            case VR_IN_T:       value[i] = m->hydr_in_T; break;
            case VR_IN_MDOT:    value[i] = m->hydr_in_mdot; break;
            case VR_IN_P:       value[i] = m->hydr_in_p; break;
            case VR_T_AMBIENT:  value[i] = m->therm_in_T_ambient; break;
            case VR_OUT_T:      value[i] = m->hydr_out_T; break;
            case VR_OUT_MDOT:   value[i] = m->hydr_out_mdot; break;
            case VR_OUT_P:      value[i] = m->hydr_out_p; break;
            case VR_Q_LOSS:     value[i] = m->therm_out_Q_loss; break;
            default: return fmi2Error;
        }
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Integer value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2GetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Integer value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2SetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Boolean value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2GetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Boolean value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2SetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2String value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2GetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2String value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }

/* ME functions — 1 state: T_fluid */
FMI2_EXPORT fmi2Status fmi2SetTime(fmi2Component c, fmi2Real time) {
    ((ModelData*)c)->time = time; return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetContinuousStates(fmi2Component c, const fmi2Real x[], size_t nx) {
    if (nx >= 1) ((ModelData*)c)->T_fluid = x[0];
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetContinuousStates(fmi2Component c, fmi2Real x[], size_t nx) {
    if (nx >= 1) x[0] = ((ModelData*)c)->T_fluid;
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2GetDerivatives(fmi2Component c, fmi2Real dx[], size_t nx) {
    ModelData* m = (ModelData*)c;
    if (nx >= 1) {
        double Q_in = m->hydr_in_mdot * CP_GLYCOL * (m->hydr_in_T - m->T_fluid);
        double Q_loss = m->UA * (m->T_fluid - m->therm_in_T_ambient);
        dx[0] = (Q_in - Q_loss) / m->C_fluid;
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
    if (nx >= 1) xn[0] = 300.0;  /* nominal temperature ~300K */
    return fmi2OK;
}
