within FMUPlatform.Examples;
model SmallBuilding2Floors
  "Auto-generated system model for: Petit Immeuble - Grenoble"
  extends Modelica.Icons.Example;
  // --- Central plant ---
  FMUPlatform.Components.WeatherSource weather(
    filNam=Modelica.Utilities.Files.loadResource("modelica://Buildings/Resources/weatherdata/USA_CA_San.Francisco.Intl.AP.724940_TMY3.mos"));
  FMUPlatform.Components.CentralHeatPump centralHp(
    Q_flow_nominal_W=30000,
    COP_nominal=3.8,
    source_type="ground");
  Modelica.Blocks.Sources.Constant TSet_loop(k=308.15)
    "Loop supply temperature setpoint (35 degC)";
  // --- Main ambient loop pipes ---
  FMUPlatform.Components.AmbientLoopSegment mainSupply(
    length_m=20,
    diameter_mm=60,
    insulation_thickness_mm=25);
  FMUPlatform.Components.AmbientLoopSegment mainReturn(
    length_m=20,
    diameter_mm=60,
    insulation_thickness_mm=25);
  // --- Floor distribution tee ---
  FMUPlatform.Components.LoopTee floorTee(n_branches=2);
  // --- Floor 0 ---
  FMUPlatform.Components.AmbientLoopSegment riserSupply_0(
    length_m=3,
    diameter_mm=50,
    insulation_thickness_mm=20);
  FMUPlatform.Components.AmbientLoopSegment riserReturn_0(
    length_m=3,
    diameter_mm=50,
    insulation_thickness_mm=20);
  FMUPlatform.Components.LoopTee aptTee_0(n_branches=2);
  FMUPlatform.Components.ApartmentHeatPump apt_0_1_hp(
    Q_flow_nominal_W=5000,
    COP_nominal=4.2);
  FMUPlatform.Components.ApartmentThermalZone apt_0_1_zone(
    floor_area_m2=45,
    ceiling_height_m=2.5,
    U_wall=0.25,
    U_window=1.4,
    window_area_m2=6,
    n_occupants=2,
    orientation="south");
  Modelica.Blocks.Sources.Constant apt_0_1_TSet(k=293.15)
    "Zone setpoint for apt_0_1 (20 degC)";
  FMUPlatform.Components.ApartmentHeatPump apt_0_2_hp(
    Q_flow_nominal_W=8000,
    COP_nominal=4);
  FMUPlatform.Components.ApartmentThermalZone apt_0_2_zone(
    floor_area_m2=65,
    ceiling_height_m=2.5,
    U_wall=0.25,
    U_window=1.4,
    window_area_m2=8,
    n_occupants=3,
    orientation="north");
  Modelica.Blocks.Sources.Constant apt_0_2_TSet(k=293.15)
    "Zone setpoint for apt_0_2 (20 degC)";
  // --- Floor 1 ---
  FMUPlatform.Components.AmbientLoopSegment riserSupply_1(
    length_m=3,
    diameter_mm=50,
    insulation_thickness_mm=20);
  FMUPlatform.Components.AmbientLoopSegment riserReturn_1(
    length_m=3,
    diameter_mm=50,
    insulation_thickness_mm=20);
  FMUPlatform.Components.LoopTee aptTee_1(n_branches=2);
  FMUPlatform.Components.ApartmentHeatPump apt_1_1_hp(
    Q_flow_nominal_W=5000,
    COP_nominal=4.2);
  FMUPlatform.Components.ApartmentThermalZone apt_1_1_zone(
    floor_area_m2=45,
    ceiling_height_m=2.5,
    U_wall=0.25,
    U_window=1.4,
    window_area_m2=6,
    n_occupants=2,
    orientation="south");
  Modelica.Blocks.Sources.Constant apt_1_1_TSet(k=293.15)
    "Zone setpoint for apt_1_1 (20 degC)";
  FMUPlatform.Components.ApartmentHeatPump apt_1_2_hp(
    Q_flow_nominal_W=8000,
    COP_nominal=4);
  FMUPlatform.Components.ApartmentThermalZone apt_1_2_zone(
    floor_area_m2=65,
    ceiling_height_m=2.5,
    U_wall=0.25,
    U_window=1.4,
    window_area_m2=8,
    n_occupants=3,
    orientation="north");
  Modelica.Blocks.Sources.Constant apt_1_2_TSet(k=293.15)
    "Zone setpoint for apt_1_2 (20 degC)";
equation
  // --- Central plant supply chain ---
  connect(TSet_loop.y, centralHp.TSet);
  connect(centralHp.port_b, mainSupply.port_a);
  connect(mainSupply.port_b, floorTee.port_supplyIn);
  connect(floorTee.port_returnOut, mainReturn.port_a);
  connect(mainReturn.port_b, centralHp.port_a);
  // --- Floor 0 branch ---
  connect(floorTee.port_supplyOut[1], riserSupply_0.port_a);
  connect(riserSupply_0.port_b, aptTee_0.port_supplyIn);
  connect(aptTee_0.port_returnOut, riserReturn_0.port_a);
  connect(riserReturn_0.port_b, floorTee.port_returnIn[1]);
  // apt_0_1
  connect(aptTee_0.port_supplyOut[1], apt_0_1_hp.port_a);
  connect(apt_0_1_hp.port_b, aptTee_0.port_returnIn[1]);
  connect(apt_0_1_hp.heatPortCon, apt_0_1_zone.heatPortInt);
  connect(apt_0_1_zone.TZone, apt_0_1_hp.TZone);
  connect(apt_0_1_TSet.y, apt_0_1_hp.TZoneSet);
  connect(weather.TDryBul, apt_0_1_zone.TDryBul);
  connect(weather.HGloHor, apt_0_1_zone.HGloHor);
  // apt_0_2
  connect(aptTee_0.port_supplyOut[2], apt_0_2_hp.port_a);
  connect(apt_0_2_hp.port_b, aptTee_0.port_returnIn[2]);
  connect(apt_0_2_hp.heatPortCon, apt_0_2_zone.heatPortInt);
  connect(apt_0_2_zone.TZone, apt_0_2_hp.TZone);
  connect(apt_0_2_TSet.y, apt_0_2_hp.TZoneSet);
  connect(weather.TDryBul, apt_0_2_zone.TDryBul);
  connect(weather.HGloHor, apt_0_2_zone.HGloHor);
  // --- Floor 1 branch ---
  connect(floorTee.port_supplyOut[2], riserSupply_1.port_a);
  connect(riserSupply_1.port_b, aptTee_1.port_supplyIn);
  connect(aptTee_1.port_returnOut, riserReturn_1.port_a);
  connect(riserReturn_1.port_b, floorTee.port_returnIn[2]);
  // apt_1_1
  connect(aptTee_1.port_supplyOut[1], apt_1_1_hp.port_a);
  connect(apt_1_1_hp.port_b, aptTee_1.port_returnIn[1]);
  connect(apt_1_1_hp.heatPortCon, apt_1_1_zone.heatPortInt);
  connect(apt_1_1_zone.TZone, apt_1_1_hp.TZone);
  connect(apt_1_1_TSet.y, apt_1_1_hp.TZoneSet);
  connect(weather.TDryBul, apt_1_1_zone.TDryBul);
  connect(weather.HGloHor, apt_1_1_zone.HGloHor);
  // apt_1_2
  connect(aptTee_1.port_supplyOut[2], apt_1_2_hp.port_a);
  connect(apt_1_2_hp.port_b, aptTee_1.port_returnIn[2]);
  connect(apt_1_2_hp.heatPortCon, apt_1_2_zone.heatPortInt);
  connect(apt_1_2_zone.TZone, apt_1_2_hp.TZone);
  connect(apt_1_2_TSet.y, apt_1_2_hp.TZoneSet);
  connect(weather.TDryBul, apt_1_2_zone.TDryBul);
  connect(weather.HGloHor, apt_1_2_zone.HGloHor);
  annotation (
    experiment(
      StartTime=0,
      StopTime=31536000,
      Interval=3600,
      Tolerance=1e-6),
    __OpenModelica_simulationFlags(s="cvode"));
end SmallBuilding2Floors;
