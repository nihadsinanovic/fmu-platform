within FMUPlatform.Components;
model WeatherSource "Outdoor conditions driver wrapping Buildings ReaderTMY3"
  parameter String filNam=
      Modelica.Utilities.Files.loadResource(
        "modelica://Buildings/Resources/weatherdata/USA_CA_San.Francisco.Intl.AP.724940_TMY3.mos")
    "Path to the TMY3 weather file";

  Buildings.BoundaryConditions.WeatherData.ReaderTMY3 weaDat(
    final filNam=filNam,
    computeWetBulbTemperature=false)
    "TMY3 weather data reader";

  Buildings.BoundaryConditions.WeatherData.Bus weaBus
    "Aggregated weather signal bus";

  Modelica.Blocks.Interfaces.RealOutput TDryBul(
    final unit="K",
    displayUnit="degC")
    "Outdoor dry-bulb temperature";
  Modelica.Blocks.Interfaces.RealOutput HGloHor(final unit="W/m2")
    "Global horizontal solar irradiance";
  Modelica.Blocks.Interfaces.RealOutput vWin(final unit="m/s")
    "Wind speed";

equation
  connect(weaDat.weaBus, weaBus);
  connect(weaBus.TDryBul, TDryBul);
  connect(weaBus.HGloHor, HGloHor);
  connect(weaBus.winSpe, vWin);

  annotation (Documentation(info="<html>
<p>
Maps the platform's <code>weather_source</code> atomic FMU onto a Buildings
ReaderTMY3 instance. Outputs the three signals consumed by downstream
components: dry-bulb temperature, global horizontal irradiance and wind speed.
</p>
</html>"));
end WeatherSource;
