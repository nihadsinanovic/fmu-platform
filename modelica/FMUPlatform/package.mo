within ;
package FMUPlatform "Modelica wrappers and generated systems for the FMU composition platform"
  extends Modelica.Icons.Package;

  annotation (
    uses(
      Modelica(version="4.0.0"),
      Buildings(version="11.0.0")),
    version="0.1.0",
    Documentation(info="<html>
<p>
This package provides per-component Modelica wrappers around the LBNL
<code>Buildings</code> library, mapping the FMU composition platform's atomic
component vocabulary (central heat pump, ambient loop segment, loop tee,
apartment heat pump, apartment thermal zone, weather source) onto Buildings
library models.
</p>
<p>
The wrappers expose ports and parameters that match the platform's port-naming
convention so a Python generator can render any building topology JSON into a
self-contained Modelica system model. See <code>FMUPlatform.Examples</code> for
a worked example.
</p>
</html>"));
end FMUPlatform;
