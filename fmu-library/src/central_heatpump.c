/*
 * central_heatpump FMU — Central heat pump for ambient-loop building system.
 *
 * Physics: Takes return water from the ambient loop, heats it, and delivers
 * it at a higher temperature. Modulated by ctrl_in_signal (0-1).
 *
 *   Q_heating = nominal_power * COP_nominal * ctrl_signal
 *   T_out = T_in + Q_heating / (mdot * cp)   (clamped to avoid division by zero)
 *   P_elec = Q_heating / COP_nominal
 *
 * No continuous states — algebraic model (quasi-static heat pump).
 *
 * Value references:
 *   Parameters: 1=nominal_power_kW, 2=COP_nominal, 3=source_type
 *   Inputs:     4=hydr_in_T, 5=hydr_in_mdot, 6=hydr_in_p, 7=ctrl_in_signal
 *   Outputs:    8=hydr_out_T, 9=hydr_out_mdot, 10=hydr_out_p, 11=elec_out_P, 12=therm_out_Q
 */

#include "fmu_common.h"

#define VR_NOMINAL_POWER  1
#define VR_COP_NOMINAL    2
#define VR_SOURCE_TYPE    3
#define VR_IN_T           4
#define VR_IN_MDOT        5
#define VR_IN_P           6
#define VR_CTRL_SIGNAL    7
#define VR_OUT_T          8
#define VR_OUT_MDOT       9
#define VR_OUT_P          10
#define VR_ELEC_P         11
#define VR_THERM_Q        12

typedef struct {
    FMU_BASE_FIELDS

    /* Parameters */
    fmi2Real nominal_power_kW;
    fmi2Real COP_nominal;
    char source_type[32];

    /* Inputs */
    fmi2Real hydr_in_T;
    fmi2Real hydr_in_mdot;
    fmi2Real hydr_in_p;
    fmi2Real ctrl_in_signal;

    /* Outputs */
    fmi2Real hydr_out_T;
    fmi2Real hydr_out_mdot;
    fmi2Real hydr_out_p;
    fmi2Real elec_out_P;
    fmi2Real therm_out_Q;
} ModelData;


static void compute_outputs(ModelData* m) {
    double signal = m->ctrl_in_signal;
    if (signal < 0.0) signal = 0.0;
    if (signal > 1.0) signal = 1.0;

    double Q_max = m->nominal_power_kW * 1000.0;  /* convert kW to W */
    double Q_heating = Q_max * signal;

    /* COP adjustment based on temperature lift (simplified Carnot fraction) */
    double T_source = m->hydr_in_T;
    double T_supply_target = T_source + 10.0;  /* typical 10K lift */
    double COP = m->COP_nominal;
    if (T_supply_target > T_source + 1.0) {
        /* Carnot-limited COP: COP = eta_carnot * T_hot / (T_hot - T_cold) */
        double eta_carnot = 0.45;  /* typical fraction of Carnot */
        double COP_carnot = T_supply_target / (T_supply_target - T_source);
        double COP_adj = eta_carnot * COP_carnot;
        /* Use the lesser of nominal and Carnot-adjusted */
        if (COP_adj < COP) COP = COP_adj;
    }

    m->therm_out_Q = Q_heating;
    m->elec_out_P = (COP > 0.1) ? Q_heating / COP : 0.0;

    /* Temperature rise in the fluid */
    double mdot = m->hydr_in_mdot;
    if (mdot > 0.001) {
        m->hydr_out_T = m->hydr_in_T + Q_heating / (mdot * CP_GLYCOL);
    } else {
        m->hydr_out_T = m->hydr_in_T;
    }

    /* Mass flow and pressure pass through */
    m->hydr_out_mdot = m->hydr_in_mdot;
    /* Small pressure drop across heat pump */
    m->hydr_out_p = m->hydr_in_p - 5000.0;  /* 5 kPa drop */
    if (m->hydr_out_p < 0.0) m->hydr_out_p = 0.0;
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

    /* Defaults */
    m->nominal_power_kW = 50.0;
    m->COP_nominal = 3.8;
    strcpy(m->source_type, "ground");
    m->hydr_in_T = KELVIN_0C + 30.0;  /* 30°C return */
    m->hydr_in_mdot = 2.0;
    m->hydr_in_p = 200000.0;  /* 2 bar */
    m->ctrl_in_signal = 1.0;

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
    m->initialized = fmi2True;
    compute_outputs(m);
    return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2Terminate(fmi2Component c) { (void)c; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2Reset(fmi2Component c) {
    ModelData* m = (ModelData*)c;
    m->time = 0.0; m->initialized = fmi2False;
    m->nominal_power_kW = 50.0; m->COP_nominal = 3.8;
    strcpy(m->source_type, "ground");
    m->ctrl_in_signal = 1.0;
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Real value[]) {
    ModelData* m = (ModelData*)c;
    for (size_t i = 0; i < nvr; i++) {
        switch (vr[i]) {
            case VR_NOMINAL_POWER: m->nominal_power_kW = value[i]; break;
            case VR_COP_NOMINAL:   m->COP_nominal = value[i]; break;
            case VR_IN_T:          m->hydr_in_T = value[i]; break;
            case VR_IN_MDOT:       m->hydr_in_mdot = value[i]; break;
            case VR_IN_P:          m->hydr_in_p = value[i]; break;
            case VR_CTRL_SIGNAL:   m->ctrl_in_signal = value[i]; break;
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
            case VR_NOMINAL_POWER: value[i] = m->nominal_power_kW; break;
            case VR_COP_NOMINAL:   value[i] = m->COP_nominal; break;
            case VR_IN_T:          value[i] = m->hydr_in_T; break;
            case VR_IN_MDOT:       value[i] = m->hydr_in_mdot; break;
            case VR_IN_P:          value[i] = m->hydr_in_p; break;
            case VR_CTRL_SIGNAL:   value[i] = m->ctrl_in_signal; break;
            case VR_OUT_T:         value[i] = m->hydr_out_T; break;
            case VR_OUT_MDOT:      value[i] = m->hydr_out_mdot; break;
            case VR_OUT_P:         value[i] = m->hydr_out_p; break;
            case VR_ELEC_P:        value[i] = m->elec_out_P; break;
            case VR_THERM_Q:       value[i] = m->therm_out_Q; break;
            default: return fmi2Error;
        }
    }
    return fmi2OK;
}

FMI2_EXPORT fmi2Status fmi2SetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Integer value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2GetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Integer value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2SetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Boolean value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2GetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Boolean value[]) { (void)c; (void)vr; (void)nvr; (void)value; return fmi2OK; }

FMI2_EXPORT fmi2Status fmi2SetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2String value[]) {
    ModelData* m = (ModelData*)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_SOURCE_TYPE) {
            strncpy(m->source_type, value[i], sizeof(m->source_type) - 1);
            m->source_type[sizeof(m->source_type) - 1] = '\0';
        }
    }
    return fmi2OK;
}
FMI2_EXPORT fmi2Status fmi2GetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2String value[]) {
    ModelData* m = (ModelData*)c;
    for (size_t i = 0; i < nvr; i++) {
        if (vr[i] == VR_SOURCE_TYPE) value[i] = m->source_type;
        else return fmi2Error;
    }
    return fmi2OK;
}

/* ME functions — no states */
FMI2_EXPORT fmi2Status fmi2SetTime(fmi2Component c, fmi2Real time) { ((ModelData*)c)->time = time; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2SetContinuousStates(fmi2Component c, const fmi2Real x[], size_t nx) { (void)c; (void)x; (void)nx; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2GetContinuousStates(fmi2Component c, fmi2Real x[], size_t nx) { (void)c; (void)x; (void)nx; return fmi2OK; }
FMI2_EXPORT fmi2Status fmi2GetDerivatives(fmi2Component c, fmi2Real dx[], size_t nx) { (void)c; (void)dx; (void)nx; return fmi2OK; }
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
    (void)c; for (size_t i = 0; i < nx; i++) xn[i] = 1.0; return fmi2OK;
}
