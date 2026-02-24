from dataclasses import dataclass


@dataclass(frozen=True)
class ZoneDefinition:
    zone_id: str
    name: str
    territory: str  # CONED or OR
    nws_zone: str
    latitude: float
    longitude: float
    nws_grid_office: str  # NWS forecast office (e.g. OKX, PHI)
    nws_grid_x: int
    nws_grid_y: int
    county: str
    peak_load_share: float  # fraction of territory peak load


# Con Edison zones (NYC boroughs + Westchester)
CONED_ZONES = [
    ZoneDefinition(
        zone_id="CONED-MAN",
        name="Manhattan",
        territory="CONED",
        nws_zone="NYZ072",
        latitude=40.7831,
        longitude=-73.9712,
        nws_grid_office="OKX",
        nws_grid_x=33,
        nws_grid_y=37,
        county="New York",
        peak_load_share=0.30,
    ),
    ZoneDefinition(
        zone_id="CONED-BRX",
        name="Bronx",
        territory="CONED",
        nws_zone="NYZ073",
        latitude=40.8448,
        longitude=-73.8648,
        nws_grid_office="OKX",
        nws_grid_x=35,
        nws_grid_y=39,
        county="Bronx",
        peak_load_share=0.10,
    ),
    ZoneDefinition(
        zone_id="CONED-BKN",
        name="Brooklyn",
        territory="CONED",
        nws_zone="NYZ075",
        latitude=40.6782,
        longitude=-73.9442,
        nws_grid_office="OKX",
        nws_grid_x=34,
        nws_grid_y=35,
        county="Kings",
        peak_load_share=0.18,
    ),
    ZoneDefinition(
        zone_id="CONED-QNS",
        name="Queens",
        territory="CONED",
        nws_zone="NYZ076",
        latitude=40.7282,
        longitude=-73.7949,
        nws_grid_office="OKX",
        nws_grid_x=36,
        nws_grid_y=36,
        county="Queens",
        peak_load_share=0.16,
    ),
    ZoneDefinition(
        zone_id="CONED-SI",
        name="Staten Island",
        territory="CONED",
        nws_zone="NYZ074",
        latitude=40.5795,
        longitude=-74.1502,
        nws_grid_office="OKX",
        nws_grid_x=30,
        nws_grid_y=34,
        county="Richmond",
        peak_load_share=0.04,
    ),
    ZoneDefinition(
        zone_id="CONED-WST",
        name="Westchester",
        territory="CONED",
        nws_zone="NYZ067",
        latitude=41.1220,
        longitude=-73.7949,
        nws_grid_office="OKX",
        nws_grid_x=35,
        nws_grid_y=45,
        county="Westchester",
        peak_load_share=0.22,
    ),
]

# O&R zones (Orange, Rockland, Sullivan counties + NJ portions)
OR_ZONES = [
    ZoneDefinition(
        zone_id="OR-ORA",
        name="Orange County",
        territory="OR",
        nws_zone="NYZ068",
        latitude=41.4018,
        longitude=-74.3118,
        nws_grid_office="OKX",
        nws_grid_x=25,
        nws_grid_y=50,
        county="Orange",
        peak_load_share=0.35,
    ),
    ZoneDefinition(
        zone_id="OR-ROC",
        name="Rockland County",
        territory="OR",
        nws_zone="NYZ069",
        latitude=41.1489,
        longitude=-73.9830,
        nws_grid_office="OKX",
        nws_grid_x=31,
        nws_grid_y=44,
        county="Rockland",
        peak_load_share=0.30,
    ),
    ZoneDefinition(
        zone_id="OR-SUL",
        name="Sullivan County",
        territory="OR",
        nws_zone="NYZ070",
        latitude=41.7170,
        longitude=-74.7713,
        nws_grid_office="OKX",
        nws_grid_x=18,
        nws_grid_y=56,
        county="Sullivan",
        peak_load_share=0.10,
    ),
    ZoneDefinition(
        zone_id="OR-BER",
        name="Northern Bergen/Passaic",
        territory="OR",
        nws_zone="NJZ006",
        latitude=41.0534,
        longitude=-74.1310,
        nws_grid_office="OKX",
        nws_grid_x=30,
        nws_grid_y=42,
        county="Bergen",
        peak_load_share=0.15,
    ),
    ZoneDefinition(
        zone_id="OR-SSX",
        name="Sussex County",
        territory="OR",
        nws_zone="NJZ008",
        latitude=41.1394,
        longitude=-74.6904,
        nws_grid_office="OKX",
        nws_grid_x=22,
        nws_grid_y=46,
        county="Sussex",
        peak_load_share=0.10,
    ),
]

ALL_ZONES = CONED_ZONES + OR_ZONES

ZONE_MAP: dict[str, ZoneDefinition] = {z.zone_id: z for z in ALL_ZONES}


def get_zones_for_territory(territory: str) -> list[ZoneDefinition]:
    territory = territory.upper()
    if territory == "CONED":
        return CONED_ZONES
    elif territory == "OR":
        return OR_ZONES
    return ALL_ZONES


def get_zone(zone_id: str) -> ZoneDefinition | None:
    return ZONE_MAP.get(zone_id)
