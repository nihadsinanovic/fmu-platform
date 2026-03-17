"""Apply parameter values to FMU instances, validating against manifest constraints."""

from __future__ import annotations

from typing import Any

from engine.connection_resolver import FMUInstance
from engine.manifest import FMUManifest


class ParameterValidationError(Exception):
    def __init__(self, instance_name: str, param_name: str, message: str):
        self.instance_name = instance_name
        self.param_name = param_name
        super().__init__(f"{instance_name}.{param_name}: {message}")


class Parameterizer:
    """Validate and apply parameter values to FMU instances using manifest constraints."""

    def __init__(self, manifests: dict[str, FMUManifest]):
        self.manifests = manifests

    def validate_parameters(self, instance: FMUInstance) -> list[str]:
        """Validate instance parameters against its manifest. Returns list of warnings."""
        manifest = self.manifests.get(instance.fmu_type)
        if not manifest:
            raise ParameterValidationError(
                instance.name, "", f"No manifest found for FMU type '{instance.fmu_type}'"
            )

        warnings = []
        for param_name, value in instance.parameters.items():
            param_def = manifest.get_parameter(param_name)
            if not param_def:
                warnings.append(
                    f"{instance.name}: parameter '{param_name}' not declared in manifest"
                )
                continue

            if isinstance(value, (int, float)) and param_def.min is not None:
                if value < param_def.min:
                    raise ParameterValidationError(
                        instance.name,
                        param_name,
                        f"value {value} below minimum {param_def.min}",
                    )
            if isinstance(value, (int, float)) and param_def.max is not None:
                if value > param_def.max:
                    raise ParameterValidationError(
                        instance.name,
                        param_name,
                        f"value {value} above maximum {param_def.max}",
                    )

        return warnings

    def apply_defaults(self, instance: FMUInstance) -> None:
        """Fill in default values for parameters not explicitly set."""
        manifest = self.manifests.get(instance.fmu_type)
        if not manifest:
            return

        for param_def in manifest.parameters:
            if param_def.name not in instance.parameters and param_def.default is not None:
                instance.parameters[param_def.name] = param_def.default

    def get_ssv_parameters(self, instance: FMUInstance) -> dict[str, Any]:
        """Return the final parameter dict for SSV generation."""
        self.apply_defaults(instance)
        self.validate_parameters(instance)
        return dict(instance.parameters)
