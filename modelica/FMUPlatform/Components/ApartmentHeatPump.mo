within FMUPlatform.Components;
model ApartmentHeatPump
  "Per-apartment heat pump drawing from the ambient loop, with integrated PI control"
  replaceable package Medium = Buildings.Media.Water "Evaporator-side medium";

  parameter Modelica.Units.SI.Power Q_flow_nominal_W=5000
    "Nominal heating capacity at the condenser (zone) side";
  parameter Real COP_nominal=4.2 "Nominal coefficient of performance";
  parameter Modelica.Units.SI.MassFlowRate mEva_flow_nominal=
      Q_flow_nominal_W*(1 - 1/COP_nominal)/(4186*3)
    "Nominal mass flow rate on the evaporator (loop) side, sized for 3 K dT";
  parameter Real k=0.5 "PI controller gain";
  parameter Modelica.Units.SI.Time Ti=900 "PI controller integral time";

  Modelica.Fluid.Interfaces.FluidPort_a port_a(redeclare package Medium = Medium)
    "Loop supply (evaporator inlet)";
  Modelica.Fluid.Interfaces.FluidPort_b port_b(redeclare package Medium = Medium)
    "Loop return (evaporator outlet)";
  Modelica.Thermal.HeatTransfer.Interfaces.HeatPort_a heatPortCon
    "Condenser heat port — heat injection into the apartment thermal zone";
  Modelica.Blocks.Interfaces.RealInput TZoneSet(final unit="K", displayUnit="degC")
    "Zone temperature setpoint";
  Modelica.Blocks.Interfaces.RealInput TZone(final unit="K", displayUnit="degC")
    "Measured zone temperature";

  Buildings.Fluid.HeatPumps.Carnot_y heaPum(
    redeclare package Medium1 = Medium,
    redeclare package Medium2 = Medium,
    P_nominal=Q_flow_nominal_W/COP_nominal,
    QCon_flow_nominal=Q_flow_nominal_W,
    m1_flow_nominal=Q_flow_nominal_W/(4186*5),
    m2_flow_nominal=mEva_flow_nominal,
    dTEva_nominal=-3,
    dTCon_nominal=5,
    use_eta_Carnot_nominal=true,
    etaCarnot_nominal=COP_nominal*(273.15 + 35)/(45 - 5))
    "Carnot heat pump model (idealised compressor)";

  Buildings.Fluid.Movers.FlowControlled_m_flow pumEva(
    redeclare package Medium = Medium,
    m_flow_nominal=mEva_flow_nominal,
    inputType=Buildings.Fluid.Types.InputType.Constant,
    constantMassFlowRate=mEva_flow_nominal,
    nominalValuesDefineDefaultPressureCurve=true)
    "Evaporator-side circulator drawing from the ambient loop";

  Buildings.Fluid.Sources.Boundary_pT conBou(
    redeclare package Medium = Medium,
    nPorts=2)
    "Local condenser-side closed loop boundary (pressure reference)";
  Buildings.Fluid.Movers.FlowControlled_m_flow pumCon(
    redeclare package Medium = Medium,
    m_flow_nominal=Q_flow_nominal_W/(4186*5),
    inputType=Buildings.Fluid.Types.InputType.Constant,
    constantMassFlowRate=Q_flow_nominal_W/(4186*5),
    nominalValuesDefineDefaultPressureCurve=true)
    "Condenser-side circulator";
  Buildings.Fluid.HeatExchangers.HeaterCooler_u conHex(
    redeclare package Medium = Medium,
    m_flow_nominal=Q_flow_nominal_W/(4186*5),
    Q_flow_nominal=-Q_flow_nominal_W,
    dp_nominal=0)
    "Condenser-to-zone coupling (delivers heaPum.QCon_flow as a HeatPort)";
  Modelica.Thermal.HeatTransfer.Sources.PrescribedHeatFlow preHea
    "Prescribed heat flow injected into heatPortCon";
  Modelica.Blocks.Math.Gain negate(k=1)
    "Pass-through; QCon_flow is positive when heating, sign already correct for HeatPort";

  Buildings.Controls.Continuous.LimPID conPI(
    controllerType=Modelica.Blocks.Types.SimpleController.PI,
    k=k,
    Ti=Ti,
    yMax=1,
    yMin=0,
    reverseActing=true)
    "PI controller modulating compressor speed against zone temperature";

equation
  connect(port_a, pumEva.port_a);
  connect(pumEva.port_b, heaPum.port_a2);
  connect(heaPum.port_b2, port_b);

  connect(conBou.ports[1], pumCon.port_a);
  connect(pumCon.port_b, heaPum.port_a1);
  connect(heaPum.port_b1, conHex.port_a);
  connect(conHex.port_b, conBou.ports[2]);

  connect(heaPum.QCon_flow, negate.u);
  connect(negate.y, preHea.Q_flow);
  connect(preHea.port, heatPortCon);

  connect(TZoneSet, conPI.u_s);
  connect(TZone, conPI.u_m);
  connect(conPI.y, heaPum.y);
  connect(conPI.y, conHex.u);

  annotation (Documentation(info="<html>
<p>
Per-apartment heat pump that draws thermal energy from the ambient loop on the
evaporator side and injects heat into the apartment zone via a thermal
<code>HeatPort</code> on the condenser side. A small condenser-side closed
loop carries the heat to a HeaterCooler block, which exposes its delivered
power as a heat flow on <code>heatPortCon</code>.
</p>
<p>
The integrated PI controller modulates compressor speed against the zone
temperature setpoint. Closing the control loop inside the wrapper keeps the
generated system model's connect graph minimal.
</p>
</html>"));
end ApartmentHeatPump;
