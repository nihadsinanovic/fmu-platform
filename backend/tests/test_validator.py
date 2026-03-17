"""Tests for the system validator."""

from engine.connection_resolver import Connection, ConnectionGraph, FMUInstance
from engine.manifest import FMUManifest, PortDefinition
from engine.validator import SystemValidator


def _make_test_manifests():
    return {
        "type_a": FMUManifest(
            fmu_type="type_a",
            outputs=[PortDefinition(name="out_T", type="Real")],
            inputs=[PortDefinition(name="in_T", type="Real")],
        ),
        "type_b": FMUManifest(
            fmu_type="type_b",
            outputs=[PortDefinition(name="out_T", type="Real")],
            inputs=[PortDefinition(name="in_T", type="Real")],
        ),
    }


class TestSystemValidator:
    def test_valid_system(self):
        manifests = _make_test_manifests()
        graph = ConnectionGraph(
            instances=[
                FMUInstance(name="a", fmu_type="type_a"),
                FMUInstance(name="b", fmu_type="type_b"),
            ],
            connections=[
                Connection("a", "out_T", "b", "in_T"),
            ],
        )
        result = SystemValidator(manifests).validate(graph)
        assert result.valid

    def test_unknown_fmu_type(self):
        manifests = _make_test_manifests()
        graph = ConnectionGraph(
            instances=[
                FMUInstance(name="x", fmu_type="nonexistent"),
            ],
            connections=[],
        )
        result = SystemValidator(manifests).validate(graph)
        assert not result.valid
        assert any("nonexistent" in e for e in result.errors)

    def test_orphan_instance_warning(self):
        manifests = _make_test_manifests()
        graph = ConnectionGraph(
            instances=[
                FMUInstance(name="a", fmu_type="type_a"),
                FMUInstance(name="b", fmu_type="type_b"),
                FMUInstance(name="orphan", fmu_type="type_a"),
            ],
            connections=[
                Connection("a", "out_T", "b", "in_T"),
            ],
        )
        result = SystemValidator(manifests).validate(graph)
        assert any("orphan" in w for w in result.warnings)

    def test_unknown_connection_reference(self):
        manifests = _make_test_manifests()
        graph = ConnectionGraph(
            instances=[
                FMUInstance(name="a", fmu_type="type_a"),
            ],
            connections=[
                Connection("a", "out_T", "nonexistent", "in_T"),
            ],
        )
        result = SystemValidator(manifests).validate(graph)
        assert not result.valid

    def test_type_mismatch(self):
        manifests = {
            "type_a": FMUManifest(
                fmu_type="type_a",
                outputs=[PortDefinition(name="out_T", type="Real")],
            ),
            "type_b": FMUManifest(
                fmu_type="type_b",
                inputs=[PortDefinition(name="in_T", type="Integer")],
            ),
        }
        graph = ConnectionGraph(
            instances=[
                FMUInstance(name="a", fmu_type="type_a"),
                FMUInstance(name="b", fmu_type="type_b"),
            ],
            connections=[
                Connection("a", "out_T", "b", "in_T"),
            ],
        )
        result = SystemValidator(manifests).validate(graph)
        assert not result.valid
        assert any("mismatch" in e.lower() for e in result.errors)
