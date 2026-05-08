within FMUPlatform.Components;
model LoopTee "N-branch tee for connecting apartments to a riser"
  replaceable package Medium = Buildings.Media.Water "Loop medium";

  parameter Integer n_branches(min=1)=2 "Number of branch outlets/inlets";
  parameter Modelica.Units.SI.MassFlowRate m_flow_nominal=0.5
    "Nominal main-line mass flow rate";
  parameter Modelica.Units.SI.MassFlowRate m_branch_nominal=
      m_flow_nominal/n_branches
    "Nominal per-branch mass flow rate";
  parameter Modelica.Units.SI.PressureDifference dp_nominal=100
    "Nominal pressure drop per junction";

  Modelica.Fluid.Interfaces.FluidPort_a port_supplyIn(redeclare package Medium = Medium)
    "Supply manifold inlet (from upstream riser)";
  Modelica.Fluid.Interfaces.FluidPort_b port_supplyOut[n_branches](
    redeclare each package Medium = Medium)
    "Per-branch supply outlets (to apartment heat pumps)";
  Modelica.Fluid.Interfaces.FluidPort_b port_returnOut(redeclare package Medium = Medium)
    "Return manifold outlet (back to upstream riser)";
  Modelica.Fluid.Interfaces.FluidPort_a port_returnIn[n_branches](
    redeclare each package Medium = Medium)
    "Per-branch return inlets (from apartment heat pumps)";

  Buildings.Fluid.FixedResistances.Junction supJun[n_branches](
    redeclare each package Medium = Medium,
    each m_flow_nominal={m_flow_nominal,m_flow_nominal,m_branch_nominal},
    each dp_nominal={dp_nominal,dp_nominal,dp_nominal},
    each energyDynamics=Modelica.Fluid.Types.Dynamics.SteadyState)
    "Supply manifold junctions (one per branch, cascaded)";
  Buildings.Fluid.FixedResistances.Junction retJun[n_branches](
    redeclare each package Medium = Medium,
    each m_flow_nominal={m_flow_nominal,m_flow_nominal,m_branch_nominal},
    each dp_nominal={dp_nominal,dp_nominal,dp_nominal},
    each energyDynamics=Modelica.Fluid.Types.Dynamics.SteadyState)
    "Return manifold junctions (one per branch, cascaded)";

  Modelica.Fluid.Sources.MassFlowSource_T capSup(
    redeclare package Medium = Medium,
    m_flow=0,
    T=293.15,
    nPorts=1)
    "Closed plug capping the supply manifold's far end";
  Modelica.Fluid.Sources.MassFlowSource_T capRet(
    redeclare package Medium = Medium,
    m_flow=0,
    T=293.15,
    nPorts=1)
    "Closed plug capping the return manifold's far end";

equation
  connect(port_supplyIn, supJun[1].port_1);
  for i in 1:n_branches - 1 loop
    connect(supJun[i].port_2, supJun[i+1].port_1);
  end for;
  for i in 1:n_branches loop
    connect(supJun[i].port_3, port_supplyOut[i]);
  end for;
  connect(supJun[n_branches].port_2, capSup.ports[1]);

  connect(port_returnOut, retJun[1].port_1);
  for i in 1:n_branches - 1 loop
    connect(retJun[i].port_2, retJun[i+1].port_1);
  end for;
  for i in 1:n_branches loop
    connect(retJun[i].port_3, port_returnIn[i]);
  end for;
  connect(retJun[n_branches].port_2, capRet.ports[1]);

  annotation (Documentation(info="<html>
<p>
Parametric N-branch tee, modelled as cascaded Junctions on the supply and
return manifolds. The far end of each cascade is internally capped with a
zero-flow boundary, so the wrapper presents only the platform-level ports
(<code>port_supplyIn</code>, <code>port_supplyOut[]</code>,
<code>port_returnOut</code>, <code>port_returnIn[]</code>).
</p>
</html>"));
end LoopTee;
