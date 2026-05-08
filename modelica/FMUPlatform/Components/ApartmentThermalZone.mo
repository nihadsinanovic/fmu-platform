within FMUPlatform.Components;
model ApartmentThermalZone "Single-zone reduced-order RC thermal model of an apartment"
  parameter Modelica.Units.SI.Area floor_area_m2=45 "Floor area";
  parameter Modelica.Units.SI.Length ceiling_height_m=2.5 "Ceiling height";
  parameter Real U_wall(unit="W/(m2.K)")=0.25 "Wall U-value";
  parameter Real U_window(unit="W/(m2.K)")=1.4 "Window U-value";
  parameter Modelica.Units.SI.Area window_area_m2=6 "Window area";
  parameter Integer n_occupants=2 "Number of occupants";
  parameter String orientation="south" "Façade orientation (descriptive)";

  parameter Modelica.Units.SI.Volume V=floor_area_m2*ceiling_height_m
    "Zone volume";
  parameter Modelica.Units.SI.Area A_wall=
      4*ceiling_height_m*sqrt(floor_area_m2)
    "Approximate envelope wall area (square footprint assumption)";
  parameter Modelica.Units.SI.HeatCapacity C_zone=V*1.2*1005*5
    "Lumped zone thermal capacity (air mass × cp × furniture multiplier)";
  parameter Modelica.Units.SI.ThermalConductance G_env=
      U_wall*A_wall + U_window*window_area_m2
    "Envelope thermal conductance (wall + window)";
  parameter Modelica.Units.SI.Power Q_int_per_occupant=80
    "Sensible internal-gain heat per occupant (W)";

  Modelica.Thermal.HeatTransfer.Interfaces.HeatPort_a heatPortInt
    "Internal heat input port (from apartment heat pump)";
  Modelica.Blocks.Interfaces.RealInput TDryBul(final unit="K", displayUnit="degC")
    "Outdoor dry-bulb temperature";
  Modelica.Blocks.Interfaces.RealInput HGloHor(final unit="W/m2")
    "Global horizontal solar irradiance";
  Modelica.Blocks.Interfaces.RealOutput TZone(final unit="K", displayUnit="degC")
    "Zone air temperature";

  Modelica.Thermal.HeatTransfer.Components.HeatCapacitor zoneCap(
    C=C_zone,
    T(start=293.15, fixed=true))
    "Lumped zone thermal mass";
  Modelica.Thermal.HeatTransfer.Components.ThermalConductor envCon(G=G_env)
    "Envelope conductance to outdoor";
  Modelica.Thermal.HeatTransfer.Sources.PrescribedTemperature TOutPre
    "Prescribed outdoor boundary";
  Modelica.Thermal.HeatTransfer.Sensors.TemperatureSensor TZoneSen
    "Zone temperature sensor";
  Modelica.Thermal.HeatTransfer.Sources.PrescribedHeatFlow Q_int
    "Internal occupant gains";
  Modelica.Thermal.HeatTransfer.Sources.PrescribedHeatFlow Q_sol
    "Solar gain through windows";
  Modelica.Blocks.Sources.Constant Q_int_const(k=n_occupants*Q_int_per_occupant)
    "Constant internal-gain schedule (placeholder)";
  Modelica.Blocks.Math.Gain solApe(k=window_area_m2*0.5)
    "Solar aperture: window area × effective transmittance (0.5 placeholder)";

equation
  connect(heatPortInt, zoneCap.port);
  connect(zoneCap.port, envCon.port_a);
  connect(envCon.port_b, TOutPre.port);
  connect(TDryBul, TOutPre.T);
  connect(zoneCap.port, TZoneSen.port);
  connect(TZoneSen.T, TZone);

  connect(Q_int_const.y, Q_int.Q_flow);
  connect(Q_int.port, zoneCap.port);

  connect(HGloHor, solApe.u);
  connect(solApe.y, Q_sol.Q_flow);
  connect(Q_sol.port, zoneCap.port);

  annotation (Documentation(info="<html>
<p>
Lumped single-capacity RC model of an apartment thermal zone. Connects:
</p>
<ul>
  <li><code>heatPortInt</code> for heat input from the apartment heat pump,</li>
  <li>an envelope conductance to outdoor (driven by <code>TDryBul</code>),</li>
  <li>a constant internal-gains placeholder scaled by occupant count,</li>
  <li>a simple solar gain proportional to window area and global horizontal irradiance.</li>
</ul>
<p>
This is intentionally simpler than <code>Buildings.ThermalZones.ReducedOrder.RC</code>:
v1 prioritises a small, debuggable model. Drop in the ISO 13790 multi-element
RC zone later by swapping this class for a wrapper of <code>OneElement</code>.
</p>
</html>"));
end ApartmentThermalZone;
