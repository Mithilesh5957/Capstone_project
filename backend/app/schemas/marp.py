from pydantic import BaseModel, Field


class ChaosIn(BaseModel):
    failure: str = "db_drop"


class ChaosTune(BaseModel):
    vram_latency_s: float = 0.0
    frame_drop_rate: float = 0.0
    model_stall: bool = False


class ChaosConfig(BaseModel):
    """In-situ chaos payload — applied live, no restart."""
    simulated_latency_sec: float = Field(default=0.0, ge=0.0, le=30.0)
    frame_drop_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    simulate_vram_exhaustion: bool = False
    artificial_probe_failure: bool = False
    model_stall: bool = False


class LoginIn(BaseModel):
    username: str = ""
    email: str = ""
    password: str = ""
    role: str = ""
