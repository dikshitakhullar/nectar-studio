"""Spatial Digest data models.

The digest is what we hand to a language model so it can reason about a room
without doing mental geometry. It packages the IR's coordinate-soup as resolved
facts: which wall is north, which wall each opening sits on, which rooms
connect via doors.

Design doc §1.3: "LLMs are bad at mental geometry from coordinate lists. We
resolve the spatial relationships in code and hand the model conclusions, not
coordinates."
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from lighting_engine.models.geometry import Point, RoomType


class WallOrientation(StrEnum):
    """8-way compass orientation of a wall's outward normal.

    Computed from polygon geometry and `Project.north_orientation_deg`.
    Used by the LLM to talk about "the south wall" or "windows facing east".
    """
    N = "N"
    NE = "NE"
    E = "E"
    SE = "SE"
    S = "S"
    SW = "SW"
    W = "W"
    NW = "NW"


class WallSegment(BaseModel):
    """A single edge of a room polygon with its computed orientation."""
    index: int                       # index in the polygon (0..N-1)
    orientation: WallOrientation
    length_m: float = Field(gt=0)
    start: Point
    end: Point


class OpeningOnWall(BaseModel):
    """A door or window's position on a specific wall."""
    kind: str                        # "door" | "window" | "glazed_door"
    id: str                          # IR opening id (door.id / window.id)
    wall_index: int                  # which wall of the room
    along_wall: float = Field(ge=0.0, le=1.0)
    width_m: float = Field(gt=0)


class RoomDigest(BaseModel):
    """LLM-friendly per-room facts derived from the IR."""
    room_id: str
    name: str
    type: RoomType
    floor_level: int
    area_sqm: float
    bbox_w_m: float                  # bounding-box width
    bbox_h_m: float                  # bounding-box height
    aspect_ratio: float              # max(w,h) / min(w,h)
    ceiling_height_m: float
    walls: list[WallSegment] = []
    openings: list[OpeningOnWall] = []
    furniture_count: int = 0
    existing_fixture_count: int = 0
    is_outdoor: bool = False
    notes: list[str] = []            # auto-generated qualitative notes
    summary: str = ""                # human/LLM-readable text


class Adjacency(BaseModel):
    """Two rooms connected by a door — the design doc's adjacency graph edge."""
    room_a_id: str
    room_b_id: str
    via: str = "door"                # future: "open_plan" if no wall between


class ProjectDigest(BaseModel):
    """The complete spatial digest for one project."""
    project_id: str
    project_name: str
    north_orientation_deg: float
    rooms: list[RoomDigest] = []
    adjacencies: list[Adjacency] = []
