"""Shared test fixtures."""

import pytest


@pytest.fixture
def sample_topology() -> dict:
    """A minimal valid building topology for testing."""
    return {
        "project_id": "test_proj_001",
        "building": {
            "name": "Test Building",
            "location": {"lat": 45.19, "lon": 5.72, "climate_zone": "H1c"},
            "central_system": {
                "heatpump": {
                    "type": "central_heatpump",
                    "params": {
                        "nominal_power_kW": 120,
                        "COP_nominal": 3.8,
                        "source_type": "ground",
                    },
                }
            },
            "ambient_loop": {
                "main_pipe": {
                    "length_m": 40,
                    "diameter_mm": 80,
                    "insulation_thickness_mm": 30,
                }
            },
            "floors": [
                {
                    "floor_number": 0,
                    "riser_length_m": 3.0,
                    "apartments": [
                        {
                            "id": "apt_0_1",
                            "label": "T2 - Ground Floor Left",
                            "type_preset": "T2",
                            "floor_area_m2": 45,
                            "orientation": "south",
                            "heatpump": {"nominal_power_kW": 5, "COP_nominal": 4.2},
                            "thermal_zone": {
                                "U_wall": 0.25,
                                "U_window": 1.4,
                                "window_area_m2": 6,
                                "n_occupants": 2,
                                "ceiling_height_m": 2.5,
                            },
                        },
                        {
                            "id": "apt_0_2",
                            "label": "T3 - Ground Floor Right",
                            "type_preset": "T3",
                            "floor_area_m2": 65,
                            "orientation": "north",
                            "heatpump": {"nominal_power_kW": 8, "COP_nominal": 4.0},
                            "thermal_zone": {
                                "U_wall": 0.25,
                                "U_window": 1.4,
                                "window_area_m2": 8,
                                "n_occupants": 3,
                                "ceiling_height_m": 2.5,
                            },
                        },
                    ],
                },
                {
                    "floor_number": 1,
                    "riser_length_m": 3.0,
                    "apartments": [
                        {
                            "id": "apt_1_1",
                            "label": "T2 - First Floor Left",
                            "type_preset": "T2",
                            "floor_area_m2": 45,
                            "orientation": "south",
                            "heatpump": {"nominal_power_kW": 5, "COP_nominal": 4.2},
                            "thermal_zone": {
                                "U_wall": 0.25,
                                "U_window": 1.4,
                                "window_area_m2": 6,
                                "n_occupants": 2,
                                "ceiling_height_m": 2.5,
                            },
                        }
                    ],
                },
            ],
        },
        "simulation": {
            "start_time": 0,
            "end_time": 31536000,
            "step_size": 900,
            "solver": "CVode",
            "output_interval": 3600,
        },
    }
