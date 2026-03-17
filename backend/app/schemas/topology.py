from pydantic import BaseModel, Field


class Location(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    climate_zone: str = ""


class HeatPumpParams(BaseModel):
    nominal_power_kW: float = Field(..., gt=0)
    COP_nominal: float = Field(..., gt=0)
    source_type: str = "ground"


class CentralSystem(BaseModel):
    heatpump: "CentralHeatPump"


class CentralHeatPump(BaseModel):
    type: str = "central_heatpump"
    params: HeatPumpParams


class MainPipe(BaseModel):
    length_m: float = Field(..., gt=0)
    diameter_mm: float = Field(..., gt=0)
    insulation_thickness_mm: float = Field(0, ge=0)


class AmbientLoop(BaseModel):
    main_pipe: MainPipe


class ThermalZoneConfig(BaseModel):
    U_wall: float = Field(..., gt=0)
    U_window: float = Field(..., gt=0)
    window_area_m2: float = Field(..., gt=0)
    n_occupants: int = Field(..., ge=0)
    ceiling_height_m: float = Field(2.5, gt=0)


class ApartmentHeatPump(BaseModel):
    nominal_power_kW: float = Field(..., gt=0)
    COP_nominal: float = Field(..., gt=0)


class Apartment(BaseModel):
    id: str
    label: str = ""
    type_preset: str = ""
    floor_area_m2: float = Field(..., gt=0)
    orientation: str = "south"
    heatpump: ApartmentHeatPump
    thermal_zone: ThermalZoneConfig


class Floor(BaseModel):
    floor_number: int = Field(..., ge=0)
    riser_length_m: float = Field(3.0, gt=0)
    apartments: list[Apartment] = Field(..., min_length=1)


class Building(BaseModel):
    name: str
    location: Location
    central_system: CentralSystem
    ambient_loop: AmbientLoop
    floors: list[Floor] = Field(..., min_length=1)


class SimulationConfig(BaseModel):
    start_time: float = 0
    end_time: float = Field(31536000, gt=0)
    step_size: float = Field(900, gt=0)
    solver: str = "CVode"
    output_interval: float = Field(3600, gt=0)


class BuildingTopology(BaseModel):
    project_id: str = ""
    building: Building
    simulation: SimulationConfig = SimulationConfig()
