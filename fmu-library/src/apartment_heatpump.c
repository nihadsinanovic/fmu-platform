/*
 * apartment_heatpump FMU — Per-apartment heat pump.
 *
 * Physics:
 *   Draws heat from the ambient loop, delivers to the apartment.
 *   Modulates based on room temperature feedback (PI-like control).
 *
 *   T_setpoint = 293.15 K (20°C)
 *   error = T_setpoint - T_room
 *   modulation = clamp(ctrl_signal * (1 + Kp * error), 0, 1)
 *   Q_heating = nominal_power * modulation
 *   P_elec = Q_heating / COP (COP adjusted for temperature lift)
 *   T_out_hydr = T_in_hydr - Q_evap / (mdot * cp)  (heat extracted from loop)
 *
 * No continuous states — algebraic model.
 *
 * Value references:
 *   Parameters: 1=nominal_power_kW, 2=COP_nominal
 *   Inputs:     3=hydr_in_T, 4=hydr_in_mdot, 5=hydr_in_p, 6=therm_in_T_room, 7=ctrl_in_signal
 *   Outputs:    8=hydr_out_T, 9=hydr_out_mdot, 10=hydr_out_p, 11=therm_out_Q_heating, 12=elec_out_P
 */

#include "fmu_common.h"

#define VR_NOMINAL_POWER  1
#define VR_COP_NOMINAL    2
#define VR_IN_T           3
#define VR_IN_MDOT        4
#define VR_IN_P           5
#define VR_T_ROOM         6
#define VR_CTRL_SIGNAL    7
#define VR_OUT_T          8
#define VR_OUT_MDOT       9
#define VR_OUT_P          10
#define VR_Q_HEATING      11
#define VR_ELEC_P         12

#define T_SETPOINT (KELVIN_0C + 20.0)  /* 20°C room setpoint */
#define KP 0.2  /* proportional gain per K error */

typedef struct {
    FMU_BASE_FIELDS

    /* Parameters */
    fmi2Real nominal_power_kW;
    fmi2Real COP_nominal;

    /* Inputs */
    fmi2Real hydr_in_T;
    fmi2Real hydr_in_mdot;
    fmi2Real hydr_in_p;
    fmi2Real therm_in_T_room;
    fmi2Real ctrl_in_signal;

    /* Outputs */
    fmi2Real hydr_out_T;
    fmi2Real hydr_out_mdot;
    fmi2Real hydr_out_p;
    fmi2Real therm_out_Q_heating;
    fmi2Real elec_out_P;
} ModelData;


static void compute_outputs(ModelData* m) {
    /* Temperature error for modulation */
    double error = T_SETPOINT - m->therm_in_T_room;

    /* Modulation: increase when room is cold, decrease when warm */
    double modulation = m->ctrl_in_signal * (1.0 + KP * error);
    if (modulation < 0.0) modulation = 0.0;
    if (modulation > 1.0) modulation = 1.0;

    /* If room is above setpoint + 1K, turn off */
    if (error < -1.0) modulation = 0.0;

    double Q_max = m->nominal_power_kW * 1000.0;
    double Q_heating = Q_max * modulation;

    /* COP adjustment for temperature lift */
    double T_source = m->hydr_in_T;        /* ambient loop temperature */
    double T_sink = m->therm_in_T_room;     /* room temperature (condenser side) */
    double COP = m->COP_nominal;

    if (T_sink > T_source + 1.0) {
        double eta = 0.45;
        double COP_carnot = (T_sink + 5.0) / ((T_sink + 5.0) - T_source);
        double COP_adj = eta * COP_carnot;
        if (COP_adj < COP) COP = COP_adj;
    }
    if (COP < 1.0) COP = 1.0;

    m->therm_out_Q_heating = Q_heating;
    m->elec_out_P = Q_heating / COP;

    /* Heat extracted from ambient loop (evaporator side) */
    double Q_evap = Q_heating - m->elec_out_P;  /* Q_evap = Q_cond - W_elec */
    if (Q_evap < 0.0) Q_evap = 0.0;

    /* Loop water cooled by evaporator */
    double mdot = m->hydr_in_mdot;
    if (mdot > 0.001) {
        m->hydr_out_T = m->hydr_in_T - Q_evap / (mdot * CP_GLYCOL);
    } else {
        m->hydr_out_T = m->hydr_in_T;
    }

    m->hydr_out_mdot = m->hydr_in_mdot;
    m->hydr_out_p = m->hydr_in_p - 3000.0;  /* 3 kPa pressure drop */
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

    m->nominal_power_kW = 5.0;
    m->COP_nominal = 4.2;
    m->hydr_in_T = KELVIN_0C + 30.0;
    m->hydr_in_mdot = 0.5;
    m->hydr_in_p = 180000.0;
    m->therm_in_T_room = KELVIN_0C + 20.0;
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
    m->nominal_power_kW = 5.0; m->COP_nominal = 4.2;
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
            case VR_T_ROOM:        m->therm_in_T_room = value[i]; break;
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
            case VR_T_ROOM:        value[i] = m->therm_in_T_room; break;
            case VR_CTRL_SIGNAL:   value[i] = m->ctrl_in_signal; break;
            case VR_OUT_T:         value[i] = m->hydr_out_T; break;
            case VR_OUT_MDOT:      value[i] = m->hydr_out_mdot; break;
            case VR_OUT_P:         value[i] = m->hydr_out_p; break;
            case VR_Q_HEATING:     value[i] = m->therm_out_Q_heating; break;
            case VR_ELEC_P:        value[i] = m->elec_out_P; break;
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

/* Common FMI 2.0 function stubs (debug logging, state serialization, etc.) */
#include "fmu_common_impl.h"
