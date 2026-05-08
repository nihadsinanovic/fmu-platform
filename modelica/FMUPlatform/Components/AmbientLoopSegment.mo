within FMUPlatform.Components;
model AmbientLoopSegment "Ambient-loop pipe section with transport delay and ground heat loss"
  replaceable package Medium = Buildings.Media.Water "Loop medium";

  parameter Modelica.Units.SI.Length length_m=10 "Pipe length";
  parameter Modelica.Units.SI.Length diameter_mm=60
    "Pipe inner diameter (millimetres, converted internally to metres)";
  parameter Modelica.Units.SI.Length insulation_thickness_mm=25
    "Insulation thickness (millimetres, converted internally to metres)";
  parameter Modelica.Units.SI.Temperature T_ground=283.15
    "Surrounding ground temperature";
  parameter Modelica.Units.SI.MassFlowRate m_flow_nominal=0.5
    "Nominal mass flow rate";

  parameter Modelica.Units.SI.Length dh=diameter_mm/1000
    "Pipe inner hydraulic diameter (m)";
  parameter Modelica.Units.SI.Length thickness=insulation_thickness_mm/1000
    "Insulation thickness (m)";

  Modelica.Fluid.Interfaces.FluidPort_a port_a(redeclare package Medium = Medium);
  Modelica.Fluid.Interfaces.FluidPort_b port_b(redeclare package Medium = Medium);

  Buildings.Fluid.FixedResistances.PlugFlowPipe pipe(
    redeclare package Medium = Medium,
    length=length_m,
    dh=dh,
    m_flow_nominal=m_flow_nominal,
    dIns=thickness,
    kIns=0.028,
    cPip=2300,
    rhoPip=930,
    thickness=0.0035)
    "Plug-flow pipe with insulation and ground heat loss";

  Modelica.Thermal.HeatTransfer.Sources.FixedTemperature TGro(T=T_ground)
    "Surrounding ground temperature boundary";

equation
  connect(port_a, pipe.port_a);
  connect(pipe.port_b, port_b);
  connect(TGro.port, pipe.heatPort);

  annotation (Documentation(info="<html>
<p>
Wraps <code>Buildings.Fluid.FixedResistances.PlugFlowPipe</code>. Converts the
platform's millimetre-valued diameter and insulation thickness parameters into
the SI metres expected by Buildings, and ties the pipe's heat port to a
constant ground temperature boundary.
</p>
</html>"));
end AmbientLoopSegment;
