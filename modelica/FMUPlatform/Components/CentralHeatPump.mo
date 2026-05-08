within FMUPlatform.Components;
model CentralHeatPump
  "Central heat pump with integrated pump, ground-source boundary, and PI control"
  replaceable package Medium = Buildings.Media.Water "Loop-side medium";

  parameter Modelica.Units.SI.Power Q_flow_nominal_W=120000
    "Nominal heating capacity at the load (loop) side";
  parameter Real COP_nominal=3.8 "Nominal coefficient of performance";
  parameter String source_type="ground" "Source type identifier (ground|air|water)";
  parameter Modelica.Units.SI.Temperature T_ground=283.15
    "Source-side fluid temperature (used for ground/water source)";
  parameter Modelica.Units.SI.MassFlowRate mLoad_flow_nominal=
      Q_flow_nominal_W/(4186*5)
    "Nominal mass flow rate on the load side (sized for 5 K dT)";
  parameter Modelica.Units.SI.MassFlowRate mSou_flow_nominal=
      Q_flow_nominal_W*(1 - 1/COP_nominal)/(4186*3)
    "Nominal mass flow rate on the source side (sized for 3 K dT)";
  parameter Real k=0.1 "PI controller gain";
  parameter Modelica.Units.SI.Time Ti=600 "PI controller integral time";

  Modelica.Fluid.Interfaces.FluidPort_a port_a(redeclare package Medium = Medium)
    "Loop return (cold side)";
  Modelica.Fluid.Interfaces.FluidPort_b port_b(redeclare package Medium = Medium)
    "Loop supply (hot side)";
  Modelica.Blocks.Interfaces.RealInput TSet(final unit="K", displayUnit="degC")
    "Loop supply temperature setpoint";

  Buildings.Fluid.HeatPumps.Carnot_y heaPum(
    redeclare package Medium1 = Medium,
    redeclare package Medium2 = Medium,
    P_nominal=Q_flow_nominal_W/COP_nominal,
    QCon_flow_nominal=Q_flow_nominal_W,
    m1_flow_nominal=mLoad_flow_nominal,
    m2_flow_nominal=mSou_flow_nominal,
    dTEva_nominal=-3,
    dTCon_nominal=5,
    use_eta_Carnot_nominal=true,
    etaCarnot_nominal=COP_nominal*(273.15 + 5)/(45 - 5))
    "Carnot heat pump (idealised compressor)";

  Buildings.Fluid.Movers.FlowControlled_m_flow pumLoad(
    redeclare package Medium = Medium,
    m_flow_nominal=mLoad_flow_nominal,
    inputType=Buildings.Fluid.Types.InputType.Constant,
    constantMassFlowRate=mLoad_flow_nominal,
    nominalValuesDefineDefaultPressureCurve=true)
    "Loop-side circulator pump";

  Buildings.Fluid.Sources.Boundary_pT souBou(
    redeclare package Medium = Medium,
    use_T_in=true,
    nPorts=2)
    "Source-side boundary representing the ground loop";
  Modelica.Blocks.Sources.Constant TSouBou(k=T_ground)
    "Source-side fluid temperature";

  Buildings.Fluid.Movers.FlowControlled_m_flow pumSou(
    redeclare package Medium = Medium,
    m_flow_nominal=mSou_flow_nominal,
    inputType=Buildings.Fluid.Types.InputType.Constant,
    constantMassFlowRate=mSou_flow_nominal,
    nominalValuesDefineDefaultPressureCurve=true)
    "Source-side circulator pump";

  Buildings.Fluid.Sensors.TemperatureTwoPort TSup(
    redeclare package Medium = Medium,
    m_flow_nominal=mLoad_flow_nominal)
    "Loop supply temperature sensor";

  Buildings.Controls.Continuous.LimPID conPI(
    controllerType=Modelica.Blocks.Types.SimpleController.PI,
    k=k,
    Ti=Ti,
    yMax=1,
    yMin=0)
    "PI controller modulating compressor speed";

equation
  connect(port_a, pumLoad.port_a);
  connect(pumLoad.port_b, heaPum.port_a1);
  connect(heaPum.port_b1, TSup.port_a);
  connect(TSup.port_b, port_b);

  connect(souBou.T_in, TSouBou.y);
  connect(souBou.ports[1], pumSou.port_a);
  connect(pumSou.port_b, heaPum.port_a2);
  connect(heaPum.port_b2, souBou.ports[2]);

  connect(TSet, conPI.u_s);
  connect(TSup.T, conPI.u_m);
  connect(conPI.y, heaPum.y);

  annotation (Documentation(info="<html>
<p>
Central heat pump for the ambient loop, wrapping a Carnot heat pump model on
the load side, an integrated loop pump, and a fixed-temperature source-side
boundary representing the ground loop. A PI controller modulates compressor
speed against the loop supply temperature setpoint.
</p>
<p>
The source-side boundary doubles as the system pressure reference for the
hydraulic loop. The borefield model is intentionally omitted in this v1
wrapper; <code>T_ground</code> can be made time-varying by replacing the
constant.
</p>
</html>"));
end CentralHeatPump;
